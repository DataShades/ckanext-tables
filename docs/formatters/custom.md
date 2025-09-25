# Custom Formatters

To create a custom formatter, you need to define a new class that inherits from `BaseFormatter` and implement the `format` method.

Below is an example of how to create a simple custom formatter, that replaces the cell content with a bold "Hello World" text.

```python
from ckanext.tables.shared import BaseFormatter

class MyCustomFormatter(BaseFormatter):
    """Replaces cell content with a bold Hello World."""

    def format(
        self, value: types.Value, options: types.Options
    ) -> types.FormatterResult:
        return tk.literal(f"<strong>Hello World</strong>")
```

Each formatter has an access to the cell value and the options passed to the formatter. Also, `self.table`, `self.row`, and `self.column` attributes are available to access the table, row, and column definitions respectively.

::: tables.formatters
    options:
      show_source: true
      show_bases: false
      filters:
        - "BaseFormatter"
