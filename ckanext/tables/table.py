from __future__ import annotations

import uuid
from collections.abc import Callable
from dataclasses import dataclass
from dataclasses import field as dataclass_field
from typing import Any

import ckan.plugins.toolkit as tk
from ckan.types import Context

from ckanext.tables.data_sources import BaseDataSource
from ckanext.tables.types import GlobalActionHandlerResult, Row


@dataclass
class QueryParams:
    page: int = 1
    size: int = 10
    field: str | None = None
    operator: str | None = None
    value: str | None = None
    sort_by: str | None = None
    sort_order: str | None = None


@dataclass
class TableDefinition:
    """Table definition.

    Attributes:
        name: Unique identifier for the table.
        data_source: Data source for the table.
        ajax_url: (Optional) URL to fetch data from. Defaults to an auto-generated URL.
        columns: (Optional) List of ColumnDefinition objects.
        actions: (Optional) List of ActionDefinition objects for each row.
        global_actions: (Optional) List of GlobalActionDefinition objects for bulk actions.
        placeholder: (Optional) Placeholder text for an empty table.
        page_size: (Optional) Number of rows per page. Defaults to 10.
        table_action_snippet: (Optional) Snippet to render table actions.
        table_template: (Optional) Template to render the table. Defaults to "tables/base.html".
    """

    name: str
    data_source: BaseDataSource
    ajax_url: str | None = None
    columns: list[ColumnDefinition] = dataclass_field(default_factory=list)
    actions: list[ActionDefinition] = dataclass_field(default_factory=list)
    global_actions: list[GlobalActionDefinition] = dataclass_field(default_factory=list)
    placeholder: str | None = None
    page_size: int = 10
    table_action_snippet: str | None = None
    table_template: str = "tables/base.html"

    def __post_init__(self):
        self.id = f"table_{self.name}_{uuid.uuid4().hex[:8]}"

        if self.ajax_url is None:
            self.ajax_url = tk.url_for("tables.ajax", table_name=self.name)

        if self.placeholder is None:
            self.placeholder = tk._("No data found")

        if self.global_actions:
            self.selectable = True

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
        }

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

    def get_data(self, params: QueryParams) -> list[Any]:
        """Get the data for the table with applied formatters."""
        self._formatters = tk.h.tables_get_all_formatters()

        return [self.apply_formatters(dict(row)) for row in self.get_raw_data(params)]

    def get_raw_data(self, params: QueryParams) -> list[dict[str, Any]]:
        return (
            self.data_source.filter(params.field, params.operator, params.value)
            .sort(params.sort_by, params.sort_order)
            .paginate(params.page, params.size)
            .all()
        )

    def get_total_count(self, params: QueryParams) -> int:
        # for total count we only apply filter, without sort and pagination
        return self.data_source.filter(params.field, params.operator, params.value).count()

    def apply_formatters(self, row: dict[str, Any]) -> dict[str, Any]:
        """Apply formatters to each cell in a row."""
        for column in self.columns:
            cell_value = row.get(column.field)

            if not column.formatters:
                continue

            for formatter, formatter_options in column.formatters:
                formatter_function = self._formatters[formatter]

                cell_value = formatter_function(cell_value, formatter_options, column, row, self)

            row[column.field] = cell_value

        return row

    @classmethod
    def check_access(cls, context: Context) -> None:
        """Check if the current user has access to view the table.

        Args:
            context: The CKAN auth context

        Raises:
            tk.NotAuthorized: if the user does not have access
        """
        tk.check_access("package_search", context)

    def get_global_action(self, action: str) -> GlobalActionDefinition | None:
        for ga in self.global_actions:
            if ga.action != action:
                continue
            return ga

        return None


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
    formatters: list[tuple[str, dict[str, Any]]] = dataclass_field(default_factory=list)
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
class ActionDefinition:
    """Defines an action that can be performed on a row.

    Attributes:
        name: Unique identifier for the action.
        label: Display label for the action.
        icon: CSS class for an icon (e.g., "fa fa-edit").
        url: A static URL for the action's link.
        endpoint: A dynamic endpoint to generate a URL.
        url_params: A dictionary of parameters to use when generating a URL from an endpoint.
        css_class: An additional CSS class for styling the action's link or button.
        attrs: A dictionary of extra HTML attributes to add to the action's link.
    """

    name: str
    label: str | None = None
    icon: str | None = None
    url: str | None = None
    endpoint: str | None = None
    url_params: dict[str, Any] = dataclass_field(default_factory=dict)
    css_class: str | None = None
    attrs: dict[str, Any] = dataclass_field(default_factory=dict)

    def __post_init__(self):
        if self.url and self.endpoint:
            raise ValueError("Provide either a `url` or an `endpoint`, but not both.")  # noqa: TRY003

    def get_url(self, row: Row) -> str:
        if self.endpoint:
            return tk.h.tables_build_url_from_params(self.endpoint, self.url_params, row)

        if self.url:
            return self.url

        return "#"


@dataclass(frozen=True)
class GlobalActionDefinition:
    """Defines an action that can be performed on multiple rows."""

    action: str
    label: str
    callback: Callable[[list[Row]], GlobalActionHandlerResult]

    def __call__(self, rows: list[Row]) -> GlobalActionHandlerResult:
        return self.callback(rows)
