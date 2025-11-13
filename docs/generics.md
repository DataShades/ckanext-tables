# Generic Views

The [`ckanext.tables.generics`](https://github.com/DataShades/ckanext-tables/tree/master/ckanext/tables/generics.py) module provides a ready-to-use view class that can render tables without writing custom view code.

## GenericTableView

The `GenericTableView` is a Flask `MethodView` that automatically renders any registered table definition.

### Basic Usage

```python
--8<-- "ckanext/tables_demo/views.py"
```

### Constructor Parameters

- **`table`** (`type[TableDefinition]`, required): The table definition class to be rendered.
- **`breadcrumb_label`** (`str`, optional): Label shown in breadcrumbs. Defaults to "Table"
- **`page_title`** (`str`, optional): Page title shown in the browser/header. Defaults to empty string

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
