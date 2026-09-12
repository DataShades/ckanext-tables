import csv
import json
from collections.abc import Iterator
from datetime import datetime, timezone
from io import BytesIO
from typing import TYPE_CHECKING

import yaml

import ckan.plugins.toolkit as tk

if TYPE_CHECKING:
    from ckanext.tables.table import ColumnDefinition, TableDefinition
    from ckanext.tables.types import QueryParams


class _Echo:
    """A file-like object whose ``write`` just returns what it was given.

    Lets ``csv.writer`` be used to format one row at a time into a string,
    instead of accumulating into a real buffer, for exporters that stream.
    """

    def write(self, value: str) -> str:
        return value


class ExporterBase:
    """Base class for table data exporters."""

    name: str
    label: str
    mime_type: str

    @classmethod
    def is_available(cls) -> bool:
        """Whether this exporter's dependencies are installed.

        Checked by the view *before* building the response — export() runs inside a
        streamed generator body by the time it would raise, which is too late to
        change the response's status code (headers are already committed by then).
        Override for an exporter with an optional dependency.
        """
        return True

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        """Export the table data.

        Args:
            table: The table definition.
            params: The query parameters.

        Returns:
            The exported data as bytes.
        """
        raise NotImplementedError

    @classmethod
    def export_stream(cls, table: "TableDefinition", params: "QueryParams") -> Iterator[bytes]:
        """Yield the exported data in chunks.

        The default just wraps ``export()`` as a single chunk; override this (and, for
        the reverse direction, have ``export()`` join it) for exporters that can be
        produced incrementally, so the response can start sending before the whole
        file is built and without holding two full copies of it in memory at once.
        """
        yield cls.export(table, params)

    @classmethod
    def get_table_columns(cls, table: "TableDefinition") -> list["ColumnDefinition"]:
        """Get the list of table columns to be exported.

        Returns:
            A list of column field names.
        """
        # avoid circular import
        from ckanext.tables.table import COLUMN_ACTIONS_FIELD  # noqa PLC0415

        return [col for col in table.columns if col.field != COLUMN_ACTIONS_FIELD]


class CSVExporter(ExporterBase):
    """CSV exporter for table data."""

    name = "csv"
    label = tk._("CSV")
    mime_type = "text/csv"

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        return b"".join(cls.export_stream(table, params))

    @classmethod
    def export_stream(cls, table: "TableDefinition", params: "QueryParams") -> Iterator[bytes]:
        writer = csv.writer(_Echo())
        columns = cls.get_table_columns(table)

        yield writer.writerow([col.title for col in columns]).encode("utf-8")

        for row in table.get_raw_data(params, paginate=False):
            yield writer.writerow([row.get(col.field, "") for col in columns]).encode("utf-8")


class JSONExporter(ExporterBase):
    """JSON exporter for table data."""

    name = "json"
    label = tk._("JSON")
    mime_type = "application/json"

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        data = table.get_raw_data(params, paginate=False)

        return json.dumps(data, default=str).encode("utf-8")


class XLSXExporter(ExporterBase):
    """Excel (XLSX) exporter for table data."""

    name = "xlsx"
    label = tk._("Excel")
    mime_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"

    @classmethod
    def is_available(cls) -> bool:
        try:
            import openpyxl  # noqa: F401, PLC0415
        except ImportError:
            return False
        return True

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        if not cls.is_available():
            raise ImportError("openpyxl is required for XLSX export but is not installed.")

        from openpyxl import Workbook  # noqa: PLC0415

        wb = Workbook()
        ws = wb.active
        ws.title = "Data"  # type: ignore

        columns = cls.get_table_columns(table)
        header = [col.title for col in columns]
        ws.append(header)  # type: ignore

        # Write data rows
        data = table.get_raw_data(params, paginate=False)
        for row in data:
            ws.append([row.get(col.field, "") for col in columns])  # type: ignore

        output = BytesIO()
        wb.save(output)
        return output.getvalue()


class TSVExporter(ExporterBase):
    """TSV exporter for table data."""

    name = "tsv"
    label = tk._("TSV")
    mime_type = "text/tab-separated-values"

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        return b"".join(cls.export_stream(table, params))

    @classmethod
    def export_stream(cls, table: "TableDefinition", params: "QueryParams") -> Iterator[bytes]:
        writer = csv.writer(_Echo(), delimiter="\t")
        columns = cls.get_table_columns(table)

        yield writer.writerow([col.title for col in columns]).encode("utf-8")

        for row in table.get_raw_data(params, paginate=False):
            yield writer.writerow([row.get(col.field, "") for col in columns]).encode("utf-8")


class YAMLExporter(ExporterBase):
    """YAML exporter for table data."""

    name = "yaml"
    label = tk._("YAML")
    mime_type = "application/x-yaml"

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        data = table.get_raw_data(params, paginate=False)
        return yaml.safe_dump(data, allow_unicode=True).encode("utf-8")


class NDJSONExporter(ExporterBase):
    """NDJSON exporter for table data."""

    name = "ndjson"
    label = tk._("NDJSON")
    mime_type = "application/x-ndjson"

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        return b"".join(cls.export_stream(table, params))

    @classmethod
    def export_stream(cls, table: "TableDefinition", params: "QueryParams") -> Iterator[bytes]:
        for row in table.get_raw_data(params, paginate=False):
            yield (json.dumps(row, default=str) + "\n").encode("utf-8")


class HTMLExporter(ExporterBase):
    """HTML exporter for table data."""

    name = "html"
    label = tk._("HTML")
    mime_type = "text/html"

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        data = table.get_raw_data(params, paginate=False)
        columns = cls.get_table_columns(table)
        headers = [col.title for col in columns]
        timestamp = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S")

        return tk.render(
            "tables/exporters/html_export.html",
            {
                "data": data,
                "headers": headers,
                "table": table,
                "timestamp": timestamp,
                "columns": columns,
            },
        ).encode("utf-8")


class PDFExporter(ExporterBase):
    """PDF exporter for table data."""

    name = "pdf"
    label = tk._("PDF")
    mime_type = "application/pdf"

    @classmethod
    def is_available(cls) -> bool:
        try:
            import weasyprint  # noqa: F401, PLC0415
        except ImportError:
            return False
        return True

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        if not cls.is_available():
            raise ImportError("WeasyPrint is required for PDF export but is not installed.")

        from weasyprint import HTML  # noqa: PLC0415

        # reuse HTML exporter template for PDF generation
        html_content = HTMLExporter.export(table, params).decode("utf-8")
        return HTML(string=html_content).write_pdf() or b""
