from __future__ import annotations

import contextlib
import csv
import decimal
import json
import logging
import os
import re
import tempfile
from collections.abc import Callable, Iterator
from datetime import datetime
from itertools import islice
from typing import Any
from urllib.parse import urlparse

import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyarrow import feather, orc
from sqlalchemy import Boolean, DateTime, Integer
from sqlalchemy.engine import RowMapping
from sqlalchemy.sql import Select, func, select
from sqlalchemy.sql.elements import BinaryExpression, ClauseElement, ColumnElement
from typing_extensions import Self

import ckan.plugins.toolkit as tk
from ckan import model
from ckan.lib import uploader

from ckanext.tables.cache import CacheBackend, CachedDataSourceMixin
from ckanext.tables.config import get_cache_backend, get_cache_ttl
from ckanext.tables.net import fetch_remote_file
from ckanext.tables.types import FilterItem

log = logging.getLogger(__name__)

_ALLOWED_URL_SCHEMES = ("http", "https")

_CSV_SNIFF_LINES = 10


def _sniff_csv_delimiter(path: str) -> str | None:
    """Detect a local CSV file's delimiter from its first few lines.

    Returns ``None`` if sniffing fails (e.g. a single-column file, or too few
    rows to compare), so the caller can fall back to pandas' own slower but
    more thorough auto-detection instead of guessing wrong.
    """
    try:
        with open(path, encoding="utf-8", errors="replace", newline="") as f:
            sample = "".join(islice(f, _CSV_SNIFF_LINES))
    except OSError:
        return None

    if not sample:
        return None

    try:
        return csv.Sniffer().sniff(sample).delimiter
    except csv.Error:
        return None


class BaseDataSource:
    def filter(self, filters: list[FilterItem]) -> Self: ...
    def sort(self, sort_by: str | None, sort_order: str | None) -> Self: ...
    def paginate(self, page: int, size: int) -> Self: ...
    def all(self) -> list[dict[str, Any]]: ...
    def count(self) -> int: ...
    def get_columns(self) -> list[str]: ...


class DatabaseDataSource(BaseDataSource):
    """A data source that uses a SQLAlchemy statement as the data source.

    Args:
        stmt: The SQLAlchemy statement to use as the data source
    """

    def __init__(self, stmt: Select):
        self.base_stmt = stmt
        self.stmt = stmt

    def filter(self, filters: list[FilterItem]) -> Self:
        self.stmt = self.base_stmt

        for filter_item in filters:
            if not hasattr(self.stmt.selected_columns, filter_item.field):
                continue

            col = getattr(self.stmt.selected_columns, filter_item.field)
            expr = self.build_filter(col, filter_item.operator, filter_item.value)

            if expr is not None:
                self.stmt = self.stmt.where(expr)

        return self

    def build_filter(self, column: ColumnElement, operator: str, value: str) -> BinaryExpression | ClauseElement | None:
        try:
            if isinstance(column.type, Boolean):
                casted_value = str(value).lower() in ("true", "1", "yes", "y")
            elif isinstance(column.type, Integer):
                casted_value = int(value)
            elif isinstance(column.type, DateTime):
                casted_value = datetime.fromisoformat(value)
            else:
                casted_value = str(value)
        except ValueError:
            return None

        operators: dict[
            str,
            Callable[[ColumnElement, Any], BinaryExpression | ClauseElement | None],
        ] = {
            "=": lambda col, val: col == val,
            "<": lambda col, val: col < val,
            "<=": lambda col, val: col <= val,
            ">": lambda col, val: col > val,
            ">=": lambda col, val: col >= val,
            "!=": lambda col, val: col != val,
            "like": lambda col, val: col.ilike(f"%{val}%") if isinstance(val, str) else None,
        }

        func = operators.get(operator)
        return func(column, casted_value) if func else None

    def sort(self, sort_by: str | None, sort_order: str | None) -> Self:
        if not sort_by or not hasattr(self.stmt.selected_columns, sort_by):
            return self

        col = getattr(self.stmt.selected_columns, sort_by)

        # Clear existing order_by clauses
        self.stmt = self.stmt.order_by(None)

        if sort_order and sort_order.lower() == "desc":
            self.stmt = self.stmt.order_by(col.desc())
        else:
            self.stmt = self.stmt.order_by(col.asc())

        return self

    def paginate(self, page: int, size: int) -> Self:
        if page and size:
            self.stmt = self.stmt.limit(size).offset((page - 1) * size)

        return self

    def all(self) -> list[dict[str, Any]]:
        return [self.serialize_row(row) for row in model.Session.execute(self.stmt).mappings().all()]  # type: ignore

    def serialize_row(self, row: RowMapping) -> dict[str, Any]:
        return dict(row)

    def count(self) -> int:
        return model.Session.execute(select(func.count()).select_from(self.stmt.subquery())).scalar_one()

    def get_columns(self) -> list[str]:
        return [c.name for c in self.stmt.selected_columns]


def _numeric_or_string_pair(row_value: Any, filter_value: Any) -> tuple[Any, Any]:
    """Compare two values numerically when both parse as numbers, else as strings."""
    if not isinstance(row_value, bool) and not isinstance(filter_value, bool):
        try:
            return float(row_value), float(filter_value)
        except (TypeError, ValueError):
            pass

    return str(row_value), str(filter_value)


class ListDataSource(BaseDataSource):
    """A data source that uses a list of dictionaries as the data source.

    This is useful for testing and demo purposes, when you already have data
    on your hand.

    Args:
        data: The list of dictionaries to use as the data source

    """

    def __init__(self, data: list[dict[str, Any]]):
        self.data = data
        self.filtered = data

    def filter(self, filters: list[FilterItem]) -> Self:
        self.filtered = self.data

        for filter_item in filters:
            pred = self.build_filter(filter_item.field, filter_item.operator, filter_item.value)

            if pred:
                self.filtered = [row for row in self.filtered if pred(row)]

        return self

    def build_filter(self, field: str, operator: str, value: str) -> Callable[[dict[str, Any]], bool] | None:
        string_operators: dict[str, Callable[[str, str], bool]] = {
            "=": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "like": lambda a, b: b.lower() in a.lower(),
        }
        ordering_operators: dict[str, Callable[[Any, Any], bool]] = {
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
        }

        if op_func := string_operators.get(operator):
            return lambda row: op_func(str(row.get(field, "")), str(value))

        if op_func := ordering_operators.get(operator):
            return lambda row: op_func(*_numeric_or_string_pair(row.get(field, ""), value))

        return None

    def sort(self, sort_by: str | None, sort_order: str | None) -> Self:
        if not sort_by:
            return self

        self.filtered = sorted(
            self.filtered,
            # A type-stable (bool, str) key: rows missing the field, or with a None
            # value, sort together at one end instead of raising TypeError against
            # rows whose value is an int/str/float mix.
            key=lambda x: (x.get(sort_by) is None, str(x.get(sort_by, ""))),
            reverse=(sort_order or "").lower() == "desc",
        )

        return self

    def paginate(self, page: int, size: int) -> Self:
        if page and size:
            start = (page - 1) * size
            end = start + size
            self.filtered = self.filtered[start:end]
        return self

    def all(self):
        return self.filtered

    def count(self):
        return len(self.filtered)

    def get_columns(self) -> list[str]:
        return list(self.data[0].keys()) if self.data else []


class PandasDataSource(BaseDataSource):
    """Base class for data sources that use a pandas DataFrame.

    Subclasses must implement :meth:`fetch_dataframe`. Caching is **not**
    included here — mix in :class:`~ckanext.tables.cache.CachedDataSourceMixin`
    and set ``cache_backend`` if you want it.
    """

    def __init__(self):
        self._df: pd.DataFrame | None = None
        self._filtered_df: pd.DataFrame | None = None

    def fetch_dataframe(self) -> pd.DataFrame:
        """Fetch the data and return it as a pandas DataFrame."""
        raise NotImplementedError

    def _load_from_cache(self) -> bool:
        """Attempt to restore the dataframe from cache. Returns True on success."""
        if self._df is not None:
            return True

        if isinstance(self, CachedDataSourceMixin):
            try:
                cached = self.cache_backend.get(self.get_cache_key())
                if cached is not None:
                    # File-based backends already return a DataFrame; only the Redis
                    # backend (JSON records) needs reconstructing into one — skip the
                    # otherwise-unnecessary copy for the common (file-based) case.
                    self._df = cached if isinstance(cached, pd.DataFrame) else pd.DataFrame(cached)
                    return True
            except (ValueError, TypeError, OSError):
                log.debug("Failed to restore DataFrame from cache", exc_info=True)

        return False

    def _ensure_loaded(self) -> None:
        """Load the dataframe, using the cache backend when available."""
        if self._load_from_cache():
            self._filtered_df = self._df
            return

        if self._df is None:
            self._df = self.fetch_dataframe()

            if isinstance(self, CachedDataSourceMixin) and self._df is not None and not self._df.empty:
                try:
                    self.cache_backend.set(
                        self.get_cache_key(),
                        self._df,
                        self.cache_ttl,
                    )
                except (OSError, ValueError, TypeError):
                    log.warning("Failed to write DataFrame to cache", exc_info=True)

        self._filtered_df = self._df

    def filter(self, filters: list[FilterItem]) -> Self:  # noqa: C901
        self._ensure_loaded()
        self._filtered_df = self._df  # Reset filtering

        if self._filtered_df is None or self._filtered_df.empty:
            return self

        # Work through a local variable, not self._filtered_df directly: it's
        # reassigned on every loop iteration below, and a type checker can't
        # carry the "not None" guard above across those reassignments the way
        # it can for a local variable.
        df = self._filtered_df

        for filter_item in filters:
            if filter_item.field not in df.columns:
                continue

            try:
                series = df[filter_item.field]
                val = filter_item.value
                op = filter_item.operator

                # Attempt to convert types if possible, otherwise use string comparison.
                # Skip numeric cast for "like" — we need the raw string for str.contains().
                if op != "like" and pd.api.types.is_numeric_dtype(series):
                    with contextlib.suppress(ValueError):
                        val = float(val)

                if op == "=":
                    df = df[series == val]
                elif op == "!=":
                    df = df[series != val]
                elif op == "<":
                    df = df[series < val]
                elif op == "<=":
                    df = df[series <= val]
                elif op == ">":
                    df = df[series > val]
                elif op == ">=":
                    df = df[series >= val]
                elif op == "like":
                    # Cast series to str so LIKE works on numeric columns too.
                    # Use filter_item.value (the original string) to avoid float repr like "157.0".
                    df = df[series.astype(str).str.contains(str(filter_item.value), case=False, na=False)]
            except (ValueError, TypeError):
                log.debug("Failed to apply filter %s", filter_item, exc_info=True)

        self._filtered_df = df
        return self

    def sort(self, sort_by: str | None, sort_order: str | None) -> Self:
        if not sort_by or self._filtered_df is None or self._filtered_df.empty:
            return self

        if sort_by not in self._filtered_df.columns:
            return self

        ascending = (sort_order or "").lower() != "desc"
        self._filtered_df = self._filtered_df.sort_values(by=sort_by, ascending=ascending)

        return self

    def paginate(self, page: int, size: int) -> Self:
        if self._filtered_df is None or self._filtered_df.empty:
            return self

        start = (page - 1) * size
        self._filtered_df = self._filtered_df.iloc[start : start + size]

        return self

    def all(self) -> list[dict[str, Any]]:  # noqa: C901
        if self._filtered_df is None or self._filtered_df.empty:
            return []

        df = self._filtered_df.astype(object).where(self._filtered_df.notnull(), None)

        records = df.to_dict(orient="records")
        return [self.serialize_value(record) for record in records]  # type: ignore

    def count(self) -> int:
        return len(self._filtered_df) if self._filtered_df is not None else 0

    def get_columns(self) -> list[str]:
        self._ensure_loaded()
        return list(self._df.columns) if self._df is not None else []

    def serialize_value(self, val: Any) -> Any:  # noqa: PLR0911
        if val is None:
            return None
        if isinstance(val, (bool, int, float, str)):
            return val
        if isinstance(val, bytes):
            return val.decode("utf-8", errors="replace")
        if isinstance(val, (datetime, pd.Timestamp)):
            return val.isoformat()
        if isinstance(val, decimal.Decimal):
            return float(val)
        if isinstance(val, (list, tuple, np.ndarray)):
            return [self.serialize_value(x) for x in val]
        if isinstance(val, dict):
            return {k: self.serialize_value(v) for k, v in val.items()}
        if hasattr(val, "item"):
            return self.serialize_value(val.item())

        return str(val)


class BaseResourceDataSource(CachedDataSourceMixin, PandasDataSource):
    """A data source that loads resource data from a file or URL.

    The cache backend defaults to the value of ``ckanext.tables.cache.backend``
    (``"feather"`` by default). Pass an explicit *cache_backend* to
    override for a specific instance.

    Override ``cache_ttl`` on a subclass or pass it to the constructor to
    change the expiry.

    Args:
        url: Direct URL to fetch data from.
        resource: The CKAN resource dictionary.
        cache_backend: Override the configured cache backend for this instance.
        cache_ttl: Override the default TTL (seconds) for this instance.
    """

    def __init__(
        self,
        url: str | None = None,
        resource: dict[str, Any] | None = None,
        cache_backend: CacheBackend | None = None,
        cache_ttl: int | None = None,
    ):
        super().__init__()

        if not url and not resource:
            raise ValueError("Either url or resource_id must be provided")

        self.url = url
        self.resource = resource
        self._source_path: str = ""
        self._upload_storage: Any | None = None
        self.cache_backend = cache_backend if cache_backend is not None else get_cache_backend()
        self.cache_ttl = cache_ttl if cache_ttl is not None else get_cache_ttl()

    def get_cache_key(self) -> str:
        return f"resource-{self.resource['id']}" if self.resource else f"url-{self.url}"

    def get_source_path(self) -> str:
        if self._source_path:
            return self._source_path

        if self.resource:
            try:
                if self.resource.get("url_type") == "upload":
                    upload = uploader.get_resource_uploader(self.resource)
                    self._source_path = upload.get_path(self.resource["id"])

                    # On CKAN 2.12+ with file-keeper storage, get_path() returns a
                    # storage-relative Location, not a filesystem path — stash the
                    # storage so _open_source() reads through its API instead of
                    # handing that relative string straight to pandas.
                    fk_upload_cls = getattr(uploader, "FKResourceUpload", None)
                    if fk_upload_cls is not None and isinstance(upload, fk_upload_cls):
                        self._upload_storage = upload.storage

                    return self._source_path

                if self.resource.get("url"):
                    self._source_path = self._ensure_remote_url(self.resource["url"])
                    return self._source_path

            except (OSError, TypeError, tk.ValidationError, tk.ObjectNotFound):
                log.warning(
                    "Failed to resolve path for resource %s, falling back to provided url",
                    self.resource.get("id"),
                    exc_info=True,
                )

        if self.url:
            self._source_path = self._ensure_remote_url(self.url)
            return self._source_path

        raise ValueError("Could not resolve source path")

    @staticmethod
    def _ensure_remote_url(url: str) -> str:
        """Reject anything that is not a well-formed http(s) URL.

        These readers (``pd.read_csv``, ``read_excel``, ``read_parquet``,
        ``read_feather``, ``read_orc``) all accept local filesystem paths and
        ``file://`` URLs, not just http(s) URLs. A resource's ``url`` (or a
        resource view's ``file_url``) is set by dataset editors, not
        sysadmins, so without this check anyone able to edit a resource could
        make the server read and return the contents of an arbitrary local
        file (e.g. ``ckan.ini``, secrets, other users' uploads).
        """
        parsed = urlparse(url)

        if parsed.scheme not in _ALLOWED_URL_SCHEMES or not parsed.netloc:
            raise ValueError(f"Unsupported or unsafe URL: {url!r}. Only http(s) URLs are allowed.")

        return url

    @contextlib.contextmanager
    def _open_source(self) -> Iterator[str]:
        """Yield a local filesystem path for the source.

        A remote http(s) URL is downloaded to a guarded temporary file first
        (timeouts, size cap, SSRF checks — see :mod:`ckanext.tables.net`); a
        file-keeper-backed upload is read via its storage's real path when
        that storage is on local disk, or streamed into a temporary file
        otherwise (e.g. S3, where there's no local path to read from); a
        plain local path (resolved via the legacy CKAN uploader) is yielded
        unchanged. Any temp file created along the way is removed once the
        caller is done.
        """
        source = self.get_source_path()

        if source.startswith(("http://", "https://")):
            with fetch_remote_file(source) as local_path:
                yield local_path
        elif self._upload_storage is not None:
            with self._read_fk_upload(self._upload_storage, source) as local_path:
                yield local_path
        else:
            yield source

    @staticmethod
    @contextlib.contextmanager
    def _read_fk_upload(storage: Any, location: str) -> Iterator[str]:
        """Yield a local path for a file-keeper storage object.

        ``storage.full_path()`` is a cheap, generic ``join(base, location)`` —
        it doesn't confirm the storage is actually on local disk, so it's only
        trusted when the result exists on disk; otherwise (e.g. an S3-backed
        storage) fall back to streaming the content into a temp file.
        """
        # Resolve (and fully exit) this before yielding — a caller's exception while
        # using the yielded path must propagate normally, not get swallowed here.
        local_path = None
        with contextlib.suppress(Exception):
            candidate = storage.full_path(location)
            if os.path.isfile(candidate):
                local_path = candidate

        if local_path is not None:
            yield local_path
            return

        from ckan.lib import files  # noqa: PLC0415 — only importable on CKAN 2.12+

        fd, tmp_path = tempfile.mkstemp(prefix="ckanext-tables-")

        try:
            with os.fdopen(fd, "wb") as tmp_file:
                for chunk in storage.stream(files.FileData(location)):
                    tmp_file.write(chunk)
            yield tmp_path
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.remove(tmp_path)


class CsvUrlDataSource(BaseResourceDataSource):
    @staticmethod
    def _read_csv(path: str, **kwargs: Any) -> pd.DataFrame:
        """Read a local CSV file, using the fast C engine when possible.

        Sniffs the delimiter from the first few lines so the C engine can be
        used for the actual read; only falls back to pandas' own slower
        ``engine="python"`` auto-detection when sniffing fails.
        """
        delimiter = _sniff_csv_delimiter(path)
        if delimiter is not None:
            return pd.read_csv(path, sep=delimiter, **kwargs)

        return pd.read_csv(path, sep=None, engine="python", **kwargs)

    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            with self._open_source() as path:
                return self._read_csv(path)
        except Exception:
            log.exception("Error fetching CSV from %s", self.get_source_path())
            return pd.DataFrame()

    def get_columns(self) -> list[str]:
        if self._load_from_cache():
            return list(self._df.columns) if self._df is not None else []

        try:
            with self._open_source() as path:
                df_preview = self._read_csv(path, nrows=0)
        except (OSError, ValueError, pd.errors.ParserError):
            log.exception("Failed fast CSV schema read, falling back to full load")
            self._ensure_loaded()
            return list(self._df.columns) if self._df is not None else []

        return list(df_preview.columns)


class XlsxUrlDataSource(BaseResourceDataSource):
    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            with self._open_source() as path:
                return pd.read_excel(path)
        except Exception:
            log.exception("Error fetching XLSX from %s", self.get_source_path())
            return pd.DataFrame()

    def get_columns(self) -> list[str]:
        if self._load_from_cache():
            return list(self._df.columns) if self._df is not None else []

        try:
            with self._open_source() as path:
                df_preview = pd.read_excel(path, nrows=0)
        except (OSError, ValueError):
            log.exception("Failed fast XLSX schema read, falling back to full load")
            self._ensure_loaded()
            return list(self._df.columns) if self._df is not None else []

        return list(df_preview.columns)


class OrcUrlDataSource(BaseResourceDataSource):
    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            with self._open_source() as path:
                return pd.read_orc(path)
        except Exception:
            log.exception("Error fetching ORC from %s", self.get_source_path())
            return pd.DataFrame()

    def get_columns(self) -> list[str]:
        if self._load_from_cache():
            return list(self._df.columns) if self._df is not None else []

        try:
            with self._open_source() as path:
                schema_names = orc.ORCFile(path).schema.names
        except (OSError, ValueError, pa.ArrowInvalid):
            log.exception("Failed fast ORC schema read, falling back to full load")
            self._ensure_loaded()
            return list(self._df.columns) if self._df is not None else []

        return schema_names


class ParquetUrlDataSource(BaseResourceDataSource):
    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            with self._open_source() as path:
                return pd.read_parquet(path)
        except Exception:
            log.exception("Error fetching Parquet from %s", self.get_source_path())
            return pd.DataFrame()

    def get_columns(self) -> list[str]:
        if self._load_from_cache():
            return list(self._df.columns) if self._df is not None else []

        try:
            with self._open_source() as path:
                schema_names = pq.read_schema(path).names
        except (OSError, ValueError, pa.ArrowInvalid):
            log.exception("Failed fast Parquet schema read, falling back to full load")
            self._ensure_loaded()
            return list(self._df.columns) if self._df is not None else []

        return schema_names


class FeatherUrlDataSource(BaseResourceDataSource):
    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            with self._open_source() as path:
                return pd.read_feather(path)
        except Exception:
            log.exception("Error fetching Feather from %s", self.get_source_path())
            return pd.DataFrame()

    def get_columns(self) -> list[str]:
        if self._load_from_cache():
            return list(self._df.columns) if self._df is not None else []

        try:
            with self._open_source() as path:
                schema_names = feather.read_table(path, columns=[]).schema.names
        except (OSError, ValueError, pa.ArrowInvalid):
            log.exception("Failed fast Feather schema read, falling back to full load")
            self._ensure_loaded()
            return list(self._df.columns) if self._df is not None else []

        return schema_names


class DataStoreDataSource(BaseDataSource):
    """A data source that fetches records directly from the CKAN Datastore."""

    def __init__(self, resource_id: str):
        self.resource_id = resource_id

        self._filters: dict[str, Any] = {}
        self._q: dict[str, str] = {}
        self._sort: str | None = None
        self._limit: int | None = None
        self._offset: int | None = None

        self._datastore_enabled = "datastore" in tk.g.plugins

    def filter(self, filters: list[FilterItem]) -> Self:
        self._filters = {}
        self._q = {}

        for filter_item in filters:
            if filter_item.operator == "=":
                self._filters[filter_item.field] = filter_item.value
            elif filter_item.operator == "like":
                # replace non-alphanumeric characters (except dots) with FTS wildcard (_)
                v = str(filter_item.value)
                v = re.sub(r"[^\w\-\.]+", "_", v)
                # append ':*' so we can do partial FTS searches
                self._q[filter_item.field] = v + ":*"
            # Other operators like <, > might require datastore_search_sql
            # which is more complex, so we skip them unless necessary.
        return self

    def sort(self, sort_by: str | None, sort_order: str | None) -> Self:
        self._sort = f"{sort_by} {sort_order or 'asc'}" if sort_by else None
        return self

    def paginate(self, page: int, size: int) -> Self:
        if page and size:
            self._limit = size
            self._offset = (page - 1) * size
        return self

    def all(self) -> list[dict[str, Any]]:
        if not self._datastore_enabled:
            return []

        data_dict: dict[str, Any] = {"resource_id": self.resource_id}

        if self._filters:
            data_dict["filters"] = self._filters

        if self._q:
            data_dict["q"] = json.dumps(self._q)
            data_dict["plain"] = False
            data_dict["language"] = "simple"

        if self._sort:
            data_dict["sort"] = self._sort

        if self._limit is not None:
            data_dict["limit"] = self._limit

        if self._offset is not None:
            data_dict["offset"] = self._offset

        try:
            result = tk.get_action("datastore_search")({}, data_dict)
            return result.get("records", [])
        except (tk.ObjectNotFound, tk.NotAuthorized, tk.ValidationError):
            # ValidationError covers an invalid sort/filter field name — both come
            # straight from unvalidated request params (see filter()/sort() above).
            return []

    def count(self) -> int:
        if not self._datastore_enabled:
            return 0

        data_dict: dict[str, Any] = {"resource_id": self.resource_id, "limit": 0}

        if self._filters:
            data_dict["filters"] = self._filters

        if self._q:
            data_dict["q"] = json.dumps(self._q)
            data_dict["plain"] = False
            data_dict["language"] = "simple"

        try:
            result = tk.get_action("datastore_search")({}, data_dict)
            return result.get("total", 0)
        except (tk.ObjectNotFound, tk.NotAuthorized, tk.ValidationError):
            return 0

    def get_columns(self) -> list[str]:
        if not self._datastore_enabled:
            return []

        data_dict = {"resource_id": self.resource_id, "limit": 0}

        try:
            result = tk.get_action("datastore_search")({}, data_dict)
            return [f["id"] for f in result.get("fields", []) if f["id"] != "_id"]
        except (tk.ObjectNotFound, tk.NotAuthorized):
            return []
