# Changelog

All notable changes to this project will be documented in this file.

## [2.1.0] - 2026-09-22

### 🚀 Features

- Implement multi sheet xls, xlsx, ods support

## [2.0.1] - 2026-09-17

### 🐛 Bug Fixes

- Fix DialogModalFormatter styles, add JsonStringFormatter

## [2.0.0] - 2026-09-16

### 🚀 Features

- Allow multiple talbe instances on the same page
- Update demo tables
- Add front-end ts tests
- Add packages demo table
- Implement xls support
- Implement tsv and ods support
- Implement jsonld and jsonl support
- Improve exporting ux
- Background export for sync formats

### 🐛 Bug Fixes

- Fix potential ssrf
- Guard remote resource/file_url fetches against SSRF, hangs and unbounded downloads
- Escape formatter output and restrict URLFormatter to http(s) to prevent stored XSS
- Refuse to use an unsafe or shared cache directory instead of falling back to it
- Bound page size, export row count, and require edit rights to refresh cached table data
- Check both resource_id and resource_view_id are belongs to each other
- Scope tables-deferred-loader.js's htmx listeners to its own element and add teardown
- Duplicated request dispatch between ResourceViewHandler and GenericTableView
- Catch ArrowTypeError on cache write to prevent permanent 500s
- Key count cache on filters only, not page/size/sort
- Make file-cache writes atomic and self-expiring instead of relying on OS mtime
- Add ResizeObserver to tabulator bundle to fix resize
- Make refresh_data() and resource-controller hooks actually invalidate the cached DataFrame and its counts
- Fall back to url when resolving an uploaded resource's path raises
- Stop leaking exception text to the client and render toast/confirm messages as text
- Validate malformed/edge-case request params
- Compare ListDataSource ordering filters numerically instead of lexicographically, and make sort() null/mixed-type safe
- Fix ckan 2.12 file upload compatibility
- Return 501 for an exporter with a missing optional dependency
- Pyright fixes, setup pyright for ci and pre-commit
- Stop mutating shared columns list and action attrs on table render
- Move guess_data_source/init_preview_table out of template helpers into utils
- Add demo dependencies
- Format guess ignores
- G.plugins usage switch to plugin_loaded
- Use server Content-Disposition filename for table exports instead of a hardcoded client-side name
- Cast filter values by column python_type and support LIKE on non-string columns
- Fix table action error responses to use a single error string field instead of mismatched errors shapes
- Fix toast aria-label, fix toast/confirm fallback to og versions
- Document intended GET/POST status codes, normalize DatabaseDataSource value serialization to match PandasDataSource
- Fix pyright issues for 2.11
- Restore backdrop for modals
- Accessibility, bulk-action, label, and pagination fixes
- Guard cache-miss fetch with a per-key lock to prevent stampedes

### 🚜 Refactor

- Remove dead code
- [**breaking**] Drop the pickle cache backend
- [**breaking**] Drop the parquet cache backend
- Dedupe URL data sources, add DataSourceError, self-heal corrupted cache entries

### 📚 Documentation

- Update documentation

### ⚡ Performance

- Avoid re-reading and re-copying an unchanged cached table on every request
- Sniff the CSV delimiter instead of parsing with the slow python engine
- Delete expired cache entries on read and add a cache-cleanup CLI command
- Shallow-copy rows once and memoise per-render formatter lookups
- Fix bundle size, multiple asset optimization
- Memoise RedisCacheBackend reads via a version-key check to skip payload re-fetch/decode
- Stream CSV/TSV/NDJSON exports instead of double-buffering the full output
- Push filter/sort/paginate/count down to DuckDB for feather/parquet-cached tables
- Cache the column list across resource-preview requests

### 🧪 Testing

- Increase test coverage
- HTTP-level test coverage, stronger assertions, CI build/frontend checks

### ⚙️ Miscellaneous Tasks

- Drop CKAN 2.10 from the test matrix and align the docs' compatibility table

## [1.22.0] - 2026-09-11

### 🚀 Features

- Allow table and bulk action without confirmation

## [1.21.8] - 2026-09-07

### 🐛 Bug Fixes

- Ruff fixes
- Fix tests for 2.11 and 2.10

### ⚙️ Miscellaneous Tasks

- Upgrade version to 1.21.8

## [1.21.7] - 2026-09-07

### 🐛 Bug Fixes

- Fix tests

## [1.21.6] - 2026-06-11

### 🐛 Bug Fixes

- Include svg in manifest

## [1.21.5] - 2026-04-21

### 🐛 Bug Fixes

- Fix table columns display if title is missing

## [1.21.4] - 2026-04-06

### 🐛 Bug Fixes

- Fix cache invalidation, fix caching empty or broken df

## [1.21.3] - 2026-03-02

### 🐛 Bug Fixes

- Fix tables-deferred-loader.js init

## [1.21.2] - 2026-03-02

### 🐛 Bug Fixes

- Do not use DataStoreDataSource data source if datastore isn't enabled

## [1.21.1] - 2026-03-02

### 🐛 Bug Fixes

- Reduce extra template complexity

## [1.21.0] - 2026-03-02

### 🚀 Features

- Add table_layout arg for TableDefinition, use fitDataStretch for autogenerated tables

## [1.20.1] - 2026-02-26

### 🐛 Bug Fixes

- Fix cache dataframe performancce

## [1.20.0] - 2026-02-26

### 🚀 Features

- Add feather and parquet cache backends

## [1.19.0] - 2026-02-26

### 🚀 Features

- Implement fast column fetching for resource data sources

## [1.18.1] - 2026-02-26

### 🐛 Bug Fixes

- Fix total rows number cache

## [1.18.0] - 2026-02-26

### 🚀 Features

- Lazy load for a table with htmx

## [1.17.6] - 2026-02-26

### 🐛 Bug Fixes

- Fix resource view file_url usage

## [1.17.5] - 2026-02-26

### 📚 Documentation

- Describe resource view usage

## [1.17.4] - 2026-02-25

### 🐛 Bug Fixes

- Fix DataStoreDataSource like search

## [1.17.3] - 2026-02-25

### 🐛 Bug Fixes

- Fix tests, fix test workflow
- Fix tests, remove requirements.txt usage
- Disable pointer events for active page

### 📚 Documentation

- Fix coverage badge, replace table image with a modern one
- Fix coverage badge, part 2

### 🧪 Testing

- Improve test coverage
- Add coverage badge

## [1.17.1] - 2026-02-24

### 🐛 Bug Fixes

- Fix the columns overflow, fix datastore source error if the datastore isn't enabled

## [1.17.0] - 2026-02-23

### 🚀 Features

- Add DataStoreDataSource data source

## [1.16.4] - 2026-02-20

### 🐛 Bug Fixes

- Minor style fixes for table header, remove unused demo.html

## [1.16.3] - 2026-02-20

### 🐛 Bug Fixes

- Fix CsvUrlDataSource separator detection
- Minor style fixes for table header

## [1.16.1] - 2026-02-20

### 🚀 Features

- Add attrs for table actions

### 🐛 Bug Fixes

- Minor style fixes

## [1.15.1] - 2026-02-20

### 🐛 Bug Fixes

- Fix pyproject.toml syntax

### ⚙️ Miscellaneous Tasks

- Update version

## [1.15.0] - 2026-02-20

### 🚀 Features

- UX/IX improvement, restyling

## [1.14.0] - 2026-02-19

### 🚀 Features

- Rework cache system, part 2

## [1.13.0] - 2026-02-19

### 🚀 Features

- Rework cache system, part 1
- Add table column filter

## [1.12.0] - 2026-02-18

### 🚀 Features

- Add table total count feature

## [1.11.0] - 2026-02-17

### 🚀 Features

- Implement table_view for tabular resources
- Implement table_view for tabular resources, add column hide feature
- Implement table_view for tabular resources, add various data sources
- Implement table_view for tabular resources, use resource dict in data store init
- Implement table_view for tabular resources; bug fixes

## [1.10.1] - 2026-01-22

### 🐛 Bug Fixes

- Fix skeleton loader styles

## [1.10.0] - 2025-11-18

### 🚀 Features

- Add pdf exporter

## [1.9.1] - 2025-11-18

### 🐛 Bug Fixes

- Disable refresh button to prevent extra requests

## [1.9.0] - 2025-11-18

### 🚀 Features

- Add cache mechanism for tables and refresh button

## [1.8.0] - 2025-11-17

### 🚜 Refactor

- Rework DatabaseDataSource, do not require model arg

### 📚 Documentation

- Update readme, add result image
- Update readme, disable test badge for now

## [1.7.0] - 2025-11-13

### 🚀 Features

- Replace BulkActionHandlerResult with ActionHandlerResult to unify the architecture

### 🐛 Bug Fixes

- Fix exporters headers fetching to exclude actions

### 🚜 Refactor

- Replace btn-default with btn-light class
- Add serialize_row method to database data source

### 📚 Documentation

- Update documentation
- Update documentation, update mkdocs.yml

## [1.6.0] - 2025-11-10

### 🚀 Features

- Add URLFormatter

### ⚙️ Miscellaneous Tasks

- Update changelog [skip changelog]

## [1.5.1] - 2025-11-04

### 🐛 Bug Fixes

- Fix check_access, remove unused table register

## [1.5.0] - 2025-11-04

### 🚀 Features

- Add tables_demo sub plugin for dev and test purposes

## [1.4.0] - 2025-11-04

### 🚀 Features

- Move ajax request and export views to generic

## [1.3.2] - 2025-11-03

### ⚙️ Miscellaneous Tasks

- Refactor tables-tabulator to keep it dry

## [1.3.1] - 2025-11-03

### ⚙️ Miscellaneous Tasks

- Rewrite tables-tabulator script with typescript

## [1.3.0] - 2025-11-03

### 🚀 Features

- Add exporters system, finish

## [1.2.0] - 2025-10-21

### 🚀 Features

- Add redirect support for table action, change actions signatures

## [1.1.1] - 2025-10-21

### 🐛 Bug Fixes

- Fix breadcrumb link

## [1.1.0] - 2025-10-21

### 🚀 Features

- Rework filters and actions, part 1
- Rework filters and actions, part 2
- Rework filters and actions, part 3
- Add initial_row to formatters

## [0.4.0] - 2025-09-30

### 🚀 Features

- Add DialogModalFormatter formatter

### 💼 Other

- Update changelog [no ci]

## [0.3.1] - 2025-09-25

### 🚀 Features

- Use dataclasses, rework formatters system, bug fixes

### 🐛 Bug Fixes

- Fix data sources count mechanism, update type hints, update doc

### 💼 Other

- Update changelog [no ci]

## [0.1.0] - 2025-09-23

### 🚀 Features

- Add skeleton on load, fix styles, fix bugs

<!-- generated by git-cliff -->
