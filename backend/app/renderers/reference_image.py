from __future__ import annotations

import io
import warnings
from dataclasses import dataclass

from PIL import Image, UnidentifiedImageError

MAX_REFERENCE_BYTES = 5 * 1024 * 1024
MAX_REFERENCE_DIMENSION = 2_048
MAX_REFERENCE_PIXELS = 40_000_000
SUPPORTED_FORMATS = {"PNG": "image/png", "JPEG": "image/jpeg", "WEBP": "image/webp"}


class ReferenceImageError(ValueError):
    def __init__(self, code: str) -> None:
        self.code = code
        super().__init__(code)


@dataclass(frozen=True)
class PreparedReferenceImage:
    data: bytes
    mime_type: str
    width: int
    height: int
    was_downscaled: bool


def prepare_reference_image(data: bytes) -> PreparedReferenceImage:
    if not data:
        raise ReferenceImageError("empty_reference_image")
    if len(data) > MAX_REFERENCE_BYTES:
        raise ReferenceImageError("reference_image_too_large")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(io.BytesIO(data)) as image:
                image_format = (image.format or "").upper()
                if image_format not in SUPPORTED_FORMATS:
                    raise ReferenceImageError("unsupported_reference_image_type")
                width, height = image.size
                if width < 1 or height < 1 or width * height > MAX_REFERENCE_PIXELS:
                    raise ReferenceImageError("reference_image_dimensions_invalid")
                image.load()
                normalized = image.convert("RGB")
    except ReferenceImageError:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ReferenceImageError("reference_image_dimensions_invalid") from None
    except (UnidentifiedImageError, OSError, ValueError):
        raise ReferenceImageError("malformed_reference_image") from None

    was_downscaled = max(width, height) > MAX_REFERENCE_DIMENSION
    if was_downscaled:
        normalized.thumbnail((MAX_REFERENCE_DIMENSION, MAX_REFERENCE_DIMENSION), Image.Resampling.LANCZOS)
    output = io.BytesIO()
    output_format = "JPEG"
    normalized.save(output, format=output_format, quality=88, optimize=True)
    result_width, result_height = normalized.size
    normalized.close()
    return PreparedReferenceImage(
        data=output.getvalue(),
        mime_type=SUPPORTED_FORMATS[output_format],
        width=result_width,
        height=result_height,
        was_downscaled=was_downscaled,
    )
