# Exporters

The tables extension provides several built-in exporters to export the table data in different formats. You can specify the exporters to be used in the `exporters` attribute of the `TableDefinition`.

Each exporter is a class that inherits from `BaseExporter` and implements the `export` method.

To use an exporter, you need to import the desired exporter from `ckanext.tables.shared` and add it to the `exporters` list in the `TableDefinition`.

```python
import ckanext.tables.shared as t

class MyTable(t.TableDefinition):
    def __init__(self):
        super().__init__(
            ...
            exporters=[
                t.exporters.CSVExporter,
                t.exporters.TSVExporter,
            ]
        )
```

Below you can see the source code for the base exporter class.

::: tables.exporters
    options:
      show_source: true
      force_inspection: true
      filters:
        - "ExporterBase"

## List of Built-in Exporters

Below is a list of the available built-in exporters along with a brief description of each.

### CSV Exporter

::: tables.exporters.CSVExporter
    options:
      show_source: true
      show_bases: false

---

### TSV Exporter

::: tables.exporters.TSVExporter
    options:
      show_source: true
      show_bases: false

---

### JSON Exporter

::: tables.exporters.JSONExporter
    options:
      show_source: true
      show_bases: false

---

### XLSX Exporter

::: tables.exporters.XLSXExporter
    options:
      show_source: true
      show_bases: false

---

### HTML Exporter

::: tables.exporters.HTMLExporter
    options:
      show_source: true
      show_bases: false

---

### YAML Exporter

::: tables.exporters.YAMLExporter
    options:
      show_source: true
      show_bases: false

---

### NDJSON Exporter

::: tables.exporters.NDJSONExporter
    options:
      show_source: true
      show_bases: false
