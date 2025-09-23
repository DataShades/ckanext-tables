from __future__ import annotations

import json
import logging
from abc import abstractmethod

from flask import Response, jsonify
from flask.views import MethodView

import ckan.plugins.toolkit as tk

from ckanext.tables import types
from ckanext.tables.table import QueryParams, TableDefinition

log = logging.getLogger(__name__)


class GenericTableView(MethodView):
    def __init__(
        self,
        table: type[TableDefinition],
        breadcrumb_label: str = "Table",
        page_title: str = "Table",
    ):
        """A generic view to render tables.

        Args:
            table: a table definition
            render_template (optional): a path to a render template
            breadcrumb_label (optional): the label to use in the breadcrumb
            page_title (optional): the title to use in the page
        """
        self.table = table
        self.breadcrumb_label = breadcrumb_label
        self.page_title = page_title

    def get(self) -> str | Response:
        """Render a table.

        If the data argument is provided, returns the table data
        """
        table = self.table() # type: ignore

        if tk.request.args.get("data"):
            params = QueryParams(
                page=tk.request.args.get("page", 1, int),
                size=tk.request.args.get("size", 10, int),
                field=tk.request.args.get("field"),
                operator=tk.request.args.get("operator"),
                value=tk.request.args.get("q"),
                sort_by=tk.request.args.get("sort[0][field]"),
                sort_order=tk.request.args.get("sort[0][dir]"),
            )

            data = table.get_data(params)
            total = table.get_total_count(params)

            return jsonify(
                {"data": data, "last_page": (total + params.size - 1) // params.size}
            )

        return table.render_table(
            breadcrumb_label=self.breadcrumb_label, page_title=self.page_title
        )

    def post(self) -> Response:
        """Handle global actions on a table."""
        global_action = tk.request.form.get("global_action")
        rows = tk.request.form.get("rows")

        action_func = self.get_global_action(global_action) if global_action else None

        if not action_func or not rows:
            return jsonify(
                {
                    "success": False,
                    "errors": [tk._("The global action is not implemented")],
                }
            )

        errors = []

        for row in json.loads(rows):
            success, error = action_func(row)

            if not success:
                log.debug("Error during global action %s: %s", global_action, error)
                errors.append(error)

        return jsonify({"success": not errors, "errors": errors})

    @abstractmethod
    def get_global_action(self, value: str) -> types.GlobalActionHandler | None:
        pass
