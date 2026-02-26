# Resource View

The `tables` plugin implements CKAN's `IResourceView` interface, which means it can act as a **resource view** — a built-in CKAN mechanism that allows you to preview resource data directly on a dataset resource page, without writing any custom code.

Once the plugin is active, CKAN will automatically offer a *Tables View* option whenever a resource is in one of the supported formats.

## Supported Formats

The view is available for resources whose **Format** field (case-insensitive) is one of:

| Format    | Data Source                |
| --------- | -------------------------- |
| `csv`     | `CsvUrlDataSource`         |
| `xlsx`    | `XlsxUrlDataSource`        |
| `orc`     | `OrcUrlDataSource`         |
| `parquet` | `ParquetUrlDataSource`     |
| `feather` | `FeatherUrlDataSource`     |

If the resource has been pushed to the **CKAN Datastore** (i.e. its `datastore_active` flag is `True`), the `DataStoreDataSource` is used regardless of the format field, providing direct and efficient access to stored records without any caching overhead.

## Caching

For file-based data sources (CSV, XLSX, ORC, Parquet, Feather), fetched data is cached with a default TTL of **3600 seconds** (1 hour), configurable via `ckanext.tables.cache.ttl`. The cache backend is configurable:

| Config value | Backend |
| ------------ | ------- |
| `pickle` *(default)* | Disk-based pickle files |
| `redis` | CKAN's Redis connection |
| `parquet` | Disk-based parquet files |
| `feather` | Disk-based feather (Arrow IPC) files |

```ini
# Switch to Redis
ckanext.tables.cache.backend = redis

# Or keep pickle and customise the cache directory
ckanext.tables.cache.backend = pickle
ckanext.tables.cache.cache_dir = /var/cache/ckanext-tables
```

The Datastore-backed view does **not** use caching — it queries the Datastore API directly on every request.

## View Configuration

When a CKAN administrator creates a *Tables View* manually, an optional **File URL** field is available in the view configuration form. If filled in, the data is fetched from that URL instead of the resource's own URL. This is useful when:

- The resource URL points to an HTML download page rather than a direct file link.
- You want to preview data from a different but related file.

If the field is left blank, the resource URL is used as-is.

## Enabling the View

No additional setup is required beyond having the `tables` plugin enabled:

```ini
ckan.plugins = ... tables ...
```

Once active, the view is registered and will appear as *Tables* in the **Add View** dropdown on any resource whose format is supported.

!!! note
    If you want the view to be added **automatically** for matching resources during resource creation or update, set CKAN's `ckan.views.default_views` configuration option:

    ```ini
    ckan.views.default_views = tables_view
    ```
