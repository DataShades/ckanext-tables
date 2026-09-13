/**
 * Tabulator integration for ckanext-tables
 *
 * Note:
 *  Replace the `ckan.tablesConfirm` and `ckan.tablesToast` functions with the `ckan.confirm` and `ckan.toast` from CKAN core
 *  when CKAN 2.12 is the minimum supported version.
 *
 */

namespace ckan {
    export var sandbox: any;
    export var pubsub: any;
    export var module: (name: string, initializer: ($: any) => any) => any;
    export var i18n: {
        _: (msgid: string, values?: Record<string, string | number>) => string;
    };
    export var tablesToast: (options: { message: string; type?: string; title?: string, stacking?: boolean }) => void;
    export var tablesConfirm: (options: { message: string; onConfirm: () => void }) => void;
}

type TableFilter = {
    field: string;
    operator: string;
    value: string;
};

type TabulatorRow = {
    getData: () => Record<string, any>;
};

type TabulatorAction = {
    name: string;
    label: string;
    icon?: string;
    attrs?: Record<string, string>;
    with_confirmation?: boolean;
};

declare var Tabulator: any;
declare var htmx: {
    process: (element: HTMLElement) => void;
};
declare var bootstrap: {
    Dropdown: { getInstance: (el: Element | null) => { hide: () => void } | null };
};

ckan.module("tables-tabulator", function ($) {
    "use strict";
    return {
        options: {
            config: null as any,
            rowActions: null as Record<string, TabulatorAction> | null,
            enableFullscreenToggle: true,
        },

        initialize: function (): void {
            $.proxyAll(this, /_/);

            if (!this.options.config) {
                this._showToast(ckan.i18n._("No config provided for tabulator"), "danger");
                return;
            }

            this._initAssignVariables();
            this._initFiltersFromUrl();
            this._initTabulatorInstance();
            this._initAddTableEvents();
            this._updateClearButtonsState();

            this.sandbox.subscribe("tables:tabulator:refresh", this._refreshData);
        },

        _id: function (base: string): string {
            return `${base}-${this.tableId}`;
        },

        _urlKey: function (base: string): string {
            return `${base}-${this.tableName}`;
        },

        _initAssignVariables: function (): void {
            this.tableId = this.el[0].id;
            this.tableName = this.options.config.tableName || this.tableId;
            this.wrapperEl = this.el.closest(".table-wrapper")[0];

            this.filtersModal = document.getElementById(this._id("filters-modal"));
            this.filtersContainer = document.getElementById(this._id("filters-container"));
            this.applyFiltersBtn = document.getElementById(this._id("apply-filters"));
            this.clearFiltersModalBtn = document.getElementById(this._id("clear-filters"));
            this.clearFiltersBtn = document.getElementById(this._id("clear-all-filters"));
            this.filterTemplate = document.getElementById(this._id("filter-template"));
            this.addFilterBtn = document.getElementById(this._id("add-filter"));
            this.filtersCounter = document.getElementById(this._id("filters-counter"));
            this.bulkActionsMenu = document.getElementById(this._id("bulk-actions-menu"));
            this.tableActionsMenu = document.getElementById(this._id("table-actions-menu"));
            this.tableExportersMenu = document.getElementById(this._id("table-exporters-menu"));
            this.tableRefreshBtn = document.getElementById(this._id("refresh-table"));
            this.totalCountEl = document.getElementById(this._id("total-count-value"));
            this.tableFilters = this._updateTableFilters();

            // Column visibility controls
            this.columnsModal = document.getElementById(this._id("columns-modal"));
            this.columnsContainer = document.getElementById(this._id("columns-container"));
            this.applyColumnsBtn = document.getElementById(this._id("apply-columns"));
            this.resetColumnsBtn = document.getElementById(this._id("reset-columns"));
            this.selectAllColumnsBtn = document.getElementById(this._id("select-all-columns"));
            this.deselectAllColumnsBtn = document.getElementById(this._id("deselect-all-columns"));
            this.columnToggles = this.columnsContainer.querySelectorAll(".column-toggle");
            this.hiddenColumnsCounter = document.getElementById(this._id("hidden-columns-counter"));
            this.hiddenColumnsBadge = document.getElementById(this._id("hidden-columns-badge"));
        },

        _initFiltersFromUrl: function (): void {
            const url = new URL(window.location.href);
            const fields = url.searchParams.getAll(this._urlKey("field"));
            const operators = url.searchParams.getAll(this._urlKey("operator"));
            const values = url.searchParams.getAll(this._urlKey("value"));

            if (fields.length && fields.length === operators.length && fields.length === values.length) {
                this.tableFilters = fields.map((field: string, i: number) => ({
                    field,
                    operator: operators[i],
                    value: values[i],
                }));
                this.filtersCounter.textContent = this.tableFilters.length.toString();
                this.filtersCounter.classList.toggle("d-none", this.tableFilters.length === 0);
                this._updateClearButtonsState();
            }
        },

        _initTabulatorInstance: function (): void {
            // Use custom ajax URL if provided, otherwise use current pathname
            if (!this.options.config.ajaxURL) {
                this.options.config.ajaxURL = window.location.pathname;
            }

            if (this.options.rowActions) {
                const rowActions = this.options.rowActions as Record<string, TabulatorAction>;
                this.options.config.rowContextMenu = Object.values(rowActions).map((action: TabulatorAction) => {
                    const attrs = Object.entries(action.attrs || {})
                        .map(([k, v]) => `${k}="${v}"`)
                        .join(" ");
                    const icon = action.icon ? `<i class='${action.icon} me-1'></i> ` : "";

                    return {
                        label: `<span ${attrs}>${icon}${action.label}</span>`,
                        action: this._rowActionCallback.bind(this, action),
                    };
                });
            }

            if (this.options.config.rowHeader) {
                this.options.config.rowHeader.cellClick = function (e: Event, cell: any) {
                    cell.getRow().toggleSelect();
                };
            }

            const initialPage = new URLSearchParams(window.location.search).get(this._urlKey("page"));

            this.table = new Tabulator(this.el[0], {
                ...this.options.config,
                langs: {
                    "default": {
                        pagination: {
                            page_size: ckan.i18n._("Rows per page"),
                            first: '<i class="fa fa-angle-double-left"></i>',
                            prev:  '<i class="fa fa-angle-left"></i>',
                            next:  '<i class="fa fa-angle-right"></i>',
                            last:  '<i class="fa fa-angle-double-right"></i>'
                        }
                    }
                },
                paginationCounter: "rows",
                paginationInitialPage: parseInt(initialPage || "1"),
                ajaxParams: () => ({ filters: JSON.stringify(this.tableFilters) }),
                ajaxResponse: (_url: string, _params: any, response: any) => {
                    if (this.totalCountEl && response.total !== undefined) {
                        this.totalCountEl.innerHTML = response.total;
                    }
                    return response;
                },
            });
        },

        _showToast: function (message: string, type: string = "default", stacking: boolean = true): void {
            ckan.tablesToast({
                message,
                type,
                title: ckan.i18n._("Tables"),
                stacking,
            });
        },

        _confirmAction: function (label: string, callback: () => void): void {
            ckan.tablesConfirm({
                message: ckan.i18n._("Are you sure you want to perform this action: %(label)s?", { label }),
                onConfirm: callback,
            });
        },

        _rowActionCallback: function (action: TabulatorAction, e: Event, row: TabulatorRow): void {
            if (action.with_confirmation) {
                this._confirmAction(action.label, () => this._onRowActionConfirm(action, row));
            } else {
                this._onRowActionConfirm(action, row);
            }
        },

        _onRowActionConfirm: function (action: TabulatorAction, row: TabulatorRow): void {
            const form = new FormData();
            form.append("row_action", action.name);
            form.append("row", JSON.stringify(row.getData()));
            this._sendActionRequest(form, ckan.i18n._("Row action completed: %(label)s", { label: action.label }));
        },

        _sendActionRequest: function (form: FormData, successMessage: string): Promise<void> {
            return fetch(this.sandbox.client.url(this.options.config.ajaxURL), {
                method: "POST",
                body: form,
                headers: { "X-CSRFToken": this._getCSRFToken() },
            })
                .then((resp) => resp.json())
                .then((resp) => {
                    if (!resp.success) {
                        const err = resp.error || resp.errors?.[0] || "Unknown error";
                        this._showToast(err, "danger");
                        if (resp.errors?.length > 1) {
                            this._showToast(ckan.i18n._("Multiple errors occurred and were suppressed"), "error");
                        }
                    } else {
                        if (resp.redirect) {
                            window.location.href = resp.redirect;
                            return;
                        }
                        this._refreshData().then(() => {
                            this._showToast(resp.message || successMessage);
                        });
                    }
                })
                .catch((error) => this._showToast(error.message, "danger"));
        },

        _initAddTableEvents: function (): void {
            this.applyFiltersBtn.addEventListener("click", this._onApplyFilters);
            this.clearFiltersModalBtn.addEventListener("click", this._onClearFilters);
            this.clearFiltersBtn.addEventListener("click", this._onClearFilters);
            this.addFilterBtn.addEventListener("click", this._onAddFilter);
            $(this.filtersModal).on("hidden.bs.modal", this._onCloseFilters);

            this.filtersContainer.addEventListener("click", (e: Event) => {
                const removeBtn = (e.target as HTMLElement).closest(".btn-remove-filter");
                if (removeBtn && this.filtersContainer.contains(removeBtn)) {
                    this._onFilterItemRemove(removeBtn);
                }
            });

            // Column visibility event listeners
            $(this.columnsModal).on("hidden.bs.modal", this._onCloseColumns);

            if (this.applyColumnsBtn) {
                this.applyColumnsBtn.addEventListener("click", this._onApplyColumns);
            }
            if (this.resetColumnsBtn) {
                this.resetColumnsBtn.addEventListener("click", this._onResetColumns);
            }
            if (this.selectAllColumnsBtn) {
                this.selectAllColumnsBtn.addEventListener("click", this._onSelectAllColumns);
            }
            if (this.deselectAllColumnsBtn) {
                this.deselectAllColumnsBtn.addEventListener("click", this._onDeselectAllColumns);
            }

            const bindMenuButtons = (menu: HTMLElement, handler: (e: Event) => void) => {
                if (menu) {
                    menu.querySelectorAll("button").forEach((btn: HTMLButtonElement) => {
                        btn.addEventListener("click", handler);
                    });
                }
            };

            bindMenuButtons(this.bulkActionsMenu, this._onApplyBulkAction);
            bindMenuButtons(this.tableActionsMenu, this._onApplyTableAction);
            bindMenuButtons(this.tableExportersMenu, this._onTableExportClick);

            if (this.tableRefreshBtn) {
                this.tableRefreshBtn.addEventListener("click", this._onRefreshTable);
            }

            document.addEventListener("click", (e: Event) => {
                const rowActionsBtn = (e.target as HTMLElement).closest(".btn-row-actions");
                if (rowActionsBtn && this.el[0].contains(rowActionsBtn)) {
                    this._onRowActionsDropdownClick(e);
                }
            });

            this.table.on("tableBuilt", () => {
                if (this.options.enableFullscreenToggle) {
                    this.btnFullscreen = document.getElementById(this._id("btn-fullscreen"));
                    this.btnFullscreen.addEventListener("click", this._onFullscreen);
                }

                this._applyColumnVisibilityFromUrl();
                this._initHeaderFilterToggles();
            });

            this.table.on("renderComplete", function (this: any) {
                htmx.process(this.element);
                const pageSizeSelect = this.element.querySelector(".tabulator-page-size");
                if (pageSizeSelect) pageSizeSelect.classList.add("form-select");
            });

            this.table.on("pageLoaded", (pageno: number) => {
                const url = new URL(window.location.href);
                url.searchParams.set(this._urlKey("page"), pageno.toString());
                window.history.replaceState({}, "", url);
            });
        },

        _onRowActionsDropdownClick: function (e: Event): void {
            e.preventDefault();
            const targetEl = e.target as HTMLElement;
            const rowEl = targetEl.closest(".tabulator-row");
            if (!rowEl) return;

            const rect = targetEl.getBoundingClientRect();
            rowEl.dispatchEvent(
                new MouseEvent("contextmenu", {
                    bubbles: true,
                    cancelable: true,
                    view: window,
                    clientX: rect.left + rect.width / 2,
                    clientY: rect.bottom,
                    button: 2,
                })
            );
        },

        _collectValidFilters: function (): TableFilter[] {
            const filters: TableFilter[] = [];
            this.filtersContainer.querySelectorAll(".filter-item").forEach((item: HTMLElement) => {
                const field = (item.querySelector(".filter-field") as HTMLSelectElement)?.value;
                const operator = (item.querySelector(".filter-operator") as HTMLSelectElement)?.value;
                const value = (item.querySelector(".filter-value") as HTMLInputElement)?.value;
                if (field && operator && value) filters.push({ field, operator, value });
            });
            return filters;
        },

        _updateTableFilters: function (): TableFilter[] {
            this.tableFilters = this._collectValidFilters();
            this.filtersCounter.textContent = this.tableFilters.length.toString();
            this.filtersCounter.classList.toggle("d-none", this.tableFilters.length === 0);
            return this.tableFilters;
        },

        _removeUnfilledFilters: function (): void {
            this.filtersContainer.querySelectorAll(".filter-item").forEach((item: HTMLElement) => {
                const field = (item.querySelector(".filter-field") as HTMLSelectElement)?.value;
                const operator = (item.querySelector(".filter-operator") as HTMLSelectElement)?.value;
                const value = (item.querySelector(".filter-value") as HTMLInputElement)?.value;
                if (!field || !operator || !value) item.remove();
            });
        },

        _onApplyFilters: function (): void {
            this._updateTableFilters();
            this._removeUnfilledFilters();
            this._updateClearButtonsState();
            this._updateUrl();
            this._refreshData();
        },

        _updateClearButtonsState: function (): void {
            const hasFilters = this.tableFilters.length > 0;
            this.clearFiltersBtn.classList.toggle("btn-table-disabled", !hasFilters);
            this.clearFiltersModalBtn.classList.toggle("btn-table-disabled", !hasFilters);
        },

        _onClearFilters: function (): void {
            this.filtersContainer.innerHTML = "";
            this._updateTableFilters();
            this._updateClearButtonsState();
            this._updateUrl();
            this._refreshData();
        },

        _onAddFilter: function (): void {
            const newFilter = this.filterTemplate.cloneNode(true) as HTMLElement;
            newFilter.style.display = "block";
            this.filtersContainer.appendChild(newFilter);
        },

        _onFilterItemRemove: function (filterEl: Element): void {
            const parent = filterEl.closest(".filter-item");
            if (parent) parent.remove();
        },

        _onCloseFilters: function (): void {
            this._recreateFilters();
        },

        _recreateFilters: function (): void {
            this.filtersContainer.innerHTML = "";
            this.tableFilters.forEach((filter: TableFilter) => {
                const newFilter = this.filterTemplate.cloneNode(true) as HTMLElement;
                newFilter.style.display = "block";
                (newFilter.querySelector(".filter-field") as HTMLSelectElement).value = filter.field;
                (newFilter.querySelector(".filter-operator") as HTMLSelectElement).value = filter.operator;
                (newFilter.querySelector(".filter-value") as HTMLInputElement).value = filter.value;
                this.filtersContainer.appendChild(newFilter);
            });
            this._updateUrl();
        },

        _updateUrl: function (): void {
            const url = new URL(window.location.href);
            const fieldKey = this._urlKey("field");
            const operatorKey = this._urlKey("operator");
            const valueKey = this._urlKey("value");

            url.searchParams.delete(fieldKey);
            url.searchParams.delete(operatorKey);
            url.searchParams.delete(valueKey);

            this.tableFilters.forEach((filter: TableFilter) => {
                url.searchParams.append(fieldKey, filter.field);
                url.searchParams.append(operatorKey, filter.operator);
                url.searchParams.append(valueKey, filter.value);
            });
            window.history.replaceState({}, "", url);
        },

        _onApplyBulkAction: function (e: Event): void {
            const target = e.currentTarget as HTMLElement;
            const action = target.dataset.action;
            const label = target.textContent?.trim() || "";
            if (!action) return;
            const withConfirmation = target.dataset.withConfirmation !== "false";
            if (withConfirmation) {
                this._confirmAction(label, () => this._onBulkActionConfirm(action, label));
            } else {
                this._onBulkActionConfirm(action, label);
            }
        },

        _onBulkActionConfirm: function (bulkAction: string, label: string): void {
            const selectedData = this.table.getSelectedData();
            if (!selectedData.length) return;
            const data = selectedData.map(({ actions, ...rest }: Record<string, any>) => rest);
            const form = new FormData();
            form.append("bulk_action", bulkAction);
            form.append("rows", JSON.stringify(data));
            this._sendActionRequest(form, ckan.i18n._("Bulk action completed: %(label)s", { label }));
        },

        _onApplyTableAction: function (e: Event): void {
            const target = e.currentTarget as HTMLElement;
            const action = target.dataset.action;
            const label = target.textContent?.trim() || "";
            if (!action) return;
            const withConfirmation = target.dataset.withConfirmation !== "false";
            if (withConfirmation) {
                this._confirmAction(label, () => this._onTableActionConfirm(action, label));
            } else {
                this._onTableActionConfirm(action, label);
            }
        },

        _onTableActionConfirm: function (action: string, label: string): void {
            const form = new FormData();
            form.append("table_action", action);
            this._sendActionRequest(form, ckan.i18n._("Table action completed: %(label)s", { label }));
        },

        _onTableExportClick: async function (e: Event): Promise<void> {
            const target = e.target as HTMLElement;
            const exporter = target.dataset.exporter;
            if (!exporter) return;

            const toggle = this.tableExportersMenu.previousElementSibling;
            // Must close before disabling the toggle — Dropdown.hide() no-ops on a disabled element.
            bootstrap.Dropdown.getInstance(toggle)?.hide();

            const exportButtons = Array.from(this.tableExportersMenu.querySelectorAll("button")) as HTMLButtonElement[];
            exportButtons.forEach((btn) => (btn.disabled = true));
            toggle?.setAttribute("disabled", "true");

            try {
                const url = new URL(window.location.href);
                url.searchParams.set("exporter", exporter);
                url.searchParams.set("filters", JSON.stringify(this.tableFilters));
                this.table.getSorters().forEach((s: { field: string; dir: string }) => {
                    url.searchParams.set(`sort[0][field]`, s.field);
                    url.searchParams.set(`sort[0][dir]`, s.dir);
                });

                this._showToast(ckan.i18n._("%(name)s export started.", { name: target.innerText }));

                const targetUrl = new URL(this.sandbox.client.url(this.options.config.ajaxURL), window.location.origin);
                url.searchParams.forEach((value, key) => {
                    targetUrl.searchParams.append(key, value);
                });
                const fullUrl = targetUrl.toString();

                const response = await fetch(fullUrl);

                if (!response.ok) throw new Error(`${target.innerText} export failed`);

                const blob = await response.blob();
                const a = document.createElement("a");
                a.href = URL.createObjectURL(blob);
                a.download = `${this.tableName || "table"}.${exporter}`;
                document.body.appendChild(a);
                a.click();
                document.body.removeChild(a);
                URL.revokeObjectURL(a.href);

                this._showToast(ckan.i18n._("%(name)s export completed.", { name: target.innerText }), "default", false);
            } catch (error) {
                this._showToast(
                    ckan.i18n._("%(name)s export failed. Please try again.", { name: target.innerText }),
                    "danger",
                    false
                );
                console.error('Export error:', error);
            } finally {
                exportButtons.forEach((btn) => (btn.disabled = false));
                toggle?.removeAttribute("disabled");
            }
        },

        _onRefreshTable: function (): void {
            const form = new FormData();
            form.append("refresh", "true");

            this.tableRefreshBtn.setAttribute("disabled", "true");

            fetch(this.sandbox.client.url(this.options.config.ajaxURL), {
                method: "POST",
                body: form,
                headers: { "X-CSRFToken": this._getCSRFToken() },
            })
                .then((resp) => {
                    if (!resp.ok) {
                        throw new Error(ckan.i18n._("Failed to refresh table data."));
                    }
                    return this._refreshData().then(() => {
                        this._showToast(ckan.i18n._("Table data refreshed successfully."));
                    });
                })
                .catch((error) => this._showToast(error.message, "danger"))
                .finally(() => this.tableRefreshBtn.removeAttribute("disabled"));
        },

        _refreshData: function (): Promise<void> {
            return this.table.replaceData();
        },

        _initHeaderFilterToggles: function (): void {
            const tableEl = this.el[0] as HTMLElement;

            tableEl.querySelectorAll<HTMLElement>(".tabulator-col[tabulator-field]").forEach((colEl) => {
                if (colEl.querySelector(".btn-header-filter-toggle")) return;

                const filterInput = colEl.querySelector<HTMLInputElement>(".tabulator-header-filter input");
                if (!filterInput) return;

                const sorterEl = colEl.querySelector(".tabulator-col-sorter");
                if (!sorterEl) return;

                filterInput.id = this._id(`header-filter-${colEl.getAttribute("tabulator-field") || ""}`);

                const btn = this._buildFilterToggleButton(colEl, filterInput);

                this._syncHeaderFilterState(colEl, filterInput, btn);

                // Keep button state in sync as the user types
                filterInput.addEventListener("input", () => {
                    this._syncHeaderFilterState(colEl, filterInput, btn);
                });

                sorterEl.insertAdjacentElement("afterend", btn);
            });
        },

        _buildFilterToggleButton: function(colEl: HTMLElement, filterInput: HTMLInputElement): HTMLButtonElement {
            const btn = document.createElement("button");
            btn.type = "button";
            btn.className = "btn-header-filter-toggle";
            btn.title = ckan.i18n._("Toggle column filter");
            btn.setAttribute("aria-controls", filterInput.id);
            btn.innerHTML = '<i class="fa fa-search"></i>';

            btn.addEventListener("click", (e: Event) => {
                e.stopPropagation();

                // Do not close if filter has value
                if (filterInput.value.trim()) {
                    colEl.classList.add("filter-visible");
                    return;
                }

                colEl.classList.toggle("filter-visible");
                this._syncHeaderFilterState(colEl, filterInput, btn);

                // Force Tabulator to recalculate column header heights
                this.table.redraw();

                if (colEl.classList.contains("filter-visible")) {
                    filterInput.focus();
                }
            });

            return btn;
        },

        _syncHeaderFilterState: function (colEl: HTMLElement, filterInput: HTMLInputElement, btn: HTMLButtonElement): void {
            const hasValue = Boolean(filterInput.value.trim());
            colEl.classList.toggle("filter-active", hasValue);
            btn.classList.toggle("active", hasValue || colEl.classList.contains("filter-visible"));
        },

        _onFullscreen: function (): void {
            this.wrapperEl.classList.toggle("table-fullscreen");
            document.body.classList.toggle(
                "tables-fullscreen",
                document.querySelector(".table-wrapper.table-fullscreen") !== null
            );
        },

        _onApplyColumns: function (): void {
            const hiddenColumns: string[] = [];

            this.columnToggles.forEach((toggle: HTMLInputElement) => {
                const field = toggle.dataset.field;
                if (!field) return;

                if (toggle.checked) {
                    this.table.showColumn(field);
                } else {
                    hiddenColumns.push(field);
                    this.table.hideColumn(field);
                }
            });

            this._updateColumnsUrl(hiddenColumns);
            this._updateHiddenColumnsCounter();

            // Redraw table to recalculate column widths
            this.table.redraw(true);
        },

        _onResetColumns: function (): void {
            this.columnToggles.forEach((toggle: HTMLInputElement) => {
                toggle.checked = true;
                const field = toggle.dataset.field;
                if (field) {
                    this.table.showColumn(field);
                }
            });

            this._updateColumnsUrl([]);
            this._updateHiddenColumnsCounter();

            // Redraw table to recalculate column widths
            this.table.redraw(true);
        },

        _onCloseColumns: function (): void {
            // Restore checkboxes to match current column visibility
            this.columnToggles.forEach((toggle: HTMLInputElement) => {
                const field = toggle.dataset.field;
                if (field) {
                    const column = this.table.getColumn(field);
                    if (column) {
                        toggle.checked = column.isVisible();
                    }
                }
            });
        },

        _onSelectAllColumns: function (): void {
            this.columnToggles.forEach((toggle: HTMLInputElement) => {
                toggle.checked = true;
            });
        },

        _onDeselectAllColumns: function (): void {
            this.columnToggles.forEach((toggle: HTMLInputElement) => {
                toggle.checked = false;
            });
        },

        _applyColumnVisibilityFromUrl: function (): void {
            const urlParams = new URLSearchParams(window.location.search);
            const hiddenColumns = urlParams.getAll(this._urlKey("hidden_column"));

            // Hide columns that are marked as hidden in URL
            hiddenColumns.forEach((field: string) => {
                try {
                    this.table.hideColumn(field);
                } catch (e) {
                    // Column might not exist, ignore error
                }
            });

            // Update counter after applying visibility from URL
            this._updateHiddenColumnsCounter();
        },

        _updateHiddenColumnsCounter: function (): void {
            const urlParams = new URLSearchParams(window.location.search);
            const hiddenCount = urlParams.getAll(this._urlKey("hidden_column")).length;

            this.hiddenColumnsCounter.textContent = hiddenCount.toString();
            this.hiddenColumnsBadge.classList.toggle("d-none", hiddenCount === 0);
        },

        _updateColumnsUrl: function (hiddenColumns: string[]): void {
            const url = new URL(window.location.href);
            const key = this._urlKey("hidden_column");

            url.searchParams.delete(key);

            hiddenColumns.forEach((field) => {
                url.searchParams.append(key, field);
            });

            window.history.replaceState({}, "", url);
        },

        _getCSRFToken: function (): string | null {
            const csrf_field = document.querySelector('meta[name="csrf_field_name"]')?.getAttribute("content");
            return document.querySelector(`meta[name="${csrf_field}"]`)?.getAttribute("content") || null;
        },
    };
});
