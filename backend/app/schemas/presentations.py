from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field

BulletText = Annotated[str, Field(min_length=1, max_length=180)]
TableText = Annotated[str, Field(max_length=80)]


class TitleSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["title"]
    title: str = Field(min_length=1, max_length=100)
    subtitle: str | None = Field(default=None, max_length=180)


class BulletsSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["bullets"]
    title: str = Field(min_length=1, max_length=100)
    bullets: list[BulletText] = Field(min_length=1, max_length=6)


class SectionSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["section"]
    title: str = Field(min_length=1, max_length=100)
    subtitle: str | None = Field(default=None, max_length=180)


class MetricCard(BaseModel):
    model_config = ConfigDict(extra="forbid")
    label: str = Field(min_length=1, max_length=60)
    value: str = Field(min_length=1, max_length=50)


class KeyMetricsSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["key_metrics"]
    title: str = Field(min_length=1, max_length=100)
    metrics: list[MetricCard] = Field(min_length=1, max_length=4)


class TableSlide(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["table"]
    title: str = Field(min_length=1, max_length=100)
    headers: list[TableText] = Field(min_length=1, max_length=5)
    rows: list[list[TableText]] = Field(min_length=1, max_length=8)


class ConclusionSlide(BaseModel):
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


class PresentationPlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: PresentationPlan
