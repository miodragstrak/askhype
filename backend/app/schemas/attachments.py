from dataclasses import dataclass
from io import BytesIO
import warnings

from PIL import Image, UnidentifiedImageError

MAX_IMAGES = 3
MAX_IMAGE_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 40_000_000
SUPPORTED_IMAGE_TYPES = {"JPEG": "image/jpeg", "PNG": "image/png", "WEBP": "image/webp"}

@dataclass(frozen=True)
class ImageAttachment:
    content_type: str
    data: bytes
    filename: str | None = None

class ImageAttachmentError(ValueError):
    pass

def validate_image(data: bytes, declared_type: str | None, filename: str | None = None) -> ImageAttachment:
    unreadable = "Ne mogu da pročitam ovu sliku. Pokušaj sa drugom JPG, PNG ili WebP datotekom."
    if not data:
        raise ImageAttachmentError(unreadable)
    if len(data) > MAX_IMAGE_BYTES:
        raise ImageAttachmentError("Slika je prevelika. Maksimalna veličina je 10 MB.")
    if declared_type not in SUPPORTED_IMAGE_TYPES.values():
        raise ImageAttachmentError("Podržane su JPG, PNG i WebP slike.")
    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as image:
                actual_type = SUPPORTED_IMAGE_TYPES.get(image.format or "")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise ImageAttachmentError("Slika ima prevelike dimenzije.")
                image.verify()
    except ImageAttachmentError:
        raise
    except (UnidentifiedImageError, OSError, SyntaxError, Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise ImageAttachmentError(unreadable) from exc
    if actual_type is None or actual_type != declared_type:
        raise ImageAttachmentError("Tip slike ne odgovara njenom sadržaju.")
    return ImageAttachment(actual_type, data, filename)
