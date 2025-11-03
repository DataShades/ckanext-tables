from __future__ import annotations

import json
import logging
from datetime import datetime as dt
from datetime import timezone as tz

from flask import Blueprint, Response, jsonify
from flask.views import MethodView

from ckan.plugins import toolkit as tk

from ckanext.tables.table import TableDefinition
from ckanext.tables.types import ActionHandlerResult
from ckanext.tables.utils import tables_build_params

log = logging.getLogger(__name__)
bp = Blueprint("tables", __name__)


class AjaxURLView(MethodView):
    def get(self, table_name: str) -> Response:
        table_class = tk.h.tables_get_table(table_name)

        if not table_class:
            return tk.abort(404, tk._(f"Table {table_name} not found"))

        params = tables_build_params()
        table_instance = table_class()  # type: ignore
        data = table_instance.get_data(params)
        total = table_instance.get_total_count(params)
        return jsonify({"data": data, "last_page": (total + params.size - 1) // params.size})

    def post(self, table_name: str) -> Response:
        table_class = tk.h.tables_get_table(table_name)

        if not table_class:
            return tk.abort(404, tk._(f"Table {table_name} not found"))

        row_action = tk.request.form.get("row_action")
        table_action = tk.request.form.get("table_action")
        bulk_action = tk.request.form.get("bulk_action")
        row = tk.request.form.get("row")
        rows = tk.request.form.get("rows")

        table: TableDefinition = table_class()

        if table_action:
            return self._apply_table_action(table, table_action)

        if row_action:
            return self._apply_row_action(table, row_action, row)

        return self._apply_bulk_action(table, bulk_action, rows)

    def _apply_table_action(self, table: TableDefinition, action: str) -> Response:
        table_action = table.get_table_action(action)

        if not table_action:
            return jsonify(
                {
                    "success": False,
                    "errors": tk._("The table action is not implemented"),
                }
            )

        try:
            result = table_action.callback()
        except Exception as e:
            log.exception("Error during table action %s", action)
            return jsonify({"success": False, "errors": str(e)})

        return jsonify(result)

    def _apply_row_action(self, table: TableDefinition, action: str, row: str | None) -> Response:
        row_action_func = table.get_row_action(action) if action else None

        if not row_action_func or not row:
            return jsonify(
                {
                    "success": False,
                    "error": [tk._("The row action is not implemented")],
                }
            )

        try:
            result = row_action_func(json.loads(row))
        except Exception as e:
            log.exception("Error during row action %s", action)
            return jsonify({"success": False, "error": str(e)})

        return jsonify(
            ActionHandlerResult(
                success=result["success"],
                error=result.get("error", None),
                redirect=result.get("redirect", None),
                message=result.get("message", None),
            )
        )

    def _apply_bulk_action(self, table: TableDefinition, action: str, rows: str | None) -> Response:
        bulk_action_func = table.get_bulk_action(action) if action else None

        if not bulk_action_func or not rows:
            return jsonify(
                {
                    "success": False,
                    "errors": [tk._("The bulk action is not implemented")],
                }
            )

        errors = []

        for row in json.loads(rows):
            result = bulk_action_func(row)

            if not result["success"] and "error" in result:
                log.debug("Error during bulk action %s: %s", action, result["error"])
                errors.append(result["error"])

        return jsonify({"success": not errors, "errors": errors})


class TableExportView(MethodView):
    def get(self, table_name: str) -> Response:
        table_class = tk.h.tables_get_table(table_name)

        if not table_class:
            return tk.abort(404, tk._(f"Table {table_name} not found"))

        exporter_name = tk.request.args.get("exporter")

        if not exporter_name:
            return tk.abort(404, tk._("No exporter specified"))

        params = tables_build_params()

        table_instance = table_class()  # type: ignore
        exporter = table_instance.get_exporter(exporter_name)

        if not exporter:
            return tk.abort(404, tk._(f"Exporter {exporter_name} not found"))

        data = exporter.export(table_instance, params)
        timestamp = dt.now(tz.utc).strftime("%Y-%m-%d %H-%M-%S")

        response = Response(data, mimetype=exporter.mime_type)
        response.headers.set(
            "Content-Disposition",
            "attachment",
            filename=f"{table_name}-{timestamp}.{exporter.name}",
        )

        return response


bp.add_url_rule("/tables/ajax-url/<table_name>", view_func=AjaxURLView.as_view("ajax"))
bp.add_url_rule("/tables/export/<table_name>", view_func=TableExportView.as_view("export"))
