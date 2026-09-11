from __future__ import annotations

import decimal
import json
import os
import time
from datetime import date, datetime
from unittest import mock

import numpy as np
import pandas as pd
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
        assert result.to_dict(orient="records") == data

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
        assert result.to_dict(orient="records") == data

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


class TestFileCacheBackendUnsafeDir:
    """A cache directory another local user could write to must disable caching, not use it."""

    def test_pickle_backend_disables_caching_for_unsafe_dir(self, tmp_path):
        unsafe_dir = tmp_path / "shared"
        unsafe_dir.mkdir()
        unsafe_dir.chmod(0o777)

        backend = PickleCacheBackend(cache_dir=str(unsafe_dir))
        assert backend.cache_dir is None

        # get/set/delete become no-ops rather than writing to the unsafe directory.
        backend.set("key1", [1, 2, 3], ttl=60)
        assert backend.get("key1") is None
        backend.delete("key1")

        assert os.listdir(unsafe_dir) == []

    def test_feather_backend_disables_caching_for_unsafe_dir(self, tmp_path):
        unsafe_dir = tmp_path / "shared"
        unsafe_dir.mkdir()
        unsafe_dir.chmod(0o777)

        backend = FeatherCacheBackend(cache_dir=str(unsafe_dir))
        assert backend.cache_dir is None
        backend.set("key1", [{"a": 1}], ttl=60)
        assert backend.get("key1") is None
        assert os.listdir(unsafe_dir) == []


class TestFileCacheBackendInProcessMemo:
    """A hit that has not gone stale must be served from RAM, not re-read from disk.

    ``get()`` used to deserialise the cache file from disk on every call, even for
    repeated requests against the same still-fresh entry within the same worker
    process — that's the expensive part for a large cached table.
    """

    def test_repeated_get_does_not_re_read_the_file(self, feather_backend):
        df = pd.DataFrame([{"a": 1, "b": "x"}])
        feather_backend.set("key1", df, ttl=60)

        first = feather_backend.get("key1")  # real read, warms the memo
        assert first.to_dict() == df.to_dict()

        with mock.patch.object(feather_backend, "_read_data") as mock_read:
            second = feather_backend.get("key1")

        assert not mock_read.called
        assert second.to_dict() == df.to_dict()

    def test_a_fresh_instance_still_sees_the_shared_memo(self, tmp_path):
        """A new backend object (as constructed fresh per request) must still hit it.

        The memo is process-wide, not per-instance.
        """
        cache_dir = str(tmp_path)
        df = pd.DataFrame([{"a": 1}])
        FeatherCacheBackend(cache_dir=cache_dir).set("key1", df, ttl=60)
        FeatherCacheBackend(cache_dir=cache_dir).get("key1")  # warms the memo

        other_instance = FeatherCacheBackend(cache_dir=cache_dir)
        with mock.patch.object(other_instance, "_read_data") as mock_read:
            result = other_instance.get("key1")

        assert not mock_read.called
        assert result.to_dict() == df.to_dict()

    def test_overwrite_busts_the_memo(self, feather_backend):
        feather_backend.set("key1", pd.DataFrame([{"a": 1}]), ttl=60)
        feather_backend.get("key1")

        time.sleep(0.01)
        feather_backend.set("key1", pd.DataFrame([{"a": 99}]), ttl=60)

        assert feather_backend.get("key1").to_dict() == pd.DataFrame([{"a": 99}]).to_dict()

    def test_delete_clears_the_memo(self, feather_backend):
        feather_backend.set("key1", pd.DataFrame([{"a": 1}]), ttl=60)
        feather_backend.get("key1")

        feather_backend.delete("key1")

        assert feather_backend.get("key1") is None

    def test_ttl_expiry_still_applies_to_a_warm_memo(self, feather_backend):
        feather_backend.set("key1", pd.DataFrame([{"a": 1}]), ttl=1)
        feather_backend.get("key1")  # warms the memo

        old_mtime = time.time() - 10
        os.utime(feather_backend._meta_path("key1"), (old_mtime, old_mtime))

        assert feather_backend.get("key1") is None

    def test_memo_size_is_bounded(self, feather_backend):
        from ckanext.tables.cache import _MEMO_MAX_ENTRIES

        for i in range(_MEMO_MAX_ENTRIES + 10):
            feather_backend.set(f"bulk-{i}", pd.DataFrame([{"x": i}]), ttl=60)
            feather_backend.get(f"bulk-{i}")

        assert len(FeatherCacheBackend._memo) <= _MEMO_MAX_ENTRIES


class TestFileCacheBackendExpiryCleanup:
    """An expired entry must not be left on disk forever.

    ``get`` used to just return ``None`` for an expired entry and leave its
    file where it was — a key that's never read again (a removed resource, a
    one-off filter/page/sort count key) would then never be cleaned up.
    """

    def test_get_deletes_the_files_on_an_expired_read(self, feather_backend):
        feather_backend.set("key1", pd.DataFrame([{"a": 1}]), ttl=1)
        data_path = feather_backend.get_cache_path("key1")
        meta_path = feather_backend._meta_path("key1")
        assert os.path.exists(data_path)
        assert os.path.exists(meta_path)

        old_mtime = time.time() - 10
        os.utime(meta_path, (old_mtime, old_mtime))

        assert feather_backend.get("key1") is None
        assert not os.path.exists(data_path)
        assert not os.path.exists(meta_path)

    def test_clean_expired_removes_only_expired_entries(self, feather_backend):
        feather_backend.set("fresh", pd.DataFrame([{"a": 1}]), ttl=3600)
        feather_backend.set("expired", pd.DataFrame([{"a": 2}]), ttl=1)

        old_mtime = time.time() - 10
        os.utime(feather_backend._meta_path("expired"), (old_mtime, old_mtime))

        removed = feather_backend.clean_expired()

        assert removed == 1
        assert os.path.exists(feather_backend.get_cache_path("fresh"))
        assert not os.path.exists(feather_backend.get_cache_path("expired"))
        assert not os.path.exists(feather_backend._meta_path("expired"))

    def test_clean_expired_handles_a_scalar_entry(self, feather_backend):
        feather_backend.set("count", 42, ttl=1)
        old_mtime = time.time() - 10
        os.utime(feather_backend._meta_path("count"), (old_mtime, old_mtime))

        assert feather_backend.clean_expired() == 1
        assert not os.path.exists(feather_backend._meta_path("count"))

    def test_clean_expired_cleans_up_a_former_backend_format_too(self, tmp_path):
        """Sweeping must not assume the current backend wrote every file present.

        If ``ckanext.tables.cache.backend`` was switched, old entries in a
        different format share the same directory and sidecar format.
        """
        cache_dir = str(tmp_path)
        pickle_backend = PickleCacheBackend(cache_dir=cache_dir)
        pickle_backend.set("old", [{"x": 1}], ttl=1)
        old_mtime = time.time() - 10
        os.utime(pickle_backend._meta_path("old"), (old_mtime, old_mtime))
        pkl_path = pickle_backend.get_cache_path("old")
        assert os.path.exists(pkl_path)

        feather_backend = FeatherCacheBackend(cache_dir=cache_dir)
        removed = feather_backend.clean_expired()

        assert removed == 1
        assert not os.path.exists(pkl_path)

    def test_clean_expired_is_a_noop_for_unsafe_or_missing_dir(self, tmp_path):
        unsafe_dir = tmp_path / "shared"
        unsafe_dir.mkdir()
        unsafe_dir.chmod(0o777)

        backend = FeatherCacheBackend(cache_dir=str(unsafe_dir))
        assert backend.cache_dir is None
        assert backend.clean_expired() == 0

    def test_redis_backend_clean_expired_is_a_noop(self):
        assert RedisCacheBackend().clean_expired() == 0
