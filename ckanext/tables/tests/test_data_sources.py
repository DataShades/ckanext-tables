import contextlib
import decimal
import json
import os
import threading
import time
import uuid
from datetime import date, datetime  # noqa: DTZ001
from unittest import mock

import numpy as np
import pandas as pd
import pytest
from sqlalchemy import Date, Float, Numeric, Uuid, column, select

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
    DataSourceError,
    DataStoreDataSource,
    FeatherUrlDataSource,
    JsonLdUrlDataSource,
    ListDataSource,
    NdjsonUrlDataSource,
    OdsUrlDataSource,
    OrcUrlDataSource,
    PandasDataSource,
    ParquetUrlDataSource,
    TsvUrlDataSource,
    XlsUrlDataSource,
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


@pytest.fixture
def workbook_path(tmp_path) -> str:
    """A real two-sheet .xlsx file on disk, each sheet with its own schema."""
    path = tmp_path / "workbook.xlsx"

    with pd.ExcelWriter(path) as writer:
        pd.DataFrame([{"name": "Alice"}, {"name": "Bob"}]).to_excel(writer, sheet_name="People", index=False)
        pd.DataFrame([{"city": "Kyiv"}]).to_excel(writer, sheet_name="Other Places", index=False)

    return str(path)


@pytest.fixture
def mocked_workbook_fetch(workbook_path: str):
    """Serve ``workbook_path`` as the fetched file, without the network."""
    with mock.patch(
        "ckanext.tables.data_sources.fetch_remote_file",
        return_value=contextlib.nullcontext(workbook_path),
    ):
        yield workbook_path


@pytest.mark.usefixtures("clear_cache", "clean_redis", "mocked_workbook_fetch")
class TestXlsxUrlDataSourceSheets:
    """Sheet selection, against a real multi-sheet workbook rather than a mocked reader."""

    def _source(self, sheet_index: int = 0) -> XlsxUrlDataSource:
        return XlsxUrlDataSource(url="http://example.com/workbook.xlsx", sheet_index=sheet_index)

    def test_first_sheet_by_default(self):
        ds = self._source()

        assert ds.get_columns() == ["name"]
        assert ds.filter([]).all() == [{"name": "Alice"}, {"name": "Bob"}]

    def test_selected_sheet_is_the_one_read(self):
        ds = self._source(1)

        assert ds.get_columns() == ["city"]
        assert ds.filter([]).all() == [{"city": "Kyiv"}]
        assert ds.count() == 1

    def test_sheet_names_are_listed_in_file_order(self):
        assert self._source().get_sheet_names() == ["People", "Other Places"]

    def test_sheet_names_come_from_the_cache_on_a_second_call(self):
        self._source().get_sheet_names()

        with mock.patch("ckanext.tables.data_sources.pd.ExcelFile", side_effect=AssertionError("re-read")):
            assert self._source().get_sheet_names() == ["People", "Other Places"]

    def test_negative_sheet_index_falls_back_to_the_first_sheet(self):
        assert self._source(-1).sheet_index == 0

    def test_a_sheet_past_the_end_is_a_data_source_error(self):
        with pytest.raises(DataSourceError):
            self._source(5).filter([]).all()

    def test_each_sheet_is_cached_under_its_own_key(self):
        assert self._source().get_cache_key() != self._source(1).get_cache_key()

    def test_the_first_sheet_keeps_the_plain_resource_key(self):
        ds = XlsxUrlDataSource(resource={"id": "res-1"})

        assert ds.get_cache_key() == "resource-res-1"
        assert ds.get_cache_key() == ds.get_cache_base_key()

    def test_a_cached_sheet_does_not_bleed_into_another(self):
        """Each sheet is read and cached independently, in either order."""
        assert self._source(1).filter([]).all() == [{"city": "Kyiv"}]
        assert self._source().filter([]).all() == [{"name": "Alice"}, {"name": "Bob"}]
        assert self._source(1).filter([]).all() == [{"city": "Kyiv"}]

    def test_invalidate_orphans_every_sheet_of_the_workbook(self):
        """One resource-level invalidation has to reach the per-sheet entries too."""
        second_sheet = self._source(1)
        key_before = second_sheet.get_cache_key()

        self._source().invalidate()

        assert self._source(1).get_cache_key() != key_before

    def test_unreadable_source_has_no_sheets_to_offer(self):
        ds = XlsxUrlDataSource(url="http://example.com/missing.xlsx")

        with mock.patch(
            "ckanext.tables.data_sources.fetch_remote_file",
            side_effect=OSError("boom"),
        ):
            assert ds.get_sheet_names() == []


@pytest.mark.usefixtures("clear_cache", "clean_redis", "mocked_fetch_remote_file")
class TestXlsUrlDataSource:
    """XlsUrlDataSource only overrides XlsxUrlDataSource's `_format_name`.

    pandas picks the xlrd/openpyxl engine from the file's actual bytes, not
    its extension.
    """

    @mock.patch("ckanext.tables.data_sources.pd.read_excel")
    def test_fetch_and_parse(self, mock_read_excel):
        mock_read_excel.return_value = pd.DataFrame([{"id": "1", "name": "Alice"}])

        ds = XlsUrlDataSource(url="http://example.com/legacy.xls")
        data = ds.filter([]).all()

        assert data == [{"id": "1", "name": "Alice"}]

    def test_format_name(self):
        assert XlsUrlDataSource(url="http://example.com/legacy.xls")._format_name == "XLS"


@pytest.mark.usefixtures("clear_cache", "clean_redis", "mocked_fetch_remote_file")
class TestOdsUrlDataSource:
    """OdsUrlDataSource only overrides XlsxUrlDataSource's `_format_name`.

    pandas picks the `odf` engine from the file's actual bytes, not its
    extension.
    """

    @mock.patch("ckanext.tables.data_sources.pd.read_excel")
    def test_fetch_and_parse(self, mock_read_excel):
        mock_read_excel.return_value = pd.DataFrame([{"id": "1", "name": "Alice"}])

        ds = OdsUrlDataSource(url="http://example.com/report.ods")
        data = ds.filter([]).all()

        assert data == [{"id": "1", "name": "Alice"}]

    def test_format_name(self):
        assert OdsUrlDataSource(url="http://example.com/report.ods")._format_name == "ODS"


@pytest.mark.usefixtures("clear_cache", "clean_redis", "mocked_fetch_remote_file")
class TestTsvUrlDataSource:
    """TsvUrlDataSource only overrides CsvUrlDataSource's `_format_name`.

    The delimiter sniffer (`_sniff_csv_delimiter`) already detects tabs from
    the file's content.
    """

    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    @mock.patch("ckanext.tables.data_sources._sniff_csv_delimiter", return_value="\t")
    def test_fetch_and_parse(self, _, mock_read_csv):
        mock_read_csv.return_value = pd.DataFrame([{"id": "1", "name": "Alice"}])

        ds = TsvUrlDataSource(url="http://example.com/data.tsv")
        data = ds.filter([]).all()

        assert data == [{"id": "1", "name": "Alice"}]
        mock_read_csv.assert_called_once_with("/tmp/mocked-source", sep="\t")

    def test_format_name(self):
        assert TsvUrlDataSource(url="http://example.com/data.tsv")._format_name == "TSV"


@pytest.mark.usefixtures("clear_cache", "clean_redis", "mocked_fetch_remote_file")
class TestNdjsonUrlDataSource:
    @mock.patch("ckanext.tables.data_sources.pd.read_json")
    def test_fetch_and_parse(self, mock_read_json):
        mock_read_json.return_value = pd.DataFrame([{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}])

        ds = NdjsonUrlDataSource(url="http://example.com/data.ndjson")
        data = ds.filter([]).all()

        assert data == [{"id": "1", "name": "Alice"}, {"id": "2", "name": "Bob"}]
        mock_read_json.assert_called_once_with("/tmp/mocked-source", lines=True)

    def test_format_name(self):
        assert NdjsonUrlDataSource(url="http://example.com/data.ndjson")._format_name == "NDJSON"


@pytest.mark.usefixtures("clear_cache", "clean_redis")
class TestJsonLdUrlDataSource:
    """Exercises JsonLdUrlDataSource's real @graph/bare-object/array handling.

    It does real file I/O (json.load) rather than calling a mockable pandas
    reader, so these write a real file and point the mocked
    ``fetch_remote_file`` at it instead of using the ``mocked_fetch_remote_file``
    fixture's fake path.
    """

    def _ds(self, tmp_path, monkeypatch, content: str) -> JsonLdUrlDataSource:
        path = tmp_path / "data.jsonld"
        path.write_text(content)
        monkeypatch.setattr(
            "ckanext.tables.data_sources.fetch_remote_file",
            lambda *a, **kw: contextlib.nullcontext(str(path)),
        )
        return JsonLdUrlDataSource(url="http://example.com/data.jsonld")

    def test_top_level_array(self, tmp_path, monkeypatch):
        content = json.dumps([{"@id": "ex:1", "name": "Alice"}, {"@id": "ex:2", "name": "Bob"}])
        ds = self._ds(tmp_path, monkeypatch, content)

        assert ds.filter([]).all() == [{"@id": "ex:1", "name": "Alice"}, {"@id": "ex:2", "name": "Bob"}]

    def test_at_graph_array(self, tmp_path, monkeypatch):
        content = json.dumps(
            {
                "@context": "https://schema.org",
                "@graph": [{"@id": "ex:1", "name": "Alice"}, {"@id": "ex:2", "name": "Bob"}],
            }
        )
        ds = self._ds(tmp_path, monkeypatch, content)

        assert ds.filter([]).all() == [{"@id": "ex:1", "name": "Alice"}, {"@id": "ex:2", "name": "Bob"}]

    def test_bare_object_becomes_a_single_row(self, tmp_path, monkeypatch):
        content = json.dumps({"@id": "ex:1", "name": "Alice"})
        ds = self._ds(tmp_path, monkeypatch, content)

        assert ds.filter([]).all() == [{"@id": "ex:1", "name": "Alice"}]

    def test_nested_values_are_flattened_with_underscores(self, tmp_path, monkeypatch):
        """An underscore separator avoids colliding with Tabulator's dot-path field syntax."""
        content = json.dumps([{"@id": "ex:1", "name": {"@value": "Alice", "@language": "en"}}])
        ds = self._ds(tmp_path, monkeypatch, content)

        assert ds.filter([]).all() == [{"@id": "ex:1", "name_@value": "Alice", "name_@language": "en"}]

    def test_schema_reader_matches_full_load_columns(self, tmp_path, monkeypatch):
        content = json.dumps([{"@id": "ex:1", "name": "Alice", "age": 30}])
        ds = self._ds(tmp_path, monkeypatch, content)

        assert ds.get_columns() == ["@id", "name", "age"]

    def test_invalid_top_level_scalar_raises(self, tmp_path, monkeypatch):
        ds = self._ds(tmp_path, monkeypatch, json.dumps("just a string"))

        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    def test_malformed_json_raises(self, tmp_path, monkeypatch):
        ds = self._ds(tmp_path, monkeypatch, "{not valid json")

        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    def test_format_name(self):
        assert JsonLdUrlDataSource(url="http://example.com/data.jsonld")._format_name == "JSON-LD"


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
        assert ds.serialize_value(date(2024, 1, 1)) == "2024-01-01"
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
    exactly as they would for a cached CSV/XLSX/etc. resource.
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
    """DuckDB-pushdown path must behave identically to the pandas path above.

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


class TestCacheStampede:
    """Concurrent cache misses for the same key must fetch only once.

    Each ``_ArrowStubDataSource`` instance below simulates a separate request
    (a fresh data source object, as ``get_cache_backend()`` builds per request),
    all sharing one cache backend/key — mirroring several concurrent requests
    for the same not-yet-cached resource.
    """

    def test_concurrent_misses_fetch_only_once(self, arrow_cache_backend):
        counter = {"calls": 0, "lock": threading.Lock()}

        class _SlowFetchSource(_ArrowStubDataSource):
            def fetch_dataframe(self) -> pd.DataFrame:
                with counter["lock"]:
                    counter["calls"] += 1
                time.sleep(0.2)
                return self._source_df

        df = pd.DataFrame([{"a": 1}])
        sources = [_SlowFetchSource(df, arrow_cache_backend, key="stampede-key") for _ in range(8)]

        threads = [threading.Thread(target=s._ensure_loaded) for s in sources]
        for t in threads:
            t.start()
        for t in threads:
            t.join()

        assert counter["calls"] == 1
        assert all(s._arrow is not None or s._df is not None for s in sources)

    def test_uncached_data_source_is_unaffected(self):
        """A plain (non-cached) PandasDataSource never touches the lock at all."""

        class _PlainPandasSource(PandasDataSource):
            def fetch_dataframe(self) -> pd.DataFrame:
                return pd.DataFrame([{"a": 1}])

        ds = _PlainPandasSource()
        ds._ensure_loaded()
        assert ds._df is not None


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


@pytest.mark.usefixtures("clean_redis", "mocked_fetch_remote_file")
class TestUrlDataSourceColumnCaching:
    """get_columns() caches its result instead of recomputing it on every call.

    CsvUrlDataSource stands in for all five *UrlDataSource formats, since the
    caching lives in the shared BaseResourceDataSource.get_columns(), not per format.
    """

    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_second_call_does_not_re_read_the_source(self, mock_read_csv, tmp_path):
        mock_read_csv.return_value = pd.DataFrame({"a": [1], "b": [2]})
        ds = CsvUrlDataSource(
            "http://example.com/col-cache-1.csv",
            cache_backend=FeatherCacheBackend(cache_dir=str(tmp_path)),
        )

        first = ds.get_columns()
        mock_read_csv.reset_mock()
        second = ds.get_columns()

        assert first == second == ["a", "b"]
        mock_read_csv.assert_not_called()

    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_a_fresh_instance_with_no_shared_disk_still_reuses_the_cache(self, mock_read_csv, tmp_path):
        # Each AJAX/action request builds a brand-new data source instance (see
        # ResourceViewHandler.get_table_for_resource) — and, in a multi-worker
        # deployment, from a worker with no shared Feather cache_dir at all. The
        # column list must still come from the shared Redis metadata store.
        mock_read_csv.return_value = pd.DataFrame({"a": [1], "b": [2]})
        url = "http://example.com/col-cache-2.csv"

        CsvUrlDataSource(url, cache_backend=FeatherCacheBackend(cache_dir=str(tmp_path / "worker1"))).get_columns()
        mock_read_csv.reset_mock()

        columns = CsvUrlDataSource(
            url, cache_backend=FeatherCacheBackend(cache_dir=str(tmp_path / "worker2"))
        ).get_columns()

        assert columns == ["a", "b"]
        mock_read_csv.assert_not_called()

    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_invalidate_orphans_the_cached_columns(self, mock_read_csv, tmp_path):
        mock_read_csv.return_value = pd.DataFrame({"a": [1]})
        ds = CsvUrlDataSource(
            "http://example.com/col-cache-3.csv",
            cache_backend=FeatherCacheBackend(cache_dir=str(tmp_path)),
        )

        assert ds.get_columns() == ["a"]

        ds.invalidate()
        mock_read_csv.return_value = pd.DataFrame({"a": [1], "new_col": [2]})
        mock_read_csv.reset_mock()

        assert ds.get_columns() == ["a", "new_col"]
        mock_read_csv.assert_called_once()


@pytest.mark.usefixtures("mocked_fetch_remote_file")
class TestUrlDataSourceErrorPaths:
    """A fetch/parse failure raises DataSourceError, not a silent empty table."""

    @mock.patch("ckanext.tables.data_sources.pd.read_excel", side_effect=OSError("boom"))
    def test_xlsx_error_raises(self, _):
        ds = XlsxUrlDataSource(url="http://example.com/file.xlsx")
        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    @mock.patch("ckanext.tables.data_sources.pd.read_excel", side_effect=OSError("boom"))
    def test_xls_error_raises(self, _):
        ds = XlsUrlDataSource(url="http://example.com/file.xls")
        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    @mock.patch("ckanext.tables.data_sources.pd.read_excel", side_effect=OSError("boom"))
    def test_ods_error_raises(self, _):
        ds = OdsUrlDataSource(url="http://example.com/file.ods")
        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    @mock.patch("ckanext.tables.data_sources.pd.read_csv", side_effect=OSError("boom"))
    def test_tsv_error_raises(self, _):
        ds = TsvUrlDataSource(url="http://example.com/file.tsv")
        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    @mock.patch("ckanext.tables.data_sources.pd.read_json", side_effect=OSError("boom"))
    def test_ndjson_error_raises(self, _):
        ds = NdjsonUrlDataSource(url="http://example.com/file.ndjson")
        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    @mock.patch("ckanext.tables.data_sources.pd.read_orc", side_effect=OSError("boom"))
    def test_orc_error_raises(self, _):
        ds = OrcUrlDataSource(url="http://example.com/file.orc")
        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    @mock.patch("ckanext.tables.data_sources.pd.read_parquet", side_effect=OSError("boom"))
    def test_parquet_error_raises(self, _):
        ds = ParquetUrlDataSource(url="http://example.com/file.parquet")
        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    @mock.patch("ckanext.tables.data_sources.pd.read_feather", side_effect=OSError("boom"))
    def test_feather_error_raises(self, _):
        ds = FeatherUrlDataSource(url="http://example.com/file.feather")
        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()

    @mock.patch("ckanext.tables.data_sources.pd.read_csv", side_effect=OSError("boom"))
    def test_csv_error_raises(self, _):
        ds = CsvUrlDataSource(url="http://example.com/file.csv")
        with pytest.raises(DataSourceError):
            ds.fetch_dataframe()


class TestDatabaseDataSource:
    """Tests for DatabaseDataSource using CKAN's test DB."""

    @pytest.mark.usefixtures("clean_db")
    def test_filter_sort_paginate(self):
        """filter/sort/paginate must actually narrow, order, and page the real result set."""
        factories.User(name="a-user")
        factories.User(name="b-user")
        factories.User(name="c-user")

        # exclude site-user with empty email
        ds = DatabaseDataSource(select(model.User.name).filter(model.User.email.is_not(None)))

        # paginate(1, 2) returns exactly the first 2 of the 3 rows, in ascending order.
        page = ds.filter([]).sort("name", "asc").paginate(1, 2).all()
        assert [row["name"] for row in page] == ["a-user", "b-user"]

        # A filter narrows the result to the matching row only.
        filtered = ds.filter([FilterItem("name", "=", "b-user")]).all()
        assert [row["name"] for row in filtered] == ["b-user"]

        # Descending sort reverses the order.
        desc = ds.filter([]).sort("name", "desc").paginate(1, 3).all()
        assert [row["name"] for row in desc] == ["c-user", "b-user", "a-user"]

    def test_get_columns(self):
        ds = DatabaseDataSource(select(model.User))
        cols = ds.get_columns()
        assert isinstance(cols, list)

    @pytest.mark.usefixtures("clean_db")
    def test_all_serializes_values_like_other_data_sources(self):
        """A raw datetime must come out as the same ISO string PandasDataSource produces.

        Without this, a column with no formatter renders differently
        depending on which data source backs the table, and a custom
        formatter written against one source's shape breaks on the other.
        """
        factories.User()

        ds = DatabaseDataSource(select(model.User.id, model.User.created))
        row = ds.filter([]).all()[0]

        assert isinstance(row["created"], str)
        datetime.fromisoformat(row["created"])

    @pytest.mark.usefixtures("clean_db")
    def test_count(self):
        """count() must reflect the current filter, not the whole table."""
        factories.User(name="counted-a")
        factories.User(name="counted-b")

        ds = DatabaseDataSource(select(model.User.name).filter(model.User.email.is_not(None)))

        assert ds.filter([]).count() == 2
        assert ds.filter([FilterItem("name", "=", "counted-a")]).count() == 1
        assert ds.filter([FilterItem("name", "=", "nonexistent")]).count() == 0

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

    def test_build_filter_numeric_column_casts_value(self):
        """COR-18: a Numeric column used to be compared as a string, which Postgres rejects."""
        ds = DatabaseDataSource(select(model.User))
        col = column("amount", Numeric())
        assert ds.build_filter(col, "=", "10.5") is not None

    def test_build_filter_numeric_column_invalid_value_is_skipped(self):
        """A non-numeric value against a Numeric column must be dropped, not sent to the DB."""
        ds = DatabaseDataSource(select(model.User))
        col = column("amount", Numeric())
        assert ds.build_filter(col, "=", "not-a-number") is None

    def test_build_filter_float_column_casts_value(self):
        ds = DatabaseDataSource(select(model.User))
        col = column("score", Float())
        assert ds.build_filter(col, ">=", "3.14") is not None

    def test_build_filter_date_column_casts_value(self):
        ds = DatabaseDataSource(select(model.User))
        col = column("created", Date())
        assert ds.build_filter(col, "=", "2024-01-01") is not None

    def test_build_filter_date_column_invalid_value_is_skipped(self):
        ds = DatabaseDataSource(select(model.User))
        col = column("created", Date())
        assert ds.build_filter(col, "=", "not-a-date") is None

    def test_build_filter_uuid_column_casts_value(self):
        ds = DatabaseDataSource(select(model.User))
        col = column("id", Uuid())
        assert ds.build_filter(col, "=", str(uuid.uuid4())) is not None

    def test_build_filter_uuid_column_invalid_value_is_skipped(self):
        ds = DatabaseDataSource(select(model.User))
        col = column("id", Uuid())
        assert ds.build_filter(col, "=", "not-a-uuid") is None

    def test_build_filter_like_on_numeric_column_is_no_longer_dropped(self):
        """COR-18: `like` used to be silently dropped for any non-string column."""
        ds = DatabaseDataSource(select(model.User))
        col = column("amount", Numeric())
        assert ds.build_filter(col, "like", "10") is not None


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
