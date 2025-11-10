from flask import Blueprint

from ckanext.tables.shared import GenericTableView
from ckanext.tables_demo.table import PeopleTable

bp = Blueprint("tables_demo", __name__, url_prefix="/tables-demo")

bp.add_url_rule("/people", view_func=GenericTableView.as_view("people", table=PeopleTable))
