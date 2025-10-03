from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

import ckan.plugins.toolkit as tk
from ckan.types import Context

from ckanext.tables import formatters, types
from ckanext.tables.data_sources import BaseDataSource

table_registry: types.Registry[str, TableDefinition] = types.Registry({})


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


@dataclass
class TableDefinition:
    """Table definition.

    Attributes:
        name: Unique identifier for the table.
        data_source: Data source for the table.
        ajax_url: (Optional) URL to fetch data from. Defaults to an auto-generated URL.
        columns: (Optional) List of ColumnDefinition objects.
        row_actions: (Optional) List of RowActionDefinition objects.
        bulk_actions: (Optional) List of BulkActionDefinition objects for action on multiple rows.
        table_actions: (Optional) List of TableActionDefinition objects for actions on the table itself.
        placeholder: (Optional) Placeholder text for an empty table.
        page_size: (Optional) Number of rows per page. Defaults to 10.
        table_template: (Optional) Template to render the table. Defaults to `tables/base.html`.
    """

    name: str
    data_source: BaseDataSource
    ajax_url: str | None = None
    columns: list[ColumnDefinition] = dataclass_field(default_factory=list)
    row_actions: list[RowActionDefinition] = dataclass_field(default_factory=list)
    bulk_actions: list[BulkActionDefinition] = dataclass_field(default_factory=list)
    table_actions: list[TableActionDefinition] = dataclass_field(default_factory=list)
    placeholder: str | None = None
    page_size: int = 10
    table_template: str = "tables/base.html"

    def __post_init__(self):
        self.id = f"table_{self.name}_{uuid.uuid4().hex[:8]}"
        self.selectable = bool(self.bulk_actions)

        if self.ajax_url is None:
            self.ajax_url = tk.url_for("tables.ajax", table_name=self.name)

        if self.placeholder is None:
            self.placeholder = tk._("No data found")

        if self.row_actions:
            self.columns.append(
                ColumnDefinition(
                    field="table_actions",
                    title=tk._(""),
                    formatters=[(formatters.ActionsFormatter, {})],
                    filterable=False,
                    tabulator_formatter="html",
                    sortable=False,
                    resizable=False,
                    width=50,
                ),
            )

    def get_tabulator_config(self) -> dict[str, Any]:
        columns = [col.to_dict() for col in self.columns]

        options = {
            "columns": columns,
            "placeholder": self.placeholder,
            "ajaxURL": self.ajax_url,
            "sortMode": "remote",
            "layout": "fitColumns",
            "pagination": True,
            "paginationMode": "remote",
            "paginationSize": self.page_size,
            "paginationSizeSelector": [5, 10, 25, 50, 100],
            "minHeight": 300,
        }

        if self.selectable:
            options.update(
                {
                    "rowHeader": {
                        "headerSort": False,
                        "resizable": False,
                        "headerHozAlign": "center",
                        "hozAlign": "center",
                        "vertAlign": "middle",
                        "formatter": "rowSelection",
                        "titleFormatter": "rowSelection",
                        "width": 50,
                    }
                }
            )

        return options

    def get_row_actions(self) -> dict[str, dict[str, Any]]:
        return {
            action.action: {
                "name": action.action,
                "label": action.label,
                "icon": action.icon,
                "with_confirmation": action.with_confirmation,
            }
            for action in self.row_actions
        }

    def render_table(self, **kwargs: Any) -> str:
        return tk.render(self.table_template, extra_vars={"table": self, **kwargs})

    def get_data(self, params: QueryParams) -> list[Any]:
        return [self._apply_formatters(dict(row)) for row in self.get_raw_data(params)]

    def get_raw_data(self, params: QueryParams) -> list[dict[str, Any]]:
        return (
            self.data_source.filter(params.filters)
            .sort(params.sort_by, params.sort_order)
            .paginate(params.page, params.size)
            .all()
        )

    def get_total_count(self, params: QueryParams) -> int:
        # for total count we only apply filter, without sort and pagination
        return self.data_source.filter(params.filters).count()

    def _apply_formatters(self, row: dict[str, Any]) -> dict[str, Any]:
        """Apply formatters to each cell in a row."""
        for column in self.columns:
            cell_value = row.get(column.field)

            if not column.formatters:
                continue

            for formatter_class, formatter_options in column.formatters:
                cell_value = formatter_class(column, row, self).format(cell_value, formatter_options)

            row[column.field] = cell_value

        return row

    @classmethod
    def check_access(cls, context: Context) -> None:
        """Check if the current user has access to view the table.

        This class method can be overridden in subclasses to implement
        custom access control logic.

        By default, it checks if the user has the `package_search` permission,
        which means that the table is publicly accessible.

        Raises:
            tk.NotAuthorized: If the user does not have an access
        """
        tk.check_access("package_search", context)

    def get_bulk_action(self, action: str) -> BulkActionDefinition | None:
        return self._get_action(self.bulk_actions, action)

    def get_table_action(self, action: str) -> TableActionDefinition | None:
        return self._get_action(self.table_actions, action)

    def get_row_action(self, action: str) -> RowActionDefinition | None:
        return self._get_action(self.row_actions, action)

    def _get_action(self, actions: list[Any], action: str):
        return next((a for a in actions if a.action == action), None)


@dataclass(frozen=True)
class ColumnDefinition:
    """Column definition.

    Attributes:
        field: The field name in the data dictionary.
        title: The display title for the column. Defaults to a formatted version of `field`.
        formatters: List of custom server-side formatters to apply to the column's value.
        tabulator_formatter: The name of a built-in Tabulator.js formatter (e.g., "plaintext").
        tabulator_formatter_params: Parameters for the built-in tabulator formatter.
        width: The width of the column in pixels.
        min_width: The minimum width of the column in pixels.
        visible: Whether the column is visible.
        sorter: The default sorter for the column (e.g., "string", "number").
        filterable: Whether the column can be filtered by the user.
        resizable: Whether the column is resizable by the user.
    """

    field: str
    title: str | None = None
    formatters: list[tuple[type[formatters.BaseFormatter], dict[str, Any]]] = dataclass_field(default_factory=list)
    tabulator_formatter: str | None = None
    tabulator_formatter_params: dict[str, Any] = dataclass_field(default_factory=dict)
    width: int | None = None
    min_width: int | None = None
    visible: bool = True
    sortable: bool = True
    filterable: bool = True
    resizable: bool = True

    def __post_init__(self):
        if self.title is None:
            object.__setattr__(self, "title", self.field.replace("_", " ").title())

    def to_dict(self) -> dict[str, Any]:
        """Convert the column definition to a dict for JSON serialization."""
        result = {
            "field": self.field,
            "title": self.title,
            "visible": self.visible,
            "resizable": self.resizable,
        }

        mappings = {
            "width": "width",
            "min_width": "minWidth",
            "tabulator_formatter": "formatter",
            "tabulator_formatter_params": "formatterParams",
        }

        for name, tabulator_name in mappings.items():
            if value := getattr(self, name):
                result[tabulator_name] = value

        if self.sortable:
            result["sorter"] = "string"
        else:
            result["headerSort"] = False

        return result


@dataclass(frozen=True)
class BulkActionDefinition:
    """Defines an action that can be performed on multiple rows."""

    action: str
    label: str
    callback: Callable[[types.Row], types.BulkActionHandlerResult]
    icon: str | None = None

    def __call__(self, row: types.Row) -> types.BulkActionHandlerResult:
        return self.callback(row)


@dataclass(frozen=True)
class TableActionDefinition(BulkActionDefinition):
    """Defines an action that can be performed on the table itself."""

    callback: Callable[..., types.TableActionHandlerResult]


@dataclass(frozen=True)
class RowActionDefinition:
    """Defines an action that can be performed on a row."""

    action: str
    label: str
    callback: Callable[[types.Row], types.RowActionHandlerResult]
    icon: str | None = None
    with_confirmation: bool = False

    def __call__(self, row: types.Row) -> types.RowActionHandlerResult:
        return self.callback(row)
