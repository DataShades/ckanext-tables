from __future__ import annotations

import uuid
from abc import abstractmethod
from collections.abc import Callable
from dataclasses import dataclass
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer
from sqlalchemy.orm import Query
from sqlalchemy.sql import Select
from sqlalchemy.sql.elements import BinaryExpression, ClauseElement, ColumnElement

import ckan.plugins.toolkit as tk


@dataclass
class QueryParams:
    page: int = 1
    size: int = 10
    field: str | None = None
    operator: str | None = None
    value: str | None = None
    sort_by: str | None = None
    sort_order: str | None = None


class TableDefinition:
    """Defines a table to be rendered with Tabulator."""

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        ajax_url: str,
        columns: list[ColumnDefinition] | None = None,
        actions: list[ActionDefinition] | None = None,
        global_actions: list[GlobalActionDefinition] | None = None,
        placeholder: str | None = None,
        pagination: bool = True,
        page_size: int = 10,
        selectable: bool = False,
        table_action_snippet: str | None = None,
        table_template: str = "tables/base.html",
    ):
        """Initialize a table definition.

        Args:
            name (str): Unique identifier for the table
            ajax_url (str): URL to fetch data from
            columns (list, optional): List of ColumnDefinition objects
            actions (list, optional): List of ActionDefinition objects
            global_actions (list, optional): List of GlobalActionDefinition objects
            placeholder (str, optional): Placeholder text for the table
            pagination (bool): Whether to enable pagination
            page_size (int): Number of rows per page
            selectable (bool): Whether rows can be selected
            table_action_snippet (optional): Snippet to render table actions
            table_template (optional): Template to render the table
        """
        self.id = f"table_{name}_{uuid.uuid4().hex[:8]}"
        self.name = name
        self.ajax_url = ajax_url
        self.columns = columns or []
        self.actions = actions or []
        self.global_actions = global_actions or []
        self.placeholder = placeholder or "No data found"
        self.pagination = pagination
        self.page_size = page_size
        self.selectable = True if self.global_actions else selectable
        self.table_action_snippet = table_action_snippet
        self.table_template = table_template

    def get_tabulator_config(self) -> dict[str, Any]:
        columns = [col.to_dict() for col in self.columns]

        options = {
            "columns": columns,
            "placeholder": self.placeholder,
            "ajaxURL": self.ajax_url,
            "sortMode": "remote",
            "layout": "fitData",
        }

        if self.pagination:
            options.update(
                {
                    "pagination": True,
                    "paginationMode": "remote",
                    "paginationSize": self.page_size,
                    "paginationSizeSelector": [5, 10, 25, 50, 100],
                }
            )

        if self.selectable or self.global_actions:
            options.update(
                {
                    "selectableRows": True,
                    "selectableRangeMode": "click",
                    "selectableRollingSelection": False,
                    "selectablePersistence": False,
                }
            )

        return options

    def render_table(self, **kwargs: Any) -> str:
        return tk.render(self.table_template, extra_vars={"table": self, **kwargs})

    @abstractmethod
    def get_raw_data(self, params: QueryParams) -> list[dict[str, Any]]:
        """Return the list of rows to be rendered in the table.

        Args:
            params: Query parameters

        Returns:
            list[dict[str, Any]]: List of rows to be rendered in the table
        """

    @abstractmethod
    def get_total_count(self, params: QueryParams) -> int:
        """Return the total number of rows in the table."""

    def get_data(self, params: QueryParams) -> list[Any]:
        """Get the data for the table with applied formatters."""
        self._formatters = tk.h.tables_get_all_formatters()

        return [self.apply_formatters(dict(row)) for row in self.get_raw_data(params)]

    def filter_query(
        self,
        stmt: Select,
        model: type[Any],
        params: QueryParams,
        apply_pagination: bool = True,
    ) -> Select:
        # Filtering
        if params.field and params.operator and params.value:
            column = getattr(model, params.field, None)

            if column:
                filter_expr = self.build_filter(column, params.operator, params.value)
                if filter_expr is not None:
                    stmt = stmt.where(filter_expr)

        # Sorting
        if params.sort_by and hasattr(model, params.sort_by):
            column = getattr(model, params.sort_by)
            if params.sort_order and params.sort_order.lower() == "desc":
                stmt = stmt.order_by(column.desc())
            else:
                stmt = stmt.order_by(column.asc())

        # Pagination
        if apply_pagination and params.page and params.size:
            stmt = stmt.limit(params.size).offset((params.page - 1) * params.size)

        return stmt

    def build_filter(
        self, column: ColumnElement, operator: str, value: str
    ) -> BinaryExpression | ClauseElement | None:
        try:
            if isinstance(column.type, Boolean):
                casted_value = value.lower() in ("true", "1", "yes", "y")
            elif isinstance(column.type, Integer):
                casted_value = int(value)
            elif isinstance(column.type, DateTime):
                casted_value = datetime.fromisoformat(value)
            else:
                casted_value = str(value)
        except ValueError:
            return None

        operators: dict[
            str,
            Callable[[ColumnElement, Any], BinaryExpression | ClauseElement | None],
        ] = {
            "=": lambda col, val: col == val,
            "<": lambda col, val: col < val,
            "<=": lambda col, val: col <= val,
            ">": lambda col, val: col > val,
            ">=": lambda col, val: col >= val,
            "!=": lambda col, val: col != val,
            "like": lambda col, val: (
                col.ilike(f"%{val}%") if isinstance(val, str) else None
            ),
        }

        func = operators.get(operator)

        return func(column, casted_value) if func else None

    def apply_formatters(self, row: dict[str, Any]) -> dict[str, Any]:
        """Apply formatters to each cell in a row."""
        for column in self.columns:
            cell_value = row.get(column.field)

            if not column.formatters:
                continue

            for formatter, formatter_options in column.formatters:
                formatter_function = self._formatters[formatter]

                cell_value = formatter_function(
                    cell_value, formatter_options, column, row, self
                )

            row[column.field] = cell_value

        return row


class ColumnDefinition:
    """Defines how a column should be rendered in Tabulator."""

    def __init__(  # noqa: PLR0913
        self,
        field: str,
        title: str | None = None,
        formatters: list[tuple[str, dict[str, Any]]] | None = None,
        tabulator_formatter: str | None = None,
        tabulator_formatter_params: dict[str, Any] | None = None,
        width: int | None = None,
        min_width: int | None = None,
        visible: bool = True,
        sorter: str | None = "string",
        filterable: bool = True,
        resizable: bool = True,
    ):
        """Initialize a column definition.

        Args:
            field: The field name in the data dict
            title: The display title for the column
            formatters: List of formatters to apply to the column
            tabulator_formatter: Tabulator formatter to apply to the column
            tabulator_formatter_params: Parameters for the tabulator formatter
            width: Width of the column
            min_width: Minimum width of the column
            visible: Whether the column is visible
            sorter: Default sorter for the column
            filterable: Whether the column can be filtered
            resizable: Whether the column is resizable
        """
        self.field = field
        self.title = title or field.replace("_", " ").title()
        self.formatters = formatters
        self.tabulator_formatter = tabulator_formatter
        self.tabulator_formatter_params = tabulator_formatter_params
        self.width = width
        self.min_width = min_width
        self.visible = visible
        self.sorter = sorter
        self.filterable = filterable
        self.resizable = resizable

    def __repr__(self):
        return f"ColumnDefinition(field={self.field}, title={self.title})"

    def to_dict(self) -> dict[str, Any]:
        """Convert the column definition to a dict for JSON serialization."""
        result = {
            "field": self.field,
            "title": self.title,
            "visible": self.visible,
            "resizable": self.resizable,
        }

        if self.sorter:
            result["sorter"] = self.sorter
        else:
            result["headerSort"] = False

        if self.tabulator_formatter:
            result["formatter"] = self.tabulator_formatter

        if self.tabulator_formatter_params:
            result["formatterParams"] = self.tabulator_formatter_params

        if self.width:
            result["width"] = self.width

        if self.min_width:
            result["minWidth"] = self.min_width

        return result


class ActionDefinition:
    """Defines an action that can be performed on a row."""

    def __init__(  # noqa: PLR0913
        self,
        name: str,
        label: str | None = None,
        icon: str | None = None,
        url: str | None = None,
        endpoint: str | None = None,
        url_params: dict[str, Any] | None = None,
        css_class: str | None = None,
        visible_callback: Callable[..., bool] | None = None,
        attrs: dict[str, Any] | None = None,
    ):
        """Initialize an action definition.

        Args:
            name: Unique identifier for the action
            label: Display label for the action
            icon: Icon class (e.g., "fa fa-edit")
            url: Static URL for the action
            endpoint: Flask endpoint to generate URL
            url_params: Parameters for the URL
            css_class: CSS class for styling
            visible_callback: Function that determines if action is visible
            attrs: Additional attributes for the action
        """
        self.name = name
        self.label = label
        self.icon = icon
        self.url = url
        self.endpoint = endpoint
        self.url_params = url_params
        self.css_class = css_class
        self.visible_callback = visible_callback
        self.attrs = attrs or {}

    def __repr__(self):
        return f"ActionDefinition(name={self.name})"

    def to_dict(self, row_data: Any | None = None):
        # Check if action should be visible for this row
        if self.visible_callback and row_data and not self.visible_callback(row_data):
            return None

        result = {
            "name": self.name,
            "label": self.label,
            "attrs": self.attrs,
        }

        if self.icon:
            result["icon"] = self.icon

        if self.css_class:
            result["cssClass"] = self.css_class

        return result


class GlobalActionDefinition:
    """Defines an action that can be performed on multiple rows."""

    def __init__(
        self,
        action: str,
        label: str,
    ):
        """Initialize a global action definition.

        Args:
            action (str): Unique identifier for the action
            label (str): Display label for the action
        """
        self.action = action
        self.label = label

    def __repr__(self):
        return f"GlobalActionDefinition(action={self.action}, label={self.label})"

    def to_dict(self):
        return {
            "action": self.action,
            "label": self.label,
        }
