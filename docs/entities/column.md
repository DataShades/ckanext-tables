# Column Definition

The column definition holds the configuration for a table column, including its field name, data type, formatters, and other options.

!!! warning "`tabulator_formatter=html` renders unescaped"
    Setting `tabulator_formatter="html"` makes the client render the cell's
    value as raw HTML. Only pair it with a formatter that actually escapes its
    output (e.g. `URLFormatter`, `TextBoldFormatter`, or a custom one built per
    [Custom Formatters](../formatters/custom.md)) — pairing it with a formatter
    that returns the value unchanged (e.g. `NoneAsEmptyFormatter`) on untrusted
    data (resource content, user input) renders it as HTML client-side, i.e.
    stored XSS.

Below you can check the available attributes of the `ColumnDefinition` class and their descriptions. Also, a full code is provided at the end of this document for reference.

::: tables.table.ColumnDefinition
    options:
      show_source: true
