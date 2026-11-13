from datetime import UTC, datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, model_validator

CharacterType = Literal["person", "child", "robot", "animal", "creature"]
BackgroundType = Literal["park", "room", "street", "office", "school", "space", "abstract"]
AnimationAction = Literal[
    "enter_left", "enter_right", "exit_left", "exit_right", "move", "wave",
    "bounce", "nod", "shake", "look_left", "look_right", "look_up", "smile",
    "surprised", "speech", "thought", "appear", "disappear",
]
Expression = Literal["neutral", "happy", "sad", "surprised", "curious"]
Palette = Literal["day", "sunset", "night", "pastel", "neon", "neutral"]
ColorToken = Literal["blue", "yellow", "red", "green", "purple", "orange", "pink", "brown", "gray", "white", "black"]


class AnimationAppearance(BaseModel):
    model_config = ConfigDict(extra="forbid")
    body_color: ColorToken = "blue"
    accent_color: ColorToken = "yellow"
    hair_style: Literal["none", "short", "long", "curly", "spiky"] = "none"
    accessory: Literal["none", "hat", "glasses", "backpack", "antenna"] = "none"


class AnimationBackground(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: BackgroundType
    description: str = Field(min_length=1, max_length=160)
    palette: Palette = "day"


class AnimationCharacter(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    type: CharacterType
    name: str = Field(min_length=1, max_length=40)
    x: float = Field(ge=5, le=95)
    y: float = Field(ge=20, le=92)
    scale: float = Field(default=1, ge=0.5, le=1.5)
    appearance: AnimationAppearance
    expression: Expression = "neutral"


class AnimationObject(BaseModel):
    model_config = ConfigDict(extra="forbid")
    id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    type: Literal["rocket", "tree", "bench", "ball", "star", "cloud", "flower", "book", "computer", "vehicle"]
    x: float = Field(ge=0, le=100)
    y: float = Field(ge=0, le=100)
    scale: float = Field(default=1, ge=0.25, le=2)
    color: ColorToken = "blue"
    label: str | None = Field(default=None, max_length=40)


class TimelineParameters(BaseModel):
    model_config = ConfigDict(extra="forbid")
    x: float | None = Field(default=None, ge=0, le=100)
    y: float | None = Field(default=None, ge=0, le=100)
    text: str | None = Field(default=None, min_length=1, max_length=160)


class TimelineEvent(BaseModel):
    model_config = ConfigDict(extra="forbid")
    start: float = Field(ge=0, le=15)
    duration: float = Field(gt=0, le=15)
    target_id: str = Field(pattern=r"^[a-z][a-z0-9_-]{0,31}$")
    action: AnimationAction
    parameters: TimelineParameters = Field(default_factory=TimelineParameters)

    @model_validator(mode="after")
    def validate_action_parameters(self) -> "TimelineEvent":
        if self.action in {"speech", "thought"} and not self.parameters.text:
            raise ValueError(f"{self.action} requires parameters.text")
        if self.action == "move" and self.parameters.x is None and self.parameters.y is None:
            raise ValueError("move requires parameters.x or parameters.y")
        if self.action not in {"speech", "thought"} and self.parameters.text is not None:
            raise ValueError("text is allowed only for speech or thought")
        if self.action != "move" and (self.parameters.x is not None or self.parameters.y is not None):
            raise ValueError("x and y parameters are allowed only for move")
        return self


class AnimationPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    title: str = Field(min_length=1, max_length=100)
    duration_seconds: float = Field(ge=1, le=15)
    background: AnimationBackground
    characters: list[AnimationCharacter] = Field(min_length=1, max_length=3)
    objects: list[AnimationObject] = Field(default_factory=list, max_length=5)
    timeline: list[TimelineEvent] = Field(default_factory=list, max_length=30)

    @model_validator(mode="after")
    def validate_scene(self) -> "AnimationPlan":
        ids = [item.id for item in self.characters] + [item.id for item in self.objects]
        if len(ids) != len(set(ids)):
            raise ValueError("character and object IDs must be unique")
        known = set(ids)
        for event in self.timeline:
            if event.target_id not in known:
                raise ValueError(f"unknown timeline target: {event.target_id}")
            if event.start + event.duration > self.duration_seconds + 0.001:
                raise ValueError("timeline event exceeds animation duration")
        return self


class AnimationPlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: AnimationPlan


class AnimationRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt: str = Field(min_length=1, max_length=3000)
    language: str = Field(default="sr", min_length=2, max_length=10)


class AnimationQuotaSnapshot(BaseModel):
    used: int
    limit: int
    remaining: int
    reset_at: datetime


class AnimationResponse(BaseModel):
    animation_id: UUID
    title: str
    plan: AnimationPlan
    generated_at: datetime = Field(default_factory=lambda: datetime.now(UTC))
    provider: str
    model: str
    quota: AnimationQuotaSnapshot
