import logging
import os
from typing import Any

from flask import Blueprint, Response, jsonify, request, stream_with_context
from flask.views import MethodView
from werkzeug.exceptions import HTTPException

import ckan.plugins.toolkit as tk
from ckan.lib.jobs import job_from_id

from ckanext.tables.config import get_export_dir
from ckanext.tables.data_sources import DataSourceError
from ckanext.tables.export_jobs import check_export_locator_access
from ckanext.tables.generics import TableDispatchMixin
from ckanext.tables.table import TableDefinition
from ckanext.tables.utils import tables_get_resource_and_view, tables_init_temporary_preview_table

log = logging.getLogger(__name__)

_DATA_LOAD_ERROR = tk._("Failed to load table. The resource may be unavailable or in an unsupported format.")

bp = Blueprint("tables", __name__)


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
        resource, resource_view = tables_get_resource_and_view(resource_id, resource_view_id)

        return tables_init_temporary_preview_table(resource, resource_view)

    def _export_locator(self, table: TableDefinition) -> dict[str, Any]:
        return {
            "kind": "resource_view",
            "resource_id": self._resource_id,
            "resource_view_id": self._resource_view_id,
        }

    def get(self, resource_id: str, resource_view_id: str) -> str | Response | tuple[Response, int]:
        """Handle AJAX requests for resource view tables.

        Args:
            resource_id: The resource ID
            resource_view_id: The resource view ID

        Returns:
            JSON response with table data or export file
        """
        self._resource_id = resource_id
        self._resource_view_id = resource_view_id

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
        self._resource_id = resource_id
        self._resource_view_id = resource_view_id

        try:
            table = self.get_table_for_resource(resource_id, resource_view_id)
        except DataSourceError:
            log.exception("Failed to initialize table for resource %s", resource_id)
            return jsonify({"success": False, "error": _DATA_LOAD_ERROR}), 502

        return self._dispatch_post(table)

    def _handle_refresh(self, table: TableDefinition) -> Response:
        try:
            tk.check_access("resource_update", {}, {"id": self._resource_id})
        except tk.NotAuthorized:
            return tk.abort(403, tk._("Not authorized to refresh this resource's cached data"))
        return self._refresh_data(table)


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
            resource, resource_view = tables_get_resource_and_view(resource_id, resource_view_id)
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


class ExportStatusHandler(MethodView):
    """Status of a background export job — see export_jobs.py. Three ways to ask.

    Shared by every view that can background an export (``ResourceViewHandler``,
    ``GenericTableView``): the job id is the only thing the URL carries, and
    access is re-checked from the job's own locator (see
    ``export_jobs.check_export_locator_access``) rather than from anything
    view-specific in the URL.

    - ``X-Requested-With: XMLHttpRequest`` (the convention this extension's
      own JS already uses everywhere else) → JSON, for the table page's own
      in-tab poll while the tab that started the export is still open — see
      ``_onTableExportClick`` in ``tables-tabulator.ts``.
    - An htmx request (``HX-Request`` header, set automatically by htmx) →
      just the status snippet, which carries its own ``hx-trigger="every
      2s"`` while the job is still running and drops it once the job
      reaches a terminal state, so it naturally stops re-polling itself.
    - A plain navigation (e.g. from the "export started" toast's link, or a
      bookmark/reload) → that same snippet wrapped in a full page — so the
      job is still trackable even if the tab that started it gets closed.
    """

    def get(self, job_id: str) -> str | Response:
        try:
            job = job_from_id(job_id)
        except KeyError:
            status, result, download_url = "not_found", None, None
        else:
            # Access is only checkable once we know the job's own locator, so
            # unlike the old per-resource routes this can't happen before the
            # lookup above — a nonexistent/expired job has nothing sensitive
            # to protect, so "not_found" is safe to hand back to anyone.
            check_export_locator_access(job.args[0])

            status = job.get_status()
            result = job.result if status in ("finished", "failed") else None

            download_url = None
            if status == "finished" and result and result.get("success"):
                download_url = tk.url_for("tables.table_export_download", job_id=job_id)

        if request.headers.get("X-Requested-With") == "XMLHttpRequest":
            return jsonify(
                {
                    "status": status,
                    "download_url": download_url,
                    "error": result.get("error") if status == "failed" and result else None,
                }
            )

        fragment = tk.render(
            "tables/snippets/export_status.html",
            extra_vars={
                "status": status,
                "result": result,
                "download_url": download_url,
                "self_url": tk.url_for("tables.table_export_status", job_id=job_id),
            },
        )

        if request.headers.get("HX-Request") == "true":
            return fragment

        return tk.render(
            "tables/view/export_status_page.html",
            extra_vars={"fragment": fragment, "breadcrumb_label": tk._("Export status")},
        )


class ExportDownloadHandler(MethodView):
    """Streams a finished background export's file. See ExportStatusHandler."""

    _CHUNK_SIZE = 64 * 1024

    def get(self, job_id: str) -> Response:
        try:
            job = job_from_id(job_id)
        except KeyError:
            return tk.abort(404, tk._("This export no longer exists — it may have expired."))

        check_export_locator_access(job.args[0])

        result = job.result if job.get_status() == "finished" else None
        if not result or not result.get("success"):
            return tk.abort(404, tk._("This export is not ready, or failed to render."))

        export_dir = get_export_dir()
        if export_dir is None:
            return tk.abort(404, tk._("The export directory is not available."))

        path = os.path.join(export_dir, result["disk_filename"])
        if not os.path.isfile(path):
            return tk.abort(404, tk._("This export's file is no longer available — it may have expired."))

        return Response(
            stream_with_context(self._stream_file(path)),
            mimetype=result["mime_type"],
            headers={"Content-Disposition": f'attachment; filename="{result["filename"]}"'},
        )

    def _stream_file(self, path: str):
        with open(path, "rb") as f:
            while chunk := f.read(self._CHUNK_SIZE):
                yield chunk


bp.add_url_rule(
    "/resource-table-ajax/<resource_id>/<resource_view_id>",
    view_func=ResourceViewHandler.as_view("resource_table_ajax"),
)

bp.add_url_rule(
    "/resource-table-deferred/<resource_id>/<resource_view_id>",
    view_func=ResourceViewDeferredHandler.as_view("resource_table_deferred"),
)

bp.add_url_rule(
    "/table-export-status/<job_id>",
    view_func=ExportStatusHandler.as_view("table_export_status"),
)

bp.add_url_rule(
    "/table-export-download/<job_id>",
    view_func=ExportDownloadHandler.as_view("table_export_download"),
)
