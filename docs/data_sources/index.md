# Data Sources

Data sources provide the underlying data for table definitions. They handle filtering, sorting, and pagination operations while abstracting away the specific data storage mechanism.

**Each table definition must specify a data source to fetch its data from.**

## Available Data Sources

### Custom table definitions

Use these when you are building your own table view with a `TableDefinition`.

| Data Source | Description |
| ----------- | ----------- |
| [`DatabaseDataSource`](./database.md) | SQLAlchemy queries — the standard choice for production tables backed by the database. |
| [`ListDataSource`](./list.md) | In-memory list of dicts — ideal for small datasets, demos, and tests. |

### Resource preview (automatic)

These data sources are used automatically by the [Resource View](../resource_view.md) feature to preview uploaded or linked resources. You generally do not need to instantiate them directly.

| Data Source | Triggered by format | Description |
| ----------- | ------------------- | ----------- |
| [`CsvUrlDataSource`](./resource.md#csvurldatasource) | `csv` | Reads CSV files with auto-detected delimiter. |
| [`XlsxUrlDataSource`](./resource.md#xlsxurldatasource) | `xlsx` | Reads the first sheet of an Excel workbook. |
| [`OrcUrlDataSource`](./resource.md#orcurldatasource) | `orc` | Reads Apache ORC columnar files. |
| [`ParquetUrlDataSource`](./resource.md#parqueturldatasource) | `parquet` | Reads Apache Parquet columnar files. |
| [`FeatherUrlDataSource`](./resource.md#featherurldatasource) | `feather` | Reads Apache Arrow Feather files. |
| [`DataStoreDataSource`](./resource.md#datastoredatasource) | any (when `datastore_active`) | Queries the CKAN Datastore API directly — no caching. |
