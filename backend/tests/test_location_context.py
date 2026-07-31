from app.prompts.askhype import ASKHYPE_SYSTEM_INSTRUCTION
from app.schemas.chat import ChatRequest
from app.services.location_context import build_location_context


def test_prompt_contains_explicit_location_precedence_rule() -> None:
    normalized = ASKHYPE_SYSTEM_INSTRUCTION.casefold()

    assert "location priority is strict" in normalized
    assert "explicitly stated in the current" in normalized
    assert "do not recommend beograd" in normalized
    assert "selected location is beograd" in normalized


def test_selected_location_does_not_override_message_location_in_context() -> None:
    request = ChatRequest(
        message="Šta da posetim u Boru?",
        location="Beograd",
        language="sr",
    )

    context = build_location_context(request)

    assert "Selected application location: Beograd" in context
    assert "Explicit message location: not deterministically extracted by the backend" in context
    assert "Any explicit place named in the current user message overrides" in context
    assert "Do not silently combine conflicting locations" in context
