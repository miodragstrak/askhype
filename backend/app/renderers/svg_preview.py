from __future__ import annotations

import shutil
import subprocess
import tempfile
import xml.etree.ElementTree as ET
from pathlib import Path


class SvgPreviewError(RuntimeError): pass


def chrome_command(svg_path: Path, png_path: Path, profile_path: Path, *, virtual_time_ms: int) -> list[str]:
    return [
        "google-chrome", "--headless=new", "--disable-gpu", "--disable-javascript",
        "--disable-background-networking", "--disable-component-update", "--disable-sync",
        "--metrics-recording-only", "--no-first-run", "--no-default-browser-check",
        "--no-proxy-server", "--host-resolver-rules=MAP * ~NOTFOUND",
        f"--user-data-dir={profile_path}", "--window-size=1280,720", "--force-device-scale-factor=1",
        "--hide-scrollbars", "--run-all-compositor-stages-before-draw",
        f"--virtual-time-budget={virtual_time_ms}", f"--screenshot={png_path}", svg_path.resolve().as_uri(),
    ]


def render_svg_preview(
    svg_path: Path,
    png_path: Path,
    *,
    virtual_time_ms: int = 5_000,
    freeze_at_ms: int | None = None,
) -> float:
    if not 0 <= virtual_time_ms <= 15_000:
        raise SvgPreviewError("Virtual render time must be between 0 and 15000 ms.")
    profile = Path(tempfile.mkdtemp(prefix="askhype-svg-chrome-"))
    try:
        render_path = svg_path
        if freeze_at_ms is not None:
            if not 0 <= freeze_at_ms <= 15_000:
                raise SvgPreviewError("Frozen render time must be between 0 and 15000 ms.")
            root = ET.parse(svg_path).getroot()
            style = ET.SubElement(root, "{http://www.w3.org/2000/svg}style")
            style.text = (
                "* { animation-play-state: paused !important; "
                f"animation-delay: -{freeze_at_ms / 1000:g}s !important; }}"
            )
            render_path = profile / "frozen.svg"
            ET.ElementTree(root).write(render_path, encoding="unicode")
        import time
        started = time.monotonic()
        try:
            result = subprocess.run(
                chrome_command(render_path, png_path, profile, virtual_time_ms=virtual_time_ms),
                capture_output=True, text=True, timeout=30, check=False,
            )
        except subprocess.TimeoutExpired as exc:
            raise SvgPreviewError("SVG preview rendering timed out.") from exc
        if result.returncode != 0 or not png_path.is_file():
            raise SvgPreviewError("Chrome could not render the sanitized SVG.")
        return time.monotonic() - started
    finally:
        shutil.rmtree(profile, ignore_errors=True)
