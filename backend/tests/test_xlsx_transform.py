import asyncio
import io
from copy import deepcopy
from uuid import uuid4

import httpx
import pytest
from openpyxl import Workbook, load_workbook
from pydantic import ValidationError

from app.main import app
from app.schemas.xlsx_transform import (
    AddColumnPlan, ArithmeticExpression, CreateSummarySheetPlan, FilterRowsPlan,
    RenameColumnPlan, RowCondition, SortRowsPlan, TransformationPlanEnvelope, UpdateColumnPlan,
)
from app.services.xlsx_transform import SpreadsheetTransformationError, TransformationResult, transform_workbook
from app.services.xlsx_transformation import XlsxTransformationService


def workbook_bytes() -> bytes:
    workbook = Workbook()
    sheet = workbook.active
    sheet.title = "Prodaja"
    sheet.append(["Mesec", "Region", "Prihod_RSD", "Trosak_RSD"])
    sheet.append(["Januar", "Beograd", 1_000_000, 620_000])
    sheet.append(["Februar", "Novi Sad", 1_150_000, 760_000])
    sheet.append(["Mart", "Beograd", 1_600_000, 1_000_000])
    other = workbook.create_sheet("Napomene")
    other.append(["Ne menjaj", 42])
    output = io.BytesIO()
    workbook.save(output)
    workbook.close()
    return output.getvalue()


def read_result(content: bytes):
    return load_workbook(io.BytesIO(content), data_only=False)


def test_add_derived_column_preserves_original_and_unrelated_sheet() -> None:
    original = workbook_bytes()
    before = deepcopy(original)
    result = transform_workbook(original, "prodaja.xlsx", AddColumnPlan(
        operation="add_column", sheet="Prodaja", target_column="Marža_RSD",
        expression=ArithmeticExpression(operator="subtract", left_column="Prihod", right_column="Trošak"),
    ))
    assert original == before
    workbook = read_result(result.content)
    try:
        assert [workbook["Prodaja"].cell(row, 5).value for row in range(2, 5)] == [380000, 390000, 600000]
        assert workbook["Napomene"]["A1"].value == "Ne menjaj"
        assert result.filename == "prodaja_transformed.xlsx"
    finally:
        workbook.close()


def test_percentage_and_divide_by_zero_are_safe() -> None:
    workbook = Workbook()
    sheet = workbook.active
    sheet.append(["Prihod", "Trošak"])
    sheet.append([100, 25])
    sheet.append([0, 10])
    stream = io.BytesIO(); workbook.save(stream); workbook.close()
    result = transform_workbook(stream.getvalue(), "p.xlsx", AddColumnPlan(
        operation="add_column", target_column="Marža %",
        expression=ArithmeticExpression(operator="percentage", left_column="Prihod", right_column="Trošak"),
    ))
    output = read_result(result.content)
    try:
        assert output.active["C2"].value == 0.75
        assert output.active["C3"].value is None
        assert result.warnings
    finally: output.close()


def test_update_column_uses_one_safe_condition() -> None:
    result = transform_workbook(workbook_bytes(), "p.xlsx", UpdateColumnPlan(
        operation="update_column", sheet="Prodaja", target_column="Trosak_RSD",
        expression=ArithmeticExpression(operator="multiply", left_column="Trosak_RSD", right_value=0.9),
        condition=RowCondition(column="Region", comparator="equals", value="Beograd"),
    ))
    workbook = read_result(result.content)
    try:
        assert [workbook["Prodaja"].cell(row, 4).value for row in range(2, 5)] == [558000, 760000, 900000]
    finally:
        workbook.close()


def test_rename_filter_sort_and_summary_operations() -> None:
    original = workbook_bytes()
    renamed = transform_workbook(original, "p.xlsx", RenameColumnPlan(
        operation="rename_column", sheet="Prodaja", source_column="Trosak", target_column="Trošak",
    ))
    assert read_result(renamed.content)["Prodaja"]["D1"].value == "Trošak"

    filtered = transform_workbook(original, "p.xlsx", FilterRowsPlan(
        operation="filter_rows", sheet="Prodaja",
        condition=RowCondition(column="Prihod", comparator="greater_than", value=1_000_000),
    ))
    filtered_book = read_result(filtered.content)
    assert [cell.value for cell in filtered_book["Prodaja"]["A"]] == ["Mesec", "Februar", "Mart"]
    filtered_book.close()

    sorted_result = transform_workbook(original, "p.xlsx", SortRowsPlan(
        operation="sort_rows", sheet="Prodaja", column="Prihod", direction="descending",
    ))
    sorted_book = read_result(sorted_result.content)
    assert [sorted_book["Prodaja"].cell(row, 1).value for row in range(2, 5)] == ["Mart", "Februar", "Januar"]
    sorted_book.close()

    summary = transform_workbook(original, "p.xlsx", CreateSummarySheetPlan(
        operation="create_summary_sheet", sheet="Prodaja", target_sheet="Sažetak",
        group_by_column="Region", value_column="Prihod", aggregation="sum",
    ))
    summary_book = read_result(summary.content)
    assert dict(summary_book["Sažetak"].iter_rows(min_row=2, values_only=True)) == {"Beograd": 2600000, "Novi Sad": 1150000}
    summary_book.close()


def test_ambiguous_column_and_missing_sheet_fail_clearly() -> None:
    workbook = Workbook(); sheet = workbook.active
    sheet.append(["Prihod_RSD", "Prihod_EUR"]); sheet.append([1, 2])
    stream = io.BytesIO(); workbook.save(stream); workbook.close()
    with pytest.raises(SpreadsheetTransformationError, match="jednoznačna"):
        transform_workbook(stream.getvalue(), "p.xlsx", SortRowsPlan(operation="sort_rows", column="Prihod", direction="ascending"))
    with pytest.raises(SpreadsheetTransformationError, match="ne postoji"):
        transform_workbook(workbook_bytes(), "p.xlsx", SortRowsPlan(operation="sort_rows", sheet="Nema", column="Prihod", direction="ascending"))


def test_plan_schema_rejects_unsupported_shape() -> None:
    with pytest.raises(ValidationError):
        TransformationPlanEnvelope.model_validate({"plan": {"operation": "delete_sheet", "sheet": "Prodaja"}})


async def post_transform(anonymous_id: str, body: bytes = b"bad"):
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app), base_url="http://test") as client:
        response = await client.post(
            "/api/documents/transform-xlsx", headers={"X-Anonymous-ID": anonymous_id},
            data={"instruction": "Dodaj maržu"},
            files={"file": ("prodaja.xlsx", body, "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")},
        )
        usage = await client.get("/api/usage", headers={"X-Anonymous-ID": anonymous_id})
        return response, usage


def test_endpoint_success_returns_download_and_counts_one(monkeypatch) -> None:
    async def transform(self, instruction, body, filename, document):
        return TransformationResult(body, "prodaja_transformed.xlsx", "sort_rows", "Sortirano.", ())
    monkeypatch.setattr(XlsxTransformationService, "transform", transform)
    response, usage = asyncio.run(post_transform(str(uuid4()), workbook_bytes()))
    assert response.status_code == 200
    assert response.content.startswith(b"PK")
    assert "attachment" in response.headers["content-disposition"]
    assert usage.json()["used"] == 1


def test_invalid_file_is_rejected_without_quota() -> None:
    response, usage = asyncio.run(post_transform(str(uuid4())))
    assert response.status_code == 400
    assert usage.json()["used"] == 0


def test_invalid_plan_does_not_count_quota(monkeypatch) -> None:
    async def transform(self, instruction, body, filename, document):
        raise SpreadsheetTransformationError("Plan nije podržan.")
    monkeypatch.setattr(XlsxTransformationService, "transform", transform)
    response, usage = asyncio.run(post_transform(str(uuid4()), workbook_bytes()))
    assert response.status_code == 400
    assert usage.json()["used"] == 0
