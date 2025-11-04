from __future__ import annotations

from collections.abc import Callable
from typing import Any, TypeAlias, TypedDict

from typing_extensions import NotRequired

Value: TypeAlias = Any
Options: TypeAlias = "dict[str, Any]"
Row: TypeAlias = dict[str, Any]
FormatterResult: TypeAlias = str

BulkActionHandler: TypeAlias = Callable[[Row], "BulkActionHandlerResult"]
TableActionHandler: TypeAlias = Callable[[], "ActionHandlerResult"]
RowActionHandler: TypeAlias = Callable[[Row], "ActionHandlerResult"]


class BulkActionHandlerResult(TypedDict):
    success: bool
    error: NotRequired[str | None]


class ActionHandlerResult(TypedDict):
    success: bool
    error: NotRequired[str | None]
    redirect: NotRequired[str | None]
    message: NotRequired[str | None]
