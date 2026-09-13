from __future__ import annotations

import decimal
import json
import os
import time
from datetime import date, datetime
from unittest import mock

import numpy as np
import pandas as pd
import pyarrow as pa
import pytest

from ckan.lib.redis import connect_to_redis

from ckanext.tables import cache
from ckanext.tables.cache import (
    FeatherCacheBackend,
    RedisCacheBackend,
    _TablesJSONEncoder,
)
from ckanext.tables.types import FilterItem


def _expire(meta_path: str) -> None:
    """Rewrite a file-backend cache entry's meta sidecar so it reads as already expired."""
    with open(meta_path) as f:
        meta = json.load(f)
    meta["expires_at"] = time.time() - 10
    with open(meta_path, "w") as f:
        json.dump(meta, f)


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
def feather_backend(tmp_path):
    return FeatherCacheBackend(cache_dir=str(tmp_path))


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
        _expire(meta_path)
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

    def test_get_corrupted_file_is_deleted(self, feather_backend):
        # Left in place, a corrupted file would fail this exact way on every
        # future request until its TTL happens to expire — deleting it
        # immediately means the next set() recreates a good file right away.
        feather_backend.set("key", [{"v": 1}], ttl=60)
        path = feather_backend.get_cache_path("key")
        meta_path = feather_backend._meta_path("key")
        with open(path, "wb") as f:
            f.write(b"notfeather!!!")

        with mock.patch.object(cache, "log") as mock_log:
            feather_backend.get("key")

        assert not os.path.exists(path)
        assert not os.path.exists(meta_path)
        mock_log.warning.assert_called_once()

    def test_set_swallows_arrow_type_error_on_mixed_type_column(self, feather_backend):
        # Feather is the default backend, so an uncaught ArrowTypeError here
        # would 500 every request for the affected resource.
        df = pd.DataFrame({"mixed": [1, "two", 3.0]})
        feather_backend.set("bad", df, ttl=60)
        assert feather_backend.get("bad") is None

    def test_get_arrow_returns_pyarrow_table(self, feather_backend):
        data = [{"a": 1, "b": "x"}, {"a": 2, "b": "y"}]
        feather_backend.set("key1", data, ttl=60)

        table = feather_backend.get_arrow("key1")

        assert isinstance(table, pa.Table)
        assert table.to_pylist() == data

    def test_get_arrow_and_get_do_not_collide(self, feather_backend):
        data = [{"a": 1, "b": "x"}]
        feather_backend.set("key1", data, ttl=60)

        table = feather_backend.get_arrow("key1")
        df = feather_backend.get("key1")

        assert isinstance(table, pa.Table)
        assert isinstance(df, pd.DataFrame)

    def test_get_arrow_miss_returns_none(self, feather_backend):
        assert feather_backend.get_arrow("nonexistent") is None

    def test_get_arrow_expired_returns_none(self, feather_backend):
        feather_backend.set("expiring", [{"x": 1}], ttl=1)
        meta_path = feather_backend._meta_path("expiring")
        _expire(meta_path)
        assert feather_backend.get_arrow("expiring") is None


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

    def test_set_a_dataframe_with_nan_produces_valid_json(self):
        backend = RedisCacheBackend()
        df = pd.DataFrame({"a": [1.0, np.nan], "created": [pd.Timestamp("2024-01-01"), pd.NaT]})

        backend.set("nan_df", df, ttl=60)

        with connect_to_redis() as conn:
            raw = conn.get(backend._full_key("nan_df"))
        assert b"NaN" not in raw

        result = backend.get("nan_df")
        assert result[1]["a"] is None
        assert result[1]["created"] is None

    def test_set_a_dataframe_with_infinity_raises(self):
        # +-inf is a real value, not a missing one, and there's no correct
        # substitute for it — unlike NaN/NaT it's left to raise rather than
        # silently writing non-standard JSON.
        backend = RedisCacheBackend()
        df = pd.DataFrame({"a": [1.0, float("inf")]})

        with pytest.raises(ValueError, match="not JSON compliant"):
            backend.set("inf_df", df, ttl=60)

    def test_get_memoises_after_first_fetch(self):
        # A repeat get() for an unchanged value should skip json.loads on the
        # (potentially large) payload, not just return the same result.
        backend = RedisCacheBackend()
        backend.set("memo_key", {"x": 1}, ttl=60)

        with mock.patch("ckanext.tables.cache.json.loads", wraps=json.loads) as mock_loads:
            first = backend.get("memo_key")
            second = backend.get("memo_key")

        assert first == second == {"x": 1}
        assert mock_loads.call_count == 1

    def test_overwrite_busts_the_memo(self):
        backend = RedisCacheBackend()
        backend.set("memo_key2", {"x": 1}, ttl=60)
        backend.get("memo_key2")

        backend.set("memo_key2", {"x": 2}, ttl=60)
        assert backend.get("memo_key2") == {"x": 2}

    def test_delete_clears_the_memo(self):
        backend = RedisCacheBackend()
        backend.set("memo_key3", {"x": 1}, ttl=60)
        backend.get("memo_key3")

        backend.delete("memo_key3")
        assert backend.get("memo_key3") is None

    def test_no_get_arrow(self):
        # RedisCacheBackend stores JSON records, not an Arrow-native format,
        # so it deliberately doesn't implement get_arrow() — PandasDataSource
        # detects this via hasattr() to fall back to the plain pandas path.
        assert not hasattr(RedisCacheBackend(), "get_arrow")

    def test_get_corrupted_value_is_deleted(self):
        backend = RedisCacheBackend()
        full_key = backend._full_key("bad_key")
        version_key = backend._version_key("bad_key")

        with connect_to_redis() as conn:
            conn.setex(version_key, 60, "v1")
            conn.setex(full_key, 60, b"not json!!!")

        with mock.patch.object(cache, "log") as mock_log:
            result = backend.get("bad_key")

        assert result is None
        with connect_to_redis() as conn:
            assert conn.get(full_key) is None
            assert conn.get(version_key) is None
        mock_log.warning.assert_called_once()


class TestFileCacheBackendUnsafeDir:
    """A cache directory another local user could write to must disable caching, not use it."""

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

        _expire(feather_backend._meta_path("key1"))

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

        _expire(meta_path)

        assert feather_backend.get("key1") is None
        assert not os.path.exists(data_path)
        assert not os.path.exists(meta_path)

    def test_clean_expired_removes_only_expired_entries(self, feather_backend):
        feather_backend.set("fresh", pd.DataFrame([{"a": 1}]), ttl=3600)
        feather_backend.set("expired", pd.DataFrame([{"a": 2}]), ttl=1)

        _expire(feather_backend._meta_path("expired"))

        removed = feather_backend.clean_expired()

        assert removed == 1
        assert os.path.exists(feather_backend.get_cache_path("fresh"))
        assert not os.path.exists(feather_backend.get_cache_path("expired"))
        assert not os.path.exists(feather_backend._meta_path("expired"))

    def test_clean_expired_handles_a_scalar_entry(self, feather_backend):
        feather_backend.set("count", 42, ttl=1)
        _expire(feather_backend._meta_path("count"))

        assert feather_backend.clean_expired() == 1
        assert not os.path.exists(feather_backend._meta_path("count"))

    def test_clean_expired_is_a_noop_for_unsafe_or_missing_dir(self, tmp_path):
        unsafe_dir = tmp_path / "shared"
        unsafe_dir.mkdir()
        unsafe_dir.chmod(0o777)

        backend = FeatherCacheBackend(cache_dir=str(unsafe_dir))
        assert backend.cache_dir is None


class TestFileCacheBackendAtomicWrite:
    """A concurrent reader must never see a half-written file or a mismatched pair."""

    def test_set_leaves_no_stray_tmp_file_on_success(self, feather_backend, tmp_path):
        feather_backend.set("key1", pd.DataFrame([{"a": 1}]), ttl=60)
        assert [f for f in os.listdir(str(tmp_path)) if f.startswith(".tmp-")] == []

    def test_failed_write_does_not_clobber_the_previous_value(self, feather_backend):
        feather_backend.set("key1", pd.DataFrame([{"a": 1}]), ttl=60)

        with mock.patch.object(FeatherCacheBackend, "_write_df", side_effect=OSError("disk full")):
            feather_backend.set("key1", pd.DataFrame([{"a": 99}]), ttl=60)

        # The failed write's temp file was cleaned up, and never replaced the
        # previous complete data/meta pair, so the old value is still served.
        assert feather_backend.get("key1").to_dict(orient="records") == [{"a": 1}]

    def test_clean_expired_sweeps_an_abandoned_tmp_file(self, feather_backend, tmp_path):
        from ckanext.tables.cache import _STALE_TMP_FILE_AGE

        stale_tmp = tmp_path / ".tmp-abandoned"
        stale_tmp.write_text("partial")
        old_time = time.time() - _STALE_TMP_FILE_AGE - 10
        os.utime(str(stale_tmp), (old_time, old_time))

        removed = feather_backend.clean_expired()

        assert removed == 1
        assert not stale_tmp.exists()

    def test_clean_expired_keeps_a_fresh_tmp_file(self, feather_backend, tmp_path):
        fresh_tmp = tmp_path / ".tmp-inprogress"
        fresh_tmp.write_text("partial")

        removed = feather_backend.clean_expired()

        assert removed == 0
        assert fresh_tmp.exists()

    def test_redis_backend_clean_expired_is_a_noop(self):
        assert RedisCacheBackend().clean_expired() == 0


@pytest.mark.usefixtures("clean_redis")
class TestInvalidateCacheEntry:
    """invalidate_cache_entry deletes the data key and bumps a generation token in Redis."""

    def test_deletes_the_key(self, feather_backend):
        from ckanext.tables.cache import invalidate_cache_entry

        feather_backend.set("key1", pd.DataFrame([{"a": 1}]), ttl=60)
        invalidate_cache_entry(feather_backend, "key1", ttl=60)
        assert feather_backend.get("key1") is None

    def test_bumps_the_generation_token_to_a_new_value(self, feather_backend):
        from ckanext.tables.cache import invalidate_cache_entry

        invalidate_cache_entry(feather_backend, "key1", ttl=60)
        first_gen = RedisCacheBackend().get("key1:gen")
        assert first_gen is not None

        invalidate_cache_entry(feather_backend, "key1", ttl=60)
        second_gen = RedisCacheBackend().get("key1:gen")

        assert second_gen is not None
        assert second_gen != first_gen

    def test_generation_token_lands_in_redis_not_the_data_backend(self, feather_backend):
        # The token must be visible to every worker, not just whichever one ran
        # invalidate() — a file-based cache_backend can't do that on its own.
        from ckanext.tables.cache import invalidate_cache_entry

        invalidate_cache_entry(feather_backend, "key1", ttl=60)

        assert feather_backend.get("key1:gen") is None
        assert RedisCacheBackend().get("key1:gen") is not None


class _FakeCachedDataSource(cache.CachedDataSourceMixin):
    """Minimal concrete data source for exercising the mixin's count-cache logic."""

    def __init__(self, backend: cache.CacheBackend, key: str = "fake-key", ttl: int = 60):
        self.cache_backend = backend
        self.cache_ttl = ttl
        self._key = key

    def get_cache_key(self) -> str:
        return self._key


@pytest.mark.usefixtures("clean_redis")
class TestCachedDataSourceMixinCounts:
    def test_get_cached_count_is_none_on_a_miss(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)
        assert ds.get_cached_count([]) is None

    def test_set_then_get_returns_the_cached_value(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)
        ds.set_cached_count([], 3)
        assert ds.get_cached_count([]) == 3

    def test_count_cache_key_ignores_page_size_and_sort(self, feather_backend):
        # get_total_count only ever passes filters (see TableDefinition.get_total_count),
        # so nothing here needs to be sensitive to page/size/sort.
        ds = _FakeCachedDataSource(feather_backend)
        filters = [FilterItem("x", "=", "1")]
        assert ds._count_cache_key(filters) == ds._count_cache_key(filters)

    def test_count_cache_key_stable_across_filter_value_types(self, feather_backend):
        # Equal filters with "30" vs 30 should not produce different keys.
        ds = _FakeCachedDataSource(feather_backend)
        str_key = ds._count_cache_key([FilterItem("age", "=", "30")])
        int_key = ds._count_cache_key([FilterItem("age", "=", 30)])
        assert str_key == int_key

    def test_count_cache_key_differs_by_filter(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)
        no_filter = ds._count_cache_key([])
        with_filter = ds._count_cache_key([FilterItem("age", "=", 30)])
        other_filter = ds._count_cache_key([FilterItem("age", "=", 31)])
        assert no_filter != with_filter != other_filter

    def test_invalidate_orphans_previously_cached_counts(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)
        ds.set_cached_count([], 3)
        assert ds.get_cached_count([]) is not None

        ds.invalidate()

        assert ds.get_cached_count([]) is None

    def test_count_lands_in_redis_regardless_of_the_configured_cache_backend(self, feather_backend):
        # The DataFrame itself is Feather-backed here, but the count must be
        # readable straight out of Redis too — that's what makes it visible
        # to every worker, not just the one that computed it.
        ds = _FakeCachedDataSource(feather_backend, key="cross-worker-key")
        ds.set_cached_count([], 7)

        assert RedisCacheBackend().get(ds._count_cache_key([])) == 7


@pytest.mark.usefixtures("clean_redis")
class TestCachedDataSourceMixinColumns:
    def test_get_cached_columns_is_none_on_a_miss(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)
        assert ds.get_cached_columns() is None

    def test_set_then_get_returns_the_cached_value(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)
        ds.set_cached_columns(["a", "b"])
        assert ds.get_cached_columns() == ["a", "b"]

    def test_invalidate_orphans_previously_cached_columns(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)
        ds.set_cached_columns(["a", "b"])
        assert ds.get_cached_columns() is not None

        ds.invalidate()

        assert ds.get_cached_columns() is None

    def test_columns_land_in_redis_regardless_of_the_configured_cache_backend(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend, key="cross-worker-columns-key")
        ds.set_cached_columns(["x", "y"])

        assert RedisCacheBackend().get(ds._columns_cache_key()) == ["x", "y"]


class TestCacheMetadataResilience:
    """A Redis outage must degrade count/generation caching, not break the request."""

    def test_get_cached_count_returns_none_when_redis_is_unreachable(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)

        with mock.patch.object(cache.RedisCacheBackend, "get", side_effect=cache.RedisError("down")):
            assert ds.get_cached_count([]) is None

    def test_set_cached_count_does_not_raise_when_redis_is_unreachable(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)

        with mock.patch.object(cache.RedisCacheBackend, "set", side_effect=cache.RedisError("down")):
            ds.set_cached_count([], 3)  # must not raise

    def test_generation_falls_back_to_the_baseline_when_redis_is_unreachable(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)

        with mock.patch.object(cache.RedisCacheBackend, "get", side_effect=cache.RedisError("down")):
            assert ds._generation() == "0"

    def test_invalidate_does_not_raise_when_redis_is_unreachable(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)

        with mock.patch.object(cache.RedisCacheBackend, "set", side_effect=cache.RedisError("down")):
            ds.invalidate()  # the Feather delete must still happen, the Redis bump must not raise

    def test_get_cached_columns_returns_none_when_redis_is_unreachable(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)

        with mock.patch.object(cache.RedisCacheBackend, "get", side_effect=cache.RedisError("down")):
            assert ds.get_cached_columns() is None

    def test_set_cached_columns_does_not_raise_when_redis_is_unreachable(self, feather_backend):
        ds = _FakeCachedDataSource(feather_backend)

        with mock.patch.object(cache.RedisCacheBackend, "set", side_effect=cache.RedisError("down")):
            ds.set_cached_columns(["a"])  # must not raise
