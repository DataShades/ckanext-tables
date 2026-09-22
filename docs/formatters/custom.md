# Custom Formatters

To create a custom formatter, you need to define a new class that inherits from `BaseFormatter` and implement the `format` method.

Below is an example of how to create a simple custom formatter that renders the cell value in bold.

```python
from ckan.plugins import toolkit as tk

from ckanext.tables import types
from ckanext.tables.shared import BaseFormatter


class MyCustomFormatter(BaseFormatter):
    """Renders the cell value in bold."""

    def format(self, value: types.Value, options: types.Options) -> types.FormatterResult:
        # `value` is untrusted cell data (from a resource, a database row, etc.).
        # `tk.literal(...).format(value)` auto-escapes it — never build markup with
        # an f-string (e.g. `tk.literal(f"<strong>{value}</strong>")`), which would
        # inject the raw value as HTML.
        return tk.literal("<strong>{}</strong>").format(value)
```

!!! warning "Escape untrusted values"
    Anything a formatter returns via `tk.literal(...)` is rendered as-is on the
    client, unescaped. Only use `tk.literal(...).format(value)` (or an
    autoescaping template via `tk.render(...)`) to build it — never interpolate
    `value` (or any other untrusted data) into a literal with an f-string or
    `%`/`.format()` on a plain string, since that reintroduces stored XSS.

Each formatter has an access to the cell value and the options passed to the formatter. Also, `self.table`, `self.row`, and `self.column` attributes are available to access the table, row, and column definitions respectively.

::: tables.formatters
    options:
      show_source: true
      show_bases: false
      filters:
        - "BaseFormatter"
