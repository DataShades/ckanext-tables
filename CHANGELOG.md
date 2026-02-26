# Changelog

All notable changes to this project will be documented in this file.

## [1.17.4] - 2026-02-25

### 🐛 Bug Fixes

- Fixed `like` search support in `DataStoreDataSource`

## [1.17.3] - 2026-02-25

### 🐛 Bug Fixes

- Disabled pointer events on the active pagination page to prevent double-navigation
- Fixed test suite and CI workflow configuration
- Dropped legacy `requirements.txt` usage in favour of `pyproject.toml`

### 📚 Documentation

- Replaced the outdated table screenshot with a modern one
- Fixed the coverage badge URL

### 🧪 Testing

- Added coverage badge to the README
- Expanded test coverage across multiple modules

## [1.17.1] - 2026-02-24

### 🐛 Bug Fixes

- Fixed column overflow rendering
- Gracefully handle the case where the DataStore plugin is not enabled

## [1.17.0] - 2026-02-23

### 🚀 Features

- Added `DataStoreDataSource` — tables backed by CKAN DataStore resources no longer require local caching and query the datastore directly

## [1.16.4] - 2026-02-20

### 🐛 Bug Fixes

- Minor table header style polish; removed unused `demo.html`

## [1.16.3] - 2026-02-20

### 🐛 Bug Fixes

- Fixed automatic separator detection in `CsvUrlDataSource`
- Minor table header style fixes

## [1.16.1] - 2026-02-20

### 🚀 Features

- Table action elements now accept arbitrary HTML attributes via the `attrs` parameter

### 🐛 Bug Fixes

- Minor style fixes

## [1.15.1] - 2026-02-20

### 🐛 Bug Fixes

- Fixed a syntax error in `pyproject.toml`

## [1.15.0] - 2026-02-20

### 🚀 Features

- Significant UX and visual rework: improved layout, typography, and interactive styling throughout the table view

## [1.14.0] - 2026-02-19

### 🚀 Features

- Reworked the cache system to support configurable cache directories and safer temporary file handling (part 2 of 2)

## [1.13.0] - 2026-02-19

### 🚀 Features

- Reworked the cache system with a cleaner internal API (part 1 of 2)
- Added per-column header filters to the table view

## [1.12.0] - 2026-02-18

### 🚀 Features

- Added a total row count indicator to the table footer

## [1.11.0] - 2026-02-17

### 🚀 Features

- Introduced `table_view` — a first-class CKAN resource view for tabular data, with support for:
  - Multiple pluggable data sources (CSV, URL, DataStore, Database)
  - Column visibility toggling
  - Resource dict integration for DataStore initialization

## [1.10.1] - 2026-01-22

### 🐛 Bug Fixes

- Fixed skeleton loader animation styles

## [1.10.0] - 2025-11-18

### 🚀 Features

- Added PDF export support

## [1.9.1] - 2025-11-18

### 🐛 Bug Fixes

- Disabled the refresh button while a request is in-flight to prevent duplicate fetches

## [1.9.0] - 2025-11-18

### 🚀 Features

- Added a client-side caching layer for table data with a manual refresh button

## [1.8.0] - 2025-11-17

### 🚜 Refactor

- Simplified `DatabaseDataSource` — the `model` argument is no longer required at construction time

### 📚 Documentation

- Updated README with a result screenshot and current badges

## [1.7.0] - 2025-11-13

### 🚀 Features

- Unified bulk and single-item action results under a single `ActionHandlerResult` type

### 🐛 Bug Fixes

- Fixed exporter header extraction to correctly exclude action columns

### 🚜 Refactor

- Replaced deprecated `btn-default` CSS class with `btn-light`
- Extracted `serialize_row` into `DatabaseDataSource` for reuse

### 📚 Documentation

- Updated MkDocs configuration and API documentation pages

## [1.6.0] - 2025-11-10

### 🚀 Features

- Added `URLFormatter` for rendering cell values as hyperlinks

## [1.5.1] - 2025-11-04

### 🐛 Bug Fixes

- Fixed `check_access` integration; removed the unused table registry

## [1.5.0] - 2025-11-04

### 🚀 Features

- Added `tables_demo` sub-plugin for local development and manual testing

## [1.4.0] - 2025-11-04

### 🚀 Features

- Moved AJAX request handling and export views into the shared generic layer

## [1.3.2] - 2025-11-03

### ⚙️ Miscellaneous Tasks

- Refactored the `tables-tabulator` script to eliminate duplication (DRY)

## [1.3.1] - 2025-11-03

### ⚙️ Miscellaneous Tasks

- Rewrote the `tables-tabulator` frontend script in TypeScript

## [1.3.0] - 2025-11-03

### 🚀 Features

- Completed the exporters system with support for pluggable export formats

## [1.2.0] - 2025-10-21

### 🚀 Features

- Added redirect support for table actions
- Standardised action handler signatures across the board

## [1.1.1] - 2025-10-21

### 🐛 Bug Fixes

- Fixed an incorrect breadcrumb link

## [1.1.0] - 2025-10-21

### 🚀 Features

- Reworked the filters and actions system with a cleaner, more extensible API
- Added `initial_row` support to formatters

## [0.4.0] - 2025-09-30

### 🚀 Features

- Added `DialogModalFormatter` for rendering cell values inside a modal dialog

## [0.3.1] - 2025-09-25

### 🚀 Features

- Migrated internal models to dataclasses; reworked the formatters system

### 🐛 Bug Fixes

- Fixed the row count mechanism in data sources; updated type hints and documentation

## [0.1.0] - 2025-09-23

### 🚀 Features

- Initial release: skeleton loader on data fetch, base styles, and core bug fixes

<!-- generated by git-cliff -->
