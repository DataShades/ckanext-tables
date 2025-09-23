import json
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.tables import formatters, types

_formatter_cache: dict[str, types.Formatter] = {}

collect_formatters_signal = tk.signals.ckanext.signal(
    "ckanext.tables.get_formatters",
    "Collect table cell formatters from plugins",
)


def tables_get_all_formatters() -> dict[str, types.Formatter]:
    """Get all registered table cell formatters.

    A formatter is a function that takes a cell value and can modify its appearance
    in a table.

    Returns:
        A mapping of formatter names to formatter functions
    """
    if _formatter_cache:
        return _formatter_cache

    _formatter_cache.update(formatters.get_formatters())

    for _, plugin_formatters in collect_formatters_signal.send():
        _formatter_cache.update(plugin_formatters)

    return _formatter_cache


def tables_json_dumps(value: Any) -> str:
    """Convert a value to a JSON string.

    Args:
        value: The value to convert to a JSON string

    Returns:
        The JSON string
    """
    return json.dumps(value)


def tables_build_url_from_params(
    endpoint: str, url_params: dict[str, Any], row: dict[str, Any]
) -> str:
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
