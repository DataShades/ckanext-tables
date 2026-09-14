from __future__ import annotations

import json
import logging
from datetime import datetime as dt
from datetime import timezone as tz

from flask import Response, jsonify, request, stream_with_context
from flask.views import MethodView

import ckan.plugins.toolkit as tk

from ckanext.tables import exporters
from ckanext.tables.config import get_export_max_rows
from ckanext.tables.data_sources import DataSourceError
from ckanext.tables.table import TableDefinition
from ckanext.tables.types import ActionHandlerResult
from ckanext.tables.utils import tables_build_params

log = logging.getLogger(__name__)

_GENERIC_ACTION_ERROR = tk._("An unexpected error occurred while performing this action.")
_DATA_LOAD_ERROR = tk._("Failed to load table data. The resource may be unavailable or in an unsupported format.")


class AjaxTableMixin:
    """Provides AJAX data loading and action handling."""

    def _ajax_data(self, table: TableDefinition) -> Response | tuple[Response, int]:
        params = tables_build_params()

        try:
            data = table.get_data(params)
            total = table.get_total_count(params)
        except DataSourceError:
            log.exception("Failed to load data for table %s", table.name)
            return jsonify({"error": _DATA_LOAD_ERROR}), 502

        return jsonify({"data": data, "last_page": (total + params.size - 1) // params.size, "total": total})

    def _action_result(self, result: ActionHandlerResult) -> Response:
        return jsonify(
            {
                "success": result.get("success", False),
                "error": result.get("error"),
                "message": result.get("message"),
                "redirect": result.get("redirect"),
            }
        )

    def _action_error(self, message: str) -> Response:
        return self._action_result(ActionHandlerResult(success=False, error=message))

    def _apply_table_action(self, table: TableDefinition, action: str) -> Response:
        table_action = table.get_table_action(action)
        if not table_action:
            return self._action_error(tk._("The table action is not implemented"))

        try:
            result = table_action()
        except Exception:
            log.exception("Error during table action %s", action)
            return self._action_error(_GENERIC_ACTION_ERROR)

        return self._action_result(result)

    def _apply_row_action(self, table: TableDefinition, action: str, row: str | None) -> Response:
        row_action_func = table.get_row_action(action) if action else None
        if not row_action_func or not row:
            return self._action_error(tk._("The row action is not implemented"))

        try:
            result = row_action_func(json.loads(row))
        except Exception:
            log.exception("Error during row action %s", action)
            return self._action_error(_GENERIC_ACTION_ERROR)

        return self._action_result(result)

    def _apply_bulk_action(self, table: TableDefinition, action: str, rows: str | None) -> Response:
        bulk_action_func = table.get_bulk_action(action) if action else None

        if not bulk_action_func or not rows:
            return self._action_error(tk._("The bulk action is not implemented"))

        try:
            rows_list = json.loads(rows)
            result = bulk_action_func(rows_list)
        except Exception:
            log.exception("Error during bulk action %s", action)
            return self._action_error(_GENERIC_ACTION_ERROR)

        return self._action_result(result)

    def _refresh_data(self, table: TableDefinition) -> Response:
        """Refresh the table data cache."""
        table.refresh_data()

        return self._action_result(ActionHandlerResult(success=True))


class ExportTableMixin:
    def _export(self, table: TableDefinition, exporter_name: str) -> Response:
        exporter = table.get_exporter(exporter_name)

        if not exporter:
            message = tk._("Exporter %(name)s not found") % {"name": exporter_name}
            return tk.abort(404, message)

        if not exporter.is_available():
            log.warning("Exporter %s is unavailable: a required dependency is not installed", exporter_name)
            message = tk._("%(label)s export is not available: a required dependency is not installed.") % {
                "label": exporter.label
            }
            return tk.abort(501, message)

        params = tables_build_params()
        total = table.get_total_count(params)
        max_rows = get_export_max_rows()

        if total > max_rows:
            message = tk._(
                "Cannot export %(total)d rows: the maximum is %(max_rows)d. Add filters to narrow the result set."
            ) % {"total": total, "max_rows": max_rows}
            return tk.abort(413, message)

        filename = self._prepare_export_filename(table, exporter)

        return Response(
            stream_with_context(exporter.export_stream(table, params)),
            mimetype=exporter.mime_type,
            headers={"Content-Disposition": f'attachment; filename="{filename}"'},
        )

    def _prepare_export_filename(self, table: TableDefinition, exporter: type[exporters.ExporterBase]) -> str:
        timestamp = dt.now(tz.utc).strftime("%Y-%m-%d %H-%M-%S")
        return f"{table.name}-{timestamp}.{exporter.name}"


class TableDispatchMixin(AjaxTableMixin, ExportTableMixin):
    """Shared GET/POST request dispatch for table views.

    Both ``ResourceViewHandler`` and ``GenericTableView`` route a GET to
    export/AJAX/full-page rendering and a POST to one of the table/row/bulk
    actions or a cache refresh in exactly the same order; this mixin is the
    single place that ordering lives so the two views can't drift apart.
    """

    def _dispatch_get(self, table: TableDefinition) -> str | Response | tuple[Response, int]:
        if exporter_name := request.args.get("exporter"):
            return self._export(table, exporter_name)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return self._ajax_data(table)

        return self._render_full_page(table)

    def _render_full_page(self, table: TableDefinition) -> str | Response:
        """Fallback for a GET that is neither an export nor an AJAX call."""
        return tk.abort(400, tk._("This endpoint only accepts AJAX requests"))

    def _dispatch_post(self, table: TableDefinition) -> Response:
        row_action = request.form.get("row_action")
        table_action = request.form.get("table_action")
        bulk_action = request.form.get("bulk_action")
        row = request.form.get("row")
        rows = request.form.get("rows")
        refresh = request.form.get("refresh")

        if table_action:
            return self._apply_table_action(table, table_action)
        if row_action:
            return self._apply_row_action(table, row_action, row)
        if bulk_action:
            return self._apply_bulk_action(table, bulk_action, rows)
        if refresh:
            return self._handle_refresh(table)

        return self._action_error(tk._("No action specified"))

    def _handle_refresh(self, table: TableDefinition) -> Response:
        return self._refresh_data(table)


class GenericTableView(TableDispatchMixin, MethodView):
    """Unified view to render tables, serve AJAX, and export data."""

    def __init__(
        self,
        table: type[TableDefinition],
        breadcrumb_label: str | None = None,
        page_title: str = "",
    ):
        """Set up the view.

        Args:
            table: The table definition class to render.
            breadcrumb_label: Already-translated label shown in the breadcrumb (the
                template renders it as-is, so pass the result of your own ``tk._(...)``
                call if it needs translating). Defaults to a translated "Table".
            page_title: Already-translated page title shown above the table.
        """
        self.table = table
        self.breadcrumb_label = breadcrumb_label if breadcrumb_label is not None else tk._("Table")
        self.page_title = page_title

    def get(self) -> str | Response | tuple[Response, int]:
        if not self.check_access():
            return tk.abort(403, tk._("You are not authorized to view this table."))

        table_instance = self.table()  # type: ignore

        return self._dispatch_get(table_instance)

    def _render_full_page(self, table: TableDefinition) -> str:
        return table.render_table(
            breadcrumb_label=self.breadcrumb_label,
            page_title=self.page_title,
        )

    def post(self) -> Response:
        if not self.check_access():
            return tk.abort(403, tk._("You are not authorized to perform this action."))

        table_instance = self.table()  # type: ignore

        return self._dispatch_post(table_instance)

    def check_access(self) -> bool:
        try:
            self.table.check_access({})
        except tk.NotAuthorized:
            return False

        return True
