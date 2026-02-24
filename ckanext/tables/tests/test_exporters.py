import csv
import json
from io import StringIO
from unittest import mock

import pytest

from ckanext.tables.data_sources import ListDataSource
from ckanext.tables.exporters import (
    CSVExporter,
    JSONExporter,
    NDJSONExporter,
    TSVExporter,
    XLSXExporter,
    YAMLExporter,
)
from ckanext.tables.table import ColumnDefinition, TableDefinition
from ckanext.tables.types import QueryParams


@pytest.fixture
def params():
    return QueryParams()


class TestCSVExporter:
    def test_export_returns_bytes(self, simple_table, params):
        result = CSVExporter.export(simple_table, params)
        assert isinstance(result, bytes)

    def test_export_has_header(self, simple_table, params):
        result = CSVExporter.export(simple_table, params).decode("utf-8")
        rows = list(csv.reader(StringIO(result)))
        # Columns in simple_table from conftest: name, age, score
        # Since they are automatically titled: Name, Age, Score
        assert rows[0] == ["Name", "Age", "Score"]

    def test_export_has_data_rows(self, simple_table, params):
        result = CSVExporter.export(simple_table, params).decode("utf-8")
        rows = list(csv.reader(StringIO(result)))
        # header + 3 data rows from simple_table
        assert len(rows) == 4

    def test_exporter_attributes(self):
        assert CSVExporter.name == "csv"
        assert CSVExporter.mime_type == "text/csv"


class TestJSONExporter:
    def test_export_valid_json(self, simple_table, params):
        result = JSONExporter.export(simple_table, params)
        data = json.loads(result)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_export_contains_fields(self, simple_table, params):
        result = json.loads(JSONExporter.export(simple_table, params))
        assert result[0]["name"] == "Alice"

    def test_exporter_attributes(self):
        assert JSONExporter.name == "json"
        assert JSONExporter.mime_type == "application/json"


class TestTSVExporter:
    def test_export_tab_delimited(self, simple_table, params):
        result = TSVExporter.export(simple_table, params).decode("utf-8")
        rows = list(csv.reader(StringIO(result), delimiter="\t"))
        assert rows[0] == ["Name", "Age", "Score"]
        assert len(rows) == 4

    def test_exporter_attributes(self):
        assert TSVExporter.name == "tsv"
        assert TSVExporter.mime_type == "text/tab-separated-values"


# ---------------------------------------------------------------------------
# YAMLExporter
# ---------------------------------------------------------------------------


class TestYAMLExporter:
    def test_export_valid_yaml(self, simple_table, params):
        import yaml

        result = YAMLExporter.export(simple_table, params).decode("utf-8")
        data = yaml.safe_load(result)
        assert isinstance(data, list)
        assert len(data) == 3

    def test_exporter_attributes(self):
        assert YAMLExporter.name == "yaml"


class TestNDJSONExporter:
    def test_export_one_json_per_line(self, simple_table, params):
        result = NDJSONExporter.export(simple_table, params).decode("utf-8")
        lines = [l for l in result.strip().split("\n") if l]
        assert len(lines) == 3
        first = json.loads(lines[0])
        assert first["name"] == "Alice"

    def test_exporter_attributes(self):
        assert NDJSONExporter.name == "ndjson"


class TestXLSXExporter:
    def test_export_returns_bytes(self, simple_table, params):
        pytest.importorskip("openpyxl")
        result = XLSXExporter.export(simple_table, params)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_export_without_openpyxl_returns_empty(self, simple_table, params):
        with mock.patch.dict("sys.modules", {"openpyxl": None}):
            result = XLSXExporter.export(simple_table, params)
            assert result == b""

    def test_exporter_attributes(self):
        assert XLSXExporter.name == "xlsx"


class TestGetTableColumns:
    def test_excludes_actions_column(self, simple_data):
        from ckanext.tables.table import RowActionDefinition

        action = RowActionDefinition(
            action="view",
            label="View",
            callback=lambda row: {"success": True},
        )
        tbl = TableDefinition(
            name="t",
            data_source=ListDataSource(simple_data),
            columns=[
                ColumnDefinition(field="name"),
                ColumnDefinition(field="age"),
            ],
            row_actions=[action],
        )
        cols = CSVExporter.get_table_columns(tbl)
        field_names = [c.field for c in cols]
        assert "__table_actions" not in field_names
        assert "name" in field_names
