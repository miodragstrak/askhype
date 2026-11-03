from app.schemas.chat import ChatRequest


def build_location_context(request: ChatRequest) -> str:
    selected_location = request.location.strip() or "not supplied"
    return "\n".join(
        [
            f"Selected application location (fallback only): {selected_location}",
            "Explicit message location: not deterministically extracted by the backend",
            "Rule: Any explicit place named in the current user message has highest priority and overrides earlier conversation context and the selected application location.",
            "If the current message has no explicit location, use an obvious location established by the recent conversation before the selected application location.",
            "The selected application location must not override an obvious location established by the recent conversation.",
            "Do not silently combine conflicting locations; ask a short clarification if the location is ambiguous.",
        ]
    )
