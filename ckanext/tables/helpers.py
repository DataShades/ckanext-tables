import json
from typing import Any

from flask.globals import request

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


def tables_get_table(table_name: str) -> table.TableDefinition | None:
    """Get a table definition by its name.

    Args:
        table_name: The name of the table to get

    Returns:
        The table definition or None if the table does not exist
    """
    table_class = table.table_registry.get(table_name)

    if not table_class:
        return None

    try:
        table_class.check_access({"user": tk.current_user.name})
    except tk.NotAuthorized:
        return None

    return table_class


def tables_get_filters_from_request() -> list[dict[str, str]]:
    """Get the filters from the request arguments.

    Returns:
        A dictionary of filters
    """
    fields = tk.request.args.getlist("field")
    operators = tk.request.args.getlist("operator")
    values = tk.request.args.getlist("q")

    return [
        {"field": f, "operator": op, "q": q}
        for f, op, q in zip(fields, operators, values, strict=True)
    ]
