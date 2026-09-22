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

### NdjsonUrlDataSource

Reads a newline-delimited JSON file (`.ndjson`/`.jsonl`) — one JSON object per line.

```python
from ckanext.tables.shared import NdjsonUrlDataSource

source = NdjsonUrlDataSource(url="https://example.com/data.ndjson")
```

::: tables.data_sources.NdjsonUrlDataSource
    options:
      show_source: true
      show_bases: false

---

### XlsxUrlDataSource

Reads one sheet of an Excel workbook (`.xlsx`) — the first one unless `sheet_index` says otherwise.

```python
from ckanext.tables.shared import XlsxUrlDataSource

source = XlsxUrlDataSource(url="https://example.com/report.xlsx")

# A different sheet, by its zero-based position in the workbook
source = XlsxUrlDataSource(url="https://example.com/report.xlsx", sheet_index=1)

# What the workbook actually offers, in file order
source.get_sheet_names()  # ["Summary", "Raw data"]
```

Every sheet is cached under its own key, since each has its own columns and row count. Invalidating
the resource (a re-upload, or the table's **Refresh** button) invalidates all of them together.

`get_sheet_names()` is defined on every data source — it returns an empty list for the formats that
have no sheets — so a caller can offer a sheet selector without checking the source's type first.

::: tables.data_sources.XlsxUrlDataSource
    options:
      show_source: true
      show_bases: false

---

### XlsUrlDataSource

Reads one sheet of a legacy Excel 97-2003 workbook (`.xls`), with the same `sheet_index`/`get_sheet_names()` support as `XlsxUrlDataSource`.

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

Reads one sheet of an OpenDocument Spreadsheet (`.ods`), with the same `sheet_index`/`get_sheet_names()` support as `XlsxUrlDataSource`.

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

### JsonLdUrlDataSource

Tabulates a JSON-LD document (`.jsonld`). This is a shallow, non-semantic reader: no `@context` expansion, IRI compaction, or blank-node resolution — it just reads whichever array of node objects the document exposes (its `@graph` array, itself if it's already an array, or a single bare object treated as one row), with nested values flattened into underscore-joined column names (e.g. `name_@value` — not dot-joined, which would collide with Tabulator's dot-path field syntax on the client). Triggered by the format `jsonld` or `json-ld`.

```python
from ckanext.tables.shared import JsonLdUrlDataSource

source = JsonLdUrlDataSource(url="https://example.com/data.jsonld")
```

::: tables.data_sources.JsonLdUrlDataSource
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
