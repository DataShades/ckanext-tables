import os
from unittest import mock

import pandas as pd
import pytest

from ckanext.tables.data_sources import CsvUrlDataSource


@pytest.mark.usefixtures("clear_cache")
class TestCsvUrlDataSource:
    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_fetch_and_parse(self, mock_read_csv):
        mock_read_csv.return_value = pd.DataFrame(
            [
                {"id": "1", "name": "Alice", "age": "30"},
                {"id": "2", "name": "Bob", "age": "25"},
            ]
        )

        ds = CsvUrlDataSource("http://example.com/data.csv")
        data = ds.filter([]).all()

        assert len(data) == 2
        assert data[0]["name"] == "Alice"
        assert data[0]["id"] == "1"
        assert data[0]["age"] == "30"

    @mock.patch("ckanext.tables.data_sources.pd.read_csv")
    def test_caching(self, mock_read_csv):
        url = "http://example.com/cached_data.csv"
        ds = CsvUrlDataSource(url)

        mock_read_csv.return_value = pd.DataFrame([{"id": "1", "name": "Alice", "age": "30"}])

        # First fetch should create cache
        ds.filter([]).all()

        cache_file_path = ds._get_cache_path()
        assert os.path.exists(cache_file_path)
        cached_df = pd.read_pickle(cache_file_path)
        assert len(cached_df) == 1
        assert cached_df.iloc[0]["name"] == "Alice"

        modified_df = pd.DataFrame([{"id": "99", "name": "Hacker", "age": "99"}])
        modified_df.to_pickle(cache_file_path)

        ds2 = CsvUrlDataSource(url)
        data = ds2.filter([]).all()
        assert len(data) == 1
        assert data[0]["name"] == "Hacker"
