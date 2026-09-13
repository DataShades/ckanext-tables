from unittest import mock

import pytest

import ckan.plugins.toolkit as tk

from ckanext.tables.data_sources import DataSourceError, ListDataSource
from ckanext.tables.table import TableDefinition
from ckanext.tables.views import ResourceViewHandler, _get_resource_and_view


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
    ``_get_resource_and_view`` checks it.
    """

    def test_mismatched_pair_is_rejected(self, app):
        resource = {"id": "res-1", "url": "http://example.com/data.csv", "format": "csv"}
        # This view genuinely exists, but it belongs to a *different* resource.
        resource_view = {"id": "view-1", "resource_id": "res-OTHER", "file_url": ""}

        with (
            app.flask_app.test_request_context("/"),
            mock.patch("ckanext.tables.views.tk.get_action", side_effect=_fake_get_action(resource, resource_view)),
            mock.patch("ckanext.tables.views.tk.abort", side_effect=tk.ObjectNotFound) as mock_abort,
            pytest.raises(tk.ObjectNotFound),
        ):
            _get_resource_and_view("res-1", "view-1")

        assert mock_abort.call_args[0][0] == 404

    def test_matching_pair_is_returned(self, app):
        resource = {"id": "res-1", "url": "http://example.com/data.csv", "format": "csv"}
        resource_view = {"id": "view-1", "resource_id": "res-1", "file_url": ""}

        with (
            app.flask_app.test_request_context("/"),
            mock.patch("ckanext.tables.views.tk.get_action", side_effect=_fake_get_action(resource, resource_view)),
        ):
            fetched_resource, fetched_resource_view = _get_resource_and_view("res-1", "view-1")

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
