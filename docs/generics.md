# Generic Views

The [`ckanext.tables.generics`](https://github.com/DataShades/ckanext-tables/tree/master/ckanext/tables/generics.py) module provides a ready-to-use view class that can render tables without writing custom view code.

## GenericTableView

The `GenericTableView` is a Flask `MethodView` that automatically renders any registered table definition.

### Basic Usage

```python
from flask import Blueprint
from ckanext.tables.shared import GenericTableView

# Create a blueprint
bp = Blueprint("my_tables", __name__)

# Add a route using GenericTableView
bp.add_url_rule(
    "/admin/users",
    view_func=GenericTableView.as_view("users_table", table="users")
)
```

### Constructor Parameters

- **`table`** (str, required): The name of the registered table definition
- **`breadcrumb_label`** (str, optional): Label shown in breadcrumbs. Defaults to "Table"
- **`page_title`** (str, optional): Page title shown in the browser/header. Defaults to empty string

### Error Handling

If the specified table is not found in the registry or the user isn’t authorized, `GenericTableView` raises a `tk.ObjectNotFound` exception:

### Access Control

The `GenericTableView` delegates access control to the table definition's `check_access()` method. Make sure your table definitions implement proper authorization:

```python
class MyTableDefinition(TableDefinition):
    @classmethod
    def check_access(cls, context: Context) -> None:
        """Only allow sysadmins to view this table."""
        tk.check_access("sysadmin", context)
```
