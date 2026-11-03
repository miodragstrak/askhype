from app.prompts.askhype import ASKHYPE_SYSTEM_INSTRUCTION
from app.schemas.chat import ChatRequest
from app.services.location_context import build_location_context


def test_prompt_contains_explicit_location_precedence_rule() -> None:
    normalized = ASKHYPE_SYSTEM_INSTRUCTION.casefold()

    assert "location priority is strict" in normalized
    assert "explicitly stated in the current" in normalized
    assert "do not recommend beograd" in normalized
    assert "selected location is beograd" in normalized


def test_prompt_requires_intent_matching_without_padding_or_invented_details() -> None:
    normalized = " ".join(ASKHYPE_SYSTEM_INSTRUCTION.casefold().split())

    assert "directly satisfy the user's explicit intent" in normalized
    assert "accommodation-related options only" in normalized
    assert "never pad the response" in normalized
    assert "do not invent proper names" in normalized
    assert "clearly generic categories and types" in normalized
    assert "use null for estimated_price and" in normalized
    assert "date_or_duration" in normalized
    assert "information is not verified live" in normalized


def test_selected_location_does_not_override_message_location_in_context() -> None:
    request = ChatRequest(
        message="Šta da posetim u Boru?",
        location="Beograd",
        language="sr",
    )

    context = build_location_context(request)

    assert "Selected application location (fallback only): Beograd" in context
    assert "Explicit message location: not deterministically extracted by the backend" in context
    assert "Any explicit place named in the current user message has highest priority" in context
    assert "recent conversation before the selected application location" in context
    assert "Do not silently combine conflicting locations" in context
