import logging

from flask import Blueprint, Response, jsonify, request
from flask.views import MethodView

import ckan.plugins.toolkit as tk

from ckanext.tables.generics import AjaxTableMixin, ExportTableMixin
from ckanext.tables.helpers import tables_init_temporary_preview_table
from ckanext.tables.table import TableDefinition

log = logging.getLogger(__name__)

bp = Blueprint("tables", __name__)


class ResourceViewHandler(AjaxTableMixin, ExportTableMixin, MethodView):
    """Handler for resource view AJAX requests."""

    def get_table_for_resource(self, resource_id: str) -> TableDefinition:
        """Get a table definition for a given resource.

        Args:
            resource_id: The resource ID

        Returns:
            A TableDefinition object
        """
        try:
            resource = tk.get_action("resource_show")({"ignore_auth": False}, {"id": resource_id})
        except tk.ObjectNotFound:
            tk.abort(404, tk._("Resource not found"))
        except tk.NotAuthorized:
            tk.abort(403, tk._("Not authorized to view this resource"))

        return tables_init_temporary_preview_table(resource)

    def get(self, resource_id: str) -> str | Response:
        """Handle AJAX requests for resource view tables.

        Args:
            resource_id: The resource ID

        Returns:
            JSON response with table data or export file
        """
        handler = ResourceViewHandler()
        table = handler.get_table_for_resource(resource_id)

        if exporter_name := request.args.get("exporter"):
            return handler._export(table, exporter_name)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return handler._ajax_data(table)

        tk.abort(400, tk._("This endpoint only accepts AJAX requests"))

    def post(self, resource_id: str) -> Response:
        """Handle POST requests for resource view tables (actions, refresh).

        Args:
            resource_id: The resource ID

        Returns:
            JSON response with action result
        """
        handler = ResourceViewHandler()
        table = handler.get_table_for_resource(resource_id)

        row_action = request.form.get("row_action")
        table_action = request.form.get("table_action")
        bulk_action = request.form.get("bulk_action")
        row = request.form.get("row")
        rows = request.form.get("rows")
        refresh = request.form.get("refresh")

        if table_action:
            return handler._apply_table_action(table, table_action)
        if row_action:
            return handler._apply_row_action(table, row_action, row)
        if bulk_action:
            return handler._apply_bulk_action(table, bulk_action, rows)
        if refresh:
            return handler._refresh_data(table)

        return jsonify({"success": False, "error": "No action specified"})


bp.add_url_rule("/resource-table-ajax/<resource_id>", view_func=ResourceViewHandler.as_view("resource_table_ajax"))
