import json
import uuid
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.tables.table import COLUMN_ACTIONS_FIELD
from ckanext.tables.types import FILTER_OPERATORS, FilterItem

SHEET_PARAM = "sheet"


def tables_json_dumps(value: Any) -> str:
    """Convert a value to a JSON string.

    Args:
        value: The value to convert to a JSON string

    Returns:
        The JSON string
    """
    return json.dumps(value)


def tables_get_filters_from_request(table_name: str) -> list[FilterItem]:
    """Get the filters from the request arguments.

    Args:
        table_name: The table's own name.

    Returns:
        A dictionary of filters
    """
    fields = tk.request.args.getlist(f"field-{table_name}")
    operators = tk.request.args.getlist(f"operator-{table_name}")
    values = tk.request.args.getlist(f"value-{table_name}")

    filters = []

    for field, op, value in zip(fields, operators, values):  # noqa: B905
        if not field or not op or not value:
            continue
        filters.append(FilterItem(field=field, operator=op, value=value))

    return filters


def tables_get_columns_visibility_from_request(table_name: str) -> dict[str, bool]:
    """Get the column visibility settings from the request arguments.

    Args:
        table_name: The table's own name. The request argument is namespaced by
            it (``hidden_column-<table_name>``), same as every other bit of
            per-table state the frontend persists to the URL (see
            ``tables-tabulator.ts``'s ``_urlKey``) — so two tables on one page,
            or two sheets of the same resource, never collide.

    Returns:
        A dictionary mapping column field names to their visibility state (True/False).
        Only hidden columns are included in the dictionary with False value.
    """
    return dict.fromkeys(tk.request.args.getlist(f"hidden_column-{table_name}"), False)


def tables_generate_unique_id() -> str:
    return str(uuid.uuid4())


def tables_column_actions_field() -> str:
    """Return the synthetic field name used for the row-actions column.

    Lets templates recognise/exclude it without duplicating the constant.
    """
    return COLUMN_ACTIONS_FIELD


def tables_filter_operators() -> list[dict[str, str]]:
    """Return the filter-operator dropdown options, with translated labels.

    Single source for ``value``/``operator`` in every filter UI, translated
    here (render time) rather than baked into the ``FILTER_OPERATORS``
    constant at import time.
    """
    return [{"value": value, "label": tk._(label)} for value, label in FILTER_OPERATORS]


def tables_requested_sheet() -> int:
    """Return the sheet index the current request asks for, or 0.

    Anything that isn't a usable index — absent, not a number, negative —
    means the first sheet. A number past the end of the workbook is left to
    ``tables_init_temporary_preview_table``, which is the first place that
    knows how many sheets there actually are.
    """
    return max(0, tk.request.args.get(SHEET_PARAM, 0, int))


def tables_deferred_url(resource_id: str, resource_view_id: str) -> str:
    """Return the deferred-render URL, carrying the current request's own query string."""
    base = tk.url_for("tables.resource_table_deferred", resource_id=resource_id, resource_view_id=resource_view_id)
    qs = tk.request.query_string.decode("utf-8")

    return f"{base}?{qs}" if qs else base
