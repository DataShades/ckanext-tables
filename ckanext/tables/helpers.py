import csv
import json
import uuid
from typing import Any

import requests

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

    return [
        t.FilterItem(field=field, operator=op, value=value)
        for field, op, value in zip(fields, operators, values, strict=True)
    ]


def tables_generate_unique_id() -> str:
    return str(uuid.uuid4())


def tables_init_temporary_preview_table(
    resource: dict[str, Any],
) -> t.TableDefinition:
    """Initialize a temporary preview table for a given resource.

    Args:
        resource: The resource dictionary containing the URL and format of the data.

    Returns:
        A TableDefinition object representing the initialized temporary preview table.
    """
    data = _fetch_csv_from_url(resource["url"])
    columns = [t.ColumnDefinition(field=col) for col in data[0]] if data else []

    return t.TableDefinition(
        name=f"preview resource {resource['id']}",
        data_source=t.ListDataSource(data=data),
        exporters=t.ALL_EXPORTERS,
        ajax_url=tk.url_for("tables.resource_table_ajax", resource_id=resource["id"]),
        columns=columns,
    )


def _fetch_csv_from_url(url: str) -> list[dict[str, Any]]:
    """Fetch CSV data from a given URL and return it as a list of dictionaries.

    Args:
        url: The URL to fetch the CSV data from.

    Returns:
        A list of dictionaries representing the CSV data,
        where each dictionary corresponds to a row in the CSV file,
        with keys as column headers and values as cell values.
    """
    try:
        response = requests.get(url, timeout=10)
        response.raise_for_status()
    except requests.RequestException:
        return []

    decoded_content = response.content.decode("utf-8")
    lines = decoded_content.splitlines()

    if not lines:
        return []

    # Use csv.Sniffer to automatically detect the delimiter
    try:
        sample = "\n".join(lines[:5])  # Use first 5 lines as sample
        sniffer = csv.Sniffer()
        dialect = sniffer.sniff(sample)
        reader = csv.DictReader(lines, dialect=dialect)
    except csv.Error:
        reader = csv.DictReader(lines)

    return list(reader)
