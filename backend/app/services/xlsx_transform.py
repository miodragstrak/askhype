import io
import re
import unicodedata
from copy import copy
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import PurePath

from openpyxl import load_workbook
from openpyxl.cell.cell import Cell
from openpyxl.worksheet.worksheet import Worksheet

from app.schemas.xlsx_transform import (
    AddColumnPlan,
    ArithmeticExpression,
    CreateSummarySheetPlan,
    FilterRowsPlan,
    RenameColumnPlan,
    RowCondition,
    SortRowsPlan,
    TransformationPlan,
    UnsupportedPlan,
    UpdateColumnPlan,
)

MAX_TRANSFORM_SHEETS = 20
MAX_TRANSFORM_ROWS = 10_000
MAX_TRANSFORM_COLUMNS = 200


class SpreadsheetTransformationError(ValueError):
    pass


@dataclass(frozen=True)
class TransformationResult:
    content: bytes
    filename: str
    operation: str
    summary: str
    warnings: tuple[str, ...]


@dataclass(frozen=True)
class _CellSnapshot:
    value: object
    style: object
    hyperlink: object
    comment: object


def transform_workbook(body: bytes, filename: str, plan: TransformationPlan) -> TransformationResult:
    if isinstance(plan, UnsupportedPlan):
        raise SpreadsheetTransformationError("Tražena Excel izmena nije podržana ili nije dovoljno jasna.")
    workbook = load_workbook(io.BytesIO(body), read_only=False, data_only=False, keep_links=False)
    warnings: list[str] = []
    try:
        _validate_workbook_size(workbook)
        if isinstance(plan, CreateSummarySheetPlan):
            summary = _create_summary_sheet(workbook, plan, warnings)
        else:
            sheet = _resolve_sheet(workbook, plan.sheet)
            if isinstance(plan, AddColumnPlan):
                summary = _add_column(sheet, plan, warnings)
            elif isinstance(plan, UpdateColumnPlan):
                summary = _update_column(sheet, plan, warnings)
            elif isinstance(plan, FilterRowsPlan):
                summary = _filter_rows(sheet, plan)
            elif isinstance(plan, SortRowsPlan):
                summary = _sort_rows(sheet, plan)
            elif isinstance(plan, RenameColumnPlan):
                summary = _rename_column(sheet, plan)
            else:
                raise SpreadsheetTransformationError("Tražena Excel izmena nije podržana.")
        output = io.BytesIO()
        workbook.save(output)
    finally:
        workbook.close()
    return TransformationResult(
        content=output.getvalue(),
        filename=_output_filename(filename),
        operation=plan.operation,
        summary=summary,
        warnings=tuple(warnings),
    )


def _validate_workbook_size(workbook) -> None:
    if len(workbook.worksheets) > MAX_TRANSFORM_SHEETS:
        raise SpreadsheetTransformationError(f"Excel dokument može imati najviše {MAX_TRANSFORM_SHEETS} radnih listova za izmenu.")
    for sheet in workbook.worksheets:
        if (sheet.max_row or 0) > MAX_TRANSFORM_ROWS + 1:
            raise SpreadsheetTransformationError(f"Radni list može imati najviše {MAX_TRANSFORM_ROWS} redova podataka.")
        if (sheet.max_column or 0) > MAX_TRANSFORM_COLUMNS:
            raise SpreadsheetTransformationError(f"Radni list može imati najviše {MAX_TRANSFORM_COLUMNS} kolona.")


def _resolve_sheet(workbook, requested: str | None) -> Worksheet:
    if requested:
        matches = [sheet for sheet in workbook.worksheets if _normalized(sheet.title) == _normalized(requested)]
        if len(matches) == 1:
            return matches[0]
        if len(matches) > 1:
            raise SpreadsheetTransformationError(f"Naziv radnog lista „{requested}” nije jednoznačan.")
        raise SpreadsheetTransformationError(f"Radni list „{requested}” ne postoji.")
    if len(workbook.worksheets) == 1:
        return workbook.worksheets[0]
    raise SpreadsheetTransformationError("Excel ima više radnih listova. Navedite radni list za izmenu.")


def _headers(sheet: Worksheet) -> dict[int, str]:
    headers = {
        cell.column: str(cell.value).strip()
        for cell in sheet[1]
        if cell.value is not None and str(cell.value).strip()
    }
    if not headers:
        raise SpreadsheetTransformationError(f"Radni list „{sheet.title}” nema zaglavlje u prvom redu.")
    return headers


def _resolve_column(sheet: Worksheet, requested: str) -> int:
    headers = _headers(sheet)
    query = _normalized(requested)
    exact = [index for index, header in headers.items() if _normalized(header) == query]
    if len(exact) == 1:
        return exact[0]
    query_tokens = set(_tokens(requested))
    logical = [
        index for index, header in headers.items()
        if query_tokens and query_tokens.issubset(set(_tokens(header)))
    ]
    if len(logical) == 1:
        return logical[0]
    if len(exact) > 1 or len(logical) > 1:
        raise SpreadsheetTransformationError(f"Kolona „{requested}” nije jednoznačna.")
    raise SpreadsheetTransformationError(f"Kolona „{requested}” ne postoji na listu „{sheet.title}”.")


def _ensure_new_column(sheet: Worksheet, target: str) -> int:
    try:
        _resolve_column(sheet, target)
    except SpreadsheetTransformationError as exc:
        if "ne postoji" not in str(exc):
            raise
    else:
        raise SpreadsheetTransformationError(f"Kolona „{target}” već postoji.")
    if sheet.max_column >= MAX_TRANSFORM_COLUMNS:
        raise SpreadsheetTransformationError(f"Nije moguće dodati više od {MAX_TRANSFORM_COLUMNS} kolona.")
    return sheet.max_column + 1


def _add_column(sheet: Worksheet, plan: AddColumnPlan, warnings: list[str]) -> str:
    target_index = _ensure_new_column(sheet, plan.target_column)
    source_indexes = _expression_columns(sheet, plan.expression)
    target_header = sheet.cell(1, target_index, plan.target_column)
    if target_index > 1:
        target_header._style = copy(sheet.cell(1, target_index - 1)._style)
    skipped = 0
    for row in range(2, sheet.max_row + 1):
        value = _calculate(sheet, row, plan.expression, source_indexes)
        if value is None:
            skipped += 1
        sheet.cell(row, target_index, value)
    _append_calculation_warning(warnings, skipped)
    return f"Dodata je kolona „{plan.target_column}” na radni list „{sheet.title}”."


def _update_column(sheet: Worksheet, plan: UpdateColumnPlan, warnings: list[str]) -> str:
    target_index = _resolve_column(sheet, plan.target_column)
    source_indexes = _expression_columns(sheet, plan.expression)
    condition = _resolved_condition(sheet, plan.condition) if plan.condition else None
    skipped = 0
    updated = 0
    for row in range(2, sheet.max_row + 1):
        if condition and not _condition_matches(sheet.cell(row, condition[0]).value, condition[1]):
            continue
        value = _calculate(sheet, row, plan.expression, source_indexes)
        if value is None:
            skipped += 1
            continue
        sheet.cell(row, target_index, value)
        updated += 1
    _append_calculation_warning(warnings, skipped)
    return f"Ažurirana je kolona „{plan.target_column}” u {updated} redova na listu „{sheet.title}”."


def _filter_rows(sheet: Worksheet, plan: FilterRowsPlan) -> str:
    column_index, condition = _resolved_condition(sheet, plan.condition)
    removed = 0
    for row in range(sheet.max_row, 1, -1):
        if not _condition_matches(sheet.cell(row, column_index).value, condition):
            sheet.delete_rows(row)
            removed += 1
    return f"Filter je primenjen na list „{sheet.title}”; uklonjeno je {removed} redova."


def _sort_rows(sheet: Worksheet, plan: SortRowsPlan) -> str:
    column_index = _resolve_column(sheet, plan.column)
    rows = [
        [_snapshot(cell) for cell in sheet[row]]
        for row in range(2, sheet.max_row + 1)
    ]
    populated = [row for row in rows if _sort_key(row[column_index - 1].value)[0] != 2]
    blank = [row for row in rows if _sort_key(row[column_index - 1].value)[0] == 2]
    populated.sort(
        key=lambda row: _sort_key(row[column_index - 1].value),
        reverse=plan.direction == "descending",
    )
    rows = populated + blank
    for row_index, snapshots in enumerate(rows, start=2):
        for column_index_out, snapshot in enumerate(snapshots, start=1):
            _restore(sheet.cell(row_index, column_index_out), snapshot)
    direction = "opadajuće" if plan.direction == "descending" else "rastuće"
    return f"Radni list „{sheet.title}” je sortiran po koloni „{plan.column}” {direction}."


def _rename_column(sheet: Worksheet, plan: RenameColumnPlan) -> str:
    source_index = _resolve_column(sheet, plan.source_column)
    if _normalized(plan.source_column) != _normalized(plan.target_column):
        try:
            existing = _resolve_column(sheet, plan.target_column)
        except SpreadsheetTransformationError as exc:
            if "ne postoji" not in str(exc):
                raise
        else:
            if existing != source_index:
                raise SpreadsheetTransformationError(f"Kolona „{plan.target_column}” već postoji.")
    sheet.cell(1, source_index, plan.target_column)
    return f"Kolona „{plan.source_column}” je preimenovana u „{plan.target_column}” na listu „{sheet.title}”."


def _create_summary_sheet(workbook, plan: CreateSummarySheetPlan, warnings: list[str]) -> str:
    source = _resolve_sheet(workbook, plan.sheet)
    if any(_normalized(sheet.title) == _normalized(plan.target_sheet) for sheet in workbook.worksheets):
        raise SpreadsheetTransformationError(f"Radni list „{plan.target_sheet}” već postoji.")
    if any(character in plan.target_sheet for character in "\\/*?:[]"):
        raise SpreadsheetTransformationError("Naziv novog radnog lista sadrži nedozvoljene znakove.")
    group_index = _resolve_column(source, plan.group_by_column)
    value_index = _resolve_column(source, plan.value_column)
    groups: dict[str, list[Decimal]] = {}
    skipped = 0
    for row in range(2, source.max_row + 1):
        group = source.cell(row, group_index).value
        number = _number(source.cell(row, value_index).value)
        if group is None or not str(group).strip() or number is None:
            skipped += 1
            continue
        groups.setdefault(str(group).strip(), []).append(number)
    if not groups:
        raise SpreadsheetTransformationError("Nema dovoljno numeričkih podataka za sažetak.")
    target = workbook.create_sheet(plan.target_sheet)
    target.append([plan.group_by_column, f"{plan.aggregation}_{plan.value_column}"])
    for group, values in groups.items():
        if plan.aggregation == "sum":
            aggregated = sum(values, Decimal(0))
        elif plan.aggregation == "average":
            aggregated = sum(values, Decimal(0)) / len(values)
        else:
            aggregated = Decimal(len(values))
        target.append([group, _excel_number(aggregated)])
    _append_calculation_warning(warnings, skipped)
    return f"Napravljen je radni list „{plan.target_sheet}” sa agregacijom {plan.aggregation} po koloni „{plan.group_by_column}”."


def _expression_columns(sheet: Worksheet, expression: ArithmeticExpression) -> tuple[int, int | None]:
    left = _resolve_column(sheet, expression.left_column)
    right = _resolve_column(sheet, expression.right_column) if expression.right_column else None
    return left, right


def _calculate(sheet: Worksheet, row: int, expression: ArithmeticExpression, indexes: tuple[int, int | None]):
    left = _number(sheet.cell(row, indexes[0]).value)
    right = _number(sheet.cell(row, indexes[1]).value) if indexes[1] else Decimal(str(expression.right_value))
    if left is None or right is None:
        return None
    if expression.operator == "add":
        result = left + right
    elif expression.operator == "subtract":
        result = left - right
    elif expression.operator == "multiply":
        result = left * right
    elif expression.operator == "divide":
        if right == 0:
            return None
        result = left / right
    else:
        if left == 0:
            return None
        result = (left - right) / left
    return _excel_number(result)


def _resolved_condition(sheet: Worksheet, condition: RowCondition) -> tuple[int, RowCondition]:
    return _resolve_column(sheet, condition.column), condition


def _condition_matches(actual: object, condition: RowCondition) -> bool:
    if condition.comparator == "contains":
        return _normalized(str(condition.value)) in _normalized(str(actual or ""))
    actual_number = _number(actual)
    expected_number = _number(condition.value)
    if actual_number is not None and expected_number is not None:
        left, right = actual_number, expected_number
    else:
        left, right = _normalized(str(actual or "")), _normalized(str(condition.value))
    return {
        "equals": left == right,
        "not_equals": left != right,
        "greater_than": left > right,
        "greater_or_equal": left >= right,
        "less_than": left < right,
        "less_or_equal": left <= right,
    }.get(condition.comparator, False)


def _number(value: object) -> Decimal | None:
    if value is None or isinstance(value, bool) or (isinstance(value, str) and value.startswith("=")):
        return None
    try:
        if isinstance(value, str):
            normalized = value.strip().replace(" ", "").replace(",", ".")
            return Decimal(normalized) if normalized else None
        return Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None


def _excel_number(value: Decimal) -> int | float:
    return int(value) if value == value.to_integral_value() else float(value)


def _sort_key(value: object) -> tuple[int, object]:
    if value is None or value == "":
        return (2, "")
    number = _number(value)
    return (0, number) if number is not None else (1, _normalized(str(value)))


def _snapshot(cell: Cell) -> _CellSnapshot:
    return _CellSnapshot(cell.value, copy(cell._style), copy(cell.hyperlink), copy(cell.comment))


def _restore(cell: Cell, snapshot: _CellSnapshot) -> None:
    cell.value = snapshot.value
    cell._style = copy(snapshot.style)
    cell.hyperlink = copy(snapshot.hyperlink)
    cell.comment = copy(snapshot.comment)


def _append_calculation_warning(warnings: list[str], skipped: int) -> None:
    if skipped:
        warnings.append(f"Preskočeno je {skipped} redova zbog praznih, nenumeričkih ili nedozvoljenih vrednosti.")


def _normalized(value: str) -> str:
    value = value.casefold().replace("đ", "dj")
    decomposed = unicodedata.normalize("NFKD", value)
    return "".join(char for char in decomposed if not unicodedata.combining(char) and char.isalnum())


def _tokens(value: str) -> list[str]:
    value = value.casefold().replace("đ", "dj")
    decomposed = unicodedata.normalize("NFKD", value)
    plain = "".join(char for char in decomposed if not unicodedata.combining(char))
    return [token for token in re.split(r"[^a-z0-9]+", plain) if token]


def _output_filename(filename: str) -> str:
    stem = PurePath(filename).stem[:180].strip(" .") or "workbook"
    return f"{stem}_transformed.xlsx"

