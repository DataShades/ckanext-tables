import json
import uuid
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.tables import table


def tables_json_dumps(value: Any) -> str:
    """Convert a value to a JSON string.

    Args:
        value: The value to convert to a JSON string

    Returns:
        The JSON string
    """
    return json.dumps(value)


def tables_get_filters_from_request() -> list[table.FilterItem]:
    """Get the filters from the request arguments.

    Returns:
        A dictionary of filters
    """
    fields = tk.request.args.getlist("field")
    operators = tk.request.args.getlist("operator")
    values = tk.request.args.getlist("value")

    return [
        table.FilterItem(field=field, operator=op, value=value)
        for field, op, value in zip(fields, operators, values, strict=True)
    ]


def tables_generate_unique_id() -> str:
    return str(uuid.uuid4())
