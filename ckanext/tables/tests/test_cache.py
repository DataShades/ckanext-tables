from __future__ import annotations

import json
import decimal
import os
import time
from datetime import date, datetime

import numpy as np
import pytest

from ckanext.tables.cache import (
    FeatherCacheBackend,
    ParquetCacheBackend,
    PickleCacheBackend,
    RedisCacheBackend,
    _TablesJSONEncoder,
)


class TestTablesJSONEncoder:
    def _encode(self, value):
        return json.dumps(value, cls=_TablesJSONEncoder)

    def test_datetime(self):
        result = self._encode(datetime(2024, 1, 15, 10, 30, 0))  # noqa: DTZ001
        assert "2024-01-15" in result

    def test_date(self):
        result = self._encode(date(2024, 6, 1))
        assert "2024-06-01" in result

    def test_decimal(self):
        result = json.loads(self._encode(decimal.Decimal("3.14")))
        assert abs(result - 3.14) < 0.001

    def test_bytes(self):
        result = json.loads(self._encode(b"hello"))
        assert result == "hello"

    def test_numpy_scalar(self):
        result = json.loads(self._encode(np.int64(42)))
        assert result == 42

    def test_unsupported_type_raises(self):
        with pytest.raises(TypeError):
            self._encode(object())


@pytest.fixture
def pickle_backend(tmp_path):
    return PickleCacheBackend(cache_dir=str(tmp_path))


@pytest.fixture
def parquet_backend(tmp_path):
    return ParquetCacheBackend(cache_dir=str(tmp_path))


@pytest.fixture
def feather_backend(tmp_path):
    return FeatherCacheBackend(cache_dir=str(tmp_path))


class TestPickleCacheBackend:
    def test_set_and_get(self, pickle_backend):
        pickle_backend.set("key1", [1, 2, 3], ttl=60)
        result = pickle_backend.get("key1")
        assert result == [1, 2, 3]

    def test_miss_returns_none(self, pickle_backend):
        assert pickle_backend.get("nonexistent") is None

    def test_expired_returns_none(self, pickle_backend):
        pickle_backend.set("expiring", {"a": 1}, ttl=1)
        meta_path = pickle_backend._meta_path("expiring")
        old_mtime = time.time() - 10
        os.utime(meta_path, (old_mtime, old_mtime))
        assert pickle_backend.get("expiring") is None

    def test_delete(self, pickle_backend):
        pickle_backend.set("to_delete", "value", ttl=60)
        pickle_backend.delete("to_delete")
        assert pickle_backend.get("to_delete") is None

    def test_delete_nonexistent_is_noop(self, pickle_backend):
        pickle_backend.delete("does_not_exist")

    def test_get_cache_path(self, pickle_backend):
        path = pickle_backend.get_cache_path("mykey")
        assert path.endswith(".pkl")
        assert pickle_backend.cache_dir in path

    def test_set_creates_cache_dir(self, tmp_path):
        new_dir = str(tmp_path / "subdir" / "nested")
        backend = PickleCacheBackend(cache_dir=new_dir)
        backend.set("k", "v", ttl=60)
        assert os.path.isdir(new_dir)

    def test_get_corrupted_file_returns_none(self, pickle_backend):
        pickle_backend.set("key", [{"v": 1}], ttl=60)
        path = pickle_backend.get_cache_path("key")
        with open(path, "wb") as f:
            f.write(b"notpickle!!!")
        assert pickle_backend.get("key") is None

    def test_scalar_value(self, pickle_backend):
        pickle_backend.set("count", 42, ttl=60)
        assert pickle_backend.get("count") == 42


class TestParquetCacheBackend:
    def test_set_and_get(self, parquet_backend):
        data = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        parquet_backend.set("key1", data, ttl=60)
        result = parquet_backend.get("key1")
        assert result == data

    def test_miss_returns_none(self, parquet_backend):
        assert parquet_backend.get("nonexistent") is None

    def test_expired_returns_none(self, parquet_backend):
        parquet_backend.set("expiring", [{"x": 1}], ttl=1)
        meta_path = parquet_backend._meta_path("expiring")
        old_mtime = time.time() - 10
        os.utime(meta_path, (old_mtime, old_mtime))
        assert parquet_backend.get("expiring") is None

    def test_delete(self, parquet_backend):
        parquet_backend.set("to_delete", [{"v": 1}], ttl=60)
        parquet_backend.delete("to_delete")
        assert parquet_backend.get("to_delete") is None

    def test_delete_nonexistent_is_noop(self, parquet_backend):
        parquet_backend.delete("does_not_exist")

    def test_get_cache_path(self, parquet_backend):
        path = parquet_backend.get_cache_path("mykey")
        assert path.endswith(".parquet")
        assert parquet_backend.cache_dir in path

    def test_set_creates_cache_dir(self, tmp_path):
        new_dir = str(tmp_path / "subdir" / "nested")
        backend = ParquetCacheBackend(cache_dir=new_dir)
        backend.set("k", [{"v": 1}], ttl=60)
        assert os.path.isdir(new_dir)

    def test_scalar_value(self, parquet_backend):
        parquet_backend.set("count", 42, ttl=60)
        assert parquet_backend.get("count") == 42

    def test_get_corrupted_file_returns_none(self, parquet_backend):
        parquet_backend.set("key", [{"v": 1}], ttl=60)
        path = parquet_backend.get_cache_path("key")
        with open(path, "wb") as f:
            f.write(b"notparquet!!!")
        assert parquet_backend.get("key") is None


class TestFeatherCacheBackend:
    def test_set_and_get(self, feather_backend):
        data = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        feather_backend.set("key1", data, ttl=60)
        result = feather_backend.get("key1")
        assert result == data

    def test_miss_returns_none(self, feather_backend):
        assert feather_backend.get("nonexistent") is None

    def test_expired_returns_none(self, feather_backend):
        feather_backend.set("expiring", [{"x": 1}], ttl=1)
        meta_path = feather_backend._meta_path("expiring")
        old_mtime = time.time() - 10
        os.utime(meta_path, (old_mtime, old_mtime))
        assert feather_backend.get("expiring") is None

    def test_delete(self, feather_backend):
        feather_backend.set("to_delete", [{"v": 1}], ttl=60)
        feather_backend.delete("to_delete")
        assert feather_backend.get("to_delete") is None

    def test_delete_nonexistent_is_noop(self, feather_backend):
        feather_backend.delete("does_not_exist")

    def test_get_cache_path(self, feather_backend):
        path = feather_backend.get_cache_path("mykey")
        assert path.endswith(".feather")
        assert feather_backend.cache_dir in path

    def test_set_creates_cache_dir(self, tmp_path):
        new_dir = str(tmp_path / "subdir" / "nested")
        backend = FeatherCacheBackend(cache_dir=new_dir)
        backend.set("k", [{"v": 1}], ttl=60)
        assert os.path.isdir(new_dir)

    def test_scalar_value(self, feather_backend):
        feather_backend.set("count", 42, ttl=60)
        assert feather_backend.get("count") == 42

    def test_get_corrupted_file_returns_none(self, feather_backend):
        feather_backend.set("key", [{"v": 1}], ttl=60)
        path = feather_backend.get_cache_path("key")
        with open(path, "wb") as f:
            f.write(b"notfeather!!!")
        assert feather_backend.get("key") is None


@pytest.mark.usefixtures("clean_redis")
class TestRedisCacheBackend:
    def test_set_and_get(self):
        backend = RedisCacheBackend()
        backend.set("mykey", {"x": 1}, ttl=60)
        result = backend.get("mykey")
        assert result == {"x": 1}

    def test_miss_returns_none(self):
        backend = RedisCacheBackend()
        assert backend.get("does_not_exist") is None

    def test_delete(self):
        backend = RedisCacheBackend()
        backend.set("del_key", 42, ttl=60)
        backend.delete("del_key")
        assert backend.get("del_key") is None

    def test_full_key_format(self):
        backend = RedisCacheBackend()
        assert backend._full_key("foo") == "ckanext:tables:foo"

    def test_set_serialises_special_types(self):
        backend = RedisCacheBackend()
        # decimal.Decimal is not JSON serialisable by default
        backend.set("decimal_key", decimal.Decimal("9.99"), ttl=60)
        result = backend.get("decimal_key")
        assert abs(result - 9.99) < 0.001
