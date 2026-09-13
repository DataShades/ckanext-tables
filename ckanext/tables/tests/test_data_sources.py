import contextlib
import decimal
import os
from datetime import datetime  # noqa: DTZ001
from unittest import mock

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import select

import ckan.plugins.toolkit as tk
import ckan.tests.factories as factories
import ckan.tests.helpers as helpers
from ckan import model
from ckan.lib import uploader

from ckanext.tables.cache import (
    CachedDataSourceMixin,
    FeatherCacheBackend,
    RedisCacheBackend,
)
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
    _sniff_csv_delimiter,
)
from ckanext.tables.types import FILTER_OPERATORS, FilterItem


@pytest.fixture
def mocked_fetch_remote_file():
    """Bypass the guarded-fetch layer with a fixed dummy local path.

    These tests exercise CSV/XLSX/etc. parsing and caching by mocking the pandas
    reader directly and must not depend on real DNS/network access to resolve
    ``fetch_remote_file``'s SSRF/timeout/size checks against a live host.
    """
    with mock.patch(
        "ckanext.tables.data_sources.fetch_remote_file",
        return_value=contextlib.nullcontext("/tmp/mocked-source"),
    ):
        yield


@pytest.mark.usefixtures("clear_cache", "clean_redis", "mocked_fetch_remote_file")
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
    def test_caching_feather(self, mock_read_csv, tmp_path):
        url = "http://example.com/cached_data.csv"
        cache_dir = str(tmp_path)
        ds = CsvUrlDataSource(url, cache_backend=FeatherCacheBackend(cache_dir=cache_dir))

        mock_read_csv.return_value = pd.DataFrame([{"id": "1", "name": "Alice", "age": "30"}])

        # First fetch should create cache
        ds.filter([]).all()

        backend = ds.cache_backend
        assert isinstance(backend, FeatherCacheBackend)

        cache_file_path = backend.get_cache_path(ds.get_cache_key())
        assert os.path.exists(cache_file_path)

        backend.set(
            ds.get_cache_key(),
            [{"id": "99", "name": "Hacker", "age": "99"}, {"id": "100", "name": "Bob", "age": "25"}],
            ds.cache_ttl,
        )

        ds2 = CsvUrlDataSource(url, cache_backend=FeatherCacheBackend(cache_dir=cache_dir))
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

    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_caching_feather_mixed_type_column_does_not_500(self, mock_read_csv, tmp_path):
        # A CSV column pandas leaves as `object` with mixed Python types (numbers
        # and text) makes pyarrow raise ArrowTypeError on the Feather write. The
        # request must still succeed, just without caching.
        mock_read_csv.return_value = pd.DataFrame({"mixed": [1, "two", 3.0]})

        ds = CsvUrlDataSource(
            "http://example.com/mixed.csv",
            cache_backend=FeatherCacheBackend(cache_dir=str(tmp_path)),
        )

        data = ds.filter([]).all()

        assert len(data) == 3
        assert ds.cache_backend.get(ds.get_cache_key()) is None

    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_invalidate_removes_the_cached_dataframe(self, mock_read_csv, tmp_path):
        mock_read_csv.return_value = pd.DataFrame([{"id": "1", "name": "Alice", "age": "30"}])

        ds = CsvUrlDataSource(
            "http://example.com/invalidate.csv",
            cache_backend=FeatherCacheBackend(cache_dir=str(tmp_path)),
        )
        ds.filter([]).all()  # populates the cache
        assert ds.cache_backend.get(ds.get_cache_key()) is not None

        ds.invalidate()

        assert ds.cache_backend.get(ds.get_cache_key()) is None

    @pytest.mark.usefixtures("clean_db")
    def test_get_source_path_upload(self, package, sysadmin, create_with_upload):
        """Test retrieving path from an uploaded resource."""
        resource = create_with_upload(b"hello,world", "test.csv", package_id=package["id"])

        ds = CsvUrlDataSource(resource=resource)
        path = ds.get_source_path()

        assert path

        rid = resource["id"]
        expected = os.path.join(rid[:3], rid[3:6], rid[6:])

        # CKAN < 2.12 returns an absolute filesystem path from
        # ``ResourceUpload.get_path``; CKAN 2.12+ with a file_keeper resource
        # storage returns a storage-relative location. Assert the layout that
        # holds either way.
        assert path == expected or path.endswith(os.sep + expected)

    @pytest.mark.usefixtures("clean_db")
    def test_fetch_dataframe_from_uploaded_resource(self, package, sysadmin, create_with_upload):
        """End-to-end test of an uploaded resource.

        The actual uploaded content must be readable, whichever uploader
        backend this environment uses (legacy filesystem or file-keeper).
        """
        resource = create_with_upload(b"name,age\nAlice,30\nBob,25\n", "test.csv", package_id=package["id"])

        ds = CsvUrlDataSource(resource=resource)
        data = ds.filter([]).all()

        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[1]["name"] == "Bob"

    def test_open_source_reads_local_file_keeper_storage_directly(self, tmp_path):
        """Local file-keeper storage should be read directly, not copied.

        When the storage is on local disk, use its real path (via full_path())
        instead of copying the content through a second temp file.
        """
        real_file = tmp_path / "data.csv"
        real_file.write_text("name,age\nAlice,30\n")

        fake_storage = mock.Mock()
        fake_storage.full_path.return_value = str(real_file)

        fake_upload = mock.MagicMock(spec=uploader.FKResourceUpload)
        fake_upload.storage = fake_storage
        fake_upload.get_path.return_value = "abc/def/ghi"

        ds = CsvUrlDataSource(resource={"id": "res-1", "url_type": "upload"})

        with (
            mock.patch("ckanext.tables.data_sources.uploader.get_resource_uploader", return_value=fake_upload),
            ds._open_source() as path,
        ):
            assert path == str(real_file)

        assert not fake_storage.stream.called

    def test_open_source_streams_non_local_file_keeper_storage(self):
        """Non-local file-keeper storage must be streamed into a temp file.

        A file-keeper-backed upload with no real local path (e.g. S3), or whose
        get_path() full_path() can't resolve to a real file, must be streamed
        through the storage API instead of handing a relative string to pandas.
        """
        fake_storage = mock.Mock()
        fake_storage.full_path.side_effect = Exception("no local path for this storage")
        fake_storage.stream.return_value = [b"name,age\n", b"Alice,30\n"]

        fake_upload = mock.MagicMock(spec=uploader.FKResourceUpload)
        fake_upload.storage = fake_storage
        fake_upload.get_path.return_value = "abc/def/ghi"

        ds = CsvUrlDataSource(resource={"id": "res-1", "url_type": "upload"})

        with (
            mock.patch("ckanext.tables.data_sources.uploader.get_resource_uploader", return_value=fake_upload),
            ds._open_source() as path,
        ):
            with open(path, "rb") as f:
                content = f.read()
            assert os.path.exists(path)

        assert content == b"name,age\nAlice,30\n"
        assert not os.path.exists(path)  # cleaned up once the context exits
        fake_storage.stream.assert_called_once()

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
        # resource={} is falsy, so the try/except that's supposed to log-and-fall-back
        # is never entered — this only exercises the "if self.url" branch.
        ds = CsvUrlDataSource(resource={}, url="http://fallback.com/data.csv")
        path = ds.get_source_path()

        assert path == "http://fallback.com/data.csv"

    def test_get_source_path_falls_back_when_uploader_raises(self):
        # A truthy resource whose uploader raises must hit the except block and fall
        # back to the provided url — it used to always raise AttributeError instead,
        # since it referenced self.resource_id, which this class never defines.
        ds = CsvUrlDataSource(
            resource={"id": "res-1", "url_type": "upload"},
            url="http://fallback.com/data.csv",
        )

        with mock.patch(
            "ckanext.tables.data_sources.uploader.get_resource_uploader",
            side_effect=tk.ValidationError("Invalid storage path"),
        ):
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

    def test_invalid_sort_field_does_not_500(self):
        # An edited query string can request sorting on a field the datastore doesn't
        # have — datastore_search raises ValidationError for that, which used to be
        # uncaught here.
        self.ds.sort("nonexistent_field", "asc")

        assert self.ds.all() == []
        assert self.ds.count() == 3  # count() doesn't apply sort, so it's unaffected


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

    def test_filter_ordering_is_numeric_not_lexicographic(self):
        # As plain strings, "100" < "50" (lexicographic: '1' < '5') and "9" < "50"
        # is False ('9' > '5') — both backwards for actual numbers.
        ds = ListDataSource([{"age": "9"}, {"age": "50"}, {"age": "100"}])
        result = ds.filter([FilterItem(field="age", operator="<", value="50")]).all()
        assert [row["age"] for row in result] == ["9"]

    def test_filter_ordering_falls_back_to_string_for_non_numeric(self):
        ds = ListDataSource([{"name": "Alice"}, {"name": "Bob"}])
        result = ds.filter([FilterItem(field="name", operator="<", value="Bob")]).all()
        assert [row["name"] for row in result] == ["Alice"]

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

    def test_sort_does_not_raise_on_missing_field(self):
        # sorted(key=lambda x: x.get(sort_by)) used to raise TypeError comparing
        # None against a real value once any row lacks the field.
        ds = ListDataSource([{"name": "Alice", "age": 30}, {"name": "Bob"}])
        result = ds.filter([]).sort("age", "asc").all()
        assert len(result) == 2

    def test_sort_does_not_raise_on_mixed_types(self):
        ds = ListDataSource([{"age": 30}, {"age": "25"}, {"age": None}])
        result = ds.filter([]).sort("age", "asc").all()
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

    def fetch_dataframe(self) -> pd.DataFrame:
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


class _ArrowStubDataSource(CachedDataSourceMixin, PandasDataSource):
    """A PandasDataSource backed by a real Arrow-native cache backend.

    Unlike StubPandasDataSource above (which sets ``_df`` directly and has no
    cache backend at all, so it always exercises the plain pandas path), this
    goes through the real ``_ensure_loaded()``/``get_arrow()`` machinery, so
    ``filter``/``sort``/``paginate``/``count``/``all`` run through DuckDB
    (PERF-1) exactly as they would for a cached CSV/XLSX/etc. resource.
    """

    def __init__(self, df: pd.DataFrame, cache_backend, key: str = "arrow-stub"):
        super().__init__()
        self.cache_backend = cache_backend
        self.cache_ttl = 3600
        self._source_df = df
        self._key = key

    def get_cache_key(self) -> str:
        return self._key

    def fetch_dataframe(self) -> pd.DataFrame:
        return self._source_df


@pytest.fixture
def arrow_cache_backend(tmp_path):
    return FeatherCacheBackend(cache_dir=str(tmp_path))


@pytest.fixture
def arrow_ds(arrow_cache_backend):
    df = pd.DataFrame(
        {
            "fruit": ["apple", "banana", "cherry"],
            "count": [10, 5, 20],
        }
    )
    return _ArrowStubDataSource(df, arrow_cache_backend)


class TestPandasDataSourceArrowPath:
    """DuckDB-pushdown path (PERF-1) must behave identically to the pandas path above.

    Every case here mirrors a case in ``TestPandasDataSource`` — same inputs,
    same expected outputs — the only difference is the cache backend, which
    is what actually selects the arrow-vs-pandas code path inside
    ``PandasDataSource``.
    """

    def test_uses_the_arrow_path(self, arrow_ds):
        arrow_ds.filter([])
        assert arrow_ds._arrow is not None

    def test_all_returns_records(self, arrow_ds):
        result = arrow_ds.filter([]).all()
        assert len(result) == 3

    def test_filter_eq(self, arrow_ds):
        result = arrow_ds.filter([FilterItem("fruit", "=", "apple")]).all()
        assert len(result) == 1
        assert result[0]["fruit"] == "apple"

    def test_filter_not_eq(self, arrow_ds):
        result = arrow_ds.filter([FilterItem("fruit", "!=", "apple")]).all()
        assert len(result) == 2

    def test_filter_like(self, arrow_ds):
        result = arrow_ds.filter([FilterItem("fruit", "like", "an")]).all()
        assert len(result) == 1
        assert result[0]["fruit"] == "banana"

    def test_filter_numeric_lt(self, arrow_ds):
        result = arrow_ds.filter([FilterItem("count", "<", "10")]).all()
        assert len(result) == 1

    def test_filter_numeric_gte(self, arrow_ds):
        result = arrow_ds.filter([FilterItem("count", ">=", "10")]).all()
        assert len(result) == 2

    def test_filter_non_numeric_value_against_numeric_column_is_skipped(self, arrow_ds):
        # Matches the pandas path's behaviour for an ordering operator against
        # a value that doesn't parse as a number: skip the filter rather than
        # raising or binding a mismatched type.
        result = arrow_ds.filter([FilterItem("count", "<", "not-a-number")]).all()
        assert len(result) == 3

    def test_filter_unknown_field_ignored(self, arrow_ds):
        result = arrow_ds.filter([FilterItem("nonexistent", "=", "value")]).all()
        assert len(result) == 3

    def test_sort_asc(self, arrow_ds):
        result = arrow_ds.filter([]).sort("fruit", "asc").all()
        assert result[0]["fruit"] == "apple"

    def test_sort_desc(self, arrow_ds):
        result = arrow_ds.filter([]).sort("count", "desc").all()
        assert result[0]["count"] == 20

    def test_sort_unknown_field(self, arrow_ds):
        result = arrow_ds.filter([]).sort("nonexistent", "asc").all()
        assert len(result) == 3

    def test_paginate(self, arrow_ds):
        result = arrow_ds.filter([]).paginate(1, 2).all()
        assert len(result) == 2

    def test_paginate_page2(self, arrow_ds):
        result = arrow_ds.filter([]).paginate(2, 2).all()
        assert len(result) == 1

    def test_count(self, arrow_ds):
        arrow_ds.filter([])
        assert arrow_ds.count() == 3

    def test_count_after_filter(self, arrow_ds):
        arrow_ds.filter([FilterItem("fruit", "=", "apple")])
        assert arrow_ds.count() == 1

    def test_get_columns(self, arrow_ds):
        cols = arrow_ds.get_columns()
        assert "fruit" in cols
        assert "count" in cols

    def test_all_empty_df(self, arrow_cache_backend):
        ds = _ArrowStubDataSource(pd.DataFrame(), arrow_cache_backend, key="empty")
        ds.filter([])
        assert ds.all() == []

    def test_count_empty_df(self, arrow_cache_backend):
        ds = _ArrowStubDataSource(pd.DataFrame(), arrow_cache_backend, key="empty-count")
        ds.filter([])
        assert ds.count() == 0

    def test_repeated_query_on_same_instance_is_stable(self, arrow_ds):
        # get_data() and get_total_count() both call filter() on the same
        # instance within one request (table.py) — the second call must not
        # re-trigger a cache read or lose the loaded table.
        first = arrow_ds.filter([]).sort("fruit", "asc").all()
        second = arrow_ds.filter([]).sort("fruit", "asc").all()
        assert first == second

    def test_matches_pandas_path_on_a_larger_frame(self, arrow_cache_backend, tmp_path):
        """Cross-check: identical filter/sort/paginate/count results to the pandas path.

        Not a timing assertion (CI timing is flaky) — just a parity guard so
        the two implementations can't silently drift apart.
        """
        rng = np.random.default_rng(0)
        n = 50_000
        df = pd.DataFrame(
            {
                "id": np.arange(n),
                "name": [f"user_{i}" for i in range(n)],
                "score": rng.integers(0, 1000, size=n),
                "category": rng.choice(["alpha", "beta", "gamma", "delta"], size=n),
            }
        )

        arrow_source = _ArrowStubDataSource(df, arrow_cache_backend, key="parity")

        # A second, distinct backend instance — _use_arrow_path() is forced False
        # below regardless of what it stores, but a separate cache_dir keeps it
        # from sharing state with arrow_cache_backend's own cache entries.
        pandas_backend = FeatherCacheBackend(cache_dir=str(tmp_path / "pandas-path"))

        class PandasPathSource(_ArrowStubDataSource):
            def _use_arrow_path(self) -> bool:
                return False

        pandas_source = PandasPathSource(df, pandas_backend, key="parity-pandas")

        filters = [FilterItem("category", "=", "alpha"), FilterItem("score", ">", "200")]

        arrow_rows = arrow_source.filter(filters).sort("id", "asc").paginate(3, 25).all()
        pandas_rows = pandas_source.filter(filters).sort("id", "asc").paginate(3, 25).all()
        assert arrow_rows == pandas_rows

        arrow_count = _ArrowStubDataSource(df, arrow_cache_backend, key="parity").filter(filters).count()
        pandas_count = PandasPathSource(df, pandas_backend, key="parity-pandas").filter(filters).count()
        assert arrow_count == pandas_count


class TestCsvDelimiterSniffing:
    """Sniffing lets CsvUrlDataSource use pandas' fast C engine, not the slow one.

    Locks in that both the sniffed-delimiter (C engine) and the fallback
    (``engine="python"``) paths still parse real files identically to before.
    """

    @pytest.mark.parametrize(
        ("content", "expected_delimiter"),
        [
            ("a,b,c\n1,2,3\n4,5,6\n", ","),
            ("a;b;c\n1;2;3\n4;5;6\n", ";"),
            ("a\tb\tc\n1\t2\t3\n4\t5\t6\n", "\t"),
            ("a|b|c\n1|2|3\n", "|"),
        ],
    )
    def test_sniffs_common_delimiters(self, tmp_path, content, expected_delimiter):
        path = tmp_path / "data.csv"
        path.write_text(content)

        assert _sniff_csv_delimiter(str(path)) == expected_delimiter

    def test_returns_none_for_a_missing_file(self, tmp_path):
        assert _sniff_csv_delimiter(str(tmp_path / "does-not-exist.csv")) is None

    def test_returns_none_for_an_empty_file(self, tmp_path):
        path = tmp_path / "empty.csv"
        path.write_text("")

        assert _sniff_csv_delimiter(str(path)) is None

    def test_read_csv_parses_a_semicolon_file_via_the_c_engine(self, tmp_path):
        path = tmp_path / "data.csv"
        path.write_text("a;b\n1;x\n2;y\n")

        with mock.patch("ckanext.tables.data_sources.pd.read_csv") as mock_read_csv:
            mock_read_csv.return_value = pd.DataFrame([{"a": 1, "b": "x"}, {"a": 2, "b": "y"}])
            CsvUrlDataSource._read_csv(str(path))

        # sep is passed explicitly and engine is left at its (C) default.
        assert mock_read_csv.call_args.kwargs["sep"] == ";"
        assert "engine" not in mock_read_csv.call_args.kwargs

    def test_read_csv_falls_back_to_python_engine_when_sniffing_fails(self, tmp_path):
        path = tmp_path / "single_column.csv"
        path.write_text("a\n1\n2\n")

        with mock.patch("ckanext.tables.data_sources.pd.read_csv") as mock_read_csv:
            mock_read_csv.return_value = pd.DataFrame([{"a": 1}, {"a": 2}])
            CsvUrlDataSource._read_csv(str(path))

        assert mock_read_csv.call_args.kwargs["sep"] is None
        assert mock_read_csv.call_args.kwargs["engine"] == "python"

    def test_real_parse_matches_the_original_slow_path(self, tmp_path):
        """The actual parsed data must be identical to the pre-optimisation approach."""
        path = tmp_path / "data.csv"
        path.write_text("id,name,score\n1,Alice,95\n2,Bob,80\n3,Charlie,70\n")

        fast = CsvUrlDataSource._read_csv(str(path))
        slow = pd.read_csv(str(path), sep=None, engine="python")

        assert fast.equals(slow)


@pytest.mark.usefixtures("mocked_fetch_remote_file")
class TestUrlDataSourceErrorPaths:
    """All URL-based sources should return an empty DataFrame on errors."""

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

    def test_build_filter_boolean_with_non_string_value(self):
        # A filter value from JSON (?filters=...) can be a bool/int, not just a string —
        # value.lower() used to raise AttributeError for anything but a str.
        stmt = select(model.Package)
        ds = DatabaseDataSource(stmt)
        col = stmt.selected_columns.private
        assert ds.build_filter(col, "=", True) is not None
        assert ds.build_filter(col, "=", 1) is not None

    def test_filter_skips_unknown_field(self):
        # An edited query string can reference a field that doesn't exist on the
        # statement — this used to raise AttributeError via a bare getattr().
        ds = DatabaseDataSource(select(model.User))
        result = ds.filter([FilterItem("nonexistent_field", "=", "x")]).all()
        assert isinstance(result, list)

    @pytest.mark.usefixtures("clean_db")
    def test_dataset_source(self):
        for _ in range(10):
            factories.Dataset()

        ds = DatabaseDataSource(select(model.Package))
        result = ds.filter([]).all()
        assert len(result) == 10


class TestFilterOperatorsMatchCanonicalList:
    """The filter-operator dropdown is built solely from types.FILTER_OPERATORS.

    See helpers.tables_filter_operators — every operator listed there must be
    understood by both concrete data sources, otherwise it renders as a
    selectable option that silently filters nothing.
    """

    def test_database_data_source_supports_every_operator(self):
        stmt = select(model.User)
        ds = DatabaseDataSource(stmt)
        col = stmt.selected_columns.name  # a string column supports every operator, including "like"

        for value, _label in FILTER_OPERATORS:
            assert ds.build_filter(col, value, "test") is not None, value

    def test_list_data_source_supports_every_operator(self):
        ds = ListDataSource([])

        for value, _label in FILTER_OPERATORS:
            assert ds.build_filter("field", value, "test") is not None, value
