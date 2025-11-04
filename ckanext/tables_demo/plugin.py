from ckan import plugins as p
from ckan.common import CKANConfig
from ckan.plugins import toolkit as tk


@tk.blanket.blueprints
class TablesDemoPlugin(p.SingletonPlugin):
    p.implements(p.IConfigurer)

    # IConfigurer

    def update_config(self, config_: CKANConfig) -> None:
        tk.add_template_directory(config_, "templates")
