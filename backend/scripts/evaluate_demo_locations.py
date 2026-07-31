from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Literal

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.schemas.chat import ChatRequest
from app.services.chat_service import ChatService

ProviderName = Literal["mock", "gemini"]


@dataclass(frozen=True)
class DemoScenario:
    city: str
    country: str
    message: str


@dataclass
class DemoEvaluationResult:
    city: str
    country: str
    user_message: str
    provider: str
    success: bool
    summary: str
    recommendation_titles: list[str]
    recommendation_locations: list[str]
    exactly_3_recommendations: bool
    any_source_url: bool
    includes_unverified_caveat: bool
    response_duration_seconds: float
    locality_accuracy: str = "pending"
    factual_confidence: str = "pending"
    language_quality: str = "pending"
    demo_ready: str = "pending"
    reviewer_notes: str = ""
    error: str | None = None


DEMO_SCENARIOS: tuple[DemoScenario, ...] = (
    DemoScenario(
        city="Beograd",
        country="Serbia",
        message="Predloži mi tri ideje za kulturni i gastronomski vikend u Beogradu.",
    ),
    DemoScenario(
        city="Bor",
        country="Serbia",
        message="Šta vredi posetiti u Boru i okolini tokom jednog dana?",
    ),
    DemoScenario(
        city="Novi Sad",
        country="Serbia",
        message="Predloži mi muziku, hranu i kulturu za vikend u Novom Sadu.",
    ),
    DemoScenario(
        city="Niš",
        country="Serbia",
        message="Šta da radim tokom jednog dana u Nišu?",
    ),
    DemoScenario(
        city="Sarajevo",
        country="Bosnia and Herzegovina",
        message="Predloži mi tri autentična iskustva u Sarajevu.",
    ),
    DemoScenario(
        city="Zagreb",
        country="Croatia",
        message="Šta da posetim u Zagrebu ako volim kulturu i dobru hranu?",
    ),
    DemoScenario(
        city="Split",
        country="Croatia",
        message="Predloži mi mirniji dan u Splitu bez noćnih klubova.",
    ),
    DemoScenario(
        city="Kotor",
        country="Montenegro",
        message="Kako da provedem jedan dan u Kotoru?",
    ),
    DemoScenario(
        city="Skopje",
        country="North Macedonia",
        message="Predloži mi tri zanimljiva mesta u Skoplju.",
    ),
    DemoScenario(
        city="Ljubljana",
        country="Slovenia",
        message="Šta da radim tokom vikenda u Ljubljani?",
    ),
)


async def evaluate_scenarios(
    scenarios: list[DemoScenario],
    provider: ProviderName,
    delay: float,
) -> list[DemoEvaluationResult]:
    settings.ai_provider = provider
    service = ChatService()
    results: list[DemoEvaluationResult] = []

    if provider == "gemini":
        print("Gemini evaluation consumes API quota. Running sanitized manual demo checks.")

    for index, scenario in enumerate(scenarios):
        if provider == "gemini" and index > 0 and delay > 0:
            await asyncio.sleep(delay)

        print(f"[{index + 1}/{len(scenarios)}] {scenario.city}, {scenario.country}")
        results.append(await evaluate_scenario(service, scenario, provider))

    return results


async def evaluate_scenario(
    service: ChatService,
    scenario: DemoScenario,
    provider: ProviderName,
) -> DemoEvaluationResult:
    request = ChatRequest(
        message=scenario.message,
        location=scenario.city,
        language="sr",
        interests=["kultura", "hrana", "putovanja"],
    )
    start = time.perf_counter()

    try:
        response = await service.generate_response(request)
    except Exception as exc:
        return DemoEvaluationResult(
            city=scenario.city,
            country=scenario.country,
            user_message=scenario.message,
            provider=provider,
            success=False,
            summary="",
            recommendation_titles=[],
            recommendation_locations=[],
            exactly_3_recommendations=False,
            any_source_url=False,
            includes_unverified_caveat=False,
            response_duration_seconds=round(time.perf_counter() - start, 3),
            error=_safe_error(exc),
        )

    text_for_caveat = " ".join(
        [
            response.summary,
            *[source.title for source in response.sources],
            *[item.reason for item in response.recommendations],
        ]
    )
    return DemoEvaluationResult(
        city=scenario.city,
        country=scenario.country,
        user_message=scenario.message,
        provider=response.provider,
        success=True,
        summary=response.summary,
        recommendation_titles=[item.title for item in response.recommendations],
        recommendation_locations=[item.location for item in response.recommendations],
        exactly_3_recommendations=len(response.recommendations) == 3,
        any_source_url=any(
            bool(item.source_url) for item in response.recommendations
        )
        or any(bool(source.url) for source in response.sources),
        includes_unverified_caveat=_includes_unverified_caveat(text_for_caveat),
        response_duration_seconds=round(time.perf_counter() - start, 3),
    )


def filter_scenarios(city_filter: str | None) -> list[DemoScenario]:
    if not city_filter:
        return list(DEMO_SCENARIOS)

    normalized = city_filter.casefold()
    return [
        scenario
        for scenario in DEMO_SCENARIOS
        if normalized in scenario.city.casefold()
    ]


def serialize_results(results: list[DemoEvaluationResult]) -> list[dict[str, object]]:
    return [asdict(result) for result in results]


def render_markdown_report(results: list[DemoEvaluationResult]) -> str:
    lines = ["# AskHype Balkan Demo Evaluation", ""]
    for result in results:
        lines.extend(
            [
                f"## {result.city}, {result.country}",
                "",
                f"- Provider: {result.provider}",
                f"- Success: {result.success}",
                f"- Duration: {result.response_duration_seconds}s",
                f"- Exactly 3 recommendations: {result.exactly_3_recommendations}",
                f"- Any source URL: {result.any_source_url}",
                f"- Includes unverified caveat: {result.includes_unverified_caveat}",
                f"- Locality accuracy: {result.locality_accuracy}",
                f"- Factual confidence: {result.factual_confidence}",
                f"- Language quality: {result.language_quality}",
                f"- Demo ready: {result.demo_ready}",
                f"- Reviewer notes: {result.reviewer_notes}",
                "",
                f"Message: {result.user_message}",
                "",
                f"Summary: {result.summary}",
                "",
                "Recommendation titles:",
                *[f"- {title}" for title in result.recommendation_titles],
                "",
                "Recommendation locations:",
                *[f"- {location}" for location in result.recommendation_locations],
                "",
            ]
        )
        if result.error:
            lines.extend([f"Error: {result.error}", ""])
    return "\n".join(lines).strip() + "\n"


def write_report(path: Path, results: list[DemoEvaluationResult]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.suffix.casefold() == ".json":
        path.write_text(
            json.dumps(serialize_results(results), ensure_ascii=False, indent=2),
            encoding="utf-8",
        )
        return

    path.write_text(render_markdown_report(results), encoding="utf-8")


def print_summary(results: list[DemoEvaluationResult]) -> None:
    for result in results:
        status = "ok" if result.success else "failed"
        titles = "; ".join(result.recommendation_titles) or "no recommendations"
        print(
            f"{result.city}: {status}, provider={result.provider}, "
            f"recommendations={len(result.recommendation_titles)}, titles={titles}"
        )
        if result.error:
            print(f"{result.city}: error={result.error}")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run a manual AskHype Balkan demo evaluation without exposing secrets.",
    )
    parser.add_argument(
        "--provider",
        choices=["mock", "gemini"],
        default=settings.ai_provider,
        help="Provider to evaluate. Gemini mode consumes API quota.",
    )
    parser.add_argument(
        "--delay",
        type=float,
        default=0.0,
        help="Delay in seconds between Gemini requests.",
    )
    parser.add_argument(
        "--city",
        help="Run only scenarios whose city contains this text.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        help="Optional .json or Markdown report path.",
    )
    return parser.parse_args()


async def main() -> int:
    args = parse_args()
    scenarios = filter_scenarios(args.city)
    if not scenarios:
        print("No matching scenarios.")
        return 1

    results = await evaluate_scenarios(
        scenarios=scenarios,
        provider=args.provider,
        delay=max(args.delay, 0.0),
    )
    print_summary(results)

    if args.output:
        write_report(args.output, results)
        print(f"Wrote sanitized report: {args.output}")

    return 0 if all(result.success for result in results) else 1


def _includes_unverified_caveat(value: str) -> bool:
    normalized = value.casefold()
    return any(
        phrase in normalized
        for phrase in [
            "nije prover",
            "nije potvr",
            "proveri",
            "pre posete",
            "unverified",
            "not verified",
        ]
    )


def _safe_error(exc: Exception) -> str:
    message = str(exc).replace("\n", " ").strip()
    if settings.gemini_api_key is not None:
        secret = settings.gemini_api_key.get_secret_value()
        if secret:
            message = message.replace(secret, "[redacted]")
    if not message:
        return exc.__class__.__name__
    return f"{exc.__class__.__name__}: {message[:180]}"


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
