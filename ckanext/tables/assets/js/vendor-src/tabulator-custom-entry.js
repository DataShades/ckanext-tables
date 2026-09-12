/**
 * Custom Tabulator.js build entry point.
 *
 * Only registers the modules ckanext-tables actually uses, instead of the
 * full ~40-module build. Before adding/removing a module here, re-check
 * `table.py` / `tables-tabulator.ts` for the Tabulator option that needs it,
 * since modules resolve each other at runtime (no compile-time dependency
 * graph) and a missing one can fail silently until that code path runs.
 *
 * Kept modules and why:
 *  - Ajax:           ajaxURL / ajaxParams / ajaxResponse / replaceData()
 *  - Page:           remote pagination, paginationCounter, pageLoaded event
 *  - Sort:           sorter option, remote sortMode, getSorters()
 *  - Filter:         headerFilter, remote filterMode
 *  - Format:         formatter option ("html", "plaintext", custom formatters)
 *  - SelectRow:      rowHeader checkbox column, getSelectedData() for bulk actions
 *  - Menu:           rowContextMenu (row actions dropdown)
 *  - Interaction:    fires row-contextmenu/cell-click etc. that Menu, ResizeColumns
 *                     and Tooltip subscribe to - required even though nothing here
 *                     calls it directly
 *  - ResizeColumns:  per-column `resizable: true/false`
 *  - ResizeTable:    watches the table's container via ResizeObserver and redraws on
 *                     change - without it, `fitColumns` layout is computed once against
 *                     whatever width the container had at construction and never again,
 *                     so columns can render too narrow until something else (e.g. the
 *                     header-filter toggle) happens to call `table.redraw()`.
 *  - Tooltip:        per-column `tooltip: true`
 *  - Edit:           NOT used for cell editing anywhere in ckanext-tables, but
 *                     Filter's `headerFilter: true` code path unconditionally
 *                     reads `table.modules.edit.editors["input"]` with no
 *                     existence check - dropping this breaks every header filter.
 */
import Tabulator from "tabulator-tables/src/js/core/Tabulator.js";

import AjaxModule from "tabulator-tables/src/js/modules/Ajax/Ajax.js";
import PageModule from "tabulator-tables/src/js/modules/Page/Page.js";
import SortModule from "tabulator-tables/src/js/modules/Sort/Sort.js";
import FilterModule from "tabulator-tables/src/js/modules/Filter/Filter.js";
import FormatModule from "tabulator-tables/src/js/modules/Format/Format.js";
import SelectRowModule from "tabulator-tables/src/js/modules/SelectRow/SelectRow.js";
import MenuModule from "tabulator-tables/src/js/modules/Menu/Menu.js";
import InteractionModule from "tabulator-tables/src/js/modules/Interaction/Interaction.js";
import ResizeColumnsModule from "tabulator-tables/src/js/modules/ResizeColumns/ResizeColumns.js";
import ResizeTableModule from "tabulator-tables/src/js/modules/ResizeTable/ResizeTable.js";
import TooltipModule from "tabulator-tables/src/js/modules/Tooltip/Tooltip.js";
import EditModule from "tabulator-tables/src/js/modules/Edit/Edit.js";

Tabulator.registerModule([
    AjaxModule,
    PageModule,
    SortModule,
    FilterModule,
    FormatModule,
    SelectRowModule,
    MenuModule,
    InteractionModule,
    ResizeColumnsModule,
    ResizeTableModule,
    TooltipModule,
    EditModule,
]);

window.Tabulator = Tabulator;
