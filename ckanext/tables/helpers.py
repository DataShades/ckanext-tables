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

    return [
        t.FilterItem(field=field, operator=op, value=value)
        for field, op, value in zip(fields, operators, values, strict=True)
    ]


def tables_get_columns_visibility_from_request() -> dict[str, bool]:
    """Get the column visibility settings from the request arguments.

    Returns:
        A dictionary mapping column field names to their visibility state (True/False).
        Only hidden columns are included in the dictionary with False value.
    """
    return dict.fromkeys(tk.request.args.getlist("hidden_column"), False)


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
    data_source = tk.h.tables_guess_data_source(resource)

    return t.TableDefinition(
        name=f"preview resource {resource['id']}",
        data_source=data_source,
        exporters=t.ALL_EXPORTERS,
        ajax_url=tk.url_for("tables.resource_table_ajax", resource_id=resource["id"]),
        columns=[t.ColumnDefinition(field=col) for col in data_source.get_columns()],
    )


def tables_guess_data_source(resource: dict[str, Any]) -> t.BaseDataSource:
    fmt = resource.get("format", "").lower()
    url = resource.get("url")

    if fmt == "csv":
        return t.CsvUrlDataSource(url=url, resource=resource)
    if fmt == "xlsx":
        return t.XlsxUrlDataSource(url=url, resource=resource)
    if fmt == "orc":
        return t.OrcUrlDataSource(url=url, resource=resource)
    if fmt == "parquet":
        return t.ParquetUrlDataSource(url=url, resource=resource)
    if fmt == "feather":
        return t.FeatherUrlDataSource(url=url, resource=resource)

    raise ValueError(f"Unsupported format: {fmt}")  # noqa: TRY003
