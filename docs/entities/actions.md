# Action Definitions

Actions are operations that can be performed on table data There are 3 types of actions: bulk actions, table actions, and row actions.

1. **Bulk Actions**: Actions that can be performed on multiple selected rows. Selected rows are passed to the action callback, allowing for operations on multiple items at once.
2. **Table Actions**: Actions that can be performed on the table as a whole. It doesn't have an access to the row data, so it's typically used for operations that affect the entire table, e.g. cleaning the table data.
3. **Row Actions**: Actions that can be performed on individual rows. These actions are acce

Each action callback returns an `ActionHandlerResult` object, below you can see its definition:

::: tables.types.ActionHandlerResult
    options:
      show_root_heading: true
      show_source: true

---



::: tables.table.BulkActionDefinition
    options:
      show_root_heading: true
      show_source: true

---

::: tables.table.TableActionDefinition
    options:
      show_root_heading: true
      show_source: true

---

::: tables.table.RowActionDefinition
    options:
      show_root_heading: true
      show_source: true
