from app.schemas.chat import ChatRequest


def build_location_context(request: ChatRequest) -> str:
    selected_location = request.location.strip() or "not supplied"
    return "\n".join(
        [
            f"Selected application location: {selected_location}",
            "Explicit message location: not deterministically extracted by the backend",
            "Rule: Any explicit place named in the current user message overrides the selected application location.",
            "Do not silently combine conflicting locations; ask a short clarification if the location is ambiguous.",
        ]
    )
