"""End-to-end HTTP tests for the resource-view and generic-view blueprint routes.

Unlike ``test_views.py`` (which calls ``ResourceViewHandler.get``/``.post`` directly,
in-process, bypassing Flask's routing) and ``test_generics.py``'s ``TestGenericTableView``
(same pattern for ``_dispatch_get``/``_dispatch_post``), these go through the real
registered blueprint via ``app.get``/``app.post`` — real URL routing, a real CKAN
resource + resource view, and the real Flask test client.
"""

import json
from unittest import mock

import pytest

import ckan.plugins.toolkit as tk
import ckan.tests.factories as factories
import ckan.tests.helpers as helpers


def _ajax_url(resource_id: str, resource_view_id: str) -> str:
    return tk.url_for("tables.resource_table_ajax", resource_id=resource_id, resource_view_id=resource_view_id)


def _deferred_url(resource_id: str, resource_view_id: str) -> str:
    return tk.url_for("tables.resource_table_deferred", resource_id=resource_id, resource_view_id=resource_view_id)


@pytest.mark.ckan_config("ckan.plugins", "tables")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestResourceViewHandlerHTTP:
    """The AJAX/export/action endpoint for a Tables resource view, over real HTTP."""

    def _make_csv_resource_and_view(self, package, create_with_upload):
        resource = create_with_upload(
            b"name,age\nAlice,30\nBob,25\n",
            "people.csv",
            package_id=package["id"],
        )
        resource_view = factories.ResourceView(resource_id=resource["id"], view_type="tables_view")
        return resource, resource_view

    def test_ajax_get_returns_the_uploaded_csv_rows(self, app, package, create_with_upload):
        resource, resource_view = self._make_csv_resource_and_view(package, create_with_upload)

        response = app.get(
            _ajax_url(resource["id"], resource_view["id"]),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 200
        data = response.json
        assert data["total"] == 2
        assert data["data"][0]["name"] == "Alice"

    def test_export_get_returns_a_csv_attachment(self, app, package, create_with_upload):
        resource, resource_view = self._make_csv_resource_and_view(package, create_with_upload)

        response = app.get(f"{_ajax_url(resource['id'], resource_view['id'])}?exporter=csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers["Content-Type"]
        assert "attachment" in response.headers["Content-Disposition"]
        assert b"Alice" in response.data

    def test_export_unknown_exporter_returns_404_json(self, app, package, create_with_upload):
        resource, resource_view = self._make_csv_resource_and_view(package, create_with_upload)

        response = app.get(f"{_ajax_url(resource['id'], resource_view['id'])}?exporter=does-not-exist")

        assert response.status_code == 404
        assert response.json["success"] is False

    def test_non_ajax_get_is_rejected(self, app, package, create_with_upload):
        """This endpoint only ever serves AJAX/export requests — a plain GET is a 400."""
        resource, resource_view = self._make_csv_resource_and_view(package, create_with_upload)

        response = app.get(_ajax_url(resource["id"], resource_view["id"]))

        assert response.status_code == 400

    def test_mismatched_resource_and_view_is_404(self, app, package, create_with_upload):
        resource, _resource_view = self._make_csv_resource_and_view(package, create_with_upload)
        other_resource = factories.Resource(package_id=package["id"])
        other_view = factories.ResourceView(resource_id=other_resource["id"], view_type="tables_view")

        response = app.get(
            _ajax_url(resource["id"], other_view["id"]),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 404

    def test_nonexistent_resource_is_404(self, app, package, create_with_upload):
        _resource, resource_view = self._make_csv_resource_and_view(package, create_with_upload)

        response = app.get(
            _ajax_url("does-not-exist", resource_view["id"]),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 404

    def test_unreachable_file_url_returns_502(self, app, package, create_with_upload):
        """An unreachable file_url override surfaces as a 502, not a 500 or a hang."""
        resource, _resource_view = self._make_csv_resource_and_view(package, create_with_upload)
        resource_view = factories.ResourceView(
            resource_id=resource["id"],
            view_type="tables_view",
            file_url="http://unreachable.invalid/data.csv",
        )

        response = app.get(
            _ajax_url(resource["id"], resource_view["id"]),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 502
        assert "error" in response.json

    def test_post_refresh_requires_resource_update(self, app, package, create_with_upload):
        resource, resource_view = self._make_csv_resource_and_view(package, create_with_upload)
        url = _ajax_url(resource["id"], resource_view["id"])

        anon_response = app.post(url, data={"refresh": "true"})
        assert anon_response.status_code == 403

        app.set_session_user(package["creator_user_id"])
        owner_response = app.post(url, data={"refresh": "true"})
        assert owner_response.status_code == 200
        assert owner_response.json["success"] is True

    def test_post_unknown_table_action_returns_the_error_envelope(self, app, package, create_with_upload):
        resource, resource_view = self._make_csv_resource_and_view(package, create_with_upload)

        response = app.post(
            _ajax_url(resource["id"], resource_view["id"]),
            data={"table_action": "does_not_exist"},
        )

        assert response.status_code == 200
        data = response.json
        assert data["success"] is False
        assert data["error"]


@pytest.mark.ckan_config("ckan.plugins", "tables datastore")
@pytest.mark.usefixtures("with_plugins", "clean_db", "clean_datastore")
class TestResourceViewHandlerHTTPDatastore:
    """A datastore-backed resource uses DataStoreDataSource, not a file fetch/cache."""

    def test_ajax_get_reads_datastore_records(self, app, package):
        result = helpers.call_action(
            "datastore_create",
            resource={"package_id": package["id"]},
            fields=[{"id": "name", "type": "text"}, {"id": "age", "type": "int"}],
            records=[{"name": "Alice", "age": 30}, {"name": "Bob", "age": 25}],
        )
        resource_id = result["resource_id"]
        resource_view = factories.ResourceView(resource_id=resource_id, view_type="tables_view")

        response = app.get(
            _ajax_url(resource_id, resource_view["id"]),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 200
        data = response.json
        assert data["total"] == 2
        assert {row["name"] for row in data["data"]} == {"Alice", "Bob"}


@pytest.mark.ckan_config("ckan.plugins", "tables")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestResourceViewDeferredHandlerHTTP:
    """HTMX's lazy-load endpoint — always 200, success or failure (see its own docstring)."""

    def test_working_resource_renders_the_table_snippet(self, app, package, create_with_upload):
        resource = create_with_upload(b"name\nAlice\n", "people.csv", package_id=package["id"])
        resource_view = factories.ResourceView(resource_id=resource["id"], view_type="tables_view")

        response = app.get(_deferred_url(resource["id"], resource_view["id"]))

        assert response.status_code == 200
        assert b"tabulator-container" in response.data

    def test_broken_resource_still_returns_200_with_an_error_snippet(self, app, package, create_with_upload):
        resource = create_with_upload(b"name\nAlice\n", "people.csv", package_id=package["id"])
        resource_view = factories.ResourceView(
            resource_id=resource["id"],
            view_type="tables_view",
            file_url="http://unreachable.invalid/data.csv",
        )

        response = app.get(_deferred_url(resource["id"], resource_view["id"]))

        # Never a raw error status here — see ResourceViewDeferredHandler's own
        # docstring: HTMX won't swap a non-2xx response into the page.
        assert response.status_code == 200
        assert b"tabulator-container" not in response.data


@pytest.mark.ckan_config("ckan.plugins", "tables tables_demo")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestGenericTableViewHTTP:
    """The demo plugin's already-registered /tables-demo/packages route.

    Backed by DatabaseDataSource with no row/bulk/table actions — deliberately
    avoids PeopleTable/ProductsTable, whose actions mutate a module-level list
    shared for the life of the test process. None of the demo tables override
    ``check_access``, so every request here needs a sysadmin session — the
    default is "sysadmins only" (see ``TableDefinition.check_access``).
    """

    def test_full_page_get_renders(self, app, sysadmin):
        app.set_session_user(sysadmin["id"])
        response = app.get(tk.url_for("tables_demo.packages"))

        assert response.status_code == 200
        assert b"tabulator-container" in response.data

    def test_anonymous_get_is_403(self, app):
        response = app.get(tk.url_for("tables_demo.packages"))

        assert response.status_code == 403

    def test_ajax_get_returns_real_package_rows(self, app, sysadmin):
        factories.Dataset(name="ds-one")
        factories.Dataset(name="ds-two")

        app.set_session_user(sysadmin["id"])
        response = app.get(
            tk.url_for("tables_demo.packages"),
            headers={"X-Requested-With": "XMLHttpRequest"},
        )

        assert response.status_code == 200
        data = response.json
        assert data["total"] >= 2
        names = {row["name"] for row in data["data"]}
        assert {"ds-one", "ds-two"} <= names

    def test_export_get_returns_csv(self, app, sysadmin):
        factories.Dataset(name="export-me")

        app.set_session_user(sysadmin["id"])
        response = app.get(f"{tk.url_for('tables_demo.packages')}?exporter=csv")

        assert response.status_code == 200
        assert "text/csv" in response.headers["Content-Type"]
        assert b"export-me" in response.data

    def test_post_with_no_action_returns_the_error_envelope(self, app, sysadmin):
        app.set_session_user(sysadmin["id"])
        response = app.post(tk.url_for("tables_demo.packages"), data={})

        assert response.status_code == 200
        data = response.json
        assert data["success"] is False


def _export_status_url(job_id: str) -> str:
    return tk.url_for("tables.table_export_status", job_id=job_id)


def _export_download_url(job_id: str) -> str:
    return tk.url_for("tables.table_export_download", job_id=job_id)


def _fake_export_job(status: str, result: dict | None = None):
    job = mock.Mock()
    job.get_status.return_value = status
    job.result = result
    job.args = [{"kind": "resource_view", "resource_id": "res-1", "resource_view_id": "view-1"}]
    return job


def _allow_resource_view_access():
    resource = {"id": "res-1", "url": "http://example.com/data.csv", "format": "csv"}
    resource_view = {"id": "view-1", "resource_id": "res-1", "file_url": ""}

    def get_action(name):
        def resource_show(context, data_dict):
            if data_dict["id"] != resource["id"]:
                raise tk.ObjectNotFound
            return resource

        def resource_view_show(context, data_dict):
            if data_dict["id"] != resource_view["id"]:
                raise tk.ObjectNotFound
            return resource_view

        return {"resource_show": resource_show, "resource_view_show": resource_view_show}[name]

    return mock.patch("ckanext.tables.utils.tk.get_action", side_effect=get_action)


@pytest.mark.ckan_config("ckan.plugins", "tables")
@pytest.mark.usefixtures("with_plugins", "clean_db")
class TestExportStatusHandlerHTTP:
    """The full-page/HTML branch of ExportStatusHandler.

    Needs real routing (see ``test_views.py``'s ``TestExportStatusHandler``
    docstring): CKAN's ``page.html`` chrome relies on state a bare
    ``test_request_context()`` never sets up.
    """

    def test_in_progress_job_has_no_download_link_and_carries_its_own_poll_trigger(self, app):
        with (
            _allow_resource_view_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=_fake_export_job("started")),
        ):
            response = app.get(_export_status_url("job-1"))

        html = response.get_data(as_text=True)
        assert 'hx-trigger="every 2s"' in html
        assert "Download" not in html

    def test_finished_job_shows_a_download_link(self, app):
        job = _fake_export_job("finished", {"success": True, "filename": "t.csv"})

        with (
            _allow_resource_view_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=job),
        ):
            response = app.get(_export_status_url("job-1"))

        html = response.get_data(as_text=True)
        assert _export_download_url("job-1") in html
        assert "every 2s" not in html

    def test_failed_job_shows_the_error_without_a_download_link(self, app):
        job = _fake_export_job("failed", {"success": False, "error": "Something broke"})

        with (
            _allow_resource_view_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=job),
        ):
            response = app.get(_export_status_url("job-1"))

        html = response.get_data(as_text=True)
        assert "Something broke" in html
        assert "Download" not in html

    def test_unknown_job_shows_not_found(self, app):
        with mock.patch("ckanext.tables.views.tk.job_from_id", side_effect=KeyError("no such job")):
            response = app.get(_export_status_url("job-1"))

        assert "no longer exists" in response.get_data(as_text=True)

    def test_plain_navigation_gets_the_full_page(self, app):
        with (
            _allow_resource_view_access(),
            mock.patch("ckanext.tables.views.tk.job_from_id", return_value=_fake_export_job("started")),
        ):
            response = app.get(_export_status_url("job-1"))

        assert "Export status" in response.get_data(as_text=True)


@pytest.mark.ckan_config("ckan.plugins", "tables")
@pytest.mark.usefixtures("with_plugins", "clean_db")
def test_ajax_response_matches_docs_generics_md_contract(app, package, create_with_upload):
    """A smoke check tying the actual response shape to what docs/generics.md promises."""
    resource = create_with_upload(b"name\n", "empty.csv", package_id=package["id"])
    resource_view = factories.ResourceView(resource_id=resource["id"], view_type="tables_view")

    response = app.get(
        tk.url_for("tables.resource_table_ajax", resource_id=resource["id"], resource_view_id=resource_view["id"]),
        headers={"X-Requested-With": "XMLHttpRequest"},
    )

    assert response.status_code == 200
    data = json.loads(response.get_data(as_text=True))
    assert set(data) >= {"data", "last_page", "total"}
