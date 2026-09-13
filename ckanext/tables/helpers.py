import json
import uuid
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.tables.table import COLUMN_ACTIONS_FIELD
from ckanext.tables.types import FILTER_OPERATORS, FilterItem


def tables_json_dumps(value: Any) -> str:
    """Convert a value to a JSON string.

    Args:
        value: The value to convert to a JSON string

    Returns:
        The JSON string
    """
    return json.dumps(value)


def tables_get_filters_from_request() -> list[FilterItem]:
    """Get the filters from the request arguments.

    Returns:
        A dictionary of filters
    """
    fields = tk.request.args.getlist("field")
    operators = tk.request.args.getlist("operator")
    values = tk.request.args.getlist("value")

    filters = []

    for field, op, value in zip(fields, operators, values):  # noqa: B905
        if not field or not op or not value:
            continue
        filters.append(FilterItem(field=field, operator=op, value=value))

    return filters


def tables_get_columns_visibility_from_request() -> dict[str, bool]:
    """Get the column visibility settings from the request arguments.

    Returns:
        A dictionary mapping column field names to their visibility state (True/False).
        Only hidden columns are included in the dictionary with False value.
    """
    return dict.fromkeys(tk.request.args.getlist("hidden_column"), False)


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
