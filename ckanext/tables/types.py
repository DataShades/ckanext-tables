from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import TYPE_CHECKING, Any, Generic, TypeAlias, TypeVar

import ckan.plugins.toolkit as tk

if TYPE_CHECKING:
    from ckanext.tables.table import ColumnDefinition, TableDefinition

K = TypeVar("K", bound=Hashable)
V = TypeVar("V")

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


collect_formatters_signal = tk.signals.ckanext.signal(
    "ckanext.tables.get_formatters",
    "Collect table cell formatters from plugins",
)

collect_tables_signal = tk.signals.ckanext.signal(
    "ckanext.tables.register_tables",
    "Register tables from plugins",
)


class Registry(dict[K, V], Generic[K, V]):
    """A generic registry to store and retrieve items."""

    def reset(self):
        """Clears all items from the registry."""
        self.clear()

    def register(self, name: K, member: V) -> None:
        """Directly register an item with a given name."""
        self[name] = member


table_registry: Registry[str, TableDefinition] = Registry({})
formatter_registry: Registry[str, Formatter] = Registry({})
