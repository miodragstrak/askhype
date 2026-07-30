from datetime import datetime

from pydantic import BaseModel, Field


class ChatRequest(BaseModel):
    message: str = Field(..., min_length=1)
    conversation_id: str | None = None
    location: str = "Beograd"
    language: str = "sr"
    interests: list[str] = Field(default_factory=list)


class Recommendation(BaseModel):
    id: str
    title: str
    category: str
    short_description: str
    location: str
    estimated_price: str | None = None
    date_or_duration: str | None = None
    reason: str
    image_url: str | None = None
    source_url: str | None = None


class SourceReference(BaseModel):
    title: str
    url: str | None = None
    last_verified: datetime | None = None


class ChatResponse(BaseModel):
    conversation_id: str
    provider: str
    answer_type: str
    summary: str
    recommendations: list[Recommendation]
    follow_up_actions: list[str]
    sources: list[SourceReference]
    generated_at: datetime
