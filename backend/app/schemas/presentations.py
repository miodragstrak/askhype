from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

BulletText = Annotated[str, Field(min_length=1, max_length=180)]
TableText = Annotated[str, Field(max_length=80)]

IllustrationMode = Literal["OFF", "COVER", "ENHANCED"]


class IllustrationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid", str_strip_whitespace=True)
    slide_index: int = Field(ge=1, le=12)
    purpose: str = Field(min_length=1, max_length=160)
    subject: str = Field(min_length=1, max_length=220)
    composition: str = Field(min_length=1, max_length=220)
    visual_style: str = Field(min_length=1, max_length=120)
    palette: str = Field(min_length=1, max_length=100)
    aspect_ratio: Literal["1:1", "3:4", "4:3", "16:9"]
    crop_region: Literal["cover_right", "split_right", "full_bleed"]

ExecutiveLayout = Literal[
    "cover", "summary", "findings", "kpi", "pillars", "comparison", "problem_solution",
    "process", "roadmap", "table", "recommendations", "closing", "chart",
    "business_model", "timeline", "worked_example",
]


class SlideEditorial(BaseModel):
    model_config = ConfigDict(extra="forbid")
    objective: str = Field(default="", max_length=180)
    takeaway: str = Field(default="", max_length=220)
    layout: ExecutiveLayout | None = None
    speaker_notes: str = Field(default="", max_length=1200)
    evidence_ids: list[str] = Field(default_factory=list, max_length=4)
    claim_status: Literal["evidence", "proposal", "assumption", "illustrative", "qualitative"] = "qualitative"


class TitleSlide(SlideEditorial):
    model_config = ConfigDict(extra="forbid")
    type: Literal["title"]
    title: str = Field(min_length=1, max_length=100)
    subtitle: str | None = Field(default=None, max_length=180)


class BulletsSlide(SlideEditorial):
    model_config = ConfigDict(extra="forbid")
    type: Literal["bullets"]
    title: str = Field(min_length=1, max_length=100)
    bullets: list[BulletText] = Field(min_length=1, max_length=6)


class SectionSlide(SlideEditorial):
    model_config = ConfigDict(extra="forbid")
    type: Literal["section"]
    title: str = Field(min_length=1, max_length=100)
    subtitle: str | None = Field(default=None, max_length=180)


class MetricCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=50)


class KeyMetricsSlide(SlideEditorial):
    model_config = ConfigDict(extra="forbid")
    type: Literal["key_metrics"]
    title: str = Field(min_length=1, max_length=100)
    metrics: list[MetricCard] = Field(min_length=1, max_length=4)


class TableSlide(SlideEditorial):
    model_config = ConfigDict(extra="forbid")
    type: Literal["table"]
    title: str = Field(min_length=1, max_length=100)
    headers: list[TableText] = Field(min_length=1, max_length=5)
    rows: list[list[TableText]] = Field(min_length=1, max_length=8)


class ConclusionSlide(SlideEditorial):
    model_config = ConfigDict(extra="forbid")
    type: Literal["conclusion"]
    title: str = Field(min_length=1, max_length=100)
    bullets: list[BulletText] = Field(min_length=1, max_length=5)


PresentationSlide = Annotated[
    TitleSlide | BulletsSlide | SectionSlide | KeyMetricsSlide | TableSlide | ConclusionSlide,
    Field(discriminator="type"),
]


class PresentationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    subtitle: str | None = Field(default=None, max_length=180)
    slides: list[PresentationSlide] = Field(min_length=3, max_length=12)
    purpose: str = Field(default="", max_length=180)
    audience: str = Field(default="", max_length=100)
    language: str = Field(default="", max_length=40)
    narrative: str = Field(default="", max_length=240)
    illustrations: list[IllustrationRequest] = Field(default_factory=list, max_length=3)


class PresentationPlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: PresentationPlan
