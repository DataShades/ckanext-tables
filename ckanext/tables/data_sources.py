from __future__ import annotations

from collections.abc import Callable
from datetime import datetime
from typing import Any

from sqlalchemy import Boolean, DateTime, Integer
from sqlalchemy.sql import func, select
from sqlalchemy.sql.elements import BinaryExpression, ClauseElement, ColumnElement
from typing_extensions import Self

from ckan import model


class BaseDataSource:
    def filter(self, field: str | None, operator: str | None, value: str | None) -> Self: ...
    def sort(self, sort_by: str | None, sort_order: str | None) -> Self: ...
    def paginate(self, page: int, size: int) -> Self: ...
    def all(self) -> list[dict[str, Any]]: ...
    def count(self) -> int: ...


class DatabaseDataSource(BaseDataSource):
    """A data source that uses a SQLAlchemy statement as the data source.

    Args:
        stmt: The SQLAlchemy statement to use as the data source
        model: The SQLAlchemy model class to use for filtering and sorting

    Returns:
        A data source that uses a SQLAlchemy statement as the data source
    """

    def __init__(self, stmt: Any, model: type[Any]):
        self.base_stmt = stmt
        self.stmt = stmt
        self.model = model

    def filter(self, field: str | None, operator: str | None, value: str | None) -> Self:
        if field and hasattr(self.model, field) and value and operator:
            col = getattr(self.model, field)
            expr = self.build_filter(col, operator, value)

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
        return model.Session.execute(select(func.count()).select_from(self.base_stmt.subquery())).scalar_one()


class ListDataSource(BaseDataSource):
    """A data source that uses a list of dictionaries as the data source.

    This is useful for testing and demo purposes, when you already have data
    on your hand.

    Args:
        data: The list of dictionaries to use as the data source

    Returns:
        A data source that uses a list of dictionaries as the data source
    """

    def __init__(self, data: list[dict[str, Any]]):
        self.data = data
        self.filtered = data

    def filter(self, field: str | None, operator: str | None, value: str | None) -> Self:
        if field and operator and value:
            pred = self.build_filter(field, operator, value)
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

        op_func = operators.get(operator)
        if not op_func:
            return None

        return lambda row: op_func(str(row.get(field, "")), str(value))

    def sort(self, sort_by: str | None, sort_order: str | None) -> Self:
        if sort_by:
            reverse = (sort_order or "").lower() == "desc"
            self.filtered = sorted(self.filtered, key=lambda x: x.get(sort_by), reverse=reverse)
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
        return len(self.data)
