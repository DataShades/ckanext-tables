from __future__ import annotations

import json
import logging
from datetime import datetime as dt
from datetime import timezone as tz

from flask import Response, jsonify, request
from flask.views import MethodView

import ckan.plugins.toolkit as tk

from ckanext.tables import exporters
from ckanext.tables.table import TableDefinition
from ckanext.tables.types import ActionHandlerResult
from ckanext.tables.utils import tables_build_params

log = logging.getLogger(__name__)


class AjaxTableMixin:
    """Provides AJAX data loading and action handling."""

    def _ajax_data(self, table: TableDefinition) -> Response:
        params = tables_build_params()
        data = table.get_data(params)
        total = table.get_total_count(params)
        return jsonify({"data": data, "last_page": (total + params.size - 1) // params.size, "total": total})

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
            result = table_action()
        except Exception as e:
            log.exception("Error during table action %s", action)
            return jsonify({"success": False, "errors": str(e)})
        return jsonify(result)

    def _apply_row_action(self, table: TableDefinition, action: str, row: str | None) -> Response:
        row_action_func = table.get_row_action(action) if action else None
        if not row_action_func or not row:
            return jsonify({"success": False, "error": [tk._("The row action is not implemented")]})

        try:
            result = row_action_func(json.loads(row))
        except Exception as e:
            log.exception("Error during row action %s", action)
            return jsonify({"success": False, "error": str(e)})

        return jsonify(ActionHandlerResult(**result))

    def _apply_bulk_action(self, table: TableDefinition, action: str, rows: str | None) -> Response:
        bulk_action_func = table.get_bulk_action(action) if action else None

        if not bulk_action_func or not rows:
            return jsonify(
                {
                    "success": False,
                    "errors": [tk._("The bulk action is not implemented")],
                }
            )

        rows_list = json.loads(rows)

        try:
            result = bulk_action_func(rows_list)
        except Exception as e:
            log.exception("Error during bulk action %s", action)
            return jsonify({"success": False, "error": str(e)})

        return jsonify(ActionHandlerResult(**result))

    def _refresh_data(self, table: TableDefinition) -> Response:
        """Refresh the table data cache."""
        table.refresh_data()

        return jsonify({"success": True, "error": None})


class ExportTableMixin:
    def _export(self, table: TableDefinition, exporter_name: str) -> Response:
        exporter = table.get_exporter(exporter_name)

        if not exporter:
            return tk.abort(404, tk._(f"Exporter {exporter_name} not found"))

        data = exporter.export(table, tables_build_params())
        filename = self._prepare_export_filename(table, exporter)

        return Response(
            data,
            mimetype=exporter.mime_type,
            headers={"Content-Disposition": f"attachment; filename={filename}"},
        )

    def _prepare_export_filename(self, table: TableDefinition, exporter: type[exporters.ExporterBase]) -> str:
        timestamp = dt.now(tz.utc).strftime("%Y-%m-%d %H-%M-%S")
        return f"{table.name}-{timestamp}.{exporter.name}"


class GenericTableView(AjaxTableMixin, ExportTableMixin, MethodView):
    """Unified view to render tables, serve AJAX, and export data."""

    def __init__(
        self,
        table: type[TableDefinition],
        breadcrumb_label: str = "Table",
        page_title: str = "",
    ):
        self.table = table
        self.breadcrumb_label = breadcrumb_label
        self.page_title = page_title

    def get(self) -> str | Response:
        if not self.check_access():
            return tk.abort(403, tk._("You are not authorized to view this table."))

        table = self.table()  # type: ignore

        if exporter_name := request.args.get("exporter"):
            return self._export(table, exporter_name)

        if tk.request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return self._ajax_data(table)

        return table.render_table(
            breadcrumb_label=self.breadcrumb_label,
            page_title=self.page_title,
        )

    def _dispatch_get(self, table_instance: TableDefinition) -> str | Response:
        if exporter_name := request.args.get("exporter"):
            return self._export(table_instance, exporter_name)

        if tk.request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return self._ajax_data(table_instance)

        return table_instance.render_table(
            breadcrumb_label=self.breadcrumb_label,
            page_title=self.page_title,
        )

    def post(self) -> Response:
        if not self.check_access():
            return tk.abort(403, tk._("You are not authorized to perform this action."))

        table_instance = self.table()  # type: ignore

        return self._dispatch_post(table_instance)

    def _dispatch_post(self, table_instance: TableDefinition) -> Response:
        row_action = request.form.get("row_action")
        table_action = request.form.get("table_action")
        bulk_action = request.form.get("bulk_action")
        row = request.form.get("row")
        rows = request.form.get("rows")
        refresh = request.form.get("refresh")

        if table_action:
            return self._apply_table_action(table_instance, table_action)
        if row_action:
            return self._apply_row_action(table_instance, row_action, row)
        if bulk_action:
            return self._apply_bulk_action(table_instance, bulk_action, rows)
        if refresh:
            return self._refresh_data(table_instance)

        return jsonify({"success": False, "error": "No action specified"})

    def check_access(self) -> bool:
        try:
            self.table.check_access({})
        except tk.NotAuthorized:
            return False

        return True
