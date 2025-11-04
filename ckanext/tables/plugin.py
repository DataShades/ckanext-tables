import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan.common import CKANConfig


@tk.blanket.helpers
class TablesPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)

    # IConfigurer

    def update_config(self, config_: CKANConfig) -> None:
        tk.add_template_directory(config_, "templates")
        tk.add_resource("assets", "tables")
