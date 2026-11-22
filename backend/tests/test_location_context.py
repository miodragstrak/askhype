import pytest

from app.prompts.askhype import ASKHYPE_SYSTEM_INSTRUCTION, DOCUMENT_ANALYSIS_INSTRUCTION
from app.providers.gemini import GeminiProvider, _explicit_response_language, resolve_output_language
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


def test_prompt_is_general_purpose_and_language_follows_latest_message() -> None:
    normalized = " ".join(ASKHYPE_SYSTEM_INSTRUCTION.casefold().split())
    assert "general-purpose ai assistant" in normalized
    assert "do not restrict answers" in normalized
    assert "same language as the user's latest message" in normalized
    assert "explicit request always wins" in normalized
    assert "main answer has fully completed" in normalized
    assert "language of the user's latest message" in " ".join(DOCUMENT_ANALYSIS_INSTRUCTION.split())


def test_language_rule_handles_serbian_english_german_and_explicit_override() -> None:
    provider = object.__new__(GeminiProvider)
    cases = (
        ("Kako radi fotosinteza?", "resolved_output_language: Serbian"),
        ("How does photosynthesis work?", "resolved_output_language: English"),
        ("Wie funktioniert die Photosynthese?", "resolved_output_language: German"),
        ("Wie funktioniert die Photosynthese? Answer in English.", "resolved_output_language: English"),
    )
    for message, expected in cases:
        context = provider._build_user_context(ChatRequest(message=message, language="sr"))
        assert expected in context


def test_multilingual_explicit_output_language_requests_have_highest_priority() -> None:
    cases = (
        ("Odgovori mi na engleskom: koja su tri najveća grada u Srbiji?", "English"),
        ("Odgovori na engleskom jeziku.", "English"),
        ("Please answer in English.", "English"),
        ("Respond in English.", "English"),
        ("Antworte auf Englisch.", "English"),
        ("Réponds en anglais.", "English"),
        ("Explain photosynthesis. Answer in German.", "German"),
        ("Odgovori na francuskom.", "French"),
        ("Rispondi in spagnolo.", "Spanish"),
        ("Responde en italiano.", "Italian"),
        ("Odgovori na hrvatskom.", "Croatian"),
    )
    for message, expected in cases:
        assert _explicit_response_language(message) == expected


def test_explicit_language_rule_covers_cards_descriptions_followups_and_fallbacks() -> None:
    provider = object.__new__(GeminiProvider)
    context = provider._build_user_context(ChatRequest(
        message="Odgovori mi na engleskom: preporuči tri grada.", language="sr",
    ))
    assert "resolved_output_language: English (source: explicit_request)" in context
    assert "every recommendation/card title and category" in context
    assert "all descriptions" in context
    assert "follow-up suggestions" in context
    assert "generated fallback text" in context


@pytest.mark.parametrize(("message", "expected"), (
    ("Kako radi fotosinteza?", "Serbian"),
    ("What are three benefits of remote work?", "English"),
    ("Welche drei Vorteile hat Fernarbeit?", "German"),
    ("Quels sont trois avantages du télétravail ?", "French"),
    ("Quali sono tre vantaggi del lavoro da remoto?", "Italian"),
    ("¿Cuáles son tres beneficios del trabajo remoto?", "Spanish"),
    ("Koje su prednosti rada na daljinu za tvrtku?", "Croatian"),
    ("Odgovori mi na engleskom: navedi tri koristi.", "English"),
    ("Explain three benefits. Answer in German.", "German"),
    ("Antworte auf Englisch: Welche Vorteile gibt es?", "English"),
    ("Explain three benefits. Answer in French.", "French"),
    ("Explain three benefits. Answer in Italian.", "Italian"),
    ("Explain three benefits. Answer in Spanish.", "Spanish"),
    ("Réponds en anglais: quels avantages?", "English"),
    ("Rispondi in inglese: quali vantaggi?", "English"),
    ("Responde en inglés: ¿cuáles beneficios?", "English"),
    ("Odgovori mi na engleskom: koje su prednosti za tvrtku?", "English"),
))
def test_authoritative_resolver_priority_languages(message: str, expected: str) -> None:
    assert resolve_output_language(message, "sr").language == expected


def test_answer_depth_instruction_requires_requested_substantive_item_count() -> None:
    normalized = " ".join(ASKHYPE_SYSTEM_INSTRUCTION.split())
    assert "requested number of substantive items with brief explanations" in normalized
    assert "Do not replace or shorten the main answer in favor of follow-up suggestions" in normalized
    assert "concise but substantive" in normalized
    assert "Follow-up suggestions must never substitute" in normalized


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
