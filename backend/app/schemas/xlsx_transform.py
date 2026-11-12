from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, model_validator


class ArithmeticExpression(BaseModel):
    model_config = ConfigDict(extra="forbid")

    operator: Literal["add", "subtract", "multiply", "divide", "percentage"]
    left_column: str = Field(min_length=1, max_length=200)
    right_column: str | None = Field(default=None, min_length=1, max_length=200)
    right_value: float | None = None

    @model_validator(mode="after")
    def exactly_one_right_operand(self) -> "ArithmeticExpression":
        if (self.right_column is None) == (self.right_value is None):
            raise ValueError("exactly one right operand is required")
        return self


class RowCondition(BaseModel):
    model_config = ConfigDict(extra="forbid")

    column: str = Field(min_length=1, max_length=200)
    comparator: Literal["equals", "not_equals", "greater_than", "greater_or_equal", "less_than", "less_or_equal", "contains"]
    value: str | float


class AddColumnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["add_column"]
    sheet: str | None = Field(default=None, max_length=100)
    target_column: str = Field(min_length=1, max_length=200)
    expression: ArithmeticExpression


class UpdateColumnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["update_column"]
    sheet: str | None = Field(default=None, max_length=100)
    target_column: str = Field(min_length=1, max_length=200)
    expression: ArithmeticExpression
    condition: RowCondition | None = None


class FilterRowsPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["filter_rows"]
    sheet: str | None = Field(default=None, max_length=100)
    condition: RowCondition


class SortRowsPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["sort_rows"]
    sheet: str | None = Field(default=None, max_length=100)
    column: str = Field(min_length=1, max_length=200)
    direction: Literal["ascending", "descending"]


class RenameColumnPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["rename_column"]
    sheet: str | None = Field(default=None, max_length=100)
    source_column: str = Field(min_length=1, max_length=200)
    target_column: str = Field(min_length=1, max_length=200)


class CreateSummarySheetPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["create_summary_sheet"]
    sheet: str | None = Field(default=None, max_length=100)
    target_sheet: str = Field(min_length=1, max_length=31)
    group_by_column: str = Field(min_length=1, max_length=200)
    value_column: str = Field(min_length=1, max_length=200)
    aggregation: Literal["sum", "average", "count"]


class UnsupportedPlan(BaseModel):
    model_config = ConfigDict(extra="forbid")
    operation: Literal["unsupported"]
    reason: str = Field(min_length=1, max_length=500)


TransformationPlan = Annotated[
    AddColumnPlan | UpdateColumnPlan | FilterRowsPlan | SortRowsPlan | RenameColumnPlan | CreateSummarySheetPlan | UnsupportedPlan,
    Field(discriminator="operation"),
]


class TransformationPlanEnvelope(BaseModel):
    model_config = ConfigDict(extra="forbid")
    plan: TransformationPlan

