"""Compare Gemini Search and structured output with an offline transport by default."""

import argparse
import asyncio
from importlib.metadata import version
import json
import logging
from time import monotonic
from uuid import uuid4

from google import genai
from google.genai import types
import httpx

from app.core.config import Settings
from app.providers.exceptions import AIProviderResponseError
from app.providers.gemini import GeminiProvider, grounding_error_details
from app.schemas.chat import ChatRequest

QUERIES = {
    "news": "What are three major international news developments today? Cite your sources.",
    "football": "Which Premier League football fixtures are scheduled this coming weekend?",
    "weather": "What is tomorrow's weather forecast for Belgrade, Serbia?",
    "explicit": "Search the web for the latest European Central Bank policy rate decision.",
    "control": "Why does the Moon have phases?",
}
VARIANTS = ("A", "B", "C")
MAX_CALLS = 13  # Three variants per freshness query and one non-grounded control.


def offline_response(request: httpx.Request) -> httpx.Response:
    body = json.loads(request.content)
    config = body["generationConfig"]
    grounded = bool(body.get("tools"))
    if grounded:
        assert body["tools"] == [{"googleSearch": {}}]
    structured = config.get("responseMimeType") == "application/json"
    assert ("responseJsonSchema" in config) == structured
    text = '{"answer":"Synthetic answer"}' if structured else "Synthetic answer"
    candidate = {"content": {"role": "model", "parts": [{"text": text}]}, "finishReason": "STOP"}
    if grounded:
        candidate["groundingMetadata"] = {"groundingChunks": [
            {"web": {"uri": "https://example.com/synthetic", "title": "Synthetic source"}},
            {"web": {"uri": "ftp://example.com/rejected", "title": "Rejected"}},
        ]}
    return httpx.Response(200, json={"candidates": [candidate]})


async def probe(client, provider, query, variant, model, timeout):
    config = provider._build_generation_config(enable_grounding=variant != "A")
    if variant == "B":
        config = config.model_copy(update={"response_mime_type": None, "response_json_schema": None})
    request = ChatRequest(message=QUERIES[query], language="en")
    record = {
        "correlation_id": uuid4().hex, "query_id": query, "variant": variant, "model": model,
        "tool": "google_search" if variant != "A" else None, "structured_output": variant != "B",
        "retry_count": 0,
    }
    started = monotonic()
    try:
        async with asyncio.timeout(timeout):
            response = await client.models.generate_content(
                model=model, contents=provider._build_user_context(request), config=config,
            )
    except Exception as exc:
        record.update(grounding_error_details(exc), outcome="provider_error")
    else:
        sources = provider._grounding_sources(response, record)
        record.update(outcome="sources_returned" if sources else "no_sources", http_status=200)
        if variant != "B":
            try:
                provider._parse_payload(response, log_exception=False)
            except AIProviderResponseError:
                record["outcome"] = "invalid_response"
        elif not (response.text or "").strip():
            record["outcome"] = "invalid_response"
    record["duration_seconds"] = round(monotonic() - started, 6)
    print(json.dumps(record))
    return record


async def run(args, cases):
    # Offline transport uses a synthetic key even when app settings contain credentials.
    config = Settings() if args.live else Settings(_env_file=None, app_env="development")
    key = config.gemini_api_key.get_secret_value() if args.live and config.gemini_api_key else ""
    if args.live and not key.strip():
        print(json.dumps({"outcome": "credentials_unavailable"}))
        return 2
    options = types.HttpOptions(
        timeout=config.gemini_timeout_seconds * 1000,
        retry_options=types.HttpRetryOptions(attempts=1),
        async_client_args={} if args.live else {"transport": httpx.MockTransport(offline_response)},
    )
    model = args.alternative_model or config.gemini_model
    print(json.dumps({"mode": "live" if args.live else "mock_transport", "sdk_version": version("google-genai"),
                      "request_budget": len(cases), "timeout_seconds": config.gemini_timeout_seconds}))
    # Keep SDK and HTTP library logs away from credentials and exception bodies.
    for logger_name in ("google", "httpx", "httpcore"):
        logging.getLogger(logger_name).setLevel(logging.CRITICAL)
    try:
        async with genai.Client(api_key=key if args.live else "offline-placeholder",
                                vertexai=False, http_options=options).aio as client:
            provider = GeminiProvider(config, client=client)
            results = [await probe(client, provider, query, variant, model, config.gemini_timeout_seconds)
                       for query, variant in cases]
    except Exception as exc:
        print(json.dumps({"outcome": "diagnostic_error", **grounding_error_details(exc)}))
        return 2
    expected = {"A": "no_sources", "B": "sources_returned", "C": "sources_returned"}
    return int(any(result["outcome"] != expected[result["variant"]] for result in results))


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--query", choices=(*QUERIES, "all"), default="news")
    parser.add_argument("--variant", choices=VARIANTS)
    parser.add_argument("--live", action="store_true")
    parser.add_argument("--max-requests", type=int, default=0)
    parser.add_argument("--alternative-model", help="One explicitly verified Search-capable model.")
    args = parser.parse_args()
    if args.alternative_model and (not args.live or args.query in {"all", "control"}
                                   or args.variant not in {"B", "C"}):
        parser.error("An alternative model requires --live, one freshness query and one grounded variant.")
    if args.query == "control" and args.variant not in {None, "A"}:
        parser.error("The control uses only non-grounded variant A.")
    cases = [(query, variant) for query in (QUERIES if args.query == "all" else [args.query])
             for variant in ([args.variant] if args.variant else VARIANTS)
             if query != "control" or variant == "A"]
    if args.live and not len(cases) <= args.max_requests <= MAX_CALLS:
        parser.error("Set --max-requests to cover the selected matrix (maximum 13).")
    return asyncio.run(run(args, cases))


if __name__ == "__main__":
    raise SystemExit(main())
