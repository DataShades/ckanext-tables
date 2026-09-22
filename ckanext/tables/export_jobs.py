"""Background rendering for exporters that have no incremental/streaming mode."""

from __future__ import annotations

import contextlib
import logging
import os
import pydoc
from typing import Any

import rq
from flask import has_request_context

import ckan.config.middleware
import ckan.plugins.toolkit as tk

from ckanext.tables.exporters import ExporterBase
from ckanext.tables.table import TableDefinition
from ckanext.tables.types import FilterItem, QueryParams
from ckanext.tables.utils import tables_get_resource_and_view, tables_init_temporary_preview_table

log = logging.getLogger(__name__)

_GENERIC_EXPORT_ERROR = tk._("An unexpected error occurred while preparing this export.")


@contextlib.contextmanager
def _ensure_request_context():
    """Push a request context for the export if one isn't already active."""
    if has_request_context():
        yield
        return

    flask_app = ckan.config.middleware.make_app(tk.config)
    with flask_app.test_request_context():
        yield


def _resolve_table_class(dotted_path: str) -> type[TableDefinition]:
    """Resolve a ``"module.ClassName"`` string into the class object.

    Only ever call this with a string this codebase generated itself from an
    already-instantiated table class (see ``GenericTableView._export_locator``)
    — never with one taken directly from a request. That's what makes the
    import here safe: it's never an attacker-influenced path, unlike say a
    table name read from a URL.

    Uses stdlib ``pydoc.locate`` rather than a hand-rolled ``rpartition(".")``
    + ``getattr`` split: the naive split only peels the last dot, so it
    breaks for a class nested inside another class (``Outer.Inner`` splits
    into module ``"...Outer"`` and attribute ``"Inner"``, and ``getattr``
    fails); ``pydoc.locate`` instead tries importing progressively longer
    prefixes and ``getattr``-walks whatever's left, which handles that case
    correctly.

    A class defined inside a function (a closure, not a module-level
    definition) still has no such importable path and will raise here — the
    same as any other export failure, this surfaces as the job's generic
    error result rather than a crash, since the caller always runs inside
    the same broad ``try/except`` as the rest of ``run_export_job``.
    """
    resolved = pydoc.locate(dotted_path)

    if not isinstance(resolved, type) or not issubclass(resolved, TableDefinition):
        # ValueError, not TypeError: this is one of several "invalid locator
        # content" failures in this module (see the ValueErrors above/below),
        # all handled identically by callers regardless of exception type.
        raise ValueError(f"{dotted_path!r} does not resolve to a TableDefinition subclass")  # noqa: TRY004

    return resolved


def _rebuild_table(locator: dict[str, Any]) -> TableDefinition:
    """Reconstruct the table a job's ``locator`` points at.

    ``locator["kind"]`` selects how: ``"resource_view"`` (``ResourceViewHandler``'s
    tables) rebuilds via the same resource/view lookup the request path uses,
    on the sheet the export was started from (``sheet_index``, absent on jobs
    enqueued before sheet selection existed — hence the default);
    ``"generic"`` (``GenericTableView``'s tables) resolves the table class from
    its dotted path and instantiates it with no arguments, same as
    ``GenericTableView.get`` already does.
    """
    kind = locator.get("kind")

    if kind == "resource_view":
        resource, resource_view = tables_get_resource_and_view(locator["resource_id"], locator["resource_view_id"])
        return tables_init_temporary_preview_table(resource, resource_view, locator.get("sheet_index", 0))

    if kind == "generic":
        table_class = _resolve_table_class(locator["table_class"])
        return table_class()  # type: ignore

    raise ValueError(f"Unsupported export locator kind: {kind!r}")


def check_export_locator_access(locator: dict[str, Any]) -> None:
    """Re-run the access check implied by *locator*, given only a job's own args.

    Lets the status/download routes take just a job id — nothing else in
    the URL — and still enforce the same access control the export endpoint
    itself already applied when it built this locator, instead of trusting
    whatever the caller passes in (a job id alone must not be enough to read
    someone else's export).
    """
    kind = locator.get("kind")

    if kind == "resource_view":
        tables_get_resource_and_view(locator["resource_id"], locator["resource_view_id"])
        return

    if kind == "generic":
        table_class = _resolve_table_class(locator["table_class"])
        try:
            table_class.check_access({})
        except tk.NotAuthorized:
            tk.abort(403, tk._("Not authorized to view this table."))
        return

    tk.abort(404, tk._("This export no longer exists — it may have expired."))


def _get_exporter(table: TableDefinition, exporter_name: str) -> type[ExporterBase]:
    exporter = table.get_exporter(exporter_name)

    if exporter is None:
        raise ValueError(f"Unknown exporter: {exporter_name!r}")

    return exporter


def _rebuild_params(params: dict[str, Any]) -> QueryParams:
    return QueryParams(
        filters=[FilterItem(**f) for f in params.get("filters", [])],
        sort_by=params.get("sort_by"),
        sort_order=params.get("sort_order"),
    )


def run_export_job(
    locator: dict[str, Any], exporter_name: str, params: dict[str, Any], export_dir: str
) -> dict[str, Any]:
    """Render one export and write it to *export_dir*. Runs inside an RQ worker.

    Returns a JSON-serialisable result — ``{"success": True, "disk_filename":
    ..., "filename": ..., "mime_type": ...}`` on success, ``{"success": False,
    "error": ...}`` on failure. The real exception is logged here and never
    put in the result: this becomes ``job.result``, readable by anyone who
    passes ``check_export_locator_access`` for this job's locator, and a raw
    traceback can embed data (a file path, a query fragment) that shouldn't
    be exposed that way — same principle as ``_GENERIC_ACTION_ERROR`` in
    ``generics.py``.

    The on-disk filename is the job's own id, not the table/timestamp name
    ``_prepare_export_filename`` produces for ``Content-Disposition`` — job
    ids are what the download endpoint looks files up by, and are never
    user-controlled, unlike a table name.
    """
    job = rq.get_current_job()
    job_id = job.id if job is not None else "unknown"

    try:
        with _ensure_request_context():
            table = _rebuild_table(locator)
            exporter = _get_exporter(table, exporter_name)
            data = exporter.export(table, _rebuild_params(params))

        disk_filename = f"{job_id}.{exporter.name}"
        with open(os.path.join(export_dir, disk_filename), "wb") as f:
            f.write(data)
    except Exception:
        log.exception("Background export failed (job=%s, exporter=%s)", job_id, exporter_name)
        return {"success": False, "error": str(_GENERIC_EXPORT_ERROR)}

    return {
        "success": True,
        "disk_filename": disk_filename,
        "filename": f"{table.name}.{exporter.name}",
        "mime_type": exporter.mime_type,
    }
