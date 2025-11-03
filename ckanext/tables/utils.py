from __future__ import annotations

import json

from ckan.plugins import toolkit as tk

from ckanext.tables.table import FilterItem, QueryParams


def tables_build_params() -> QueryParams:
    filters = json.loads(tk.request.args.get("filters", "[]"))

    return QueryParams(
        page=tk.request.args.get("page", 1, int),
        size=tk.request.args.get("size", 10, int),
        filters=[FilterItem(f["field"], f["operator"], f["value"]) for f in filters],
        sort_by=tk.request.args.get("sort[0][field]"),
        sort_order=tk.request.args.get("sort[0][dir]"),
    )
