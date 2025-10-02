from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import TYPE_CHECKING, Any

from sqlalchemy import Boolean, DateTime, Integer
from sqlalchemy.sql import Select, func, select
from sqlalchemy.sql.elements import BinaryExpression, ClauseElement, ColumnElement
from typing_extensions import Self

from ckan import model

if TYPE_CHECKING:
    from ckanext.tables.table import FilterItem


class BaseDataSource:
    def filter(self, filters: list[FilterItem]) -> Self: ...
    def sort(self, sort_by: str | None, sort_order: str | None) -> Self: ...
    def paginate(self, page: int, size: int) -> Self: ...
    def all(self) -> list[dict[str, Any]]: ...
    def count(self) -> int: ...


class DatabaseDataSource(BaseDataSource):
    """A data source that uses a SQLAlchemy statement as the data source.

    Args:
        stmt: The SQLAlchemy statement to use as the data source
        model: The model class to use for filtering and sorting, e.g. `model.User`
    """

    def __init__(self, stmt: Select, model: type[Any]):
        self.base_stmt = stmt
        self.stmt = stmt
        self.model = model

    def filter(self, filters: list[FilterItem]) -> Self:
        self.stmt = self.base_stmt

        for filter_item in filters:
            col = getattr(self.model, filter_item.field)
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
        if not sort_by or not hasattr(self.model, sort_by):
            return self

        col = getattr(self.model, sort_by)

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

    def all(self):
        return [dict(row) for row in model.Session.execute(self.stmt).mappings().all()]

    def count(self):
        return model.Session.execute(select(func.count()).select_from(self.stmt.subquery())).scalar_one()


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
