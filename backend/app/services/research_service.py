from __future__ import annotations

from uuid import UUID, uuid4

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


class ResearchService:
    def __init__(self, repository: ResearchRepository, provider: ResearchProvider) -> None:
        self.repository, self.provider = repository, provider

    async def start(self, request: ResearchRequest, identity: RequestIdentity,
                    document: ExtractedDocument | None = None) -> ResearchJobResponse:
        if identity.user_id is None:
            raise ResearchNotFound("Authentication required.")
        if _DEPTH_ORDER[request.depth] > _DEPTH_ORDER[settings.research_max_depth]:
            raise ResearchDepthNotAllowed("Tražena dubina istraživanja nije omogućena.")
        research_id = uuid4()
        row = await self.repository.create(
            research_id=research_id, user_id=identity.user_id, provider="gemini",
            model=settings.gemini_research_model or "unconfigured", depth=request.depth,
            language=request.language, provider_job_id="pending", limit=settings.research_daily_limit,
        )
        quota = row.get("_quota")
        try:
            started = await self.provider.start_research(request.query, request.language, request.depth, document)
        except Exception as exc:
            await self.repository.update(research_id, status="failed", failure_category=_failure_category(exc))
            raise
        row = await self.repository.update(research_id, status=started.status,
                                           provider_job_id=started.provider_job_id)
        row["_quota"] = quota
        return _response(row)

    async def get(self, research_id: UUID, identity: RequestIdentity) -> ResearchJobResponse:
        if identity.user_id is None:
            raise ResearchNotFound("Research not found.")
        row = await self.repository.get(research_id, identity.user_id)
        if row is None:
            raise ResearchNotFound("Research not found.")
        if row["status"] in {"completed", "failed"}:
            return _response(row)
        try:
            current = await self.provider.get_research(row["provider_job_id"], research_id)
        except Exception as exc:
            await self.repository.update(research_id, status="failed", failure_category=_failure_category(exc))
            raise
        row = await self.repository.update(research_id, status=current.status,
                                           result=current.result, failure_category=current.failure_category)
        return _response(row)


def _response(row) -> ResearchJobResponse:
    result = row.get("result")
    return ResearchJobResponse(
        research_id=row["id"], status=row["status"], created_at=row["created_at"],
        updated_at=row["updated_at"], result=ResearchResult.model_validate(result) if result else None,
        failure_category=row.get("failure_category"),
        quota=row.get("_quota"),
    )


def _failure_category(exc: Exception) -> str:
    if isinstance(exc, AIProviderRateLimitError): return "provider_rate_limited"
    if isinstance(exc, AIProviderUnavailableError): return "provider_unavailable"
    if isinstance(exc, AIProviderTimeoutError): return "provider_timeout"
    if isinstance(exc, (AIProviderResponseError, AIProviderConfigurationError)): return "invalid_request"
    return "research_failed"
