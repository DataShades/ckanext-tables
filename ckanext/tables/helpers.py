import json
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.tables import table, types


def tables_get_all_formatters() -> types.Registry[str, types.Formatter]:
    """Get all registered table cell formatters.

    A formatter is a function that takes a cell value and can modify its appearance
    in a table.

    Returns:
        A mapping of formatter names to formatter functions
    """
    for _, plugin_formatters in types.collect_formatters_signal.send():
        types.formatter_registry.update(plugin_formatters)

    return types.formatter_registry


def tables_json_dumps(value: Any) -> str:
    """Convert a value to a JSON string.

    Args:
        value: The value to convert to a JSON string

    Returns:
        The JSON string
    """
    return json.dumps(value)


def tables_build_url_from_params(endpoint: str, url_params: dict[str, Any], row: dict[str, Any]) -> str:
    """Build an action URL based on the endpoint and URL parameters.

    The url_params might contain values like $id, $type, etc.
    We need to replace them with the actual values from the row

    Args:
        endpoint: The endpoint to build the URL for
        url_params: The URL parameters to build the URL for
        row: The row to build the URL for
    """
    params = url_params.copy()

    for key, value in params.items():
        if value.startswith("$"):
            params[key] = row[value[1:]]

    return tk.url_for(endpoint, **params)


def tables_get_table(table_name: str) -> table.TableDefinition | None:
    """Get a table definition by its name.

    Args:
        table_name: The name of the table to get

    Returns:
        The table definition or None if the table does not exist
    """
    table_class = types.table_registry.get(table_name)

    if not table_class:
        return None

    table_class.check_access({"user": tk.current_user.name})

    return table_class
