import csv
import json
import logging
from io import BytesIO, StringIO
from typing import TYPE_CHECKING

import yaml

import ckan.plugins.toolkit as tk

if TYPE_CHECKING:
    from ckanext.tables.table import QueryParams, TableDefinition


log = logging.getLogger(__name__)


class ExporterBase:
    """Base class for table data exporters."""

    name: str
    label: str
    mime_type: str

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


class CSVExporter(ExporterBase):
    """CSV exporter for table data."""

    name = "csv"
    label = tk._("CSV")
    mime_type = "text/csv"

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        output = StringIO()
        writer = csv.writer(output)

        # Write header
        header = [col.title for col in table.columns]
        writer.writerow(header)

        # Write data rows
        data = table.get_raw_data(params, paginate=False)

        for row in data:
            writer.writerow([row.get(col.field, "") for col in table.columns])

        return output.getvalue().encode("utf-8")


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
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        try:
            from openpyxl import Workbook
        except ImportError:
            log.warning("openpyxl is required for XLSX export but is not installed.")
            return b""

        wb = Workbook()
        ws = wb.active
        ws.title = "Data"  # type: ignore

        # Write header
        header = [col.title for col in table.columns]
        ws.append(header)  # type: ignore

        # Write data rows
        data = table.get_raw_data(params, paginate=False)
        for row in data:
            ws.append([row.get(col.field, "") for col in table.columns])  # type: ignore

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
        output = StringIO()
        writer = csv.writer(output, delimiter="\t")

        # Header
        header = [col.title for col in table.columns]
        writer.writerow(header)

        # Rows
        data = table.get_raw_data(params, paginate=False)
        for row in data:
            writer.writerow([row.get(col.field, "") for col in table.columns])

        return output.getvalue().encode("utf-8")


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
        data = table.get_raw_data(params, paginate=False)
        lines = [json.dumps(row, default=str) for row in data]
        return "\n".join(lines).encode("utf-8")


class HTMLExporter(ExporterBase):
    """HTML exporter for table data."""

    name = "html"
    label = tk._("HTML")
    mime_type = "text/html"

    @classmethod
    def export(cls, table: "TableDefinition", params: "QueryParams") -> bytes:
        data = table.get_raw_data(params, paginate=False)
        headers = [col.title for col in table.columns if col.field != "table_actions" and col.visible]

        rows_html = "\n".join(
            "<tr>{}</tr>".format(
                "".join(
                    "<td>{}</td>".format(row.get(col.field, ""))
                    for col in table.columns
                    if col.field != "table_actions" and col.visible
                )
            )
            for row in data
        )
        thead = "<tr>{}</tr>".format("".join(f"<th>{h}</th>" for h in headers))
        html = f"""
        <html>
            <head><meta charset="utf-8"><title>{table.name}</title></head>
            <body>
                <table border="1">
                    <thead>{thead}</thead>
                    <tbody>{rows_html}</tbody>
                </table>
            </body>
        </html>
        """
        return html.encode("utf-8")
