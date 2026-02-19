from __future__ import annotations

import contextlib
import decimal
import logging
from collections.abc import Callable
from datetime import datetime
from typing import Any

import numpy as np
import pandas as pd
from sqlalchemy import Boolean, DateTime, Integer
from sqlalchemy.engine import RowMapping
from sqlalchemy.sql import Select, func, select
from sqlalchemy.sql.elements import BinaryExpression, ClauseElement, ColumnElement
from typing_extensions import Self

import ckan.plugins.toolkit as tk
from ckan import model
from ckan.lib import uploader

from ckanext.tables.cache import CachedDataSourceMixin, PickleCacheBackend, RedisCacheBackend
from ckanext.tables.types import FilterItem

log = logging.getLogger(__name__)


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
        model: The model class to use for filtering and sorting, e.g. `model.User`
    """

    def __init__(self, stmt: Select):
        self.base_stmt = stmt
        self.stmt = stmt

    def filter(self, filters: list[FilterItem]) -> Self:
        self.stmt = self.base_stmt

        for filter_item in filters:
            col = getattr(self.stmt.selected_columns, filter_item.field)
            expr = self.build_filter(col, filter_item.operator, filter_item.value)

            if expr is not None:
                self.stmt = self.stmt.where(expr)

        return self

    def build_filter(self, column: ColumnElement, operator: str, value: str) -> BinaryExpression | ClauseElement | None:
        try:
            if isinstance(column.type, Boolean):
                casted_value = value.lower() in ("true", "1", "yes", "y")
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
            "like": lambda col, val: (col.ilike(f"%{val}%") if isinstance(val, str) else None),
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
        operators: dict[str, Callable[[str, str], bool]] = {
            "=": lambda a, b: a == b,
            "!=": lambda a, b: a != b,
            "<": lambda a, b: a < b,
            "<=": lambda a, b: a <= b,
            ">": lambda a, b: a > b,
            ">=": lambda a, b: a >= b,
            "like": lambda a, b: b.lower() in a.lower(),
        }

        if op_func := operators.get(operator):
            return lambda row: op_func(str(row.get(field, "")), str(value))

        return None

    def sort(self, sort_by: str | None, sort_order: str | None) -> Self:
        if not sort_by:
            return self

        self.filtered = sorted(
            self.filtered,
            key=lambda x: x.get(sort_by),
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

    def _ensure_loaded(self) -> None:
        """Load the dataframe, using the cache backend when available."""
        if self._df is not None:
            return

        # Use CachedDataSourceMixin if the subclass opted in
        if isinstance(self, CachedDataSourceMixin):
            cached = self.cache_backend.get(self.get_cache_key())
            if cached is not None:
                try:
                    self._df = pd.DataFrame(cached)
                except (ValueError, TypeError):
                    log.debug("Failed to restore DataFrame from cache", exc_info=True)

        if self._df is None:
            self._df = self.fetch_dataframe()

            if isinstance(self, CachedDataSourceMixin):
                try:
                    self.cache_backend.set(
                        self.get_cache_key(),
                        self._df.to_dict(orient="records"),
                        self.cache_ttl,
                    )
                except OSError:
                    log.warning("Failed to write DataFrame to cache", exc_info=True)

        self._filtered_df = self._df

    def filter(self, filters: list[FilterItem]) -> Self:  # noqa: C901
        self._ensure_loaded()
        self._filtered_df = self._df  # Reset filtering

        if self._filtered_df is None or self._filtered_df.empty:
            return self

        for filter_item in filters:
            if filter_item.field not in self._filtered_df.columns:
                continue

            try:
                series = self._filtered_df[filter_item.field]
                val = filter_item.value
                op = filter_item.operator

                # Attempt to convert types if possible, otherwise use string comparison.
                # Skip numeric cast for "like" — we need the raw string for str.contains().
                if op != "like" and pd.api.types.is_numeric_dtype(series):
                    with contextlib.suppress(ValueError):
                        val = float(val)

                if op == "=":
                    self._filtered_df = self._filtered_df[series == val]
                elif op == "!=":
                    self._filtered_df = self._filtered_df[series != val]
                elif op == "<":
                    self._filtered_df = self._filtered_df[series < val]
                elif op == "<=":
                    self._filtered_df = self._filtered_df[series <= val]
                elif op == ">":
                    self._filtered_df = self._filtered_df[series > val]
                elif op == ">=":
                    self._filtered_df = self._filtered_df[series >= val]
                elif op == "like":
                    # Cast series to str so LIKE works on numeric columns too.
                    # Use filter_item.value (the original string) to avoid float repr like "157.0".
                    self._filtered_df = self._filtered_df[
                        series.astype(str).str.contains(str(filter_item.value), case=False, na=False)
                    ]
            except (ValueError, TypeError):
                log.debug("Failed to apply filter %s", filter_item, exc_info=True)

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

    Uses :class:`~ckanext.tables.cache.PickleCacheBackend` by default so that
    the fetched DataFrame is cached on disk.

    Override ``cache_backend`` on a subclass to switch to a different backend,
    or set ``cache_ttl`` to change the expiry.

    Args:
        url: Direct URL to fetch data from.
        resource: The CKAN resource dictionary.
    """

    cache_backend: PickleCacheBackend = RedisCacheBackend()
    cache_ttl: int = 300

    def __init__(self, url: str | None = None, resource: dict[str, Any] | None = None):
        super().__init__()

        if not url and not resource:
            raise ValueError(  # noqa: TRY003
                "Either url or resource_id must be provided"
            )

        self.url = url
        self.resource = resource
        self._source_path: str = ""

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
                    return self._source_path

                if self.resource.get("url"):
                    self._source_path = self.resource["url"]
                    return self._source_path

            except (OSError, TypeError, tk.ValidationError, tk.ObjectNotFound):
                log.warning(
                    "Failed to resolve path for resource %s, falling back to provided url",
                    self.resource_id,  # noqa: TRY003
                    exc_info=True,
                )

        if self.url:
            self._source_path = self.url
            return self._source_path

        raise ValueError("Could not resolve source path")  # noqa: TRY003


class CsvUrlDataSource(BaseResourceDataSource):
    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            return pd.read_csv(self.get_source_path())
        except Exception:
            log.exception("Error fetching CSV from %s", self.get_source_path())
            return pd.DataFrame()


class XlsxUrlDataSource(BaseResourceDataSource):
    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            return pd.read_excel(self.get_source_path())
        except Exception:
            log.exception("Error fetching XLSX from %s", self.get_source_path())
            return pd.DataFrame()


class OrcUrlDataSource(BaseResourceDataSource):
    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            return pd.read_orc(self.get_source_path())
        except Exception:
            log.exception("Error fetching ORC from %s", self.get_source_path())
            return pd.DataFrame()


class ParquetUrlDataSource(BaseResourceDataSource):
    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            return pd.read_parquet(self.get_source_path())
        except Exception:
            log.exception("Error fetching Parquet from %s", self.get_source_path())
            return pd.DataFrame()


class FeatherUrlDataSource(BaseResourceDataSource):
    def fetch_dataframe(self) -> pd.DataFrame:
        try:
            return pd.read_feather(self.get_source_path())
        except Exception:
            log.exception("Error fetching Feather from %s", self.get_source_path())
            return pd.DataFrame()
