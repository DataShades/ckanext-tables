import json
import uuid
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.tables import shared as t


def tables_json_dumps(value: Any) -> str:
    """Convert a value to a JSON string.

    Args:
        value: The value to convert to a JSON string

    Returns:
        The JSON string
    """
    return json.dumps(value)


def tables_get_filters_from_request() -> list[t.FilterItem]:
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
        filters.append(t.FilterItem(field=field, operator=op, value=value))

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
