"""Development-only Gemini structured-output compatibility probe.

Run from backend/: python scripts/gemini_structured_output_probe.py
This sends live Gemini requests and consumes API quota. It never prints prompts,
responses, exception messages, configuration values, or credentials.
"""

from __future__ import annotations

import asyncio
import argparse
import platform
import sys
from dataclasses import dataclass
from importlib.metadata import version
from pathlib import Path
from typing import Any, Literal

from google import genai
from google.genai import types
from pydantic import BaseModel, ConfigDict

ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from app.core.config import settings
from app.prompts.askhype import PRESENTATION_PLANNING_INSTRUCTION
from app.providers.gemini import GeminiProvider, prepare_gemini_presentation_schema
from app.schemas.documents import DocumentMetadata, ExtractedDocument
from app.services.document_extraction import extract_document

PRODUCTION_PROMPT = "Napravi prezentaciju od 5 slajdova za pregled beta plana."
PRODUCTION_SLIDE_COUNT = 5
DOCUMENT_MIME_TYPES = {
    ".pdf": "application/pdf",
    ".docx": "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    ".xlsx": "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
    ".csv": "text/csv",
}


class MinimalOk(BaseModel):
    model_config = ConfigDict(extra="forbid")
    ok: bool


class MinimalTyped(BaseModel):
    model_config = ConfigDict(extra="forbid")
    type: Literal["title", "bullets"]
    title: str


MINIMAL_OK_SCHEMA = {
    "type": "object",
    "properties": {"ok": {"type": "boolean"}},
    "required": ["ok"],
}
MINIMAL_TYPED_SCHEMA = {
    "type": "object",
    "properties": {
        "type": {"type": "string", "enum": ["title", "bullets"]},
        "title": {"type": "string"},
    },
    "required": ["type", "title"],
}
STRING_ARRAY_SCHEMA = {
    "type": "object",
    "properties": {"items": {"type": "array", "items": {"type": "string"}}},
    "required": ["items"],
}
OBJECT_ARRAY_SCHEMA = {
    "type": "object",
    "properties": {
        "items": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {"title": {"type": "string"}},
                "required": ["title"],
            },
        }
    },
    "required": ["items"],
}
MINIMAL_PRESENTATION_SCHEMA = {
    "type": "object",
    "properties": {
        "title": {"type": "string"},
        "slides": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "type": {
                        "type": "string",
                        "enum": ["title", "bullets", "section", "key_metrics", "table", "conclusion"],
                    },
                    "title": {"type": "string"},
                },
                "required": ["type", "title"],
            },
        },
    },
    "required": ["title", "slides"],
}


@dataclass(frozen=True)
class Probe:
    name: str
    prompt: str
    config: types.GenerateContentConfig
    schema_probe: bool = False


@dataclass(frozen=True)
class ProbeResult:
    name: str
    passed: bool
    status: int | str
    category: str


class _CapturedResponse:
    parsed = {
        "plan": {
            "title": "Diagnostic",
            "subtitle": "",
            "slides": [
                {
                    "type": slide_type,
                    "title": f"Slide {index}",
                    "subtitle": "",
                    "bullets": ["Diagnostic"] if slide_type in {"bullets", "conclusion"} else [],
                    "metrics": [],
                    "headers": [],
                    "rows": [],
                }
                for index, slide_type in enumerate(
                    ["title", "section", "bullets", "section", "conclusion"], start=1
                )
            ],
        }
    }
    text = None


class _CaptureModels:
    def __init__(self) -> None:
        self.kwargs: dict[str, Any] | None = None

    async def generate_content(self, **kwargs: Any) -> _CapturedResponse:
        self.kwargs = kwargs
        return _CapturedResponse()


class _CaptureClient:
    def __init__(self) -> None:
        models = _CaptureModels()
        self.models = models
        self.aio = type("CaptureAio", (), {"models": models})()


def _json_config(**kwargs: Any) -> types.GenerateContentConfig:
    return types.GenerateContentConfig(response_mime_type="application/json", **kwargs)


def _probes() -> list[Probe]:
    return [
        Probe("A plain generation", "Return only the word OK.", types.GenerateContentConfig()),
        Probe("B JSON MIME", 'Return JSON: {"ok": true}.', _json_config()),
        Probe("C minimal response_json_schema", 'Return {"ok": true}.', _json_config(response_json_schema=MINIMAL_OK_SCHEMA), True),
        Probe("C2 minimal response_schema", 'Return {"ok": true}.', _json_config(response_schema=MinimalOk), True),
        Probe("D enum response_json_schema", "Return a title object.", _json_config(response_json_schema=MINIMAL_TYPED_SCHEMA), True),
        Probe("D2 enum response_schema", "Return a title object.", _json_config(response_schema=MinimalTyped), True),
        Probe("E string array", "Return two short items.", _json_config(response_json_schema=STRING_ARRAY_SCHEMA), True),
        Probe("F object array", "Return two titled items.", _json_config(response_json_schema=OBJECT_ARRAY_SCHEMA), True),
        Probe("G minimal presentation", "Return a three-slide presentation plan.", _json_config(response_json_schema=MINIMAL_PRESENTATION_SCHEMA), True),
        Probe("H full presentation", "Return a three-slide presentation plan. Include every required field.", _json_config(response_json_schema=prepare_gemini_presentation_schema()), True),
    ]


def _error_details(exc: Exception) -> tuple[int | str, str]:
    cause: BaseException | None = exc
    while cause is not None:
        status = getattr(cause, "status_code", None) or getattr(cause, "code", None)
        if status is not None:
            exc = cause if isinstance(cause, Exception) else exc
            break
        cause = cause.__cause__
    if isinstance(exc, TimeoutError):
        return "n/a", "timeout"
    status = getattr(exc, "status_code", None) or getattr(exc, "code", None) or "n/a"
    marker = " ".join(str(value) for value in (getattr(exc, "status", None), getattr(exc, "message", None), exc) if value).casefold()
    if status == 400 and "invalid_argument" in marker:
        return status, "invalid_argument"
    if isinstance(status, int) and 400 <= status < 500:
        return status, "client_error"
    if isinstance(status, int) and status >= 500:
        return status, "provider_error"
    return status, "sdk_error"


async def _capture_production_request(document: ExtractedDocument | None) -> dict[str, Any]:
    capture = _CaptureClient()
    provider = GeminiProvider(app_settings=settings, client=capture)
    await provider.generate_presentation_plan(PRODUCTION_PROMPT, PRODUCTION_SLIDE_COUNT, document)
    assert capture.models.kwargs is not None
    return capture.models.kwargs


async def _run_exact_sdk_probe(
    client: genai.Client,
    name: str,
    request_kwargs: dict[str, Any],
) -> ProbeResult:
    try:
        async with asyncio.timeout(settings.gemini_timeout_seconds):
            await client.aio.models.generate_content(**request_kwargs)
        return ProbeResult(name, True, 200, "ok")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        status, category = _error_details(exc)
        return ProbeResult(name, False, status, category)


async def _run_provider_probe(
    client: genai.Client,
    document: ExtractedDocument,
) -> ProbeResult:
    provider = GeminiProvider(app_settings=settings, client=client)
    try:
        await provider.generate_presentation_plan(PRODUCTION_PROMPT, PRODUCTION_SLIDE_COUNT, document)
        return ProbeResult("K4 actual GeminiProvider method", True, 200, "ok")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        status, category = _error_details(exc)
        return ProbeResult("K4 actual GeminiProvider method", False, status, category)


def _load_document(path: Path) -> ExtractedDocument:
    suffix = path.suffix.casefold()
    mime = DOCUMENT_MIME_TYPES.get(suffix)
    if mime is None:
        raise ValueError("unsupported_document_type")
    return extract_document(path.read_bytes(), path.name, mime)


def _document_with_text(document: ExtractedDocument, text: str) -> ExtractedDocument:
    return ExtractedDocument(
        filename=document.filename,
        file_type=document.file_type,
        text=text,
        metadata=document.metadata.model_copy(update={"extracted_characters": len(text)}),
        warnings=document.warnings,
    )


def _print_environment(document: ExtractedDocument | None) -> None:
    print(f"Python version: {platform.python_version()}")
    print(f"google-genai version: {version('google-genai')}")
    print(f"Configured max_output_tokens: {settings.gemini_max_output_tokens}")
    print(f"Configured timeout seconds: {settings.gemini_timeout_seconds}")
    print(f"System instruction characters: {len(PRESENTATION_PLANNING_INSTRUCTION)}")
    print(f"Production prompt characters: {len(PRODUCTION_PROMPT)}")
    print(f"Extracted document characters: {len(document.text) if document else 0}")


async def _production_probes(client: genai.Client, document: ExtractedDocument | None) -> None:
    prompt_request = await _capture_production_request(None)
    print(f"K1 final contents characters: {len(str(prompt_request['contents']))}")
    _print_result(await _run_exact_sdk_probe(client, "K1 prompt-only exact production config", prompt_request))

    tiny = ExtractedDocument(
        filename="synthetic.pdf",
        file_type="pdf",
        text="Beta test počinje 18. novembra 2026.",
        metadata=DocumentMetadata(extracted_characters=38),
    )
    tiny_request = await _capture_production_request(tiny)
    print(f"K2 document characters: {len(tiny.text)} bytes={len(tiny.text.encode('utf-8'))} contents={len(str(tiny_request['contents']))}")
    _print_result(await _run_exact_sdk_probe(client, "K2 tiny synthetic document", tiny_request))

    if document is None:
        print("K3 actual document raw SDK                SKIP status=n/a category=document_not_supplied")
        print("K4 actual GeminiProvider method           SKIP status=n/a category=document_not_supplied")
        return

    full_request = await _capture_production_request(document)
    print(f"K3 document characters: {len(document.text)} bytes={len(document.text.encode('utf-8'))} contents={len(str(full_request['contents']))}")
    k3 = await _run_exact_sdk_probe(client, "K3 actual document raw SDK", full_request)
    _print_result(k3)
    k4 = await _run_provider_probe(client, document)
    _print_result(k4)
    print(f"K3/K4 same outcome: {k3.passed == k4.passed}")

    if k3.passed:
        print("First reproducible document-length failure: none")
        return
    prefix_results: list[tuple[int, ProbeResult]] = []
    lengths = sorted({min(length, len(document.text)) for length in [500, 1000, 2000, 4000, 8000, 16000, len(document.text)]})
    for length in lengths:
        prefix = _document_with_text(document, document.text[:length])
        request = await _capture_production_request(prefix)
        result = await _run_exact_sdk_probe(client, f"L prefix {length} chars", request)
        prefix_results.append((length, result))
        print(f"{length:>6} chars bytes={len(prefix.text.encode('utf-8')):<7} {'PASS' if result.passed else 'FAIL'} status={result.status} category={result.category}")
    first_failed = next((length for length, result in prefix_results if not result.passed), None)
    print(f"First reproducible document-length failure: {first_failed or 'none'}")
    if any(result.passed for _, result in prefix_results) and not prefix_results[-1][1].passed:
        synthetic_text = "A" * len(document.text)
        synthetic = _document_with_text(document, synthetic_text)
        request = await _capture_production_request(synthetic)
        result = await _run_exact_sdk_probe(client, "M same-length synthetic content", request)
        print(f"Synthetic chars={len(synthetic_text)} bytes={len(synthetic_text.encode('utf-8'))} {'PASS' if result.passed else 'FAIL'} status={result.status} category={result.category}")


async def _run_probe(client: genai.Client, model: str, probe: Probe) -> ProbeResult:
    try:
        async with asyncio.timeout(settings.gemini_timeout_seconds):
            await client.aio.models.generate_content(model=model, contents=probe.prompt, config=probe.config)
        return ProbeResult(probe.name, True, 200, "ok")
    except asyncio.CancelledError:
        raise
    except Exception as exc:
        status, category = _error_details(exc)
        return ProbeResult(probe.name, False, status, category)


def _print_result(result: ProbeResult) -> None:
    outcome = "PASS" if result.passed else "FAIL"
    print(f"{result.name:<42} {outcome} status={result.status} category={result.category}")


def _interaction_probes(schema_keyword: str, schema: Any) -> list[Probe]:
    prompt = 'Return {"ok": true}.'
    schema_config = {schema_keyword: schema}
    return [
        Probe("I1 failing schema minimal config", prompt, _json_config(**schema_config), True),
        Probe("I2 + system_instruction", prompt, _json_config(**schema_config, system_instruction="Return valid JSON only."), True),
        Probe("I3 + temperature", prompt, _json_config(**schema_config, temperature=settings.gemini_temperature), True),
        Probe("I4 + max_output_tokens", prompt, _json_config(**schema_config, max_output_tokens=settings.gemini_max_output_tokens), True),
    ]


def _schema_for_probe(name: str) -> dict[str, Any] | None:
    return {
        "C minimal response_json_schema": MINIMAL_OK_SCHEMA,
        "D enum response_json_schema": MINIMAL_TYPED_SCHEMA,
        "E string array": STRING_ARRAY_SCHEMA,
        "F object array": OBJECT_ARRAY_SCHEMA,
        "G minimal presentation": MINIMAL_PRESENTATION_SCHEMA,
        "H full presentation": prepare_gemini_presentation_schema(),
    }.get(name)


def _comparison_model(client: genai.Client, current: str) -> str | None:
    try:
        for model in client.models.list():
            name = str(getattr(model, "name", ""))
            short_name = name.removeprefix("models/")
            actions = getattr(model, "supported_actions", None) or getattr(model, "supported_generation_methods", None) or []
            if short_name and short_name != current.removeprefix("models/") and "gemini" in short_name.casefold():
                if not actions or any(str(action).casefold() == "generatecontent" for action in actions):
                    return short_name
    except Exception:
        return None
    return None


def _parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Probe Gemini structured-output compatibility.")
    parser.add_argument("--document", type=Path, help="Optional local PDF, DOCX, XLSX or CSV fixture.")
    parser.add_argument(
        "--production-only",
        action="store_true",
        help="Run only exact production K probes (and document bisect when needed).",
    )
    return parser.parse_args()


async def main() -> int:
    args = _parse_args()
    if settings.ai_provider != "gemini" or not settings.gemini_api_key:
        print("CONFIG FAIL status=n/a category=missing_gemini_configuration")
        return 2
    document: ExtractedDocument | None = None
    if args.document:
        try:
            document = _load_document(args.document.resolve())
        except FileNotFoundError:
            print("DOCUMENT FAIL status=n/a category=file_not_found")
            return 2
        except Exception as exc:
            _, category = _error_details(exc)
            print(f"DOCUMENT FAIL status=n/a category={category}")
            return 2
    current_model = settings.gemini_model
    print(f"Current model: {current_model}")
    _print_environment(document)
    client = genai.Client(api_key=settings.gemini_api_key.get_secret_value())
    if args.production_only:
        await _production_probes(client, document)
        return 0
    results: list[ProbeResult] = []
    for probe in _probes():
        result = await _run_probe(client, current_model, probe)
        results.append(result)
        _print_result(result)

    first_failure = next((result for result in results if not result.passed), None)
    if first_failure:
        print(f"First exact failing probe: {first_failure.name}")
        if first_failure.name == "C2 minimal response_schema":
            interaction = ("response_schema", MinimalOk)
        elif first_failure.name == "D2 enum response_schema":
            interaction = ("response_schema", MinimalTyped)
        else:
            schema = _schema_for_probe(first_failure.name)
            interaction = ("response_json_schema", schema) if schema else None
        if interaction:
            for probe in _interaction_probes(*interaction):
                _print_result(await _run_probe(client, current_model, probe))
    else:
        print("First exact failing probe: none")

    minimal = next(result for result in results if result.name == "C minimal response_json_schema")
    if minimal.passed:
        prompt_probe = Probe(
            "J presentation instruction + minimal schema",
            'Return {"ok": true}.',
            _json_config(response_json_schema=MINIMAL_OK_SCHEMA, system_instruction=PRESENTATION_PLANNING_INSTRUCTION),
            True,
        )
        _print_result(await _run_probe(client, current_model, prompt_probe))
    else:
        comparison = _comparison_model(client, current_model)
        print(f"Comparison model: {comparison or 'unavailable'}")
        if comparison:
            comparison_probe = Probe("K comparison model minimal schema", 'Return {"ok": true}.', _json_config(response_json_schema=MINIMAL_OK_SCHEMA), True)
            _print_result(await _run_probe(client, comparison, comparison_probe))
    await _production_probes(client, document)
    return 0


if __name__ == "__main__":
    raise SystemExit(asyncio.run(main()))
