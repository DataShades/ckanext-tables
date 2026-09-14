import json
from unittest import mock

import pytest

import ckan.plugins.toolkit as tk

from ckanext.tables.data_sources import DataSourceError, ListDataSource
from ckanext.tables.table import TableDefinition
from ckanext.tables.utils import tables_get_resource_and_view
from ckanext.tables.views import ExportDownloadHandler, ExportStatusHandler, ResourceViewHandler


def _fake_get_action(resource: dict, resource_view: dict):
    """Return a tk.get_action stand-in serving the given resource/view dicts by id."""

    def resource_show(context, data_dict):
        if data_dict["id"] != resource["id"]:
            raise tk.ObjectNotFound
        return resource

    def resource_view_show(context, data_dict):
        if data_dict["id"] != resource_view["id"]:
            raise tk.ObjectNotFound
        return resource_view

    def get_action(name):
        return {"resource_show": resource_show, "resource_view_show": resource_view_show}[name]

    return get_action


@pytest.mark.usefixtures("with_request_context")
class TestGetResourceAndView:
    """A resource and a resource view are each looked up independently by id.

    Nothing else confirms the view actually belongs to that resource unless
    ``tables_get_resource_and_view`` checks it. Lives in utils.py, not
    views.py, so export_jobs.py's background-job worker can reuse the exact
    same lookup/ownership check without an import cycle (views.py imports
    generics.py, which imports export_jobs.py).
    """

    def test_mismatched_pair_is_rejected(self, app):
        resource = {"id": "res-1", "url": "http://example.com/data.csv", "format": "csv"}
        # This view genuinely exists, but it belongs to a *different* resource.
        resource_view = {"id": "view-1", "resource_id": "res-OTHER", "file_url": ""}

        with (
            app.flask_app.test_request_context("/"),
            mock.patch("ckanext.tables.utils.tk.get_action", side_effect=_fake_get_action(resource, resource_view)),
            mock.patch("ckanext.tables.utils.tk.abort", side_effect=tk.ObjectNotFound) as mock_abort,
            pytest.raises(tk.ObjectNotFound),
        ):
            tables_get_resource_and_view("res-1", "view-1")

        assert mock_abort.call_args[0][0] == 404

    def test_matching_pair_is_returned(self, app):
        resource = {"id": "res-1", "url": "http://example.com/data.csv", "format": "csv"}
        resource_view = {"id": "view-1", "resource_id": "res-1", "file_url": ""}

        with (
            app.flask_app.test_request_context("/"),
            mock.patch("ckanext.tables.utils.tk.get_action", side_effect=_fake_get_action(resource, resource_view)),
        ):
            fetched_resource, fetched_resource_view = tables_get_resource_and_view("res-1", "view-1")

        assert fetched_resource == resource
        assert fetched_resource_view == resource_view


@pytest.mark.usefixtures("with_request_context")
class TestResourceViewHandlerRefresh:
    """``refresh`` busts the resource's data cache and forces a re-fetch/re-parse.

    ``get_table_for_resource`` only requires read access (``resource_show``), so
    without an extra check here, any visitor to a public resource could repeatedly
    trigger that re-fetch — this locks in that ``refresh`` itself requires
    ``resource_update`` (edit access to the resource), independent of that read check.
    """

    def _make_handler(self):
        table = TableDefinition(name="t", data_source=ListDataSource([{"a": 1}]))
        handler = ResourceViewHandler()
        return handler, table

    def test_refresh_denied_without_resource_update(self, app):
        handler, table = self._make_handler()

        with (
            app.flask_app.test_request_context("/", method="POST", data={"refresh": "true"}),
            mock.patch.object(handler, "get_table_for_resource", return_value=table),
            mock.patch("ckanext.tables.views.tk.check_access", side_effect=tk.NotAuthorized),
            mock.patch("ckanext.tables.views.tk.abort", side_effect=tk.NotAuthorized) as mock_abort,
            mock.patch.object(table, "refresh_data") as mock_refresh,
            pytest.raises(tk.NotAuthorized),
        ):
            handler.post("res-1", "view-1")

        assert mock_abort.call_args[0][0] == 403
        assert not mock_refresh.called

    def test_refresh_checks_resource_update_for_this_resource(self, app):
        handler, table = self._make_handler()

        with (
            app.flask_app.test_request_context("/", method="POST", data={"refresh": "true"}),
            mock.patch.object(handler, "get_table_for_resource", return_value=table),
            mock.patch("ckanext.tables.views.tk.check_access", return_value=True) as mock_check,
            mock.patch.object(table, "refresh_data"),
        ):
            handler.post("res-1", "view-1")

        assert mock_check.call_args[0][0] == "resource_update"
        assert mock_check.call_args[0][2] == {"id": "res-1"}

    def test_refresh_allowed_with_resource_update(self, app):
        handler, table = self._make_handler()

        with (
            app.flask_app.test_request_context("/", method="POST", data={"refresh": "true"}),
            mock.patch.object(handler, "get_table_for_resource", return_value=table),
            mock.patch("ckanext.tables.views.tk.check_access", return_value=True),
            mock.patch.object(table, "refresh_data") as mock_refresh,
        ):
            response = handler.post("res-1", "view-1")

        assert response.status_code == 200
        assert mock_refresh.called

    def test_other_actions_unaffected_by_the_refresh_check(self, app):
        """Confirm actions other than refresh never touch the new resource_update check.

        The built-in preview table has no row/bulk/table actions configured, so they
        should still just short-circuit to "not implemented".
        """
        handler, table = self._make_handler()

        with (
            app.flask_app.test_request_context("/", method="POST", data={"table_action": "does_not_exist"}),
            mock.patch.object(handler, "get_table_for_resource", return_value=table),
            mock.patch("ckanext.tables.views.tk.check_access") as mock_check,
        ):
            response = handler.post("res-1", "view-1")

        assert not mock_check.called
        assert response.get_json()["success"] is False


@pytest.mark.usefixtures("with_request_context")
class TestResourceViewHandlerDataSourceErrors:
    """DataSourceError surfaces as a 502 JSON error."""

    def _make_handler(self):
        table = TableDefinition(name="t", data_source=ListDataSource([{"a": 1}]))
        handler = ResourceViewHandler()
        return handler, table

    def test_get_returns_502_when_the_table_cannot_be_built(self, app):
        handler, _table = self._make_handler()

        with (
            app.flask_app.test_request_context("/"),
            mock.patch.object(handler, "get_table_for_resource", side_effect=DataSourceError("boom")),
        ):
            response = handler.get("res-1", "view-1")

        assert response[1] == 502
        assert "error" in response[0].get_json()

    def test_post_returns_502_when_the_table_cannot_be_built(self, app):
        handler, _table = self._make_handler()

        with (
            app.flask_app.test_request_context("/", method="POST", data={"table_action": "whatever"}),
            mock.patch.object(handler, "get_table_for_resource", side_effect=DataSourceError("boom")),
        ):
            response = handler.post("res-1", "view-1")

        assert response[1] == 502
        assert "error" in response[0].get_json()

    def test_ajax_get_returns_502_when_fetching_data_fails(self, app):
        handler, table = self._make_handler()

        with (
            app.flask_app.test_request_context("/", headers={"X-Requested-With": "XMLHttpRequest"}),
            mock.patch.object(handler, "get_table_for_resource", return_value=table),
            mock.patch.object(table, "get_data", side_effect=DataSourceError("boom")),
        ):
            response = handler.get("res-1", "view-1")

        assert response[1] == 502
        assert "error" in response[0].get_json()


@pytest.mark.usefixtures("with_request_context")
class TestResourceViewHandlerExportLocator:
    """A background export needs enough context to rebuild the table in a worker process."""

    def _make_handler(self):
        table = TableDefinition(name="t", data_source=ListDataSource([{"a": 1}]))
        handler = ResourceViewHandler()
        return handler, table

    def test_locator_uses_the_ids_get_and_post_set_before_dispatch(self, app):
        """get()/post() set _resource_id/_resource_view_id before calling get_table_for_resource — see views.py."""
        handler, _table = self._make_handler()
        resource = {"id": "res-1", "url": "http://example.com/data.csv", "format": "csv"}
        resource_view = {"id": "view-1", "resource_id": "res-1", "file_url": ""}
        handler._resource_id = "res-1"
        handler._resource_view_id = "view-1"

        with (
            app.flask_app.test_request_context("/"),
            mock.patch("ckanext.tables.utils.tk.get_action", side_effect=_fake_get_action(resource, resource_view)),
            mock.patch("ckanext.tables.utils.tables_guess_data_source", return_value=ListDataSource([{"a": 1}])),
        ):
            table = handler.get_table_for_resource("res-1", "view-1")

        assert handler._export_locator(table) == {
            "kind": "resource_view",
            "resource_id": "res-1",
            "resource_view_id": "view-1",
        }

    def test_status_url_uses_the_export_status_endpoint(self, app):
        handler, _table = self._make_handler()

        with app.flask_app.test_request_context("/"):
            url = handler._export_status_url("job-123")

        assert url == tk.url_for("tables.table_export_status", job_id="job-123")


_RESOURCE_VIEW_LOCATOR = {"kind": "resource_view", "resource_id": "res-1", "resource_view_id": "view-1"}


def _fake_job(status: str, result: dict | None = None, locator: dict | None = None):
    job = mock.Mock()
    job.get_status.return_value = status
    job.result = result
    job.args = [locator if locator is not None else _RESOURCE_VIEW_LOCATOR]
    return job


@pytest.mark.usefixtures("with_request_context")
class TestExportStatusHandler:
    """Unit tests for the handler's branching/access logic only."""

    def _handler_and_url(self, app):
        handler = ExportStatusHandler()
        url = "/table-export-status/job-1"
        return handler, url

    def _allow_access(self):
        resource = {"id": "res-1", "url": "http://example.com/data.csv", "format": "csv"}
        resource_view = {"id": "view-1", "resource_id": "res-1", "file_url": ""}
        return mock.patch("ckanext.tables.utils.tk.get_action", side_effect=_fake_get_action(resource, resource_view))

    def test_unknown_job_reports_not_found_as_json(self, app):
        handler, url = self._handler_and_url(app)

        with (
            app.flask_app.test_request_context(url, headers={"X-Requested-With": "XMLHttpRequest"}),
            mock.patch("ckanext.tables.views.tk.job_from_id", side_effect=KeyError("no such job")),
        ):
            response = handler.get("job-1")

        data = json.loads(response.get_data(as_text=True))
        assert data == {"status": "not_found", "download_url": None, "error": None}

    def test_in_progress_job_has_no_download_url_as_json(self, app):
        handler, url = self._handler_and_url(app)

        with (
            app.flask_app.test_request_context(url, headers={"X-Requested-With": "XMLHttpRequest"}),
            self._allow_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=_fake_job("started")),
        ):
            response = handler.get("job-1")

        data = json.loads(response.get_data(as_text=True))
        assert data == {"status": "started", "download_url": None, "error": None}

    def test_finished_job_has_a_download_url_as_json(self, app):
        handler, url = self._handler_and_url(app)
        job = _fake_job("finished", {"success": True, "filename": "t.csv"})

        with (
            app.flask_app.test_request_context(url, headers={"X-Requested-With": "XMLHttpRequest"}),
            self._allow_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=job),
        ):
            response = handler.get("job-1")

        data = json.loads(response.get_data(as_text=True))
        assert data["status"] == "finished"
        assert data["download_url"]
        assert "/table-export-download/job-1" in data["download_url"]

    def test_failed_job_carries_the_error_as_json(self, app):
        handler, url = self._handler_and_url(app)
        job = _fake_job("failed", {"success": False, "error": "Something broke"})

        with (
            app.flask_app.test_request_context(url, headers={"X-Requested-With": "XMLHttpRequest"}),
            self._allow_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=job),
        ):
            response = handler.get("job-1")

        data = json.loads(response.get_data(as_text=True))
        assert data == {"status": "failed", "download_url": None, "error": "Something broke"}

    def test_htmx_request_gets_only_the_fragment(self, app):
        handler, url = self._handler_and_url(app)

        with (
            app.flask_app.test_request_context(url, headers={"HX-Request": "true"}),
            self._allow_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=_fake_job("started")),
        ):
            html = handler.get("job-1")

        assert "<html" not in html.lower()

    def test_denies_access_using_the_jobs_own_locator_not_the_url(self, app):
        """The URL carries only a job id now — access comes from the job's own locator."""
        handler, url = self._handler_and_url(app)
        job = _fake_job(
            "finished",
            {"success": True},
            locator={"kind": "resource_view", "resource_id": "other-res", "resource_view_id": "view-1"},
        )

        with (
            app.flask_app.test_request_context(url),
            mock.patch("ckanext.tables.utils.tk.get_action", side_effect=tk.NotAuthorized),
            mock.patch("ckanext.tables.utils.tk.abort", side_effect=tk.ObjectNotFound) as mock_abort,
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=job),
            pytest.raises(tk.ObjectNotFound),
        ):
            handler.get("job-1")

        assert mock_abort.call_args[0][0] == 403


@pytest.mark.usefixtures("with_request_context")
class TestExportDownloadHandler:
    def _handler_and_url(self):
        handler = ExportDownloadHandler()
        return handler, "/table-export-download/job-1"

    def _allow_access(self):
        resource = {"id": "res-1", "url": "http://example.com/data.csv", "format": "csv"}
        resource_view = {"id": "view-1", "resource_id": "res-1", "file_url": ""}
        return mock.patch("ckanext.tables.utils.tk.get_action", side_effect=_fake_get_action(resource, resource_view))

    def test_unknown_job_is_404(self, app):
        handler, url = self._handler_and_url()

        with (
            app.flask_app.test_request_context(url),
            mock.patch("ckanext.tables.views.tk.job_from_id", side_effect=KeyError("no such job")),
            mock.patch("ckanext.tables.views.tk.abort", side_effect=tk.ObjectNotFound) as mock_abort,
            pytest.raises(tk.ObjectNotFound),
        ):
            handler.get("job-1")

        assert mock_abort.call_args[0][0] == 404

    def test_unfinished_job_is_404(self, app):
        handler, url = self._handler_and_url()

        with (
            app.flask_app.test_request_context(url),
            self._allow_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=_fake_job("started")),
            mock.patch("ckanext.tables.views.tk.abort", side_effect=tk.ObjectNotFound) as mock_abort,
            pytest.raises(tk.ObjectNotFound),
        ):
            handler.get("job-1")

        assert mock_abort.call_args[0][0] == 404

    def test_failed_job_is_404_not_a_download_of_the_error(self, app):
        handler, url = self._handler_and_url()
        job = _fake_job("finished", {"success": False, "error": "boom"})

        with (
            app.flask_app.test_request_context(url),
            self._allow_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=job),
            mock.patch("ckanext.tables.views.tk.abort", side_effect=tk.ObjectNotFound) as mock_abort,
            pytest.raises(tk.ObjectNotFound),
        ):
            handler.get("job-1")

        assert mock_abort.call_args[0][0] == 404

    def test_missing_file_on_disk_is_404(self, app, tmp_path):
        handler, url = self._handler_and_url()
        job = _fake_job("finished", {"success": True, "disk_filename": "job-1.csv", "filename": "t.csv"})

        with (
            app.flask_app.test_request_context(url),
            self._allow_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=job),
            mock.patch("ckanext.tables.views.get_export_dir", return_value=str(tmp_path)),
            mock.patch("ckanext.tables.views.tk.abort", side_effect=tk.ObjectNotFound) as mock_abort,
            pytest.raises(tk.ObjectNotFound),
        ):
            handler.get("job-1")

        assert mock_abort.call_args[0][0] == 404

    def test_streams_the_file_with_the_pretty_filename(self, app, tmp_path):
        handler, url = self._handler_and_url()
        (tmp_path / "job-1.csv").write_bytes(b"a,b\n1,2\n")
        job = _fake_job(
            "finished",
            {"success": True, "disk_filename": "job-1.csv", "filename": "t.csv", "mime_type": "text/csv"},
        )

        with (
            app.flask_app.test_request_context(url),
            self._allow_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=job),
            mock.patch("ckanext.tables.views.get_export_dir", return_value=str(tmp_path)),
        ):
            response = handler.get("job-1")

        assert response.mimetype == "text/csv"
        assert 'filename="t.csv"' in response.headers["Content-Disposition"]
        assert response.get_data() == b"a,b\n1,2\n"
