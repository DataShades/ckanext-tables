# Table Definition

The table definition holds the configuration for a table, including its columns, data source, and other options.

Below you can check the available attributes of the `TableDefinition` class and their descriptions. Also, a full code is provided at the end of this document for reference.

!!! warning
    Only one table can be rendered per page. The frontend controls (filters, columns, refresh, fullscreen, etc.) are wired up by global element id, so a second table on the same page would fight the first one over the same controls.

::: tables.table.TableDefinition
    options:
      show_source: true
