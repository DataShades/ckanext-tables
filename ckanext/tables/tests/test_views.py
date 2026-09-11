from unittest import mock

import pytest

import ckan.plugins.toolkit as tk

from ckanext.tables.data_sources import ListDataSource
from ckanext.tables.table import TableDefinition
from ckanext.tables.views import ResourceViewHandler


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
