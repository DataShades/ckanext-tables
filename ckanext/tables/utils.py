import json
import re

from ckan.lib.redis import connect_to_redis
from ckan.plugins import toolkit as tk

from ckanext.tables.types import FilterItem, QueryParams

REDIS_CACHE_DEFAULT_TTL = 300  # 5 minutes
FILTER_RE = re.compile(r"^filter\[(\d+)\]\[(\w+)\]$")


def tables_build_params() -> QueryParams:
    filters = json.loads(tk.request.args.get("filters", "[]"))

    all_filters = [FilterItem(f["field"], f["operator"], f["value"]) for f in filters]
    all_filters.extend(parse_tabulator_filters())

    return QueryParams(
        page=tk.request.args.get("page", 1, int),
        size=tk.request.args.get("size", 10, int),
        filters=all_filters,
        sort_by=tk.request.args.get("sort[0][field]"),
        sort_order=tk.request.args.get("sort[0][dir]"),
    )


def parse_tabulator_filters() -> list[dict[str, str]]:
    """Parse Tabulator's remote filter params.

    They come from column native tabulator column filters.

    E.g. filter[N][field], filter[N][type], filter[N][value].
    """
    filters = {}

    for key, value in tk.request.args.items():
        match = FILTER_RE.match(key)
        if not match:
            continue

        index, subkey = match.groups()
        index = int(index)

        if index not in filters:
            filters[index] = {}

        filters[index][subkey] = value

    return [
        FilterItem(f["field"], f["type"], f["value"])
        for f in filters.values()
        if f.get("field") and f.get("value") and f.get("type")
    ]


class CacheManager:
    """Cache manager for table data."""

    _PREFIX = "ckanext:tables:table:"

    def __init__(self, cache_ttl: int = REDIS_CACHE_DEFAULT_TTL) -> None:
        self.cache_ttl = cache_ttl

    def _key(self, table_name: str) -> str:
        return f"{self._PREFIX}{table_name}"

    def save(self, table_name: str, data: dict[str, str | int]) -> None:
        """Save table data to Redis."""
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
