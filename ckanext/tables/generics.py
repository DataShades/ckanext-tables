from __future__ import annotations

import logging

from flask import Response
from flask.views import MethodView

import ckan.plugins.toolkit as tk

from ckanext.tables.table import TableDefinition

log = logging.getLogger(__name__)


class GenericTableView(MethodView):
    def __init__(
        self,
        table: str,
        breadcrumb_label: str = "Table",
        page_title: str = "",
    ):
        """A generic view to render tables.

        Args:
            table: a table definition
            render_template (optional): a path to a render template
            breadcrumb_label (optional): the label to use in the breadcrumb
            page_title (optional): the title to use in the page
        """
        self.table_class: type[TableDefinition] = tk.h.tables_get_table(table)
        self.breadcrumb_label = breadcrumb_label
        self.page_title = page_title

        if not self.table_class:
            raise tk.ObjectNotFound(f"Table {table} not found")  # noqa: TRY003

    def get(self) -> str | Response:
        """Render a table.

        If the data argument is provided, returns the table data
        """
        table = self.table_class()  # type: ignore

        return table.render_table(breadcrumb_label=self.breadcrumb_label, page_title=self.page_title)
