"""Bounded text extraction, also executable as an isolated parser worker."""

import io
import json
import re
import sys

from bs4 import BeautifulSoup
from pypdf import PdfReader

MAX_EXTRACTED_CHARS = 200_000
MAX_PDF_PAGES = 100
MAX_INPUT_BYTES = 10 * 1024 * 1024


def clean_text(value: str) -> str:
    return "\n".join(
        line for part in value.splitlines()
        if (line := re.sub(r"\s+", " ", "".join(char for char in part if char.isprintable() or char.isspace())).strip())
    )


def extract_content(body: bytes, content_type: str, encoding: str = "utf-8") -> dict:
    truncated = False
    if content_type == "application/pdf":
        reader = PdfReader(io.BytesIO(body))
        if reader.is_encrypted:
            return {"error": "encrypted_pdf"}
        title = str((reader.metadata or {}).get("/Title", ""))
        parts: list[str] = []
        size = 0
        for index, page in enumerate(reader.pages):
            if index >= MAX_PDF_PAGES or size >= MAX_EXTRACTED_CHARS:
                truncated = True
                break
            text = clean_text(page.extract_text() or "")
            parts.append(f"[Page {index + 1}]\n{text}" if text else "")
            size += len(parts[-1])
        text = "\n\n".join(parts)
        # Page labels and isolated page numbers do not count as readable text.
        if sum(char.isalpha() for part in parts for char in re.sub(r"\[Page \d+\]", "", part)) < 20:
            return {"error": "no_pdf_text"}
    elif content_type == "text/html":
        soup = BeautifulSoup(body, "html.parser", from_encoding=encoding)
        title_node = soup.title or soup.find("h1")
        title = title_node.get_text(" ", strip=True) if title_node else ""
        for tag in soup.select(
            "script, style, noscript, nav, header, footer, aside, form, iframe, svg, "
            "[hidden], [aria-hidden='true'], [role='navigation'], [role='banner'], "
            "[role='contentinfo'], .cookie-banner, #cookie-banner, .advertisement"
        ):
            tag.decompose()
        main = soup.find("main") or soup.find("article") or soup.body or soup
        text = clean_text(main.get_text("\n", strip=True))
    elif content_type == "text/plain":
        title = ""
        text = clean_text(body.decode(encoding, errors="replace"))
    else:
        return {"error": "unsupported_type"}
    if not text.strip():
        return {"error": "no_text"}
    return {
        "title": clean_text(title)[:300],
        "text": text[:MAX_EXTRACTED_CHARS],
        "truncated": truncated or len(text) > MAX_EXTRACTED_CHARS,
    }


def main() -> None:
    # Bound parser CPU/memory as well as its parent-enforced wall-clock deadline.
    if sys.platform == "linux":
        import resource

        resource.setrlimit(resource.RLIMIT_AS, (768 * 1024 * 1024,) * 2)
        resource.setrlimit(resource.RLIMIT_CPU, (6, 6))
    try:
        body = sys.stdin.buffer.read(MAX_INPUT_BYTES + 1)
        result = (
            {"error": "too_large"} if len(body) > MAX_INPUT_BYTES
            else extract_content(body, sys.argv[1], sys.argv[2])
        )
    except Exception:
        result = {"error": "unreadable_content"}
    sys.stdout.write(json.dumps(result, ensure_ascii=False))


if __name__ == "__main__":
    main()
