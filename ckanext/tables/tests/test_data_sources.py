import decimal
import os
from datetime import datetime  # noqa: DTZ001
from unittest import mock

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

import ckan.tests.factories as factories
import ckan.tests.helpers as helpers
from ckan import model

from ckanext.tables.cache import PickleCacheBackend, RedisCacheBackend
from ckanext.tables.data_sources import (
    CsvUrlDataSource,
    DatabaseDataSource,
    DataStoreDataSource,
    FeatherUrlDataSource,
    ListDataSource,
    OrcUrlDataSource,
    PandasDataSource,
    ParquetUrlDataSource,
    XlsxUrlDataSource,
)
from ckanext.tables.types import FilterItem


@pytest.mark.usefixtures("clear_cache", "clean_redis")
class TestCSVResourceDataSource:
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
    def test_caching_pickle(self, mock_read_csv):
        url = "http://example.com/cached_data.csv"
        cache_dir = "/tmp/ckan-tables-cache"
        ds = CsvUrlDataSource(url, cache_backend=PickleCacheBackend(cache_dir=cache_dir))

        mock_read_csv.return_value = pd.DataFrame([{"id": "1", "name": "Alice", "age": "30"}])

        # First fetch should create cache
        ds.filter([]).all()

        backend = ds.cache_backend
        assert isinstance(backend, PickleCacheBackend)

        cache_file_path = backend.get_cache_path(ds.get_cache_key())
        assert os.path.exists(cache_file_path)

        backend.set(
            ds.get_cache_key(),
            [{"id": "99", "name": "Hacker", "age": "99"}, {"id": "100", "name": "Bob", "age": "25"}],
            ds.cache_ttl,
        )

        ds2 = CsvUrlDataSource(url, cache_backend=PickleCacheBackend(cache_dir=cache_dir))
        data = ds2.filter([]).all()

        assert len(data) == 2
        assert data[0]["name"] == "Hacker"

    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_caching_redis(self, mock_read_csv):
        url = "http://example.com/cached_data.csv"
        ds = CsvUrlDataSource(url, cache_backend=RedisCacheBackend())

        mock_read_csv.return_value = pd.DataFrame([{"id": "1", "name": "Alice", "age": "30"}])

        # First fetch should create cache
        ds.filter([]).all()

        backend = ds.cache_backend
        assert isinstance(backend, RedisCacheBackend)

        cache_key = backend._full_key(ds.get_cache_key())
        assert cache_key == f"ckanext:tables:url-{url}"

        backend.set(
            ds.get_cache_key(),
            [{"id": "99", "name": "Hacker", "age": "99"}, {"id": "100", "name": "Bob", "age": "25"}],
            ds.cache_ttl,
        )

        ds2 = CsvUrlDataSource(url, cache_backend=RedisCacheBackend())
        data = ds2.filter([]).all()

        assert len(data) == 2
        assert data[0]["name"] == "Hacker"

    @pytest.mark.usefixtures("clean_db")
    def test_get_source_path_upload(self, package, sysadmin, create_with_upload):
        """Test retrieving path from an uploaded resource."""
        resource = create_with_upload(b"hello,world", "test.csv", package_id=package["id"])

        ds = CsvUrlDataSource(resource=resource)
        path = ds.get_source_path()

        assert path
        assert "/resources/" in path

    def test_get_source_path_resource_url(self):
        ds = CsvUrlDataSource(
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
        ds = CsvUrlDataSource(url="http://fallback.com/data.csv")
        path = ds.get_source_path()
        assert path == "http://fallback.com/data.csv"

    def test_get_source_path_fallback_on_error(self):
        ds = CsvUrlDataSource(resource={}, url="http://fallback.com/data.csv")
        path = ds.get_source_path()

        assert path == "http://fallback.com/data.csv"

    def test_init_validation(self):
        """Test that initialization fails without url or resource_id."""
        with pytest.raises(ValueError, match="Either url or resource_id must be provided"):
            CsvUrlDataSource()


class TestSerialization:
    def test_complex_types_serialization(self):
        """Test strict serialization of complex types (bytes, decimal, numpy, datetime)."""

        class MockPandasDataSource(PandasDataSource):
            def fetch_dataframe(self):
                return pd.DataFrame()

        ds = MockPandasDataSource()

        data = {
            "bytes_col": [b"hello", b"world"],
            "decimal_col": [decimal.Decimal("10.5"), decimal.Decimal("20.123")],
            "datetime_col": [
                datetime(2023, 1, 1, 12, 0, 0),  # noqa: DTZ001
                pd.Timestamp("2023-01-02 14:30:00"),
            ],
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


@pytest.mark.ckan_config("ckan.plugins", "datastore")
@pytest.mark.usefixtures("clean_datastore", "with_request_context", "with_plugins")
class TestDataStoreDataSource:
    @pytest.fixture(autouse=True)
    def setup(self, with_plugins, with_request_context, clean_datastore):
        self.resource = factories.Resource()
        self.data = {
            "resource_id": self.resource["id"],
            "force": True,
            "fields": [
                {"id": "a", "type": "int"},
                {"id": "b", "type": "text"},
                {"id": "c", "type": "int"},
            ],
            "records": [
                {"a": 1, "b": "foo!", "c": 5},
                {"a": 2, "b": "foo_test", "c": 8},
                {"a": 3, "b": "bar", "c": 15},
            ],
        }
        helpers.call_action("datastore_create", **self.data)
        self.ds = DataStoreDataSource(self.resource["id"])

    def test_all_with_args(self):
        self.ds.filter(
            [
                FilterItem(field="a", operator="=", value="1"),
                FilterItem(field="b", operator="like", value="foo!"),
                FilterItem(field="c", operator="<", value="10"),  # unsupported, ignored in queries dict
            ]
        )
        self.ds.sort("a", "desc")
        self.ds.paginate(1, 10)

        res = self.ds.all()

        assert len(res) == 1
        assert res[0]["a"] == 1
        assert res[0]["b"] == "foo!"

    def test_count(self):
        assert self.ds.count() == 3

    def test_get_columns(self):
        columns = self.ds.get_columns()
        assert "a" in columns
        assert "b" in columns
        assert "c" in columns

    def test_error_handling(self):
        ds_err = DataStoreDataSource("invalid-id")

        assert ds_err.all() == []
        assert ds_err.count() == 0
        assert ds_err.get_columns() == []


class TestListDataSource:
    @pytest.fixture
    def ds(self):
        return ListDataSource(
            [
                {"name": "Alice", "age": "30", "score": "95"},
                {"name": "Bob", "age": "25", "score": "80"},
                {"name": "Charlie", "age": "35", "score": "70"},
            ]
        )

    def test_all_returns_all(self, ds):
        result = ds.filter([]).all()
        assert len(result) == 3

    def test_filter_equal(self, ds):
        result = ds.filter([FilterItem(field="name", operator="=", value="Alice")]).all()
        assert len(result) == 1
        assert result[0]["name"] == "Alice"

    def test_filter_not_equal(self, ds):
        result = ds.filter([FilterItem(field="name", operator="!=", value="Alice")]).all()
        assert len(result) == 2

    def test_filter_like(self, ds):
        result = ds.filter([FilterItem(field="name", operator="like", value="li")]).all()
        # Matches "Alice" and "Charlie"
        assert len(result) == 2

    def test_filter_less_than(self, ds):
        result = ds.filter([FilterItem(field="age", operator="<", value="30")]).all()
        assert len(result) == 1
        assert result[0]["name"] == "Bob"

    def test_filter_greater_than(self, ds):
        result = ds.filter([FilterItem(field="score", operator=">", value="80")]).all()
        assert len(result) == 1

    def test_filter_less_than_or_equal(self, ds):
        result = ds.filter([FilterItem(field="age", operator="<=", value="30")]).all()
        assert len(result) == 2

    def test_filter_greater_than_or_equal(self, ds):
        result = ds.filter([FilterItem(field="age", operator=">=", value="35")]).all()
        assert len(result) == 1

    def test_unknown_operator_no_filter(self, ds):
        result = ds.filter([FilterItem(field="name", operator="UNKNOWN", value="Alice")]).all()
        assert len(result) == 3  # no filter applied

    def test_sort_asc(self, ds):
        result = ds.filter([]).sort("name", "asc").all()
        assert result[0]["name"] == "Alice"
        assert result[-1]["name"] == "Charlie"

    def test_sort_desc(self, ds):
        result = ds.filter([]).sort("name", "desc").all()
        assert result[0]["name"] == "Charlie"

    def test_sort_none_field(self, ds):
        result = ds.filter([]).sort(None, None).all()
        assert len(result) == 3

    def test_paginate_page1(self, ds):
        result = ds.filter([]).paginate(1, 2).all()
        assert len(result) == 2

    def test_paginate_page2(self, ds):
        result = ds.filter([]).paginate(2, 2).all()
        assert len(result) == 1

    def test_count(self, ds):
        ds.filter([])
        assert ds.count() == 3

    def test_count_after_filter(self, ds):
        ds.filter([FilterItem(field="name", operator="=", value="Alice")])
        assert ds.count() == 1

    def test_get_columns(self, ds):
        cols = ds.get_columns()
        assert "name" in cols
        assert "age" in cols

    def test_get_columns_empty(self):
        ds = ListDataSource([])
        assert ds.get_columns() == []


class StubPandasDataSource(PandasDataSource):
    def __init__(self, df: pd.DataFrame):
        super().__init__()
        self._df = df
        self._filtered_df = df

    def fetch_dataframe(self):
        return self._df


class TestPandasDataSource:
    @pytest.fixture
    def ds(self):
        df = pd.DataFrame(
            {
                "fruit": ["apple", "banana", "cherry"],
                "count": [10, 5, 20],
            }
        )
        return StubPandasDataSource(df)

    def test_all_returns_records(self, ds):
        result = ds.filter([]).all()
        assert len(result) == 3

    def test_filter_eq(self, ds):
        result = ds.filter([FilterItem("fruit", "=", "apple")]).all()
        assert len(result) == 1
        assert result[0]["fruit"] == "apple"

    def test_filter_not_eq(self, ds):
        result = ds.filter([FilterItem("fruit", "!=", "apple")]).all()
        assert len(result) == 2

    def test_filter_like(self, ds):
        result = ds.filter([FilterItem("fruit", "like", "an")]).all()
        # banana matches "an"; cherry does not; apple does not
        assert len(result) == 1
        assert result[0]["fruit"] == "banana"

    def test_filter_numeric_lt(self, ds):
        result = ds.filter([FilterItem("count", "<", "10")]).all()
        assert len(result) == 1

    def test_filter_numeric_gte(self, ds):
        result = ds.filter([FilterItem("count", ">=", "10")]).all()
        assert len(result) == 2

    def test_filter_unknown_field_ignored(self, ds):
        result = ds.filter([FilterItem("nonexistent", "=", "value")]).all()
        assert len(result) == 3

    def test_sort_asc(self, ds):
        result = ds.filter([]).sort("fruit", "asc").all()
        assert result[0]["fruit"] == "apple"

    def test_sort_desc(self, ds):
        result = ds.filter([]).sort("count", "desc").all()
        assert result[0]["count"] == 20

    def test_sort_unknown_field(self, ds):
        result = ds.filter([]).sort("nonexistent", "asc").all()
        assert len(result) == 3

    def test_paginate(self, ds):
        result = ds.filter([]).paginate(1, 2).all()
        assert len(result) == 2

    def test_paginate_page2(self, ds):
        result = ds.filter([]).paginate(2, 2).all()
        assert len(result) == 1

    def test_count(self, ds):
        ds.filter([])
        assert ds.count() == 3

    def test_get_columns(self, ds):
        cols = ds.get_columns()
        assert "fruit" in cols
        assert "count" in cols

    def test_all_empty_df(self):
        ds = StubPandasDataSource(pd.DataFrame())
        ds.filter([])
        assert ds.all() == []

    def test_count_none_filtered_df(self):
        ds = StubPandasDataSource(pd.DataFrame())
        ds._filtered_df = None
        assert ds.count() == 0

    def test_filter_on_none_df(self):
        """filter() with a None _df should return early without crashing."""
        ds = StubPandasDataSource(pd.DataFrame())
        ds._df = None
        ds._filtered_df = None
        result = ds.filter([FilterItem("x", "=", "1")]).all()
        assert result == []

    def test_serialize_value_types(self, ds):
        assert ds.serialize_value(None) is None
        assert ds.serialize_value(True) is True
        assert ds.serialize_value(42) == 42
        assert ds.serialize_value(3.14) == 3.14
        assert ds.serialize_value("text") == "text"
        assert ds.serialize_value(b"bytes") == "bytes"
        assert isinstance(ds.serialize_value(datetime(2024, 1, 1)), str)
        assert isinstance(ds.serialize_value(decimal.Decimal("1.5")), float)
        assert ds.serialize_value([1, 2]) == [1, 2]
        assert ds.serialize_value((1, 2)) == [1, 2]
        assert ds.serialize_value({"a": 1}) == {"a": 1}
        assert ds.serialize_value(np.int64(5)) == 5
        # Fallback path
        assert ds.serialize_value(object()) is not None


class TestUrlDataSourceErrorPaths:
    """All URL-based sources should return an empty DataFrame on errors."""

    def _run_with_exception(self, source_class, exc_class=Exception):
        with mock.patch.object(source_class, "fetch_dataframe", return_value=pd.DataFrame()):
            ds = source_class(url="http://example.com/file")
            ds._df = None
            ds._filtered_df = None
        return ds

    @mock.patch("ckanext.tables.data_sources.pd.read_excel", side_effect=OSError("boom"))
    def test_xlsx_error_returns_empty(self, _):
        ds = XlsxUrlDataSource(url="http://example.com/file.xlsx")
        df = ds.fetch_dataframe()
        assert df.empty

    @mock.patch("ckanext.tables.data_sources.pd.read_orc", side_effect=OSError("boom"))
    def test_orc_error_returns_empty(self, _):
        ds = OrcUrlDataSource(url="http://example.com/file.orc")
        df = ds.fetch_dataframe()
        assert df.empty

    @mock.patch("ckanext.tables.data_sources.pd.read_parquet", side_effect=OSError("boom"))
    def test_parquet_error_returns_empty(self, _):
        ds = ParquetUrlDataSource(url="http://example.com/file.parquet")
        df = ds.fetch_dataframe()
        assert df.empty

    @mock.patch("ckanext.tables.data_sources.pd.read_feather", side_effect=OSError("boom"))
    def test_feather_error_returns_empty(self, _):
        ds = FeatherUrlDataSource(url="http://example.com/file.feather")
        df = ds.fetch_dataframe()
        assert df.empty

    @mock.patch("ckanext.tables.data_sources.pd.read_csv", side_effect=OSError("boom"))
    def test_csv_error_returns_empty(self, _):
        ds = CsvUrlDataSource(url="http://example.com/file.csv")
        df = ds.fetch_dataframe()
        assert df.empty


class TestDatabaseDataSource:
    """Tests for DatabaseDataSource using CKAN's test DB."""

    def test_filter_sort_paginate(self):
        """Test filter, sort, and paginate on the CKAN user table."""
        ds = DatabaseDataSource(select(model.User))

        # Just ensure methods chain without error and return lists
        result = ds.filter([]).sort(None, None).paginate(1, 5).all()
        assert isinstance(result, list)

    def test_get_columns(self):
        ds = DatabaseDataSource(select(model.User))
        cols = ds.get_columns()
        assert isinstance(cols, list)

    def test_count(self):
        ds = DatabaseDataSource(select(model.User))
        ds.filter([])
        count = ds.count()
        assert count >= 0

    def test_build_filter_boolean(self):
        # We only test the type-casting logic via the build_filter method
        stmt = select(model.User)
        ds = DatabaseDataSource(stmt)

        col = stmt.selected_columns.state
        # build_filter for a String column
        expr = ds.build_filter(col, "=", "active")
        assert expr is not None

    def test_build_filter_like(self):
        stmt = select(model.User)
        ds = DatabaseDataSource(stmt)
        col = stmt.selected_columns.name
        expr = ds.build_filter(col, "like", "admin")
        assert expr is not None

    def test_build_filter_unknown_operator(self):
        stmt = select(model.User)
        ds = DatabaseDataSource(stmt)
        col = stmt.selected_columns.name
        expr = ds.build_filter(col, "UNKNOWN_OP", "value")
        assert expr is None

    @pytest.mark.usefixtures("clean_db")
    def test_dataset_source(self):
        for _ in range(10):
            factories.Dataset()

        ds = DatabaseDataSource(select(model.Package))
        result = ds.filter([]).all()
        assert len(result) == 10
