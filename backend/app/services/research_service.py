from __future__ import annotations

import logging
from datetime import UTC, datetime, timedelta
from uuid import UUID, uuid4
from postgrest.exceptions import APIError

from app.auth.identity import RequestIdentity
from app.core.config import settings
from app.providers.research import ResearchProvider
from app.providers.exceptions import (
    AIProviderConfigurationError, AIProviderRateLimitError, AIProviderResponseError,
    AIProviderTimeoutError, AIProviderUnavailableError,
)
from app.repositories.research_repository import ResearchRepository
from app.schemas.documents import ExtractedDocument
from app.schemas.research import ResearchJobResponse, ResearchRequest, ResearchResult


class ResearchNotFound(RuntimeError): pass
class ResearchDepthNotAllowed(RuntimeError): pass

_DEPTH_ORDER = {"quick": 0, "standard": 1, "deep": 2}
logger = logging.getLogger("uvicorn.error").getChild("research")


def _event(event, row, previous=None):
    created = row.get("created_at")
    if isinstance(created, str):
        created = datetime.fromisoformat(created)
    logger.info("%s %s", event, {
        "research_id": str(row["id"]), "provider": row.get("provider"),
        "interaction_id": row.get("provider_job_id"), "previous_status": previous,
        "status": row["status"], "category": row.get("failure_category"),
        "elapsed_seconds": round((datetime.now(UTC) - created).total_seconds()) if created else None,
    })


class ResearchService:
    def __init__(self, repository: ResearchRepository, provider: ResearchProvider) -> None:
        self.repository, self.provider = repository, provider

    async def start(self, request: ResearchRequest, identity: RequestIdentity,
                    document: ExtractedDocument | None = None) -> ResearchJobResponse:
        if identity.user_id is None:
            raise ResearchNotFound("Authentication required.")
        if _DEPTH_ORDER[request.depth] > _DEPTH_ORDER[settings.research_max_depth]:
            raise ResearchDepthNotAllowed("Tražena dubina istraživanja nije omogućena.")
        research_id = request.request_id or uuid4()
        if request.request_id:
            existing = await self.repository.get(research_id, identity.user_id)
            if existing:
                return _response(existing)
        try:
            row = await self.repository.create(
                research_id=research_id, user_id=identity.user_id, provider="gemini",
                model=settings.gemini_research_model or "unconfigured", depth=request.depth,
                language=request.language, provider_job_id="pending", limit=settings.research_daily_limit,
            )
        except APIError as exc:
            if exc.code != "23505" or not request.request_id:
                raise
            existing = await self.repository.get(research_id, identity.user_id)
            if existing:
                return _response(existing)
            raise ResearchNotFound("Research not found.") from exc
        quota = row.get("_quota")
        _event("research_job_created", row)
        if request.conversation_id and not await self.repository.link(
            research_id, identity.user_id, request.conversation_id, request.query,
        ):
            await self.repository.update(research_id, status="failed", failure_category="invalid_request")
            raise ResearchNotFound("Razgovor nije pronađen.")
        try:
            started = await self.provider.start_research(request.query, request.language, request.depth, document)
        except Exception as exc:
            failed = await self.repository.update(research_id, status="failed", failure_category=_failure_category(exc))
            if failed:
                _event("research_job_failed", failed, "queued")
            raise
        row = await self.repository.update(research_id, status=started.status,
                                           provider_job_id=started.provider_job_id)
        row["_quota"] = quota
        _event("research_provider_submitted", row, "queued")
        return _response(row)

    async def get(self, research_id: UUID, identity: RequestIdentity) -> ResearchJobResponse:
        if identity.user_id is None:
            raise ResearchNotFound("Research not found.")
        row = await self.repository.get(research_id, identity.user_id)
        if row is None:
            raise ResearchNotFound("Research not found.")
        if row["status"] in {"completed", "failed"}:
            return _response(row)
        return await self.reconcile(row) or _response(
            await self.repository.get(research_id, identity.user_id) or row,
        )

    async def reconcile(self, row):
        research_id = UUID(str(row["id"]))
        created = datetime.fromisoformat(str(row["created_at"]))
        age = datetime.now(UTC) - created
        pending = row["provider_job_id"] == "pending"
        version = row["updated_at"]
        if age > timedelta(hours=1) or (pending and age > timedelta(minutes=5)):
            updated = await self.repository.update(
                research_id, status="failed", failure_category="provider_timeout", expected_updated_at=version,
            )
            if updated:
                _event("research_job_timed_out", updated, row["status"])
            return _response(updated) if updated else None
        if pending:
            await self.repository.update(research_id, status=row["status"], expected_updated_at=version)
            return _response(row)
        try:
            current = await self.provider.get_research(row["provider_job_id"], research_id)
        except (AIProviderTimeoutError, AIProviderUnavailableError, AIProviderRateLimitError):
            await self.repository.update(research_id, status=row["status"], expected_updated_at=version)
            raise
        except (AIProviderResponseError, AIProviderConfigurationError) as exc:
            updated = await self.repository.update(
                research_id, status="failed", failure_category=_failure_category(exc), expected_updated_at=version,
            )
            if updated:
                _event("research_job_failed", updated, row["status"])
            return _response(updated) if updated else None
        previous = row["status"]
        updated = await self.repository.update(research_id, status=current.status,
                                           result=current.result, failure_category=current.failure_category,
                                           expected_updated_at=version)
        if not updated:
            return None
        if previous != current.status:
            _event("research_status_changed", updated, previous)
            if current.status in {"completed", "failed"}:
                _event("research_job_recovered", updated, previous)
                _event(f"research_job_{current.status}", updated, previous)
            if current.result and updated.get("conversation_id"):
                _event("research_result_persisted", updated, previous)
        return _response(updated)


def _response(row) -> ResearchJobResponse:
    result = row.get("result")
    return ResearchJobResponse(
        research_id=row["id"], status=row["status"], created_at=row["created_at"],
        updated_at=row["updated_at"], result=ResearchResult.model_validate(result) if result else None,
        failure_category=row.get("failure_category"),
        quota=row.get("_quota"),
        query=row.get("query"),
    )


def _failure_category(exc: Exception) -> str:
    if isinstance(exc, AIProviderRateLimitError): return "provider_rate_limited"
    if isinstance(exc, AIProviderUnavailableError): return "provider_unavailable"
    if isinstance(exc, AIProviderTimeoutError): return "provider_timeout"
    if isinstance(exc, (AIProviderResponseError, AIProviderConfigurationError)): return "invalid_request"
    return "research_failed"
