from __future__ import annotations

import json
import logging

from flask import Blueprint, Response, jsonify
from flask.views import MethodView

from ckan.plugins import toolkit as tk

from ckanext.tables.table import QueryParams

log = logging.getLogger(__name__)
bp = Blueprint("tables", __name__)


class AjaxURLView(MethodView):
    def get(self, table_name: str) -> Response:
        table_class = tk.h.tables_get_table(table_name)

        if not table_class:
            return tk.abort(404, tk._(f"Table {table_name} not found"))

        params = self.build_params()
        table_instance = table_class()  # type: ignore
        data = table_instance.get_data(params)
        total = table_instance.get_total_count(params)

        return jsonify({"data": data, "last_page": (total + params.size - 1) // params.size})

    def post(self, table_name: str) -> Response:
        table_class = tk.h.tables_get_table(table_name)

        if not table_class:
            return tk.abort(404, tk._(f"Table {table_name} not found"))

        row_action = tk.request.form.get("row_action")
        rows = tk.request.form.get("rows")

        table = table_class()
        row_action_func = table.get_rows_action(row_action) if row_action else None

        if not row_action_func or not rows:
            return jsonify(
                {
                    "success": False,
                    "errors": [tk._("The row action is not implemented")],
                }
            )

        errors = []

        for row in json.loads(rows):
            success, error = row_action_func(row)

            if not success:
                log.debug("Error during row action %s: %s", row_action, error)
                errors.append(error)

        return jsonify({"success": not errors, "errors": errors})

    def build_params(self) -> QueryParams:
        return QueryParams(
            page=tk.request.args.get("page", 1, int),
            size=tk.request.args.get("size", 10, int),
            field=tk.request.args.get("field"),
            operator=tk.request.args.get("operator"),
            value=tk.request.args.get("q"),
            sort_by=tk.request.args.get("sort[0][field]"),
            sort_order=tk.request.args.get("sort[0][dir]"),
        )


bp.add_url_rule("/tables/ajax-url/<table_name>", view_func=AjaxURLView.as_view("ajax"))
