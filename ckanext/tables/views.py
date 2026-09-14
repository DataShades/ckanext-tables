import logging
from typing import Any

from flask import Blueprint, Response, jsonify
from flask.views import MethodView
from werkzeug.exceptions import HTTPException

import ckan.plugins.toolkit as tk

from ckanext.tables.data_sources import DataSourceError
from ckanext.tables.generics import TableDispatchMixin
from ckanext.tables.table import TableDefinition
from ckanext.tables.utils import tables_init_temporary_preview_table

log = logging.getLogger(__name__)

_DATA_LOAD_ERROR = tk._("Failed to load table. The resource may be unavailable or in an unsupported format.")

bp = Blueprint("tables", __name__)


def _get_resource_and_view(resource_id: str, resource_view_id: str) -> tuple[dict[str, Any], dict[str, Any]]:
    """Fetch and authorise a resource and a resource view, confirming they actually belong together.

    Each is looked up independently by id, so without the ``resource_id`` match
    check below, a resource view's ``file_url`` override (and the table name/cache
    keys derived from this pair) could be applied against any other resource id
    the caller happens to be able to read, just by pairing a real view id with an
    unrelated resource id in the URL.
    """
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


class ResourceViewHandler(TableDispatchMixin, MethodView):
    """Handler for resource view AJAX requests."""

    def get_table_for_resource(self, resource_id: str, resource_view_id: str) -> TableDefinition:
        """Get a table definition for a given resource.

        Args:
            resource_id: The resource ID
            resource_view_id: The resource view ID

        Returns:
            A TableDefinition object
        """
        resource, resource_view = _get_resource_and_view(resource_id, resource_view_id)

        return tables_init_temporary_preview_table(resource, resource_view)

    def get(self, resource_id: str, resource_view_id: str) -> str | Response | tuple[Response, int]:
        """Handle AJAX requests for resource view tables.

        Args:
            resource_id: The resource ID
            resource_view_id: The resource view ID

        Returns:
            JSON response with table data or export file
        """
        try:
            table = self.get_table_for_resource(resource_id, resource_view_id)
        except DataSourceError:
            log.exception("Failed to initialize table for resource %s", resource_id)
            return jsonify({"error": _DATA_LOAD_ERROR}), 502

        return self._dispatch_get(table)

    def post(self, resource_id: str, resource_view_id: str) -> Response | tuple[Response, int]:
        """Handle POST requests for resource view tables (actions, refresh).

        Args:
            resource_id: The resource ID
            resource_view_id: The resource view ID

        Returns:
            JSON response with action result
        """
        try:
            table = self.get_table_for_resource(resource_id, resource_view_id)
        except DataSourceError:
            log.exception("Failed to initialize table for resource %s", resource_id)
            return jsonify({"success": False, "error": _DATA_LOAD_ERROR}), 502

        self._resource_id = resource_id

        return self._dispatch_post(table)

    def _handle_refresh(self, table: TableDefinition) -> Response:
        try:
            tk.check_access("resource_update", {}, {"id": self._resource_id})
        except tk.NotAuthorized:
            return tk.abort(403, tk._("Not authorized to refresh this resource's cached data"))
        return self._refresh_data(table)


bp.add_url_rule(
    "/resource-table-ajax/<resource_id>/<resource_view_id>",
    view_func=ResourceViewHandler.as_view("resource_table_ajax"),
)


class ResourceViewDeferredHandler(MethodView):
    """Renders the full table HTML snippet, called lazily after page load.

    HTMX fires a GET request to this endpoint on page load, so the expensive
    ``tables_init_temporary_preview_table`` call (which fetches remote data to
    discover column names) happens *after* the browser has already rendered the
    page skeleton — avoiding a blank-page experience and production timeouts on
    the initial page request.

    Every failure here — auth, a missing resource, an unreachable/unsupported
    source — is rendered as a 200 error snippet with a retry affordance instead
    of a real 403/404/500. HTMX does not swap a non-2xx response into the page
    by default, so a raw error status would leave the shimmer skeleton (see
    ``table_preview.html``) spinning forever with no message and nothing to
    retry — the request "succeeded" from the page's point of view either way,
    it just has different content to show.
    """

    def get(self, resource_id: str, resource_view_id: str) -> str:
        reload_url = tk.url_for(
            "tables.resource_table_deferred", resource_id=resource_id, resource_view_id=resource_view_id
        )

        try:
            resource, resource_view = _get_resource_and_view(resource_id, resource_view_id)
        except HTTPException as err:
            return self._render_error(reload_url, err.description or tk._("Unable to load this table."))

        try:
            table = tables_init_temporary_preview_table(resource, resource_view)
        except Exception:
            log.exception("Failed to initialize table for resource %s", resource_id)
            return self._render_error(reload_url, _DATA_LOAD_ERROR)

        return tk.render(
            "tables/render_table.html",
            extra_vars={"table": table},
        )

    @staticmethod
    def _render_error(reload_url: str, message: str) -> str:
        return tk.render(
            "tables/snippets/table_error.html",
            extra_vars={"message": message, "reload_url": reload_url},
        )


bp.add_url_rule(
    "/resource-table-deferred/<resource_id>/<resource_view_id>",
    view_func=ResourceViewDeferredHandler.as_view("resource_table_deferred"),
)
