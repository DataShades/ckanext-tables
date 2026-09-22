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
    DataSourceError,
    DataStoreDataSource,
    FeatherUrlDataSource,
    JsonLdUrlDataSource,
    NdjsonUrlDataSource,
    OdsUrlDataSource,
    OrcUrlDataSource,
    ParquetUrlDataSource,
    TsvUrlDataSource,
    XlsUrlDataSource,
    XlsxUrlDataSource,
)
from ckanext.tables.exporters import ALL_EXPORTERS
from ckanext.tables.table import ColumnDefinition, TableDefinition
from ckanext.tables.types import FilterItem, QueryParams

FILTER_RE = re.compile(r"^filter\[(\d+)\]\[(\w+)\]$")

DATA_SOURCE_BY_FORMAT = {
    "csv": CsvUrlDataSource,
    "tsv": TsvUrlDataSource,
    "xlsx": XlsxUrlDataSource,
    "xls": XlsUrlDataSource,
    "ods": OdsUrlDataSource,
    "orc": OrcUrlDataSource,
    "parquet": ParquetUrlDataSource,
    "feather": FeatherUrlDataSource,
    "jsonld": JsonLdUrlDataSource,
    "json-ld": JsonLdUrlDataSource,
    "ndjson": NdjsonUrlDataSource,
    "jsonl": NdjsonUrlDataSource,
}
SUPPORTED_FORMATS = frozenset(DATA_SOURCE_BY_FORMAT)


def guess_format(url: str, declared_format: str = "") -> str:
    """Guess a data format from a URL, falling back to a declared format."""
    ext = Path(url.split("?", maxsplit=1)[0]).suffix.lstrip(".").lower()
    return ext or declared_format.lower()


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


def tables_get_resource_and_view(resource_id: str, resource_view_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch and authorise a resource and a resource view, confirming they actually belong together."""
    try:
        resource = tk.get_action("resource_show")({"ignore_auth": False}, {"id": resource_id})
    except tk.ObjectNotFound:
        return tk.abort(404, tk._("Resource not found"))
    except tk.NotAuthorized:
        return tk.abort(403, tk._("Not authorized to view this resource"))

    try:
        resource_view = tk.get_action("resource_view_show")({"ignore_auth": False}, {"id": resource_view_id})
    except tk.ObjectNotFound:
        return tk.abort(404, tk._("Resource view not found"))
    except tk.NotAuthorized:
        return tk.abort(403, tk._("Not authorized to view this resource"))

    if resource_view["resource_id"] != resource["id"]:
        return tk.abort(404, tk._("Resource view not found"))

    return resource, resource_view


def tables_init_temporary_preview_table(
    resource: dict[str, Any],
    resource_view: dict[str, Any],
    sheet_index: int = 0,
) -> TableDefinition:
    """Initialize a temporary preview table for a given resource.

    Args:
        resource: The resource dictionary containing the URL and format of the data.
        resource_view: The resource view dictionary. When it contains a
            ``file_url`` key that URL is used instead of the resource URL and
            the format is inferred from its file extension.
        sheet_index: Which sheet of a multi-sheet workbook to preview. Ignored
            by every format that has no sheets, and falls back to the first
            sheet when the workbook has no sheet at that position — a
            bookmarked link to a sheet that a re-upload has since removed
            shows the workbook's first sheet rather than an error.

    Returns:
        A TableDefinition object representing the initialized temporary preview table.
    """
    data_source = tables_guess_data_source(resource, resource_view, sheet_index)
    sheets = data_source.get_sheet_names()

    if sheet_index and sheet_index >= len(sheets):
        sheet_index = 0
        data_source = tables_guess_data_source(resource, resource_view)

    return TableDefinition(
        name=tables_preview_table_name(resource["id"], resource_view["id"], sheet_index),
        data_source=data_source,
        exporters=ALL_EXPORTERS,
        ajax_url=tk.url_for(
            "tables.resource_table_ajax",
            resource_id=resource["id"],
            resource_view_id=resource_view["id"],
            sheet=sheet_index,
        ),
        columns=[ColumnDefinition(field=col, title=col) for col in data_source.get_columns()],
        table_layout="fitDataStretch",
        sheets=sheets,
        current_sheet=sheet_index,
        sheet_switch_url=(
            tk.url_for(
                "tables.resource_table_deferred",
                resource_id=resource["id"],
                resource_view_id=resource_view["id"],
            )
            if len(sheets) > 1
            else None
        ),
    )


def tables_preview_table_name(resource_id: str, resource_view_id: str, sheet_index: int = 0) -> str:
    """Return the ``TableDefinition.name`` of a resource preview table.

    A table's name namespaces the state the frontend persists in the address
    bar (page, filters, hidden columns), so each sheet gets its own — a
    filter on a column only the first sheet has must not follow the reader
    into a second sheet that has no such column. The first sheet keeps the
    bare, sheet-less name it had before sheet selection existed, so links
    already out there keep resolving to the state they were saved with.
    """
    name = f"preview_resource_{resource_id}_{resource_view_id}"

    return f"{name}_sheet_{sheet_index}" if sheet_index else name


def tables_guess_data_source(
    resource: dict[str, Any],
    resource_view: dict[str, Any] | None = None,
    sheet_index: int = 0,
) -> BaseDataSource:
    """Guess the appropriate data source for a resource.

    Args:
        resource: The resource dictionary.
        resource_view: Optional resource view dictionary. When it contains a
            ``file_url`` key that URL is used as the data source URL and its
            file extension is used to determine the format (overriding the
            resource format).
        sheet_index: Which sheet to read, for the formats that have sheets.
            Passed only to those — every other data source takes no such
            argument.

    Returns:
        An instantiated data source ready to use.
    """
    file_url = (resource_view or {}).get("file_url", "")

    if not file_url and resource.get("datastore_active") and p.plugin_loaded("datastore"):
        return DataStoreDataSource(resource_id=resource["id"])

    if file_url:
        url = file_url
        fmt = guess_format(file_url)
    else:
        url = resource.get("url", "")
        fmt = guess_format(url, resource.get("format", ""))

    cache_backend = get_cache_backend()
    data_source_class = DATA_SOURCE_BY_FORMAT.get(fmt)

    if not data_source_class:
        raise DataSourceError(f"Unsupported format: {fmt}")

    kwargs: dict[str, Any] = {"cache_backend": cache_backend}

    if data_source_class.supports_sheets:
        kwargs["sheet_index"] = sheet_index

    if file_url:
        return data_source_class(url=url, **kwargs)

    return data_source_class(url=url, resource=resource, **kwargs)
