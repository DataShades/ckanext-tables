from flask import Blueprint

from ckanext.tables.shared import GenericTableView
from ckanext.tables_demo.table import PeopleTable

bp = Blueprint("my_tables", __name__, url_prefix="/tables-demo")

bp.add_url_rule(
    "/people",
    view_func=GenericTableView.as_view("people_table", table=PeopleTable),
)
