import json
import re

from ckan.plugins import toolkit as tk

from ckanext.tables.types import FilterItem, QueryParams

FILTER_RE = re.compile(r"^filter\[(\d+)\]\[(\w+)\]$")


def tables_build_params() -> QueryParams:
    filters = json.loads(tk.request.args.get("filters", "[]"))

    all_filters = [FilterItem(f["field"], f["operator"], f["value"]) for f in filters]
    all_filters.extend(parse_tabulator_filters())

    return QueryParams(
        page=tk.request.args.get("page", 1, int),
        size=tk.request.args.get("size", 10, int),
        filters=all_filters,
        sort_by=tk.request.args.get("sort[0][field]"),
        sort_order=tk.request.args.get("sort[0][dir]"),
    )


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
