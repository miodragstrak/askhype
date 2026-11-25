"""Build presentation fixtures without provider calls, optionally render PDFs and PNGs."""

import argparse
from io import BytesIO
from pathlib import Path
import shutil
import subprocess
from tempfile import TemporaryDirectory

from PIL import Image, ImageDraw

from app.schemas.presentations import PresentationPlan
from app.services.executive_pptx import render_executive, verify_quantitative_evidence
from app.services.presentation_illustrations import normalize_illustration

OPERATIONS_BRIEF = """Executive operations committee decision brief

Ask the committee to authorize one controlled release pilot before wider rollout.
Editorial owns the release decision, production assembles the package, and
distribution validates the package before publishing. Preserve the duty
editor's existing authority. The pilot should use the current delivery tools
and record the primary reason for each incomplete handoff.

Supplied synthetic internal rehearsal evidence
24 packages reviewed. 7 packages had an incomplete handoff.
Primary reason counts: metadata 4, rights check 2, delivery format 1.
This is a rehearsal sample, not a production defect rate.
"""


def _slide(title, layout, *bullets, **values):
    return {"type": "bullets", "title": title, "layout": layout, "bullets": list(bullets), **values}


def _deck(title, language, body, *, subtitle=""):
    return PresentationPlan.model_validate({
        "title": title, "language": language,
        "slides": [
            {"type": "title", "title": title, "subtitle": subtitle},
            *body,
            {"type": "conclusion", "title": {
                "en": "Next steps", "sr": "Sledeći koraci", "sr-Cyrl": "Следећи кораци",
            }[language], "bullets": [{
                "en": "Review with the working group and agree the next checkpoint.",
                "sr": "Potvrditi prioritete i imenovati odgovorne za pripremu predloga.",
                "sr-Cyrl": "Примените поступак на новом примеру и објасните избор.",
            }[language]]},
        ],
    })


def fixtures():
    yield "media-executive", _deck("Regionalna televizija i produkcija", "sr", [
        _slide("Program i produkcija treba da dele jedan plan", "summary",
               "Predlog odluke: uskladiti urednički kalendar sa kapacitetom produkcije.",
               "Pilot neka poveže televizijsko emitovanje i digitalnu distribuciju.",
               takeaway="Prvo uskladiti rad timova, zatim širiti distribuciju.", claim_status="proposal"),
        _slide("Tri stuba poslovanja", "pillars",
               "Program: urednički izbor i plan emitovanja.",
               "Produkcija: razvoj formata, snimanje i postprodukcija.",
               "Distribucija: priprema materijala za televiziju i digitalne kanale."),
        _slide("Dva načina da se organizuje pilot", "comparison",
               "Zajednički urednički kalendar: brže usklađivanje, uz potrebu za jasnim vlasništvom.",
               "Odvojeni kalendari: veća autonomija, uz više koordinacije pred emitovanje."),
        _slide("Predloženi koraci za rukovodstvo", "recommendations",
               "Uredništvo: izabrati format za probni ciklus.",
               "Produkcija: potvrditi tim, rokove i prava na materijal.",
               "Distribucija: napraviti kontrolnu listu za svaku platformu.", claim_status="proposal"),
    ], subtitle="Predlog operativnog pravca za rukovodstvo"), set()

    strategy = [
        _slide("Agree the decision criteria", "summary", "Prioritize customer impact and ease of delivery."),
        _slide("Define the problem before scaling", "problem_solution", "Problem: unclear ownership.", "Proposal: one owner per initiative."),
        _slide("Make handoffs explicit", "process", "Define the brief.", "Check dependencies.", "Approve the deliverable."),
        _slide("Sequence the work", "roadmap", "Discovery: agree scope.", "Pilot: validate the approach.", "Review: decide whether to expand."),
        _slide("Options for a limited pilot", "comparison", "Try one team first.", "Trial two teams with a shared checklist."),
        _slide("Assumptions to verify", "findings", "The sponsor can allocate time.", claim_status="assumption"),
        _slide("Build the operating model", "pillars", "Ownership and escalation.", "Practical readiness checks.", "Decision records."),
        _slide("Keep decision records readable", "findings", "Record the decision, owner, and remaining uncertainty."),
        _slide("Prepare a review checklist", "recommendations", "Share the checklist with pilot owners."),
        _slide("Define review and escalation responsibilities before assessing outcomes across teams",
               "findings", *["Include context, trade-offs and the next review step. " * 3 for _ in range(6)]),
    ]
    yield "strategy-roadmap-12", _deck("Business strategy and roadmap", "en", strategy), set()
    yield "education-cyrillic-3", _deck("Како читати графикон", "sr-Cyrl", [
        {"type": "table", "title": "Проверите јединицу пре поређења", "layout": "worked_example",
         "claim_status": "illustrative", "headers": ["Мерење", "Јединице"],
         "rows": [["Пример А", "4"], ["Пример Б", "7"]],
         "takeaway": "Измишљени подаци за вежбу: пример Б има три јединице више од примера А."},
    ]), set()
    evidence = {"claim_status": "evidence", "evidence_ids": ["document"]}
    table = {"type": "table", "headers": ["Period", "Units"], "rows": [["Pilot A", "12"], ["Pilot B", "18"]]}
    yield "quantitative", _deck("Synthetic pilot evidence", "en", [
        {"type": "key_metrics", "title": "Pilot B processed 18 units", "metrics": [{"label": "Units in Pilot B", "value": "18"}], **evidence},
        {**table, "title": "Pilot throughput by period", "layout": "chart", **evidence},
        {**table, "title": "Underlying pilot observations", "layout": "table", **evidence},
    ], subtitle="Synthetic QA data only"), {"document"}

    yield "executive-operations-6", _deck("Protect the release date with a controlled pilot", "en", [
        _slide("Approve one pilot before expanding the rollout", "summary",
               "Decision: authorize a single release pilot with editorial, production and distribution represented.",
               "Evidence: the rehearsal found 7 incomplete handoffs across 24 reviewed packages.",
               "Guardrail: keep publication authority with the existing duty editor.",
               claim_status="proposal", speaker_notes="Ask the sponsor to confirm the pilot owner and the review date. The rehearsal sample is internal and does not establish a long-run defect rate."),
        {"type": "table", **evidence, "title": "Metadata was the largest handoff issue in the rehearsal",
         "layout": "chart", "headers": ["Primary issue", "Packages"], "rows": [
             ["Metadata", "4"], ["Rights check", "2"], ["Delivery format", "1"],
         ], "takeaway": "Prioritize metadata checks before changing downstream delivery tooling."},
        _slide("Put one gate between production and distribution", "business_model",
               "Editorial: approve the brief and release intent.",
               "Production: confirm metadata, rights and delivery format.",
               "Distribution: accept the package or return it with a single reason.",
               claim_status="proposal", objective="Agree which team owns each handoff."),
        _slide("Review risks at three checkpoints", "timeline",
               "Before pilot: name the duty editor and agree the acceptance checklist.",
               "During pilot: record incomplete packages and their main failure category.",
               "At readout: review exceptions before authorizing wider rollout.",
               claim_status="proposal"),
    ], subtitle="Decision brief for the executive operations committee"), {"document"}


def image_fixtures():
    existing = dict((name, (plan, sources)) for name, plan, sources in fixtures())
    yield "media", *existing["media-executive"]
    yield "business", *existing["executive-operations-6"]
    yield "education", *existing["education-cyrillic-3"]
    yield "technology", _deck("AI agents in the exception workflow", "en", [
        _slide("A human owns the payment decision", "findings", "An agent gathers context for the approver.",
               "The approver accepts or rejects the proposed next step."),
    ], subtitle="A bounded workflow for finance operations"), set()
    yield "marketing", _deck("LoopTrail launches at the packing moment", "en", [
        _slide("Show a traveler making the refill choice", "findings", "Open with the packing problem.",
               "Show the refill action as the product reveal."),
        _slide("Test one short retail story", "recommendations", "Ask a partner to run one staged concept test."),
    ], subtitle="A fictional retail launch concept"), set()


def placeholder_art(name, crop):
    """Application-owned geometric QA art, drawn locally with Pillow."""
    image = Image.new("RGB", (1000, 780), "#173645")
    draw = ImageDraw.Draw(image)
    draw.ellipse((470, 68, 962, 560), fill="#287b75")
    for number in range(9):
        x = 90 * number - 40
        draw.line((x, 780, x + 390, 330), fill="#345869", width=3)
    if name == "media":
        draw.rounded_rectangle((310, 208, 735, 495), 26, fill="#e1bd76", outline="#f8f0de", width=9)
        draw.polygon([(475, 276), (475, 428), (617, 352)], fill="#173645")
    elif name == "education":
        draw.polygon([(190, 300), (475, 254), (514, 320), (806, 264), (806, 524), (510, 598), (190, 536)],
                     fill="#f2d99f", outline="#f8f0de", width=8)
        draw.line((510, 320, 510, 592), fill="#946b42", width=8)
    elif name == "marketing":
        shift = 265 if crop == "full_bleed" else 0
        draw.rounded_rectangle((407 + shift, 217, 597 + shift, 630), 45, fill="#e1bd76", outline="#f8f0de", width=8)
        draw.rounded_rectangle((436 + shift, 145, 568 + shift, 249), 19, fill="#d6ede3")
    else:
        for x, y in [(365, 326), (528, 461), (684, 292)]:
            draw.line((505, 388, x, y), fill="#dfc17b", width=14)
            draw.rounded_rectangle((x - 67, y - 55, x + 67, y + 55), 18, fill="#d6ede3")
    buffer = BytesIO()
    image.save(buffer, format="PNG")
    return normalize_illustration(buffer.getvalue(), crop)


def contact_sheet(paths, destination, *, comparison=False):
    width, height = 360, 203
    columns = 2 if comparison else 3
    rows = (len(paths) + columns - 1) // columns
    sheet = Image.new("RGB", (columns * width, rows * (height + 22)), "#e7e9ec")
    draw = ImageDraw.Draw(sheet)
    for index, path in enumerate(paths):
        x, y = index % columns * width, index // columns * (height + 22)
        with Image.open(path) as thumbnail:
            thumbnail.thumbnail((width - 12, height - 8))
            sheet.paste(thumbnail, (x + 6, y + 4))
        caption = f"{'Before' if index % 2 == 0 else 'After'} · {index // 2 + 1}" if comparison else str(index + 1)
        draw.text((x + 8, y + height), caption, fill="#142638")
    sheet.save(destination)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--render", action="store_true")
    parser.add_argument("--baseline", type=Path)
    parser.add_argument("--input-pptx", type=Path)
    parser.add_argument("--illustration-fixtures", action="store_true")
    parser.add_argument("--libreoffice", default=shutil.which("libreoffice") or shutil.which("soffice"))
    args = parser.parse_args()
    args.output = args.output.resolve()
    args.output.mkdir(parents=True, exist_ok=True)
    files = [args.input_pptx.resolve()] if args.input_pptx else []
    if files and (not args.render or not files[0].is_file()):
        parser.error("--input-pptx requires an existing deck and --render.")
    selected_fixtures = () if files else (image_fixtures() if args.illustration_fixtures else fixtures())
    for name, plan, sources in selected_fixtures:
        if name == "executive-operations-6":
            verify_quantitative_evidence(plan, OPERATIONS_BRIEF)
            (args.output / f"{name}-brief.txt").write_text(OPERATIONS_BRIEF, encoding="utf-8")
        path = args.output / f"{name}.pptx"
        illustrations = None
        if args.illustration_fixtures:
            illustrations = {1: placeholder_art(name, "full_bleed" if name == "marketing" else "cover_right")}
            if name in {"media", "marketing", "technology"}:
                illustrations[2] = placeholder_art(name, "split_right")
        path.write_bytes(render_executive(plan, sources, illustrations=illustrations))
        files.append(path)
    if not args.render:
        return
    if not args.libreoffice:
        parser.error("LibreOffice was not found. PPTX fixtures were generated.")
    with TemporaryDirectory(prefix="lo-profile-", dir=args.output) as profile:
        subprocess.run([args.libreoffice, f"-env:UserInstallation={Path(profile).as_uri()}",
                        "--headless", "--convert-to", "pdf", "--outdir", profile, *map(str, files)],
                       check=True, timeout=120)
        for path in files:
            rendered = Path(profile) / path.with_suffix(".pdf").name
            if not rendered.is_file():
                raise RuntimeError(f"No rendered PDF for {path.name}")
            pdf = args.output / path.with_suffix(".pdf").name
            rendered.replace(pdf)
            if shutil.which("pdftoppm"):
                subprocess.run(["pdftoppm", "-r", "90", "-png", str(pdf), str(pdf.with_suffix(""))],
                               check=True, timeout=60)
                pages = sorted(args.output.glob(f"{path.stem}-[0-9]*.png"))
                contact_sheet(pages, args.output / f"{path.stem}-contact.png")
                if args.baseline:
                    before = sorted(args.baseline.glob(f"{path.stem}-[0-9]*.png"))
                    if before and len(before) == len(pages):
                        contact_sheet([page for pair in zip(before, pages) for page in pair],
                                      args.output / f"{path.stem}-comparison.png", comparison=True)


if __name__ == "__main__":
    main()
