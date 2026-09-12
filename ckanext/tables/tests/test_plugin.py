from unittest import mock

import pytest

import ckan.plugins.toolkit as tk

from ckanext.tables.cache import PickleCacheBackend
from ckanext.tables.plugin import TablesPlugin


@pytest.mark.ckan_config("ckan.plugins", "tables")
@pytest.mark.usefixtures("with_plugins", "with_request_context")
class TestTablesPlugin:
    def test_helpers_registered(self):
        assert hasattr(tk.h, "tables_json_dumps")
        assert hasattr(tk.h, "tables_get_filters_from_request")
        assert hasattr(tk.h, "tables_get_columns_visibility_from_request")
        assert hasattr(tk.h, "tables_generate_unique_id")

    def test_can_view_csv(self):
        plugin = TablesPlugin()
        assert plugin.can_view({"resource": {"format": "CSV"}}) is True

    def test_can_view_xlsx(self):
        plugin = TablesPlugin()
        assert plugin.can_view({"resource": {"format": "xlsx"}}) is True

    def test_can_view_unsupported(self):
        plugin = TablesPlugin()
        assert plugin.can_view({"resource": {"format": "XML"}}) is False

    def test_can_view_no_format(self):
        plugin = TablesPlugin()
        assert plugin.can_view({"resource": {}}) is False

    def test_view_template(self):
        plugin = TablesPlugin()
        result = plugin.view_template({}, {})
        assert "tables" in result
        assert ".html" in result

    def test_form_template(self):
        plugin = TablesPlugin()
        result = plugin.form_template({}, {})
        assert "tables" in result
        assert ".html" in result

    def test_info_returns_correct_keys(self):
        plugin = TablesPlugin()
        info = plugin.info()
        assert info["name"] == "tables_view"
        assert "schema" in info
        assert info["iframed"] is False

    def test_setup_template_variables(self):
        plugin = TablesPlugin()
        data_dict = {
            "resource": {"id": "my-resource-id"},
            "resource_view": {},
        }
        result = plugin.setup_template_variables({}, data_dict)
        assert result["resource_id"] == "my-resource-id"
        assert result["file_url"] == ""

    def test_setup_template_variables_with_file_url(self):
        plugin = TablesPlugin()
        data_dict = {
            "resource": {"id": "my-resource-id"},
            "resource_view": {"file_url": "my-file-url"},
        }
        result = plugin.setup_template_variables({}, data_dict)
        assert result["resource_id"] == "my-resource-id"
        assert result["file_url"] == "my-file-url"

    def test_setup_template_variables_defaults_title(self):
        plugin = TablesPlugin()
        resource_view = {}
        data_dict = {
            "resource": {"id": "res-123"},
            "resource_view": resource_view,
        }
        plugin.setup_template_variables({}, data_dict)
        assert resource_view["title"] == "Tables View"

    def test_blueprint_endpoint_accessible(self, app):
        """Verify the resource_table_ajax blueprint route is registered."""
        with app.flask_app.test_request_context():
            # just check the URL can be built - means the route is registered
            url = tk.h.url_for("tables.resource_table_ajax", resource_id="test-id", resource_view_id="view-id")
            assert "test-id" in url
            assert "view-id" in url


@pytest.mark.ckan_config("ckan.plugins", "tables")
@pytest.mark.usefixtures("with_plugins", "with_request_context")
class TestResourceControllerHooks:
    """before_resource_update/delete must invalidate both the DataFrame and its counts."""

    def test_before_resource_update_invalidates_on_new_upload(self, tmp_path):
        backend = PickleCacheBackend(cache_dir=str(tmp_path))
        key = "resource-res-1"
        backend.set(key, [{"a": 1}], ttl=60)

        with (
            mock.patch("ckanext.tables.plugin.get_cache_backend", return_value=backend),
            mock.patch("ckanext.tables.plugin.get_cache_ttl", return_value=60),
        ):
            TablesPlugin().before_resource_update(
                {}, current={"id": "res-1"}, resource={"id": "res-1", "url_type": "upload", "upload": "new-file"}
            )

        assert backend.get(key) is None
        assert backend.get(f"{key}:gen") is not None

    def test_before_resource_update_skips_upload_without_a_new_file(self, tmp_path):
        backend = PickleCacheBackend(cache_dir=str(tmp_path))
        key = "resource-res-1"
        backend.set(key, [{"a": 1}], ttl=60)

        with mock.patch("ckanext.tables.plugin.get_cache_backend", return_value=backend):
            TablesPlugin().before_resource_update(
                {}, current={"id": "res-1"}, resource={"id": "res-1", "url_type": "upload", "upload": None}
            )

        assert backend.get(key) == [{"a": 1}]

    def test_before_resource_delete_invalidates(self, tmp_path):
        backend = PickleCacheBackend(cache_dir=str(tmp_path))
        key = "resource-res-1"
        backend.set(key, [{"a": 1}], ttl=60)

        with (
            mock.patch("ckanext.tables.plugin.get_cache_backend", return_value=backend),
            mock.patch("ckanext.tables.plugin.get_cache_ttl", return_value=60),
        ):
            TablesPlugin().before_resource_delete({}, resource={"id": "res-1"}, resources=[])

        assert backend.get(key) is None
        assert backend.get(f"{key}:gen") is not None
