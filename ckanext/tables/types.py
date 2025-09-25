from __future__ import annotations

from collections.abc import Callable, Hashable
from typing import Any, Generic, TypeAlias, TypeVar

import ckan.plugins.toolkit as tk

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
