import pytest

from ckanext.datastore.tests.conftest import clean_datastore  # noqa: F401

from ckanext.tables import config
from ckanext.tables.data_sources import ListDataSource
from ckanext.tables.table import ColumnDefinition, TableDefinition


@pytest.fixture
def clear_cache(tmp_path, monkeypatch):
    """Point the default (config-driven) cache dir at an isolated tmp_path."""
    monkeypatch.setitem(config.tk.config, config.CONF_CACHE_DIR, str(tmp_path))

    return str(tmp_path)


@pytest.fixture
def simple_data() -> list[dict]:
    """Three rows of name/age/score data, usable by any test module."""
    return [
        {"name": "Alice", "age": 30, "score": 95},
        {"name": "Bob", "age": 25, "score": 80},
        {"name": "Charlie", "age": 35, "score": 70},
    ]


@pytest.fixture
def simple_table(simple_data: list[dict]) -> TableDefinition:
    """A plain three-column TableDefinition over simple_data."""
    return TableDefinition(
        name="test_table",
        data_source=ListDataSource(simple_data),
        columns=[
            ColumnDefinition(field="name"),
            ColumnDefinition(field="age"),
            ColumnDefinition(field="score"),
        ],
    )
