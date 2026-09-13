from flask import Blueprint

import ckan.plugins.toolkit as tk

from ckanext.tables.shared import GenericTableView
from ckanext.tables_demo.table import PackagesTable, PeopleTable, ProductsTable

bp = Blueprint("tables_demo", __name__, url_prefix="/tables-demo")

bp.add_url_rule("/people", view_func=GenericTableView.as_view("people", table=PeopleTable))
bp.add_url_rule("/products", view_func=GenericTableView.as_view("products", table=ProductsTable))
bp.add_url_rule("/packages", view_func=GenericTableView.as_view("packages", table=PackagesTable))


def dashboard() -> str:
    """Render both demo tables stacked on one page."""
    try:
        for table_cls in (PeopleTable, ProductsTable, PackagesTable):
            table_cls.check_access({})
    except tk.NotAuthorized:
        return tk.abort(403, tk._("You are not authorized to view this page."))

    tables = [
        PeopleTable(ajax_url=tk.url_for("tables_demo.people")),
        ProductsTable(ajax_url=tk.url_for("tables_demo.products")),
        PackagesTable(ajax_url=tk.url_for("tables_demo.packages")),
    ]

    return tk.render(
        "tables_demo/dashboard.html",
        extra_vars={
            "tables": tables,
            "breadcrumb_label": tk._("Dashboard"),
            "page_title": tk._("Demo Dashboard"),
        },
    )


bp.add_url_rule("/dashboard", view_func=dashboard)
