import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan import types
from ckan.common import CKANConfig

from ckanext.tables.formatters import get_formatters
from ckanext.tables.types import Formatter, collect_tables_signal, table_registry


@tk.blanket.helpers
@tk.blanket.blueprints
class TablesPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)
    p.implements(p.IConfigurable)
    p.implements(p.ISignal)

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

    # ISignal

    def get_signal_subscriptions(self) -> types.SignalMapping:
        return {
            tk.signals.ckanext.signal("ckanext.tables.get_formatters"): [self.collect_formatters],
        }

    def collect_formatters(self, sender: None) -> dict[str, Formatter]:
        return get_formatters()
