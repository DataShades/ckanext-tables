from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any, TypeAlias, TypedDict

from typing_extensions import NotRequired

Value: TypeAlias = Any
Options: TypeAlias = "dict[str, Any]"
Row: TypeAlias = dict[str, Any]
FormatterResult: TypeAlias = str

BulkActionHandler: TypeAlias = Callable[[list[Row]], "ActionHandlerResult"]
TableActionHandler: TypeAlias = Callable[[], "ActionHandlerResult"]
RowActionHandler: TypeAlias = Callable[[Row], "ActionHandlerResult"]


class ActionHandlerResult(TypedDict):
    """Represents the result of an action handler.

    Attributes:
        success: Indicates whether the action was successful.
        error: (Optional) Error message if the action failed.
        redirect: (Optional) URL to redirect to after the action.
        message: (Optional) Informational message about the action result.
    """

    success: bool
    error: NotRequired[str | None]
    redirect: NotRequired[str | None]
    message: NotRequired[str | None]


@dataclass
class QueryParams:
    page: int = 1
    size: int = 10
    filters: list[FilterItem] = dataclass_field(default_factory=list)
    sort_by: str | None = None
    sort_order: str | None = None


@dataclass(frozen=True)
class FilterItem:
    field: str
    operator: str
    value: Any
