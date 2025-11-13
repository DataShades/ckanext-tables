# Available Built-in Formatters

The tables extension comes with several built-in formatters that you can use to format the data in your table columns.

Using formatter is simple; you just need to import the desired formatter from `ckanext.tables.shared.formatters` and add it to the `formatters` list in the `ColumnDefinition`.

```python
from ckanext.tables.shared import formatters, ColumnDefinition

ColumnDefinition(
    field="timestamp",
    formatters=[(formatters.DateFormatter, {"date_format": "%Y-%m-%d %H:%M"})],
)
```

Below is a list of the available built-in formatters along with a brief description of each.

----

::: tables.formatters
    options:
      show_source: false
      show_bases: false
      filters:
        - "!BaseFormatter"
