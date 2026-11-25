from contextlib import contextmanager
from dataclasses import dataclass, field
from time import monotonic


class PresentationRuleError(ValueError):
    """A validation failure with an application-owned, safe message."""

    def __init__(self, rule: str, message: str):
        super().__init__(message)
        self.rule = rule


@dataclass
class PresentationDiagnostics:
    stage: str = "planning"
    slide_index: int | None = None
    requested_layout: str | None = None
    selected_layout: str | None = None
    durations: dict[str, float] = field(default_factory=dict)
    resolved_layouts: dict[int, str] = field(default_factory=dict)
    layout_fallbacks: list[dict] = field(default_factory=list)

    def fallback(self, layout, rule, reason):
        self.layout_fallbacks.append({
            "slide_index": self.slide_index, "requested_layout": self.requested_layout,
            "selected_layout": layout, "rule": rule, "reason": reason,
        })

    def slide(self, index=None, requested=None):
        self.slide_index = index
        self.requested_layout = requested
        self.selected_layout = None

    @contextmanager
    def measure(self, stage, bucket=None):
        self.stage = stage
        key = bucket or stage
        start = monotonic()
        try:
            yield
        finally:
            self.durations[key] = self.durations.get(key, 0.0) + monotonic() - start
