from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import AnyHttpUrl, BaseModel, ConfigDict, Field

ResearchDepth = Literal["quick", "standard", "deep"]
ResearchStatus = Literal["queued", "running", "completed", "failed"]


class ResearchRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    query: str = Field(min_length=1, max_length=3000)
    language: str = Field(default="sr", min_length=2, max_length=10)
    depth: ResearchDepth = "standard"


class ResearchSection(BaseModel):
    heading: str
    content: str


class ResearchSource(BaseModel):
    title: str
    url: AnyHttpUrl
    publisher: str | None = None
    date: str | None = None
    citation_ids: list[int] = Field(default_factory=list)


class ResearchQuotaSnapshot(BaseModel):
    used: int
    limit: int
    remaining: int
    reset_at: datetime


class ResearchResult(BaseModel):
    research_id: UUID
    status: Literal["completed"] = "completed"
    title: str
    summary: str
    sections: list[ResearchSection]
    sources: list[ResearchSource]
    limitations: list[str]
    generated_at: datetime
    provider: str
    model: str


class ResearchJobResponse(BaseModel):
    research_id: UUID
    status: ResearchStatus
    created_at: datetime
    updated_at: datetime
    result: ResearchResult | None = None
    failure_category: str | None = None
    quota: ResearchQuotaSnapshot | None = None


class ResearchQuotaDetail(BaseModel):
    code: Literal["daily_quota_reached"] = "daily_quota_reached"
    message: str = "Dnevni limit za Deep Research je dostignut."
    used: int
    limit: int
    reset_at: datetime
