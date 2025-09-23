from __future__ import annotations

from collections.abc import Callable
from typing import TYPE_CHECKING, Any, TypeAlias

if TYPE_CHECKING:
    from ckanext.tables.table import ColumnDefinition, TableDefinition

ItemList: TypeAlias = "list[dict[str, Any]]"
Item: TypeAlias = "dict[str, Any]"
ItemValue: TypeAlias = Any

Value: TypeAlias = Any
Options: TypeAlias = "dict[str, Any]"
Row: TypeAlias = dict[str, Any]
GlobalActionHandlerResult: TypeAlias = tuple[bool, str | None]
GlobalActionHandler: TypeAlias = Callable[[Row], GlobalActionHandlerResult]
FormatterResult: TypeAlias = str

Formatter: TypeAlias = Callable[
    [Value, Options, "ColumnDefinition", Row, "TableDefinition"],
    FormatterResult,
]
