import json
import uuid
from pathlib import Path
from typing import Any

import ckan.plugins.toolkit as tk

from ckanext.tables import shared as t
from ckanext.tables.config import get_cache_backend


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


def tables_init_temporary_preview_table(
    resource: dict[str, Any],
    resource_view: dict[str, Any] | None = None,
) -> t.TableDefinition:
    """Initialize a temporary preview table for a given resource.

    Args:
        resource: The resource dictionary containing the URL and format of the data.
        resource_view: Optional resource view dictionary. When it contains a
            ``file_url`` key that URL is used instead of the resource URL and
            the format is inferred from its file extension.

    Returns:
        A TableDefinition object representing the initialized temporary preview table.
    """
    data_source = tk.h.tables_guess_data_source(resource, resource_view)

    return t.TableDefinition(
        name=f"preview_resource_{resource['id']}_{resource_view['id']}",
        data_source=data_source,
        exporters=t.ALL_EXPORTERS,
        ajax_url=tk.url_for(
            "tables.resource_table_ajax",
            resource_id=resource["id"],
            resource_view_id=resource_view["id"],
        ),
        columns=[t.ColumnDefinition(field=col, title=col) for col in data_source.get_columns()],
        table_layout="fitDataStretch",
    )


def tables_guess_data_source(
    resource: dict[str, Any],
    resource_view: dict[str, Any] | None = None,
) -> t.BaseDataSource:
    """Guess the appropriate data source for a resource.

    Args:
        resource: The resource dictionary.
        resource_view: Optional resource view dictionary. When it contains a
            ``file_url`` key that URL is used as the data source URL and its
            file extension is used to determine the format (overriding the
            resource format).

    Returns:
        An instantiated data source ready to use.
    """
    file_url = (resource_view or {}).get("file_url", "")

    if resource.get("datastore_active") and not file_url:
        return t.DataStoreDataSource(resource_id=resource["id"])

    if file_url:
        url = file_url
        fmt = Path(file_url.split("?")[0]).suffix.lstrip(".").lower()
    else:
        url = resource.get("url")
        fmt = resource.get("format", "").lower()

    cache_backend = get_cache_backend()
    data_sources = {
        "csv": t.CsvUrlDataSource,
        "xlsx": t.XlsxUrlDataSource,
        "orc": t.OrcUrlDataSource,
        "parquet": t.ParquetUrlDataSource,
        "feather": t.FeatherUrlDataSource,
    }

    data_source_class = data_sources.get(fmt)

    if not data_source_class:
        raise ValueError(f"Unsupported format: {fmt}")  # noqa: TRY003

    if file_url:
        return data_source_class(url=url, cache_backend=cache_backend)

    return data_source_class(url=url, resource=resource, cache_backend=cache_backend)
