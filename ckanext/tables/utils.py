import json
import re

from ckan.plugins import toolkit as tk

from ckanext.tables.config import get_max_page_size
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
