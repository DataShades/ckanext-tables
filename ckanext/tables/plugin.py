import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan.common import CKANConfig

from ckanext.tables.table import table_registry
from ckanext.tables.types import collect_tables_signal


@tk.blanket.helpers
class TablesPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)
    p.implements(p.IConfigurable)

    # IConfigurer

    def update_config(self, config_: CKANConfig) -> None:
        tk.add_template_directory(config_, "templates")
        tk.add_resource("assets", "tables")

    # IConfigurable

    def configure(self, config_: CKANConfig):
        self.register_tables()

    @staticmethod
    def register_tables():
        table_registry.reset()

        for _, tables in collect_tables_signal.send():
            for table_name, table in tables.items():
                table_registry.register(table_name, table)
