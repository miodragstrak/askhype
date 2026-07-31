import json

from pydantic import SecretStr

from scripts import evaluate_demo_locations as evaluation


def test_demo_scenarios_contain_expected_cities() -> None:
    cities = [scenario.city for scenario in evaluation.DEMO_SCENARIOS]

    assert cities == [
        "Beograd",
        "Bor",
        "Novi Sad",
        "Niš",
        "Sarajevo",
        "Zagreb",
        "Split",
        "Kotor",
        "Skopje",
        "Ljubljana",
    ]


def test_demo_report_serialization_works() -> None:
    result = evaluation.DemoEvaluationResult(
        city="Bor",
        country="Serbia",
        user_message="Šta vredi posetiti u Boru?",
        provider="mock",
        success=True,
        summary="Proveri detalje pre posete.",
        recommendation_titles=["Muzej", "Borsko jezero", "Vidikovac"],
        recommendation_locations=["Bor", "Bor", "Bor"],
        exactly_3_recommendations=True,
        any_source_url=False,
        includes_unverified_caveat=True,
        response_duration_seconds=0.01,
    )

    serialized = evaluation.serialize_results([result])
    markdown = evaluation.render_markdown_report([result])

    assert serialized[0]["city"] == "Bor"
    assert serialized[0]["locality_accuracy"] == "pending"
    assert json.dumps(serialized, ensure_ascii=False)
    assert "## Bor, Serbia" in markdown
    assert "Locality accuracy: pending" in markdown


def test_api_key_is_never_in_report_output(monkeypatch) -> None:
    secret = "demo-secret-key"
    monkeypatch.setattr(evaluation.settings, "gemini_api_key", SecretStr(secret))
    safe_error = evaluation._safe_error(RuntimeError(f"failed with {secret}"))
    result = evaluation.DemoEvaluationResult(
        city="Beograd",
        country="Serbia",
        user_message="Predloži vikend.",
        provider="gemini",
        success=False,
        summary="",
        recommendation_titles=[],
        recommendation_locations=[],
        exactly_3_recommendations=False,
        any_source_url=False,
        includes_unverified_caveat=False,
        response_duration_seconds=0.01,
        error=safe_error,
    )

    report_json = json.dumps(evaluation.serialize_results([result]), ensure_ascii=False)
    report_markdown = evaluation.render_markdown_report([result])

    assert secret not in safe_error
    assert secret not in report_json
    assert secret not in report_markdown
    assert "[redacted]" in report_json
