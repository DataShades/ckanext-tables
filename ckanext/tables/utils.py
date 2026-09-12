import json
import re
from pathlib import Path
from typing import Any

import ckan.plugins as p
from ckan.plugins import toolkit as tk

from ckanext.tables.cache import get_cache_backend
from ckanext.tables.config import get_max_page_size
from ckanext.tables.data_sources import (
    BaseDataSource,
    CsvUrlDataSource,
    DataStoreDataSource,
    FeatherUrlDataSource,
    OrcUrlDataSource,
    ParquetUrlDataSource,
    XlsxUrlDataSource,
)
from ckanext.tables.exporters import ALL_EXPORTERS
from ckanext.tables.table import ColumnDefinition, TableDefinition
from ckanext.tables.types import FilterItem, QueryParams

FILTER_RE = re.compile(r"^filter\[(\d+)\]\[(\w+)\]$")


def tables_build_params() -> QueryParams:
    all_filters = parse_json_filters(tk.request.args.get("filters", "[]"))
    all_filters.extend(parse_tabulator_filters())

    page = tk.request.args.get("page", 1, int)
    size = tk.request.args.get("size", 10, int)

    return QueryParams(
        page=max(1, page),
        size=min(max(1, size), get_max_page_size()),
        filters=all_filters,
        sort_by=tk.request.args.get("sort[0][field]"),
        sort_order=tk.request.args.get("sort[0][dir]"),
    )


def parse_json_filters(raw: str) -> list[FilterItem]:
    """Parse the ``filters`` query param's JSON array into ``FilterItem``s.

    Anything malformed — invalid JSON, a non-array, a non-object entry, or an
    entry missing a required key — is skipped rather than left to raise past
    this point and turn into a 500 for an edited query string.
    """
    try:
        filters = json.loads(raw)
    except (json.JSONDecodeError, TypeError):
        return []

    if not isinstance(filters, list):
        return []

    result = []
    for f in filters:
        if not isinstance(f, dict):
            continue
        try:
            result.append(FilterItem(f["field"], f["operator"], f["value"]))
        except KeyError:
            continue

    return result


def parse_tabulator_filters() -> list[FilterItem]:
    """Parse Tabulator's remote filter params.

    They come from column native tabulator column filters.

    E.g. filter[N][field], filter[N][type], filter[N][value].
    """
    filters = {}

    for key, value in tk.request.args.items():
        match = FILTER_RE.match(key)
        if not match:
            continue

        index, subkey = match.groups()
        index = int(index)

        if index not in filters:
            filters[index] = {}

        filters[index][subkey] = value

    return [
        FilterItem(f["field"], f["type"], f["value"])
        for f in filters.values()
        if f.get("field") and f.get("value") and f.get("type")
    ]


def tables_init_temporary_preview_table(
    resource: dict[str, Any],
    resource_view: dict[str, Any],
) -> TableDefinition:
    """Initialize a temporary preview table for a given resource.

    Args:
        resource: The resource dictionary containing the URL and format of the data.
        resource_view: The resource view dictionary. When it contains a
            ``file_url`` key that URL is used instead of the resource URL and
            the format is inferred from its file extension.

    Returns:
        A TableDefinition object representing the initialized temporary preview table.
    """
    data_source = tables_guess_data_source(resource, resource_view)

    return TableDefinition(
        name=f"preview_resource_{resource['id']}_{resource_view['id']}",
        data_source=data_source,
        exporters=ALL_EXPORTERS,
        ajax_url=tk.url_for(
            "tables.resource_table_ajax",
            resource_id=resource["id"],
            resource_view_id=resource_view["id"],
        ),
        columns=[ColumnDefinition(field=col, title=col) for col in data_source.get_columns()],
        table_layout="fitDataStretch",
    )


def tables_guess_data_source(
    resource: dict[str, Any],
    resource_view: dict[str, Any] | None = None,
) -> BaseDataSource:
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

    if not file_url and resource.get("datastore_active") and p.plugin_loaded("datastore"):
        return DataStoreDataSource(resource_id=resource["id"])

    if file_url:
        url = file_url
        fmt = Path(file_url.split("?")[0]).suffix.lstrip(".").lower()
    else:
        url = resource.get("url")
        fmt = resource.get("format", "").lower()

    cache_backend = get_cache_backend()
    data_sources = {
        "csv": CsvUrlDataSource,
        "xlsx": XlsxUrlDataSource,
        "orc": OrcUrlDataSource,
        "parquet": ParquetUrlDataSource,
        "feather": FeatherUrlDataSource,
    }

    data_source_class = data_sources.get(fmt)

    if not data_source_class:
        raise ValueError(f"Unsupported format: {fmt}")

    if file_url:
        return data_source_class(url=url, cache_backend=cache_backend)

    return data_source_class(url=url, resource=resource, cache_backend=cache_backend)
