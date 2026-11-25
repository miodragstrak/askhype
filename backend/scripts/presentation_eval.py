"""Local planner benchmark. Default mode validates briefs without contacting Gemini."""

import argparse
import asyncio
import json
from pathlib import Path
from time import monotonic
import traceback
from types import SimpleNamespace

from app.core.config import settings
from app.providers.exceptions import (
    AIProviderConfigurationError,
    AIProviderTimeoutError,
    AIPresentationOutputExhaustedError,
    AIPresentationPlanError,
)
from app.providers.gemini import GeminiProvider, gemini_finish_reasons, gemini_http_status, presentation_thinking_config
from app.schemas.documents import DocumentMetadata, ExtractedDocument
from app.schemas.presentations import PresentationPlan
from app.services.document_extraction import extract_document
from app.services.presentation_diagnostics import PresentationDiagnostics, PresentationRuleError
from app.services.presentation_generation import apply_illustrations, build_presentation, requested_slide_count
from app.services.presentation_illustrations import resolve_gemini_illustrations

HERE = Path(__file__).resolve().parent
MODELS = ("gemini-3.5-flash-lite", "gemini-3.8-flash")


class Meter:
    def __init__(self, models, timeout_seconds=None):
        self.models = models
        self.timeout_seconds = timeout_seconds
        self.attempts = []

    async def generate_content(self, **kwargs):
        config = kwargs["config"]
        thinking = config.thinking_config
        attempt = {
            "model": kwargs["model"], "timeout_seconds": self.timeout_seconds,
            "thinking_config": thinking.model_dump(mode="json", exclude_none=True) if thinking else None,
            "http_status": None, "finish_reason": None, "output_exhausted": None,
            "prompt_token_count": None, "candidates_token_count": None, "thoughts_token_count": None,
            "total_token_count": None,
        }
        started = monotonic()
        self.attempts.append(attempt)
        try:
            response = await self.models.generate_content(**kwargs)
            usage = getattr(response, "usage_metadata", None)
            for key in ("prompt_token_count", "candidates_token_count", "thoughts_token_count", "total_token_count"):
                attempt[key] = getattr(usage, key, None)
            attempt["status"] = "response_received"
            # The installed SDK exposes headers and body on a successful response, not the status.
            attempt["finish_reason"] = next(iter(gemini_finish_reasons(response)), None)
            if attempt["finish_reason"] is not None:
                attempt["output_exhausted"] = attempt["finish_reason"] == "MAX_TOKENS"
            return response
        except (Exception, asyncio.CancelledError) as exc:
            attempt["status"] = type(exc).__name__
            attempt["http_status"] = gemini_http_status(exc)
            if attempt["http_status"] == 504 or getattr(exc, "status", None) == "DEADLINE_EXCEEDED":
                attempt["failure_category"] = "provider_deadline"
            raise
        finally:
            attempt["seconds"] = round(monotonic() - started, 3)


def _write_json(path, value):
    path.write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding="utf-8")


def _document_snapshot(document):
    if document is None:
        return None
    return {
        "filename": document.filename, "file_type": document.file_type, "text": document.text,
        "metadata": document.metadata.model_dump(mode="json"), "warnings": list(document.warnings),
    }


def _restore_document(data):
    if data is None:
        return None
    return ExtractedDocument(
        filename=data["filename"], file_type=data["file_type"], text=data["text"],
        metadata=DocumentMetadata.model_validate(data["metadata"]), warnings=tuple(data["warnings"]),
    )


def _failure(exc, trace):
    root = exc
    while root.__cause__ is not None:
        root = root.__cause__
        if isinstance(root, PresentationRuleError):
            break
    return {
        "failure_stage": trace.stage,
        "exception_class": type(exc).__name__,
        "cause_class": type(root).__name__,
        "exception_message": str(root) if isinstance(root, PresentationRuleError)
        else "Unexpected failure; see sanitized traceback locations.",
        "failed_validation_rule": root.rule if isinstance(root, PresentationRuleError) else None,
        "slide_index": trace.slide_index,
        "requested_layout": trace.requested_layout,
        "selected_layout": trace.selected_layout,
    }


async def evaluate(case, document, output, load_plan, *, mode, planner_config, attempts=None, resolve_images=None,
                   image_attempts=None):
    trace = PresentationDiagnostics()
    started = monotonic()
    record = {"brief": case["id"], "mode": mode, **planner_config, "attempts": attempts if attempts is not None else []}
    if image_attempts is not None:
        record["image_attempts"] = image_attempts
    try:
        with trace.measure("save_context"):
            _write_json(output / "context.json", {
                "version": 1, "brief": case["id"], "prompt": case["prompt"],
                "document": _document_snapshot(document), "planner_config": planner_config,
            })
        with trace.measure("planning" if mode == "live" else "load_replay_plan"):
            plan = await load_plan()
        record["schema_valid"] = True
        with trace.measure("save_plan"):
            (output / "plan.json").write_text(plan.model_dump_json(indent=2), encoding="utf-8")
        result = build_presentation(case["prompt"], plan, document, trace)
        if resolve_images is not None:
            with trace.measure("illustrations"):
                images = await resolve_images(plan, trace.resolved_layouts)
                native = result
                result = apply_illustrations(result, plan, document, images)
                if result is native:
                    for attempt in image_attempts or []:
                        if attempt["status"] == "resolved":
                            attempt.update(status="fallback", failure_category="image_layout_render",
                                           native_fallback=True)
                record["resolved_illustrations"] = sorted(images) if result is not native else []
                record["used_native_deck"] = result is native
        with trace.measure("write_pptx"):
            (output / "deck.pptx").write_bytes(result.content)
        record["status"] = "rendered"
    except Exception as exc:
        record.setdefault("schema_valid", False if isinstance(exc, AIPresentationPlanError)
                          or trace.stage == "load_replay_plan" else None)
        record["status"] = type(exc).__name__
        record.update(_failure(exc, trace))
        if isinstance(exc, AIPresentationPlanError) and getattr(exc, "validation_issues", None):
            record["validation_issues"] = exc.validation_issues
        if isinstance(exc, AIPresentationOutputExhaustedError):
            record["failed_validation_rule"] = "output_exhausted"
            record["exception_message"] = "Gemini reported MAX_TOKENS before completing the plan."
        elif isinstance(exc, AIProviderTimeoutError):
            provider_deadline = bool(attempts and attempts[-1].get("failure_category") == "provider_deadline")
            record["failure_category"] = "provider_deadline" if provider_deadline else "local_or_transport_timeout"
            record["exception_message"] = (
                "Gemini returned a provider deadline error." if provider_deadline
                else "The presentation provider call exceeded a local or transport deadline."
            )
        # Keep locations only. Exception bodies, source lines, and locals may
        # contain provider content or credentials.
        frames = traceback.extract_tb(exc.__traceback__)
        if exc.__cause__ is not None:
            frames += traceback.extract_tb(exc.__cause__.__traceback__)
        (output / "traceback.txt").write_text("\n".join(
            f"{Path(frame.filename).name}:{frame.lineno} in {frame.name}" for frame in frames
        ) + "\n", encoding="utf-8")
    for bucket in ("planning", "validation", "rendering"):
        record[f"{bucket}_seconds"] = round(trace.durations.get(bucket, 0), 6)
    if resolve_images is not None:
        record["illustration_seconds"] = round(trace.durations.get("illustrations", 0), 6)
    record["layout_fallbacks"] = trace.layout_fallbacks
    record["layout_fallback_count"] = len(trace.layout_fallbacks)
    record["seconds"] = round(monotonic() - started, 6)
    _write_json(output / "metrics.json", record)
    print(json.dumps(record, ensure_ascii=False))
    return record["status"] == "rendered"


async def run(case, document, args):
    config = settings.model_copy(update={
        "gemini_presentation_model": args.model,
        "gemini_presentation_max_output_tokens": args.output_tokens,
        "gemini_fallback_model": None,
        "gemini_presentation_timeout_seconds": args.timeout_seconds or settings.gemini_presentation_timeout_seconds,
        "gemini_presentation_thinking_level": args.thinking_level or settings.gemini_presentation_thinking_level,
        "presentation_illustration_mode": args.illustration_mode,
    })
    deadline = config.gemini_presentation_timeout_seconds or config.gemini_timeout_seconds
    provider = GeminiProvider(config)
    client = provider._client.aio
    try:
        meter = Meter(client.models, deadline)
        provider._client = SimpleNamespace(aio=SimpleNamespace(models=meter))
        async def load_plan():
            return await provider.generate_presentation_plan(
                case["prompt"], requested_slide_count(case["prompt"])[0], document,
            )
        image_attempts = []

        async def resolve_images(plan, layouts):
            return await resolve_gemini_illustrations(plan, config, layouts, attempts=image_attempts)

        return await evaluate(case, document, args.output, load_plan, mode="live", attempts=meter.attempts,
                              resolve_images=resolve_images, image_attempts=image_attempts,
                              planner_config={"model": args.model, "output_cap": args.output_tokens,
                                              "timeout_seconds": deadline,
                                              "thinking_level": config.gemini_presentation_thinking_level,
                                              "illustration_mode": args.illustration_mode,
                                              "image_model": config.gemini_presentation_image_model,
                                              "temperature": config.gemini_temperature})
    finally:
        await client.aclose()


def main():
    cases = json.loads((HERE / "presentation_eval_briefs.json").read_text(encoding="utf-8"))
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--brief", choices=[case["id"] for case in cases])
    parser.add_argument("--model", choices=MODELS)
    parser.add_argument("--output", type=Path)
    parser.add_argument("--output-tokens", type=int, choices=(4096, 6144, 8192), default=4096)
    parser.add_argument("--timeout-seconds", type=int, choices=range(1, 181), metavar="1–180")
    parser.add_argument("--thinking-level", choices=("minimal", "low", "medium", "high"))
    parser.add_argument("--illustration-mode", choices=("OFF", "COVER", "ENHANCED"), default="OFF")
    parser.add_argument("--approved-live", action="store_true")
    parser.add_argument("--replay-plan", type=Path)
    parser.add_argument("--replay-context", type=Path)
    parser.add_argument("--approved-image-only", action="store_true",
                        help="Use a saved plan and request illustrations without starting the planner.")
    args = parser.parse_args()
    if args.illustration_mode != "OFF" and not (args.approved_live or args.approved_image_only):
        parser.error("Provider illustrations require --approved-live or --approved-image-only.")
    if args.replay_context and not args.replay_plan:
        parser.error("--replay-context requires --replay-plan.")
    if args.approved_image_only and (not args.replay_plan or args.approved_live or args.model):
        parser.error("Image-only mode requires a saved plan and cannot select or invoke a planner model.")
    if args.replay_plan and (args.approved_live or not args.output):
        parser.error("Replay requires a new output directory and cannot be combined with live mode.")
    if args.approved_live and not (args.brief and args.model and args.output):
        parser.error("Live mode requires one brief, a model, and a new output directory.")
    if args.approved_live:
        try:
            presentation_thinking_config(
                args.model, args.thinking_level or settings.gemini_presentation_thinking_level,
            )
        except AIProviderConfigurationError as exc:
            parser.error(str(exc))
    snapshot = None
    if args.replay_plan:
        context_path = args.replay_context or args.replay_plan.with_name("context.json")
        if args.replay_context or context_path.is_file():
            snapshot = json.loads(context_path.read_text(encoding="utf-8"))
            if snapshot["version"] != 1 or (args.brief and args.brief != snapshot["brief"]):
                parser.error("Replay context version or brief mismatch.")
            args.brief = snapshot["brief"]
        elif not args.brief:
            parser.error("Replay requires a saved context or --brief.")
        if args.approved_image_only and snapshot is None:
            parser.error("Image-only mode requires the saved context.")
    for case in cases:
        if args.brief and case["id"] != args.brief:
            continue
        document = None
        if snapshot is not None:
            case = {"id": snapshot["brief"], "prompt": snapshot["prompt"]}
            document = _restore_document(snapshot["document"])
        elif name := case.get("document"):
            document = extract_document((HERE / name).read_bytes(), name, "text/csv")
        print(f'{case["id"]}: {requested_slide_count(case["prompt"])[0]} slides, source={bool(document)}')
        if args.approved_live:
            args.output.mkdir(parents=True, exist_ok=False)
            return 0 if asyncio.run(run(case, document, args)) else 1
        if args.replay_plan:
            args.output.mkdir(parents=True, exist_ok=False)

            async def load_replay():
                return PresentationPlan.model_validate_json(args.replay_plan.read_text(encoding="utf-8"))

            allowed = ("model", "output_cap", "timeout_seconds", "temperature", "thinking_level")
            saved_settings = (snapshot or {}).get("planner_config", {})
            config = {key: saved_settings[key] for key in allowed if key in saved_settings}
            if args.approved_image_only:
                image_attempts = []
                mode = args.illustration_mode if args.illustration_mode != "OFF" else "COVER"
                image_config = settings.model_copy(update={"presentation_illustration_mode": mode})
                config.update(
                    illustration_mode=mode,
                    image_model=image_config.gemini_presentation_image_model,
                    image_timeout_seconds=image_config.presentation_illustration_timeout_seconds,
                )

                async def resolve_images(plan, layouts):
                    return await resolve_gemini_illustrations(plan, image_config, layouts, attempts=image_attempts)

                return 0 if asyncio.run(evaluate(case, document, args.output, load_replay,
                                                 mode="image-only", planner_config=config,
                                                 resolve_images=resolve_images,
                                                 image_attempts=image_attempts)) else 1
            return 0 if asyncio.run(evaluate(case, document, args.output, load_replay,
                                             mode="replay", planner_config=config)) else 1
    if args.replay_plan:
        parser.error("Unknown replay brief.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
