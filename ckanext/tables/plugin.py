from typing import Any

import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan import types
from ckan.common import CKANConfig

from ckanext.tables.logic.schema import get_preview_schema


@tk.blanket.helpers
@tk.blanket.blueprints
@tk.blanket.config_declarations
class TablesPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)
    p.implements(p.IResourceView, inherit=True)

    # IConfigurer

    def update_config(self, config_: CKANConfig) -> None:
        tk.add_template_directory(config_, "templates")
        tk.add_resource("assets", "tables")

    # IResourceView

    def info(self) -> dict[str, Any]:
        return {
            "name": "tables_view",
            "title": tk._("Tables"),
            "icon": "table",
            "iframed": False,
            "schema": get_preview_schema(),
            "always_available": True,
            "default_title": "Tables View",
        }

    def can_view(self, data_dict: types.DataDict) -> bool:
        fmt = data_dict["resource"].get("format", "").lower()
        return fmt in ["csv", "xlsx", "orc", "parquet", "feather"]

    def view_template(self, context: types.Context, data_dict: types.DataDict) -> str:
        return "tables/view/table_preview.html"

    def form_template(self, context: types.Context, data_dict: types.DataDict) -> str:
        return "tables/view/table_form.html"

    def setup_template_variables(self, context: types.Context, data_dict: types.DataDict) -> dict[str, str]:
        data_dict["resource_view"].setdefault("title", "Tables View")

        resource_id = data_dict["resource"]["id"]

        return {"resource_id": resource_id}
