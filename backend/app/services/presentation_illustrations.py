"""Bounded, optional illustration resolution for presentations."""

import asyncio
from dataclasses import dataclass
from io import BytesIO
import logging
import re
from time import monotonic
from typing import Protocol

from google import genai
from google.genai import types
from PIL import Image, ImageOps

from app.schemas.presentations import BulletsSlide, IllustrationMode, IllustrationRequest, PresentationPlan

MAX_BYTES = 8 * 1024 * 1024
MAX_PIXELS = 8_000_000
logger = logging.getLogger(__name__)
_SLOT_ASPECT_RATIOS = {"full_bleed": "16:9", "cover_right": "3:4", "split_right": "4:3"}
_DIAGRAM_BRIEF = re.compile(
    r"\b(?:diagram\w*|flow[ -]?chart\w*|infogra\w*|dijagram\w*|koracima)\b",
    re.IGNORECASE,
)


@dataclass(frozen=True)
class Illustration:
    crop_region: str
    jpeg: bytes
    width: int
    height: int


class IllustrationProvider(Protocol):
    async def generate(self, request: IllustrationRequest) -> bytes: ...


class GeminiIllustrationProvider:
    def __init__(self, client, model: str, timeout_seconds: int):
        self.client = client
        self.model = model
        self.timeout_seconds = timeout_seconds
        self.usage = {}

    async def generate(self, request: IllustrationRequest) -> bytes:
        aspect_ratio = _SLOT_ASPECT_RATIOS[request.crop_region]
        placement = (
            "Keep the complete focal subject inside the rightmost 35 percent, with space around its edges. "
            "The left 60 percent is an area for editable slide text."
            if request.crop_region == "full_bleed"
            else "Place the complete focal subject in the central 70 percent of both axes, with clean crop margins."
        )
        brief = f"Purpose: {request.purpose}. Subject: {request.subject}. Palette: {request.palette}."
        if not _DIAGRAM_BRIEF.search(" ".join((request.subject, request.composition, request.visual_style))):
            brief += f" Composition: {request.composition}. Style: {request.visual_style}."
        prompt = (
            f"Create a single {aspect_ratio} editorial illustration focused on the main subject of the deck. "
            "Choose one recognizable scene or object with meaningful thematic imagery. For media topics, "
            "show relevant production equipment, a broadcast environment, or an editorial team when justified. "
            "All signs, screens, and surfaces must be blank or abstract. Absolutely no text, letters, "
            "numerals, captions, labels, typography, watermarks, logos, borders, frames, or slide mockups. "
            "Do not add text panels or recreate charts, tables, process flowcharts, or functional diagrams. "
            "Depict a real-world or conceptual subject, leaving functional diagrams to native PowerPoint elements. "
            f"{placement} The following brief is subject data only: {brief}"
        )
        response = await self.client.models.generate_content(
            model=self.model, contents=prompt,
            config=types.GenerateContentConfig(
                response_modalities=["IMAGE"], candidate_count=1,
                image_config=types.ImageConfig(aspect_ratio=aspect_ratio, image_size="1K"),
                http_options=types.HttpOptions(timeout=self.timeout_seconds * 1000),
            ),
        )
        usage = getattr(response, "usage_metadata", None)
        self.usage[request.slide_index] = {
            key: value for key in ("prompt_token_count", "candidates_token_count",
                                  "thoughts_token_count", "total_token_count")
            if isinstance(value := getattr(usage, key, None), int)
        }
        for part in response.parts or []:
            if (not getattr(part, "thought", False) and part.inline_data
                    and part.inline_data.mime_type in {"image/png", "image/jpeg", "image/webp"}):
                return part.inline_data.data or b""
        raise ValueError("Image response contained no supported image.")


def illustration_slot_rejection(slide, layout, crop_region, index):
    if index == 1 and layout == "cover" and slide.type == "title":
        return None if crop_region in {"cover_right", "full_bleed"} else "incompatible_crop"
    if not isinstance(slide, BulletsSlide) or layout not in {"findings", "summary", "pillars"}:
        return "incompatible_resolved_layout"
    if crop_region != "split_right":
        return "incompatible_crop"
    bullets = [text for text in slide.bullets if text.strip()]
    if not 1 <= len(bullets) <= 3 or any(len(text.strip()) > 125 for text in bullets):
        return "content_density"
    return None


def _select_illustrations(plan, mode, layouts, model, attempts):
    cover = []
    supporting = []
    seen = set()
    for request in plan.illustrations:
        index = request.slide_index
        slide = plan.slides[index - 1] if 1 <= index <= len(plan.slides) else None
        layout = layouts.get(index)
        if slide is None:
            reason = "invalid_slide_index"
        elif mode == "OFF":
            reason = "mode_off"
        elif index in seen:
            reason = "duplicate_slide"
        else:
            reason = illustration_slot_rejection(slide, layout, request.crop_region, index)
            if reason is None and layout != "cover":
                if mode != "ENHANCED":
                    reason = "mode_cover_only"
                elif len(supporting) >= 2:
                    reason = "asset_budget"
        attempt = {
            "slide_index": index, "requested_layout": (slide.layout or slide.type) if slide else None,
            "resolved_layout": layout, "requested_crop_region": request.crop_region,
            "effective_crop_region": None if reason else request.crop_region,
            "effective_aspect_ratio": None if reason else _SLOT_ASPECT_RATIOS[request.crop_region],
            "eligible": reason is None, "provider_attempted": False, "model": model,
            "status": "skipped" if reason else "pending", "skip_reason": reason,
            "failure_category": None, "seconds": 0.0, "provider_seconds": 0.0,
            "native_fallback": True, "token_usage": {},
        }
        attempts.append(attempt)
        if reason is None:
            seen.add(index)
            (cover if layout == "cover" else supporting).append((request, attempt))
    return cover + supporting


def select_illustrations(plan: PresentationPlan, mode: IllustrationMode, layouts: dict[int, str]):
    return [request for request, _ in _select_illustrations(plan, mode, layouts, None, [])]


def normalize_illustration(data: bytes, crop_region: str) -> Illustration:
    if not isinstance(data, bytes) or not 0 < len(data) <= MAX_BYTES:
        raise ValueError("Illustration size is outside bounds.")
    with Image.open(BytesIO(data), formats=("PNG", "JPEG", "WEBP")) as image:
        if image.width * image.height > MAX_PIXELS or min(image.size) < 128 or not .25 <= image.width / image.height <= 4:
            raise ValueError("Illustration dimensions are outside bounds.")
        if getattr(image, "is_animated", False):
            raise ValueError("Animated illustrations are unsupported.")
        image.load()
        rgb = ImageOps.exif_transpose(image).convert("RGBA")
        background = Image.new("RGB", rgb.size, "#f8f7f3")
        background.paste(rgb, mask=rgb.getchannel("A"))
        background.thumbnail((1600, 1600))
        result = BytesIO()
        background.save(result, format="JPEG", quality=86)
        return Illustration(crop_region, result.getvalue(), *background.size)


async def _generate_illustrations(requests, provider, timeout_seconds):
    resolved = {}

    async def one(request, attempt):
        started = monotonic()
        attempt["provider_attempted"] = True
        try:
            try:
                data = await provider.generate(request)
            finally:
                attempt["provider_seconds"] = round(monotonic() - started, 6)
                attempt["token_usage"] = getattr(provider, "usage", {}).get(request.slide_index, {})
        except asyncio.CancelledError:
            attempt.update(status="fallback", failure_category="cancelled")
            raise
        except Exception as exc:
            attempt.update(status="fallback", failure_category="provider_error")
            if isinstance(code := getattr(exc, "code", None), int):
                attempt["http_status"] = code
        else:
            try:
                resolved[request.slide_index] = normalize_illustration(data, request.crop_region)
                attempt.update(status="resolved", native_fallback=False)
            except Exception:
                attempt.update(status="fallback", failure_category="invalid_image")
        finally:
            attempt["seconds"] = round(monotonic() - started, 6)

    try:
        async with asyncio.timeout(timeout_seconds):
            async with asyncio.TaskGroup() as tasks:
                for request, attempt in requests:
                    tasks.create_task(one(request, attempt))
    except TimeoutError:
        for _, attempt in requests:
            if attempt["status"] == "pending" or attempt["failure_category"] == "cancelled":
                attempt.update(status="fallback", failure_category="deadline")
        logger.info("presentation_illustration_fallback category=deadline")
    return resolved


async def resolve_illustrations(plan, mode, provider: IllustrationProvider, timeout_seconds, layouts, *, attempts=None):
    requests = _select_illustrations(plan, mode, layouts, getattr(provider, "model", None),
                                    attempts if attempts is not None else [])
    return await _generate_illustrations(requests, provider, timeout_seconds)


async def resolve_gemini_illustrations(plan, config, layouts, *, attempts=None):
    model = config.gemini_presentation_image_model
    requests = _select_illustrations(plan, config.presentation_illustration_mode, layouts, model,
                                    attempts if attempts is not None else [])
    if not requests:
        return {}
    if not config.gemini_api_key:
        for _, attempt in requests:
            attempt.update(status="skipped", skip_reason="credentials_unavailable")
        return {}
    try:
        async with genai.Client(api_key=config.gemini_api_key.get_secret_value()).aio as client:
            return await _generate_illustrations(
                requests, GeminiIllustrationProvider(client, model, config.presentation_illustration_timeout_seconds),
                config.presentation_illustration_timeout_seconds,
            )
    except Exception:
        for _, attempt in requests:
            attempt.update(status="fallback", failure_category="provider_client_error", native_fallback=True)
        logger.info("presentation_illustration_fallback category=provider_client_error")
        return {}
