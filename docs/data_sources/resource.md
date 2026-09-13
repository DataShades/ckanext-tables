# Resource Data Sources

Resource data sources load tabular data from CKAN resources. They are used automatically by the [Resource View](../resource_view.md) feature but can also be instantiated manually when you need to build a table backed by a resource file or the Datastore.

All file-based sources extend `BaseResourceDataSource`, which handles source path resolution (local upload vs. remote URL) and pluggable caching. The CKAN Datastore source (`DataStoreDataSource`) is separate and queries the Datastore API directly without any caching.

---

## File-based sources

### CsvUrlDataSource

Reads a CSV file from a local path or remote URL. The delimiter is detected automatically.

```python
from ckanext.tables.shared import CsvUrlDataSource

# From a direct URL
source = CsvUrlDataSource(url="https://example.com/data.csv")

# From a CKAN resource dict (resolves upload path automatically)
source = CsvUrlDataSource(resource=resource_dict)
```

::: tables.data_sources.CsvUrlDataSource
    options:
      show_source: true
      show_bases: false

---

### TsvUrlDataSource

Reads a tab-separated file. Reuses `CsvUrlDataSource`'s delimiter sniffer, which already detects tabs from the file's content.

```python
from ckanext.tables.shared import TsvUrlDataSource

source = TsvUrlDataSource(url="https://example.com/data.tsv")
```

::: tables.data_sources.TsvUrlDataSource
    options:
      show_source: true
      show_bases: false

---

### XlsxUrlDataSource

Reads the first sheet of an Excel workbook (`.xlsx`).

```python
from ckanext.tables.shared import XlsxUrlDataSource

source = XlsxUrlDataSource(url="https://example.com/report.xlsx")
```

::: tables.data_sources.XlsxUrlDataSource
    options:
      show_source: true
      show_bases: false

---

### XlsUrlDataSource

Reads the first sheet of a legacy Excel 97-2003 workbook (`.xls`).

```python
from ckanext.tables.shared import XlsUrlDataSource

source = XlsUrlDataSource(url="https://example.com/legacy-report.xls")
```

::: tables.data_sources.XlsUrlDataSource
    options:
      show_source: true
      show_bases: false

---

### OdsUrlDataSource

Reads the first sheet of an OpenDocument Spreadsheet (`.ods`).

```python
from ckanext.tables.shared import OdsUrlDataSource

source = OdsUrlDataSource(url="https://example.com/report.ods")
```

::: tables.data_sources.OdsUrlDataSource
    options:
      show_source: true
      show_bases: false

---

### OrcUrlDataSource

Reads an Apache ORC columnar file.

```python
from ckanext.tables.shared import OrcUrlDataSource

source = OrcUrlDataSource(url="https://example.com/data.orc")
```

::: tables.data_sources.OrcUrlDataSource
    options:
      show_source: true
      show_bases: false

---

### ParquetUrlDataSource

Reads an Apache Parquet columnar file.

```python
from ckanext.tables.shared import ParquetUrlDataSource

source = ParquetUrlDataSource(url="https://example.com/data.parquet")
```

::: tables.data_sources.ParquetUrlDataSource
    options:
      show_source: true
      show_bases: false

---

### FeatherUrlDataSource

Reads an Apache Arrow Feather file.

```python
from ckanext.tables.shared import FeatherUrlDataSource

source = FeatherUrlDataSource(url="https://example.com/data.feather")
```

::: tables.data_sources.FeatherUrlDataSource
    options:
      show_source: true
      show_bases: false

---

## Caching

All file-based sources inherit from `BaseResourceDataSource`, which caches the fetched DataFrame (as Feather, on disk) to avoid re-downloading on every request. The cache directory and TTL are controlled globally via configuration (see [Configuration](../config.md)):

```ini
ckanext.tables.cache.cache_dir = /var/cache/ckanext-tables
ckanext.tables.cache.ttl = 3600
```

Row counts and cache invalidation always go through CKAN's Redis connection directly — see [Caching](../resource_view.md#caching) for why.

You can override the backend or TTL per instance:

```python
from ckanext.tables.shared import CsvUrlDataSource, RedisCacheBackend

source = CsvUrlDataSource(
    url="https://example.com/data.csv",
    cache_backend=RedisCacheBackend(),
    cache_ttl=120,  # seconds
)
```

::: tables.data_sources.BaseResourceDataSource
    options:
      show_source: true
      show_bases: false

---

## DataStoreDataSource

Queries the CKAN Datastore API directly. This source is used automatically when a resource has `datastore_active = True`. It does **not** use any caching, as the data is already stored in the database.

```python
from ckanext.tables.shared import DataStoreDataSource

source = DataStoreDataSource(resource_id="<resource-id>")
```

Filtering, sorting, and pagination are translated into `datastore_search` parameters:

- `=` → exact match filter
- `like` → full-text search (partial word match via PostgreSQL FTS with `:*`)
- Other comparison operators are not supported by `datastore_search` and are silently ignored.

!!! note
    `DataStoreDataSource` requires the `datastore` plugin to be enabled in CKAN. If it is not active, all methods return empty results gracefully.

::: tables.data_sources.DataStoreDataSource
    options:
      show_source: true
      show_bases: false
