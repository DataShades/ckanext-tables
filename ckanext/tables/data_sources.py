from __future__ import annotations

import contextlib
import csv
import decimal
import json
import logging
import os
import re
import tempfile
import threading
import uuid
from collections.abc import Callable, Iterator
from datetime import date, datetime
from itertools import islice
from typing import Any, ClassVar
from urllib.parse import urlparse

import duckdb
import numpy as np
import pandas as pd
import pyarrow as pa
import pyarrow.parquet as pq
from pyarrow import feather, orc
from sqlalchemy import String, cast
from sqlalchemy.engine import RowMapping
from sqlalchemy.sql import Select, func, select
from sqlalchemy.sql.elements import ColumnElement
from typing_extensions import Self

import ckan.plugins as p
import ckan.plugins.toolkit as tk
from ckan import model
from ckan.lib import uploader

from ckanext.tables.cache import CacheBackend, CachedDataSourceMixin, get_cache_backend
from ckanext.tables.config import get_cache_ttl
from ckanext.tables.net import fetch_remote_file
from ckanext.tables.types import FilterItem

log = logging.getLogger(__name__)

_ALLOWED_URL_SCHEMES = ("http", "https")

_CSV_SNIFF_LINES = 10

_thread_local = threading.local()


class DataSourceError(Exception):
    """Raised when a data source cannot fetch or parse its data."""


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

    def __init__(self, stmt: Select[Any]):
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

    def build_filter(self, column: ColumnElement[Any], operator: str, value: str) -> ColumnElement[bool] | None:
        if operator == "like":
            # Cast to text so LIKE works on non-string columns too (numeric, date,
            # UUID, ...), matching the pandas/arrow data sources' str.contains() /
            # CAST(... AS VARCHAR) behaviour instead of silently dropping the filter.
            return cast(column, String).ilike(f"%{value}%")

        try:
            python_type = column.type.python_type
        except NotImplementedError:
            # No single Python type for this column (e.g. JSON) — fall back to a
            # plain string comparison, same as the pre-existing behaviour.
            python_type = str

        try:
            if python_type is bool:
                casted_value = str(value).lower() in ("true", "1", "yes", "y")
            elif python_type is int:
                casted_value = int(value)
            elif python_type is float or python_type is decimal.Decimal:
                casted_value = float(value)
            elif python_type is datetime:
                casted_value = datetime.fromisoformat(value)
            elif python_type is date:
                casted_value = date.fromisoformat(value)
            elif python_type is uuid.UUID:
                casted_value = uuid.UUID(str(value))
            else:
                casted_value = str(value)
        except (ValueError, TypeError):
            # A value that doesn't fit the column's type (e.g. a non-numeric
            # string against a Numeric column) — skip the filter instead of
            # building a comparison the database would reject at execution time.
            log.debug("Failed to cast filter value %r for a %s column", value, python_type, exc_info=True)
            return None

        operators: dict[
            str,
            Callable[[ColumnElement[Any], Any], ColumnElement[bool] | None],
        ] = {
            "=": lambda col, val: col == val,
            "<": lambda col, val: col < val,
            "<=": lambda col, val: col <= val,
            ">": lambda col, val: col > val,
            ">=": lambda col, val: col >= val,
            "!=": lambda col, val: col != val,
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
        return [self.serialize_row(row) for row in model.Session.execute(self.stmt).mappings().all()]

    def serialize_row(self, row: RowMapping) -> dict[str, Any]:
        return dict(row)

    def count(self) -> int:
        return model.Session.execute(select(func.count()).select_from(self.stmt.subquery())).scalar_one()

    def get_columns(self) -> list[str]:
        return [c.name for c in self.stmt.selected_columns]


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

    When the configured cache backend exposes ``get_arrow()`` (the Arrow-native
    file backend, Feather), filtering/sorting/pagination/counting are pushed
    down to DuckDB running against the cached ``pyarrow.Table``
    instead of pandas scanning the full in-memory frame on every call — see
    the ``*_arrow`` methods below. Every other cache backend (Redis, or none)
    keeps using the plain pandas implementation (the ``*_pandas`` methods),
    unchanged.
    """

    def __init__(self):
        self._df: pd.DataFrame | None = None
        self._filtered_df: pd.DataFrame | None = None

        self._arrow: pa.Table | None = None
        self._con: duckdb.DuckDBPyConnection | None = None
        self._where_sql = ""
        self._where_params: list[Any] = []
        self._order_sql = ""
        self._limit_sql = ""
        self._limit_params: list[Any] = []

    def fetch_dataframe(self) -> pd.DataFrame:
        """Fetch the data and return it as a pandas DataFrame."""
        raise NotImplementedError

    def _use_arrow_path(self) -> bool:
        return isinstance(self, CachedDataSourceMixin) and hasattr(self.cache_backend, "get_arrow")

    def _set_arrow(self, table: pa.Table) -> None:  # pyright: ignore[reportUnknownParameterType]
        self._arrow = table
        self._con = _get_duckdb_connection()
        self._con.register("t", table)

    def _require_con(self) -> duckdb.DuckDBPyConnection:
        if self._con is None:
            raise RuntimeError("Arrow query connection is not available")
        return self._con

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
                log.warning("Failed to restore DataFrame from cache", exc_info=True)

        return False

    def _ensure_loaded(self) -> None:  # noqa: C901
        """Load the data, using the cache backend when available.

        Uses ``get_arrow()`` when the cache backend supports it — everything
        downstream then queries ``self._arrow`` via DuckDB instead of loading
        a full pandas DataFrame. Otherwise falls back to the plain-pandas
        path (``self._df``/``self._filtered_df``), same as before.
        """
        if self._arrow is not None or self._df is not None:
            if self._arrow is None:
                self._filtered_df = self._df
            return

        if isinstance(self, CachedDataSourceMixin) and hasattr(self.cache_backend, "get_arrow"):
            try:
                arrow = _get_arrow_from_cache(self.cache_backend, self.get_cache_key())
            except (ValueError, TypeError, OSError):
                # See the matching comment in _load_from_cache above.
                log.warning("Failed to restore Arrow table from cache", exc_info=True)
                arrow = None

            if arrow is not None:
                self._set_arrow(arrow)
                return

        if self._load_from_cache():
            self._filtered_df = self._df
            return

        self._df = self.fetch_dataframe()

        # Defensive: fetch_dataframe() is a public override point, so a misbehaving
        # subclass could violate its own "-> pd.DataFrame" contract at runtime.
        is_loaded = self._df is not None and not self._df.empty  # pyright: ignore[reportUnnecessaryComparison]
        if isinstance(self, CachedDataSourceMixin) and is_loaded:
            try:
                self.cache_backend.set(
                    self.get_cache_key(),
                    self._df,
                    self.cache_ttl,
                )
            except (OSError, ValueError, TypeError):
                log.warning("Failed to write DataFrame to cache", exc_info=True)

        if self._use_arrow_path() and is_loaded:
            # Even a cold cache gets the fast query path from here on — no need
            # to re-read the file just written, converting what's already in
            # hand is cheaper than a round trip through disk. A DataFrame that
            # failed the same conversion above (mixed-type object column) hits
            # it again here — fall back to the plain pandas path rather than
            # letting a *second* attempt at the identical conversion 500.
            try:
                self._set_arrow(pa.Table.from_pandas(self._df, preserve_index=False))
            except (pa.ArrowException, ValueError, TypeError):
                log.debug("Failed to convert DataFrame to Arrow; falling back to pandas", exc_info=True)
            else:
                return

        self._filtered_df = self._df

    def filter(self, filters: list[FilterItem]) -> Self:
        self._ensure_loaded()

        if self._arrow is not None:
            return self._filter_arrow(filters)

        return self._filter_pandas(filters)

    def _filter_pandas(self, filters: list[FilterItem]) -> Self:  # noqa: C901
        self._filtered_df = self._df  # Reset filtering

        if self._filtered_df is None or self._filtered_df.empty:
            return self

        # Work through a local variable, not self._filtered_df directly: it's
        # reassigned on every loop iteration below, and a type checker can't
        # carry the "not None" guard above across those reassignments the way
        # it can for a local variable.
        df = self._filtered_df

        for filter_item in filters:
            # pandas' own __getitem__ overloads are imprecise enough that pyright infers
            # a DataFrame | Series | ndarray union for df from the reassignments below —
            # this is correct at runtime, verified directly against pandas' own behaviour.
            if filter_item.field not in df.columns:  # pyright: ignore[reportAttributeAccessIssue]
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
                    # Cast series to str so LIKE works on numeric columns too. Use
                    # filter_item.value (the original string) to avoid float repr like "157.0".
                    str_series = series.astype(str)
                    value = str(filter_item.value)
                    str_accessor = str_series.str  # pyright: ignore[reportAttributeAccessIssue]
                    df = df[str_accessor.contains(value, case=False, na=False)]
            except (ValueError, TypeError):
                log.debug("Failed to apply filter %s", filter_item, exc_info=True)

        self._filtered_df = df  # pyright: ignore[reportAttributeAccessIssue]
        return self

    _ARROW_OPERATORS: ClassVar[dict[str, str]] = {
        "=": "=",
        "!=": "!=",
        "<": "<",
        "<=": "<=",
        ">": ">",
        ">=": ">=",
    }

    def _build_arrow_clause(
        self,
        schema: pa.Schema,  # pyright: ignore[reportUnknownParameterType]
        filter_item: FilterItem,
    ) -> tuple[str | None, list[Any]]:
        ident = _quote_ident(filter_item.field)

        if filter_item.operator == "like":
            # Cast to VARCHAR so LIKE works on numeric columns too, matching the
            # pandas path's series.astype(str) + str.contains(case=False).
            return f"CAST({ident} AS VARCHAR) ILIKE ?", [f"%{filter_item.value}%"]

        sql_op = self._ARROW_OPERATORS.get(filter_item.operator)
        if sql_op is None:
            return None, []

        val: Any = filter_item.value
        field_type = schema.field(filter_item.field).type
        if pa.types.is_integer(field_type) or pa.types.is_floating(field_type):
            try:
                val = float(val)
            except ValueError:
                # Matches the pandas path's ordering-operator behaviour when a
                # non-numeric value is compared against a numeric column: skip
                # this filter rather than binding a mismatched type DuckDB
                # would reject at execution time.
                return None, []

        return f"{ident} {sql_op} ?", [val]

    def _filter_arrow(self, filters: list[FilterItem]) -> Self:
        self._where_sql = ""
        self._where_params = []

        if self._arrow is None or self._arrow.num_rows == 0:
            return self

        schema = self._arrow.schema
        clauses: list[str] = []

        for filter_item in filters:
            if filter_item.field not in schema.names:
                continue

            try:
                clause, params = self._build_arrow_clause(schema, filter_item)
            except (ValueError, TypeError):
                log.debug("Failed to apply filter %s", filter_item, exc_info=True)
                continue

            if clause is None:
                continue

            clauses.append(clause)
            self._where_params.extend(params)

        if clauses:
            self._where_sql = "WHERE " + " AND ".join(clauses)

        return self

    def sort(self, sort_by: str | None, sort_order: str | None) -> Self:
        if self._arrow is not None:
            return self._sort_arrow(sort_by, sort_order)

        return self._sort_pandas(sort_by, sort_order)

    def _sort_pandas(self, sort_by: str | None, sort_order: str | None) -> Self:
        if not sort_by or self._filtered_df is None or self._filtered_df.empty:
            return self

        if sort_by not in self._filtered_df.columns:
            return self

        ascending = (sort_order or "").lower() != "desc"
        self._filtered_df = self._filtered_df.sort_values(by=sort_by, ascending=ascending)

        return self

    def _sort_arrow(self, sort_by: str | None, sort_order: str | None) -> Self:
        self._order_sql = ""

        if not sort_by or self._arrow is None or self._arrow.num_rows == 0:
            return self

        if sort_by not in self._arrow.schema.names:
            return self

        direction = "DESC" if (sort_order or "").lower() == "desc" else "ASC"
        self._order_sql = f"ORDER BY {_quote_ident(sort_by)} {direction}"

        return self

    def paginate(self, page: int, size: int) -> Self:
        if self._arrow is not None:
            return self._paginate_arrow(page, size)

        return self._paginate_pandas(page, size)

    def _paginate_pandas(self, page: int, size: int) -> Self:
        if self._filtered_df is None or self._filtered_df.empty:
            return self

        start = (page - 1) * size
        self._filtered_df = self._filtered_df.iloc[start : start + size]

        return self

    def _paginate_arrow(self, page: int, size: int) -> Self:
        self._limit_sql = ""
        self._limit_params = []

        if self._arrow is None or self._arrow.num_rows == 0:
            return self

        self._limit_sql = "LIMIT ? OFFSET ?"
        self._limit_params = [size, (page - 1) * size]

        return self

    def all(self) -> list[dict[str, Any]]:
        if self._arrow is not None:
            return self._all_arrow()

        return self._all_pandas()

    def _dataframe_to_records(self, df: pd.DataFrame) -> list[dict[str, Any]]:
        if df.empty:
            return []

        obj_df = df.astype(object).where(df.notnull(), None)
        records = obj_df.to_dict(orient="records")
        return [self.serialize_value(record) for record in records]

    def _all_pandas(self) -> list[dict[str, Any]]:
        if self._filtered_df is None:
            return []

        return self._dataframe_to_records(self._filtered_df)

    def _all_arrow(self) -> list[dict[str, Any]]:
        if self._arrow is None or self._arrow.num_rows == 0:
            return []

        # _where_sql/_order_sql/_limit_sql only ever contain quoted identifiers
        # already validated against self._arrow.schema.names (see
        # _filter_arrow/_sort_arrow/_quote_ident) and literal SQL keywords —
        # every value is bound via `?`, never interpolated.
        sql = f"SELECT * FROM t {self._where_sql} {self._order_sql} {self._limit_sql}"  # noqa: S608
        params = [*self._where_params, *self._limit_params]
        df = self._require_con().execute(sql, params).fetch_df()

        return self._dataframe_to_records(df)

    def count(self) -> int:
        if self._arrow is not None:
            return self._count_arrow()

        return len(self._filtered_df) if self._filtered_df is not None else 0

    def _count_arrow(self) -> int:
        if self._arrow is None or self._arrow.num_rows == 0:
            return 0

        sql = f"SELECT COUNT(*) FROM t {self._where_sql}"  # noqa: S608 — see _all_arrow
        result = self._require_con().execute(sql, self._where_params).fetchone()
        return result[0] if result else 0

    def get_columns(self) -> list[str]:
        self._ensure_loaded()

        if self._arrow is not None:
            return list(self._arrow.schema.names)

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

    The cache backend defaults to ``FeatherCacheBackend``. Pass an explicit
    *cache_backend* to override for a specific instance.

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
        return resource_cache_key(self.resource["id"]) if self.resource else f"url-{self.url}"

    def get_columns(self) -> list[str]:
        """Return the column names, preferring a cached answer over recomputing it.

        The resource-preview endpoints (``views.py``'s ``ResourceViewHandler``/
        ``ResourceViewDeferredHandler``) call this on *every* GET/POST for a given
        resource — pagination, sorting, filtering, and every action all re-derive
        the same deterministic column list before doing anything else.
        """
        cached = self.get_cached_columns()

        if cached is not None:
            return cached

        columns = self._fetch_columns()

        if columns:
            self.set_cached_columns(columns)

        return columns

    def _fetch_columns(self) -> list[str]:
        """Compute the column names, without consulting the cache above.

        Shared by every format: try a schema-only read first (via
        ``_schema_reader``, cheap — nothing is fully loaded), and only fall
        back to a full ``_ensure_loaded()`` if that fails or the DataFrame is
        already cached in this process (in which case reading it back out is
        cheaper than a second, redundant schema read).
        """
        if self._load_from_cache():
            return list(self._df.columns) if self._df is not None else []

        try:
            with self._open_source() as path:
                return self._schema_reader(path)
        except self._schema_read_errors:
            log.exception("Failed fast %s schema read, falling back to full load", self._format_name)
            self._ensure_loaded()
            return list(self._df.columns) if self._df is not None else []

    # Every format below only needs to fill these four in, instead of
    # repeating fetch_dataframe/_fetch_columns's shared try/except/fallback
    # structure five times with just the reader call swapped out.
    _format_name: ClassVar[str]
    _schema_read_errors: ClassVar[tuple[type[Exception], ...]] = (OSError, ValueError)

    def _reader(self, path: str, **kwargs: Any) -> pd.DataFrame:
        """Subclass hook: read *path* (a local file) into a DataFrame."""
        raise NotImplementedError

    def _schema_reader(self, path: str) -> list[str]:
        """Subclass hook: read just *path*'s column names, without loading the full file."""
        raise NotImplementedError

    def fetch_dataframe(self) -> pd.DataFrame:
        """Read the source file, or raise ``DataSourceError`` if it can't be read.

        A network error, an auth failure from the remote host, or a file that
        doesn't parse as this format are all "couldn't load", not "loaded
        zero rows" — conflating the two used to mean a genuinely
        broken resource silently rendered as an empty table, indistinguishable
        from one that's just empty. Callers (the resource-view handlers) catch
        this specifically and show a real error state instead.
        """
        try:
            with self._open_source() as path:
                return self._reader(path)
        except Exception as exc:
            log.exception("Error fetching %s from %s", self._format_name, self.get_source_path())
            raise DataSourceError(f"Could not read {self._format_name} data: {exc}") from exc

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
                        self._upload_storage = getattr(upload, "storage", None)

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
                for chunk in storage.stream(files.FileData(files.Location(location))):
                    tmp_file.write(chunk)
            yield tmp_path
        finally:
            with contextlib.suppress(FileNotFoundError):
                os.remove(tmp_path)


class CsvUrlDataSource(BaseResourceDataSource):
    _format_name = "CSV"
    _schema_read_errors = (OSError, ValueError, pd.errors.ParserError)

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

    def _reader(self, path: str, **kwargs: Any) -> pd.DataFrame:
        return self._read_csv(path, **kwargs)

    def _schema_reader(self, path: str) -> list[str]:
        return list(self._read_csv(path, nrows=0).columns)


class TsvUrlDataSource(CsvUrlDataSource):
    """Reads a tab-separated file.

    ``CsvUrlDataSource``'s delimiter sniffer already detects tabs from the
    file's content, so this only needs to override ``_format_name`` for
    accurate error messages/logging.
    """

    _format_name = "TSV"


class NdjsonUrlDataSource(BaseResourceDataSource):
    """Reads a newline-delimited JSON (NDJSON) file — one JSON object per line."""

    _format_name = "NDJSON"

    def _reader(self, path: str, **kwargs: Any) -> pd.DataFrame:
        return pd.read_json(path, lines=True, **kwargs)

    def _schema_reader(self, path: str) -> list[str]:
        return list(pd.read_json(path, lines=True, nrows=1).columns)


class XlsxUrlDataSource(BaseResourceDataSource):
    _format_name = "XLSX"

    def _reader(self, path: str, **kwargs: Any) -> pd.DataFrame:
        return pd.read_excel(path, **kwargs)

    def _schema_reader(self, path: str) -> list[str]:
        return list(pd.read_excel(path, nrows=0).columns)


class XlsUrlDataSource(XlsxUrlDataSource):
    """Reads a legacy Excel 97-2003 (``.xls``) workbook.

    ``pd.read_excel`` picks its engine (``xlrd`` here vs. ``openpyxl`` for
    ``.xlsx``) by sniffing the file's actual bytes, not its extension — our
    local paths are extensionless temp files anyway — so this only needs to
    override ``_format_name`` for accurate error messages/logging.
    """

    _format_name = "XLS"


class OdsUrlDataSource(XlsxUrlDataSource):
    """Reads the first sheet of an OpenDocument Spreadsheet (``.ods``).

    Like ``.xls``, ``pd.read_excel`` picks the right engine (``odf`` here) by
    sniffing the file's content, so this only needs to override
    ``_format_name``.
    """

    _format_name = "ODS"


class OrcUrlDataSource(BaseResourceDataSource):
    _format_name = "ORC"
    _schema_read_errors = (OSError, ValueError, pa.ArrowInvalid)

    def _reader(self, path: str, **kwargs: Any) -> pd.DataFrame:
        return pd.read_orc(path, **kwargs)

    def _schema_reader(self, path: str) -> list[str]:
        return orc.ORCFile(path).schema.names


class ParquetUrlDataSource(BaseResourceDataSource):
    _format_name = "Parquet"
    _schema_read_errors = (OSError, ValueError, pa.ArrowInvalid)

    def _reader(self, path: str, **kwargs: Any) -> pd.DataFrame:
        return pd.read_parquet(path, **kwargs)

    def _schema_reader(self, path: str) -> list[str]:
        return pq.read_schema(path).names


class FeatherUrlDataSource(BaseResourceDataSource):
    _format_name = "Feather"
    _schema_read_errors = (OSError, ValueError, pa.ArrowInvalid)

    def _reader(self, path: str, **kwargs: Any) -> pd.DataFrame:
        return pd.read_feather(path, **kwargs)

    def _schema_reader(self, path: str) -> list[str]:
        return feather.read_table(path, columns=[]).schema.names


class JsonLdUrlDataSource(BaseResourceDataSource):
    """Reads a JSON-LD document as a flat table.

    This is a shallow, non-semantic reader: no ``@context`` expansion, IRI
    compaction, or blank-node resolution — it just tabulates whichever array
    of node objects the document exposes, so ``@id``/``@type``/etc. show up
    as ordinary (underscore-flattened, for nested values) columns. That
    matches what "preview this resource" needs; anything requiring real
    JSON-LD semantics belongs in a dedicated linked-data library instead.

    The array of records is taken from, in order: the document's ``@graph``
    key (the common shape for a document describing several entities), or a
    single-item list wrapping the document if it's one bare object. A
    top-level JSON array is used as-is.
    """

    _format_name = "JSON-LD"
    _schema_read_errors = (OSError, ValueError, TypeError)

    # pandas' default "." would make a flattened field like "name.en" collide
    # with Tabulator's dot-path field syntax on the client (it'd look for a
    # nested `row.name.en` instead of the literal flat key) and render blank.
    _FLATTEN_SEP = "_"

    @staticmethod
    def _load_records(path: str) -> list[dict[str, Any]]:
        with open(path, encoding="utf-8") as f:
            data = json.load(f)

        if isinstance(data, dict):
            data = data.get("@graph", [data])

        if not isinstance(data, list):
            raise TypeError("A JSON-LD document must be an object, a @graph array, or a top-level array")

        return data

    def _reader(self, path: str, **kwargs: Any) -> pd.DataFrame:
        return pd.json_normalize(self._load_records(path), sep=self._FLATTEN_SEP)

    def _schema_reader(self, path: str) -> list[str]:
        records = self._load_records(path)
        return list(pd.json_normalize(records[:1], sep=self._FLATTEN_SEP).columns) if records else []


class DataStoreDataSource(BaseDataSource):
    """A data source that fetches records directly from the CKAN Datastore."""

    def __init__(self, resource_id: str):
        self.resource_id = resource_id

        self._filters: dict[str, Any] = {}
        self._q: dict[str, str] = {}
        self._sort: str | None = None
        self._limit: int | None = None
        self._offset: int | None = None

        self._datastore_enabled = p.plugin_loaded("datastore")

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


def _numeric_or_string_pair(row_value: Any, filter_value: Any) -> tuple[Any, Any]:
    """Compare two values numerically when both parse as numbers, else as strings."""
    if not isinstance(row_value, bool) and not isinstance(filter_value, bool):
        try:
            return float(row_value), float(filter_value)
        except (TypeError, ValueError):
            pass

    return str(row_value), str(filter_value)


def resource_cache_key(resource_id: str) -> str:
    """Return the cache key a resource's cached DataFrame is stored under.

    Shared with ``plugin.py``'s ``before_resource_update``/``before_resource_delete``
    hooks so cache invalidation always targets the same key ``get_cache_key()``
    below writes under, without hand-copying the ``"resource-"`` prefix.
    """
    return f"resource-{resource_id}"


def _quote_ident(name: str) -> str:
    """Quote *name* as a DuckDB identifier, escaping any embedded quote.

    Only ever called with a field name already validated against the table's
    known schema (see ``PandasDataSource._filter_arrow``/``_sort_arrow``) —
    this is defense in depth, not the actual injection guard.
    """
    return '"' + name.replace('"', '""') + '"'


def _get_arrow_from_cache(backend: CacheBackend, key: str) -> pa.Table | None:  # pyright: ignore[reportUnknownParameterType]
    """Return *key* from *backend* as a pyarrow Table, if the backend supports it.

    Only ``FeatherCacheBackend`` implements ``get_arrow`` (see ``cache.py``)
    — every other backend (Redis) has no such method, so this returns
    ``None`` for them via ``getattr``'s default rather than requiring
    ``CacheBackend`` itself to declare it.
    """
    get_arrow = getattr(backend, "get_arrow", None)
    return get_arrow(key) if get_arrow is not None else None


def _get_duckdb_connection() -> duckdb.DuckDBPyConnection:
    """Return a DuckDB connection reused for the lifetime of the current thread.

    ``duckdb.connect()`` itself costs several milliseconds (measured) — creating
    one per request would eat into exactly the per-request latency this
    pushdown path exists to cut. Each worker thread gets its own connection
    (mirroring how CKAN's own ``model.Session`` is thread-scoped and reused
    across requests), and every ``PandasDataSource`` registers its table under
    the same view name (``"t"``) on it — DuckDB's ``register()`` replaces an
    existing binding by name in place, so reusing one connection across many
    requests/tables never accumulates state.
    """
    con = getattr(_thread_local, "con", None)
    if con is None:
        con = duckdb.connect()
        _thread_local.con = con
    return con
