import asyncio
from io import BytesIO
from zipfile import ZipFile

from pptx import Presentation
from pptx.enum.shapes import MSO_SHAPE, MSO_SHAPE_TYPE
from pptx.util import Inches
import pytest

from app.services.executive_pptx import render_executive, verify_quantitative_evidence
from app.services.presentation_generation import PresentationGenerationService
from scripts.presentation_qa import OPERATIONS_BRIEF, fixtures


@pytest.mark.parametrize("name,plan,sources", list(fixtures()))
def test_executive_fixtures_reopen_with_editable_content(name, plan, sources):
    pptx = render_executive(plan, sources)
    deck = Presentation(BytesIO(pptx))
    assert len(deck.slides) == len(plan.slides)
    assert all(slide.notes_slide.notes_text_frame.text for slide in deck.slides)
    assert all(shape.left >= 0 and shape.top >= 0 for slide in deck.slides for shape in slide.shapes)
    if name == "media-executive":
        assert len({slide.name for slide in deck.slides}) >= 4
        for slide in list(deck.slides)[1:-1]:
            assert not any(
                shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
                and shape.auto_shape_type == MSO_SHAPE.RECTANGLE
                and shape.width > Inches(2) and shape.height > Inches(1)
                for shape in slide.shapes
            ), "Editorial layouts must not recreate oversized rectangular containers."
        comparison = next(slide for slide in deck.slides if slide.name == "comparison")
        text = " ".join(shape.text.replace("\v", " ") for shape in comparison.shapes if shape.has_text_frame)
        assert "Zajednički urednički kalendar" in text
        assert "…" not in text
    if name == "strategy-roadmap-12":
        assert "trade-offs" in " ".join(shape.text.replace("-\v", "-").replace("\v", " ")
                                       for shape in deck.slides[10].shapes if shape.has_text_frame)
    if name == "quantitative":
        assert any(shape.has_table for slide in deck.slides for shape in slide.shapes)
        assert any(shape.has_chart for slide in deck.slides for shape in slide.shapes)
        with ZipFile(BytesIO(pptx)) as package:
            assert package.testzip() is None
            assert any(name.startswith("ppt/embeddings/") for name in package.namelist())
    if name == "education-cyrillic-3":
        assert deck.slides[1].name == "worked_example"
        assert any(shape.has_chart for shape in deck.slides[1].shapes)
        assert any("ИЛУСТРАТИВНО" in shape.text for shape in deck.slides[1].shapes if shape.has_text_frame)
    if name == "executive-operations-6":
        verify_quantitative_evidence(plan, OPERATIONS_BRIEF)
        for slide in [slide for slide in deck.slides if slide.name in {"business_model", "timeline"}]:
            assert any(shape.shape_type == MSO_SHAPE_TYPE.LINE for shape in slide.shapes)
        flow = next(slide for slide in deck.slides if slide.name == "business_model")
        markers = [shape for shape in flow.shapes if shape.shape_type == MSO_SHAPE_TYPE.AUTO_SHAPE
                   and shape.auto_shape_type == MSO_SHAPE.OVAL]
        assert len(markers) == 3 and len({marker.top for marker in markers}) == 1


def test_rejects_unknown_sources_and_non_numeric_metrics():
    _, plan, sources = next(item for item in fixtures() if item[0] == "quantitative")
    with pytest.raises(ValueError, match="evidence"):
        render_executive(plan)
    plan.slides[1].metrics[0].value = "Excellent"
    with pytest.raises(ValueError, match="finite number"):
        render_executive(plan, sources)


def test_rejects_invalid_chart_data():
    _, plan, sources = next(item for item in fixtures() if item[0] == "quantitative")
    plan.slides[2].rows[0][1] = "NaN"
    with pytest.raises(ValueError, match="finite number"):
        render_executive(plan, sources)


def test_quantitative_evidence_requires_literal_values():
    _, plan, _ = next(item for item in fixtures() if item[0] == "quantitative")
    verify_quantitative_evidence(plan, "Pilot A: 12 units. Pilot B: 18 units.")
    with pytest.raises(ValueError, match="absent"):
        verify_quantitative_evidence(plan, "Pilot A: 12 units. Pilot B: 19 units.")


def test_rejects_incomplete_diagram_and_unlabeled_teaching_data():
    _, plan, sources = next(item for item in fixtures() if item[0] == "strategy-roadmap-12")
    plan.slides[3].bullets = ["One lonely step"]
    with pytest.raises(ValueError, match="at least two"):
        render_executive(plan, sources)

    _, plan, sources = next(item for item in fixtures() if item[0] == "education-cyrillic-3")
    plan.slides[1].claim_status = "qualitative"
    with pytest.raises(ValueError, match="illustrative"):
        render_executive(plan, sources)


def test_generation_service_uses_executive_renderer_after_one_plan():
    _, plan, _ = next(fixtures())

    class Planner:
        calls = 0

        async def generate_presentation_plan(self, prompt, count, document):
            self.calls += 1
            assert count == 6 and document is None
            return plan

    planner = Planner()
    result = asyncio.run(PresentationGenerationService(planner).generate("Napravi 6 slajdova", None))
    assert planner.calls == 1
    assert result.slide_count == 6
    assert Presentation(BytesIO(result.content)).slides[1].name == "summary"


def test_marketing_worked_example_preserves_mixed_data_as_editable_table():
    from app.schemas.presentations import TableSlide
    from app.services.presentation_diagnostics import PresentationDiagnostics

    _, plan, _ = next(item for item in fixtures() if item[0] == "education-cyrillic-3")
    item = TableSlide(
        type="table", title="Concrete Channel Test Plan", layout="worked_example",
        objective="Outline the testing framework for the retail launch.",
        takeaway="Controlled channel tests will validate customer interest efficiently.",
        speaker_notes="Review the proposed testing channels and their corresponding success metrics.",
        claim_status="illustrative", evidence_ids=[],
        headers=["Channel", "Test Duration", "Target Metric", "Proposed Budget"],
        rows=[
            ["Flagship Retail Pop-up", "2 Weeks", "500 Unit Sales", "Low"],
            ["Outdoor Gear Bundle", "4 Weeks", "1,200 Orders", "Medium"],
            ["Trailhead Kiosk Display", "3 Weeks", "350 Samples", "Low"],
        ],
    )
    plan.slides[1] = item
    original = plan.model_dump()
    diagnostics = PresentationDiagnostics()
    deck = Presentation(BytesIO(render_executive(plan, diagnostics=diagnostics)))
    slide = deck.slides[1]
    table = next(shape.table for shape in slide.shapes if shape.has_table)
    assert slide.name == "table"
    assert not any(shape.has_chart for shape in slide.shapes)
    assert [[table.cell(r, c).text.replace("-\v", "-").replace("\v", " ") for c in range(4)]
            for r in range(4)] == [item.headers, *item.rows]
    assert item.speaker_notes in slide.notes_slide.notes_text_frame.text
    assert item.takeaway in slide.notes_slide.notes_text_frame.text
    assert plan.model_dump() == original
    assert diagnostics.layout_fallbacks[0]["rule"] == "numeric_format"


def test_worked_example_mixed_units_fall_back_but_factual_chart_rejects_them():
    _, plan, _ = next(item for item in fixtures() if item[0] == "education-cyrillic-3")
    plan.slides[1].headers = ["Group", "Price (USD)", "Users (count)"]
    plan.slides[1].rows = [["A", "12", "18"], ["B", "14", "19"]]
    slide = Presentation(BytesIO(render_executive(plan))).slides[1]
    assert slide.name == "table"

    _, plan, sources = next(item for item in fixtures() if item[0] == "quantitative")
    plan.slides[2].headers = ["Group", "Price (USD)", "Users (count)"]
    plan.slides[2].rows = [["A", "12", "18"], ["B", "14", "19"]]
    with pytest.raises(ValueError, match="explicit unit"):
        render_executive(plan, sources)


def test_qualitative_kpi_preference_resolves_to_findings():
    _, plan, sources = next(item for item in fixtures() if item[0] == "media-executive")
    plan.slides[1].layout = "kpi"
    assert Presentation(BytesIO(render_executive(plan, sources))).slides[1].name == "findings"


def test_proposed_mixed_unit_targets_remain_labeled_and_editable():
    _, plan, sources = next(item for item in fixtures() if item[0] == "quantitative")
    item = plan.slides[1]
    item.claim_status = "proposal"
    item.evidence_ids = []
    item.metrics[0].value = "15 Stores"
    item.metrics.append(item.metrics[0].model_copy(update={"label": "Rating", "value": "4.8 Stars"}))
    slide = Presentation(BytesIO(render_executive(plan, sources))).slides[1]
    table = next(shape.table for shape in slide.shapes if shape.has_table)
    assert slide.name == "table"
    assert [table.cell(row, 1).text for row in (1, 2)] == ["15 Stores", "4.8 Stars"]
    assert any("PROPOSAL" in shape.text for shape in slide.shapes if shape.has_text_frame)


def test_media_decision_deadline_and_table_conditions_are_visible():
    from app.schemas.presentations import BulletsSlide, TableSlide

    _, plan, sources = next(item for item in fixtures() if item[0] == "media-executive")
    table = TableSlide(
        type="table", title="Uslovi za širenje i odgovorne funkcije", layout="table",
        claim_status="proposal",
        headers=["Oblast", "Uslov za širenje", "Odgovorna funkcija"],
        rows=[
            ["Pravna osnova", "Uspesno rešena digitalna prava za sve naslove", "Pravni sektor"],
            ["Produkcija", "Ispunjen plan bez prekoračenja deljenih kapaciteta", "Glavni producent"],
            ["Plasman", "Potvrđeni kanali distribucije za pilot sadržaj", "Direktor programa"],
        ],
    )
    decision = BulletsSlide(
        type="bullets", title="Sledeća odluka upravnog odbora", layout="roadmap",
        claim_status="proposal", speaker_notes="Detalji glasanja.",
        bullets=[
            "Zvanično usvajanje predloga o ograničenom pilot projektu",
            "Odobrenje budžeta isključivo za potrebe pilot faze",
            "Nalaženje pravnom timu da dostavi izveštaj o digitalnim pravima u roku od 30 dana",
        ],
    )
    plan.slides[3:5] = [table, decision]
    original = plan.model_dump()
    slides = Presentation(BytesIO(render_executive(plan, sources))).slides
    cells = next(shape.table for shape in slides[3].shapes if shape.has_table)
    for row_index, row in enumerate([table.headers, *table.rows]):
        assert [cells.cell(row_index, col).text.replace("\v", " ") for col in range(3)] == row
    visible = " ".join(shape.text.replace("\v", " ") for shape in slides[4].shapes if shape.has_text_frame)
    assert all(item in visible for item in decision.bullets)
    assert "30 dana" in visible and "…" not in visible
    assert decision.speaker_notes in slides[4].notes_slide.notes_text_frame.text
    assert plan.model_dump() == original


def test_dense_roadmap_uses_wider_timeline_without_removing_deadline():
    from app.services.presentation_diagnostics import PresentationDiagnostics

    _, plan, sources = next(item for item in fixtures() if item[0] == "media-executive")
    item = plan.slides[1]
    item.layout = "roadmap"
    item.bullets = [
        "The legal team must confirm all regional distribution rights, verify every agreement, "
        "and send the signed decision and supporting evidence to the board by 30 November 2026.",
        "The board approves the pilot only after the legal review.",
        "The director assigns an owner and confirms the launch budget.",
    ]
    trace = PresentationDiagnostics()
    slide = Presentation(BytesIO(render_executive(plan, sources, diagnostics=trace))).slides[1]
    assert slide.name == "timeline"
    assert trace.layout_fallbacks[0]["rule"] == "text_fit"
    visible = " ".join(shape.text.replace("\v", " ") for shape in slide.shapes if shape.has_text_frame)
    assert all(bullet in visible for bullet in item.bullets)
