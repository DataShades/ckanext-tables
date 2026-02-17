import decimal
import os
from datetime import datetime
from unittest import mock

import numpy as np
import pandas as pd
import pytest

from ckanext.tables.data_sources import BaseResourceDataSource, CsvUrlDataSource, PandasDataSource


@pytest.mark.usefixtures("clear_cache")
class TestCsvUrlDataSource:
    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_fetch_and_parse(self, mock_read_csv):
        mock_read_csv.return_value = pd.DataFrame(
            [
                {"id": "1", "name": "Alice", "age": "30"},
                {"id": "2", "name": "Bob", "age": "25"},
            ]
        )

        ds = CsvUrlDataSource("http://example.com/data.csv")
        data = ds.filter([]).all()

        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[0]["id"] == "1"
        assert data[0]["age"] == "30"

    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_caching(self, mock_read_csv):
        url = "http://example.com/cached_data.csv"
        ds = CsvUrlDataSource(url)

        mock_read_csv.return_value = pd.DataFrame([{"id": "1", "name": "Alice", "age": "30"}])

        # First fetch should create cache
        ds.filter([]).all()

        cache_file_path = ds._get_cache_path()
        assert os.path.exists(cache_file_path)
        cached_df = pd.read_pickle(cache_file_path)
        assert len(cached_df) == 1
        assert cached_df.iloc[0]["name"] == "Alice"

        modified_df = pd.DataFrame([{"id": "99", "name": "Hacker", "age": "99"}])
        modified_df.to_pickle(cache_file_path)

        ds2 = CsvUrlDataSource(url)
        data = ds2.filter([]).all()
        assert len(data) == 1
        assert data[0]["name"] == "Hacker"


class TestBaseResourceDataSource:
    @pytest.mark.usefixtures("clean_db")
    def test_get_source_path_upload(self, package, sysadmin, create_with_upload):
        """Test retrieving path from an uploaded resource."""
        resource = create_with_upload(b"hello,world", "test.csv", package_id=package["id"])

        ds = BaseResourceDataSource(resource=resource)
        path = ds.get_source_path()

        assert path
        assert "/resources/" in path

    def test_get_source_path_resource_url(self):
        ds = BaseResourceDataSource(
            resource={
                "id": "res-456",
                "url_type": "link",
                "url": "http://ckan-resource.com/file.csv",
            }
        )
        path = ds.get_source_path()

        assert path == "http://ckan-resource.com/file.csv"

    def test_get_source_path_fallback_url(self):
        """Test using the provided URL when resource_id is not present."""
        ds = BaseResourceDataSource(url="http://fallback.com/data.csv")
        path = ds.get_source_path()
        assert path == "http://fallback.com/data.csv"

    def test_get_source_path_fallback_on_error(self):
        ds = BaseResourceDataSource(resource={}, url="http://fallback.com/data.csv")
        path = ds.get_source_path()

        assert path == "http://fallback.com/data.csv"

    def test_init_validation(self):
        """Test that initialization fails without url or resource_id."""
        with pytest.raises(ValueError, match="Either url or resource_id must be provided"):
            BaseResourceDataSource()


class TestSerialization:
    def test_complex_types_serialization(self):
        """Test strict serialization of complex types (bytes, decimal, numpy, datetime)."""

        class MockPandasDataSource(PandasDataSource):
            def get_cache_key(self):
                return "mock"

            def fetch_dataframe(self):
                return pd.DataFrame()

        ds = MockPandasDataSource()

        data = {
            "bytes_col": [b"hello", b"world"],
            "decimal_col": [decimal.Decimal("10.5"), decimal.Decimal("20.123")],
            "datetime_col": [datetime(2023, 1, 1, 12, 0, 0), pd.Timestamp("2023-01-02 14:30:00")],
            "numpy_int": [np.int64(100), np.int32(200)],
            "numpy_float": [np.float64(1.23), np.float32(4.56)],
            "nested_list": [[1, 2, np.int64(3)], (4, 5)],
            "nested_dict": [{"a": decimal.Decimal("1.1")}, {"b": b"byte"}],
            "nan_col": [np.nan, np.nan],
        }
        df = pd.DataFrame(data)
        # Manually set the internal dataframe to skip fetching/caching for this unit test logic
        ds._df = df
        ds._filtered_df = df

        serialized = ds.all()

        row1 = serialized[0]

        # Assertions for Type Conversion
        assert isinstance(row1["bytes_col"], str)
        assert row1["bytes_col"] == "hello"

        assert isinstance(row1["decimal_col"], float)
        assert row1["decimal_col"] == 10.5

        assert isinstance(row1["datetime_col"], str)
        assert "2023-01-01" in row1["datetime_col"]

        assert isinstance(row1["numpy_int"], int)
        assert row1["numpy_int"] == 100

        assert isinstance(row1["numpy_float"], float)
        assert abs(row1["numpy_float"] - 1.23) < 0.0001

        assert isinstance(row1["nested_list"], list)
        assert row1["nested_list"][2] == 3  # specific numpy int check inside list

        assert isinstance(row1["nested_dict"], dict)
        assert isinstance(row1["nested_dict"]["a"], float)

        assert row1["nan_col"] is None
