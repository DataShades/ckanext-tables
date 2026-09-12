# Generic Views

The [`ckanext.tables.generics`](https://github.com/DataShades/ckanext-tables/tree/master/ckanext/tables/generics.py) module provides a ready-to-use view class that can render tables without writing custom view code.

## GenericTableView

The `GenericTableView` is a Flask `MethodView` that automatically renders any registered table definition.

### Basic Usage

```python
--8 < --"ckanext/tables_demo/views.py"
```

### Constructor Parameters

- **`table`** (`type[TableDefinition]`, required): The table definition class to be rendered.
- **`breadcrumb_label`** (`str`, optional): Label shown in breadcrumbs. The template renders it
  as-is, so pass an already-translated string (e.g. the result of your own `tk._(...)` call).
  Defaults to a translated "Table".
- **`page_title`** (`str`, optional): Page title shown in the browser/header. Also rendered as-is
  — translate it yourself before passing it in. Defaults to empty string.

### Access Control

The `GenericTableView` delegates access control to the table definition's `check_access()` method. Make sure your table definitions implement proper authorization:

```python
class PeopleTable(TableDefinition):
    ...

    @classmethod
    def check_access(cls, context: Context) -> None:
        """Only allow sysadmins to view this table."""
        tk.check_access("sysadmin", context)
```

`GenericTableView` always calls `check_access()` with a bare `{}` — no `model`, `user`, or `session` pre-populated. Routing the check through `tk.check_access(...)`, as above, fills those in for you; reading the context directly (e.g. `context["user"]`) will not work.
