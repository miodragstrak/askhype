from typing import Annotated, Literal
from datetime import UTC, datetime

from pydantic import BaseModel, ConfigDict, Field, model_validator

PaletteValue = Annotated[str, Field(min_length=1, max_length=40)]


class ArtCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    role: str = Field(min_length=1, max_length=160)
    appearance: str = Field(min_length=1, max_length=400)


class ArtObject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1, max_length=80)
    description: str = Field(min_length=1, max_length=300)


class TimelineBeat(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0, le=15)
    duration: float = Field(gt=0, le=15)
    description: str = Field(min_length=1, max_length=300)
    motion: str = Field(min_length=1, max_length=200)


class ArtDirection(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    duration_seconds: float = Field(ge=10, le=15)
    scene_description: str = Field(min_length=1, max_length=800)
    characters: list[ArtCharacter] = Field(default_factory=list, max_length=6)
    objects: list[ArtObject] = Field(default_factory=list, max_length=16)
    background_description: str = Field(min_length=1, max_length=500)
    composition: str = Field(min_length=1, max_length=400)
    visual_style: str = Field(min_length=1, max_length=300)
    shape_language: str = Field(min_length=1, max_length=300)
    palette: list[str] = Field(min_length=2, max_length=12)
    lighting: str = Field(min_length=1, max_length=250)
    line_treatment: str = Field(min_length=1, max_length=250)
    depth_style: str = Field(min_length=1, max_length=250)
    mood: str = Field(min_length=1, max_length=250)
    motion_style: str = Field(min_length=1, max_length=300)
    timeline_beats: list[TimelineBeat] = Field(min_length=1, max_length=20)

    @model_validator(mode="after")
    def beats_fit_duration(self) -> "ArtDirection":
        if any(beat.start + beat.duration > self.duration_seconds + .001 for beat in self.timeline_beats):
            raise ValueError("timeline beat exceeds duration")
        return self


class ArtDirectionEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    art_direction: ArtDirection


class ReferenceArtAnalysis(BaseModel):
    model_config = ConfigDict(extra="forbid")
    dominant_palette: list[PaletteValue] = Field(min_length=1, max_length=8)
    secondary_palette: list[PaletteValue] = Field(default_factory=list, max_length=6)
    contrast_level: str = Field(min_length=1, max_length=120)
    lighting_style: str = Field(min_length=1, max_length=220)
    shape_language: str = Field(min_length=1, max_length=260)
    line_treatment: str = Field(min_length=1, max_length=220)
    texture_feel: str = Field(min_length=1, max_length=220)
    depth_style: str = Field(min_length=1, max_length=220)
    composition_tendency: str = Field(min_length=1, max_length=260)
    mood: str = Field(min_length=1, max_length=180)
    softness: str = Field(min_length=1, max_length=140)
    visual_complexity: str = Field(min_length=1, max_length=180)
    background_character: str = Field(min_length=1, max_length=240)
    character_style_notes: str = Field(min_length=1, max_length=260)
    motion_style_suggestion: str = Field(min_length=1, max_length=220)
    confidence_notes: str = Field(min_length=1, max_length=220)


class ReferenceArtAnalysisEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    reference_analysis: ReferenceArtAnalysis


class GenerativeSvgResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    svg: str
    has_reference: bool
    generation_seconds: float = Field(ge=0)
    attempts: int = Field(ge=1, le=2)
    remaining_quota: int = Field(ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))


class StoryboardSubject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,39}$")
    name: str = Field(min_length=1, max_length=80)
    kind: Literal["person", "child", "animal", "robot", "creature", "object"]
    appearance: str = Field(min_length=1, max_length=300)


class StoryboardScene(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^scene_[1-6]$")
    duration_seconds: int = Field(ge=2, le=8)
    description: str = Field(min_length=1, max_length=500)
    environment: str = Field(min_length=1, max_length=300)
    subject_ids: list[str] = Field(default_factory=list, max_length=8)
    action: str = Field(min_length=1, max_length=250)
    mood: str = Field(min_length=1, max_length=120)
    composition: str = Field(min_length=1, max_length=220)
    transition_in: Literal["fade", "crossfade", "slide"] = "fade"
    transition_out: Literal["fade", "crossfade", "slide"] = "crossfade"


class StoryboardPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    total_duration_seconds: int = Field(ge=10, le=30)
    shared_art_direction: ArtDirection
    recurring_subjects: list[StoryboardSubject] = Field(default_factory=list, max_length=8)
    scenes: list[StoryboardScene] = Field(min_length=3, max_length=6)

    @model_validator(mode="after")
    def validate_timeline(self) -> "StoryboardPlan":
        if sum(scene.duration_seconds for scene in self.scenes) != self.total_duration_seconds:
            raise ValueError("scene durations must equal total duration")
        subject_ids = {subject.id for subject in self.recurring_subjects}
        if any(not set(scene.subject_ids).issubset(subject_ids) for scene in self.scenes):
            raise ValueError("scene references an unknown recurring subject")
        return self


class StoryboardPlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    storyboard: StoryboardPlan


class StoryboardSceneResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str
    duration_seconds: int
    transition_in: Literal["fade", "crossfade", "slide"]
    transition_out: Literal["fade", "crossfade", "slide"]
    svg: str


class StoryboardResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str
    total_duration_seconds: int
    scenes: list[StoryboardSceneResponse] = Field(min_length=3, max_length=6)
    generation_seconds: float = Field(ge=0)
    remaining_quota: int = Field(ge=0)
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
