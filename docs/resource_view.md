# Resource View

The `tables` plugin implements CKAN's `IResourceView` interface, which means it can act as a **resource view** — a built-in CKAN mechanism that allows you to preview resource data directly on a dataset resource page, without writing any custom code.

Once the plugin is active, CKAN will automatically offer a *Tables View* option whenever a resource is in one of the supported formats.

## Supported Formats

The view is available for resources whose **Format** field (case-insensitive) is one of:

| Format    | Data Source                |
| --------- | -------------------------- |
| `csv`     | `CsvUrlDataSource`         |
| `tsv`     | `TsvUrlDataSource`         |
| `xlsx`    | `XlsxUrlDataSource`        |
| `xls`     | `XlsUrlDataSource`         |
| `ods`     | `OdsUrlDataSource`         |
| `orc`     | `OrcUrlDataSource`         |
| `parquet` | `ParquetUrlDataSource`     |
| `feather` | `FeatherUrlDataSource`     |
| `jsonld` / `json-ld` | `JsonLdUrlDataSource` |
| `ndjson` / `jsonl` | `NdjsonUrlDataSource` |

If the resource has been pushed to the **CKAN Datastore** (i.e. its `datastore_active` flag is `True`), the `DataStoreDataSource` is used regardless of the format field, providing direct and efficient access to stored records without any caching overhead.

## Multi-sheet workbooks

Spreadsheet formats (`xlsx`, `xls`, `ods`) can hold more than one sheet. The view shows one at a
time and, when a workbook has several, renders a sheet selector next to the **Export** button.
Picking a sheet swaps the table in place  and updates the address bar to
a `sheet=<index>` query parameter — a zero-based position in the workbook — so the chosen sheet can
still be linked to and bookmarked:

```
/dataset/<dataset>/resource/<resource-id>?sheet=1
```

Each sheet is a table of its own: its own columns, its own row count, its own cache entry, and its
own filters, page and hidden columns in the URL. Switching sheets therefore never carries a filter
over to a sheet that has no such column. An index that the workbook has no sheet for (an old link
to a sheet a re-upload has since removed, say) falls back to the first sheet.

Sheet names are read from the file itself and cached alongside the data, so listing them costs one
read per cache TTL rather than one per request.

## Caching

For file-based data sources (CSV, TSV, XLSX, XLS, ODS, ORC, Parquet, Feather, JSON-LD, NDJSON), fetched data is cached to disk as Arrow IPC (Feather) files, with a default TTL of **3600 seconds** (1 hour). Both are configurable:

```ini
ckanext.tables.cache.ttl = 3600
ckanext.tables.cache.cache_dir = /var/cache/ckanext-tables
```

Row counts and cache invalidation are handled separately and always go through CKAN's Redis connection — a file cache is local to one worker/machine and can't otherwise make an invalidation visible everywhere.

The Datastore-backed view does **not** use caching — it queries the Datastore API directly on every request.

An expired entry is deleted the next time it's read, but one that's never read again after expiring (a removed or renamed resource, for example) would otherwise stay on disk indefinitely. Run the following periodically (e.g. from a cron job) to sweep away anything past its TTL:

```sh
ckan -c /etc/ckan/default/ckan.ini tables clean-cache
```

The row-count/generation entries in Redis already expire and remove themselves via their own TTL, so there's nothing to sweep there.

The **Refresh** button in the table's UI invalidates the cached data for that table, so the next load re-fetches and re-parses the file from its source URL. For a multi-sheet workbook it invalidates every sheet at once, not only the one on screen — they all come from the same file.

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
