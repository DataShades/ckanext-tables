from __future__ import annotations

import json

from ckan.lib.redis import connect_to_redis
from ckan.plugins import toolkit as tk

from ckanext.tables.types import FilterItem, QueryParams

REDIS_CACHE_DEFAULT_TTL = 300  # 5 minutes


def tables_build_params() -> QueryParams:
    filters = json.loads(tk.request.args.get("filters", "[]"))

    return QueryParams(
        page=tk.request.args.get("page", 1, int),
        size=tk.request.args.get("size", 10, int),
        filters=[FilterItem(f["field"], f["operator"], f["value"]) for f in filters],
        sort_by=tk.request.args.get("sort[0][field]"),
        sort_order=tk.request.args.get("sort[0][dir]"),
    )


class CacheManager:
    """Cache manager for table data."""

    _PREFIX = "ckanext:tables:table:"

    def __init__(self, cache_ttl: int = REDIS_CACHE_DEFAULT_TTL) -> None:
        self.cache_ttl = cache_ttl

    def _key(self, table_name: str) -> str:
        return f"{self._PREFIX}{table_name}"

    def save(self, table_name: str, data: dict[str, str | int]) -> None:
        """Save an archive structure to Redis."""
        with connect_to_redis() as conn:
            conn.setex(self._key(table_name), self.cache_ttl, json.dumps(data))

    def get(self, table_name: str) -> dict[str, str | int]:
        """Retrieve a table data from Redis."""
        with connect_to_redis() as conn:
            data: bytes = conn.get(self._key(table_name))  # type: ignore

        if not data:
            return {}

        return json.loads(data)

    def delete(self, table_name: str) -> None:
        """Delete a table data from Redis."""
        with connect_to_redis() as conn:
            conn.delete(self._key(table_name))  # type: ignore
