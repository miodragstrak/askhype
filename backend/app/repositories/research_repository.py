from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import Any, Protocol
from uuid import UUID

from app.clients.supabase import get_supabase_admin_client
from app.schemas.research import ResearchResult


class ResearchLimitReached(RuntimeError):
    def __init__(self, used: int, limit: int, reset_at: datetime) -> None:
        self.used, self.limit, self.reset_at = used, limit, reset_at


class ResearchRepository(Protocol):
    async def create(self, *, research_id: UUID, user_id: UUID, provider: str, model: str,
                     depth: str, language: str, provider_job_id: str, limit: int) -> dict[str, Any]: ...
    async def get(self, research_id: UUID, user_id: UUID) -> dict[str, Any] | None: ...
    async def update(self, research_id: UUID, *, status: str, result: ResearchResult | None = None,
                     failure_category: str | None = None, provider_job_id: str | None = None) -> dict[str, Any]: ...


class SupabaseResearchRepository:
    def __init__(self, client=None) -> None:
        self.client = client or get_supabase_admin_client()

    async def create(self, **values) -> dict[str, Any]:
        response = self.client.rpc("reserve_research_job", {
            "p_research_id": str(values["research_id"]), "p_user_id": str(values["user_id"]),
            "p_provider": values["provider"], "p_model": values["model"],
            "p_depth": values["depth"], "p_language": values["language"],
            "p_provider_job_id": values["provider_job_id"], "p_limit": values["limit"],
        }).execute()
        row = _row(getattr(response, "data", None))
        if not row.get("allowed"):
            raise ResearchLimitReached(int(row["used"]), int(row["limit"]), _datetime(row["reset_at"]))
        job = await self.get(values["research_id"], values["user_id"]) or {}
        job["_quota"] = {
            "used": int(row["used"]), "limit": int(row["limit"]),
            "remaining": max(int(row["limit"]) - int(row["used"]), 0),
            "reset_at": _datetime(row["reset_at"]),
        }
        return job

    async def get(self, research_id: UUID, user_id: UUID) -> dict[str, Any] | None:
        response = (self.client.table("research_jobs").select("*")
                    .eq("id", str(research_id)).eq("user_id", str(user_id)).maybe_single().execute())
        data = getattr(response, "data", None)
        return data if isinstance(data, dict) and data else None

    async def update(self, research_id: UUID, *, status: str, result=None, failure_category=None, provider_job_id=None):
        values: dict[str, Any] = {"status": status, "failure_category": failure_category,
                                  "updated_at": datetime.now(UTC).isoformat()}
        if provider_job_id is not None:
            values["provider_job_id"] = provider_job_id
        if result is not None:
            values["result"] = result.model_dump(mode="json")
        response = self.client.table("research_jobs").update(values).eq("id", str(research_id)).execute()
        return _row(getattr(response, "data", None))


class InMemoryResearchRepository:
    def __init__(self) -> None:
        self.jobs: dict[UUID, dict[str, Any]] = {}

    async def create(self, **values) -> dict[str, Any]:
        now = datetime.now(UTC)
        active = [job for job in self.jobs.values() if job["user_id"] == values["user_id"] and job["created_at"].date() == now.date()]
        if len(active) >= values["limit"]:
            reset = now.replace(hour=0, minute=0, second=0, microsecond=0)
            raise ResearchLimitReached(len(active), values["limit"], reset + timedelta(days=1))
        row = {"id": values["research_id"], **values, "status": "queued", "result": None,
               "failure_category": None, "created_at": now, "updated_at": now,
               "_quota": {"used": len(active) + 1, "limit": values["limit"],
                           "remaining": max(values["limit"] - len(active) - 1, 0),
                           "reset_at": now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)}}
        self.jobs[values["research_id"]] = row
        return row

    async def get(self, research_id, user_id):
        row = self.jobs.get(research_id)
        return row if row and row["user_id"] == user_id else None

    async def update(self, research_id, *, status, result=None, failure_category=None, provider_job_id=None):
        row = self.jobs[research_id]
        row.update(status=status, result=result.model_dump(mode="json") if result else row.get("result"),
                   failure_category=failure_category, updated_at=datetime.now(UTC))
        if provider_job_id is not None: row["provider_job_id"] = provider_job_id
        return row


def _row(value):
    if isinstance(value, list) and value: return value[0]
    return value if isinstance(value, dict) else {}


def _datetime(value) -> datetime:
    if isinstance(value, datetime): return value
    return datetime.fromisoformat(str(value).replace("Z", "+00:00"))
