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
        _: (msgid: string) => string;
    };
    export var tablesToast: (options: { message: string; type?: string; title?: string }) => void;
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
    with_confirmation?: boolean;
};

declare var Tabulator: any;
declare var htmx: {
    process: (element: HTMLElement) => void;
};


ckan.module("tables-tabulator", function ($) {
    "use strict";
    return {
        templates: {
            footerElement: `<div class='d-flex justify-content-between align-items-center gap-2'>
                <a class='btn btn-light d-none d-sm-inline-block' id='btn-fullscreen' title='Fullscreen toggle'><i class='fa fa-expand'></i></a>
            </div>`,
        },
        options: {
            config: null as any,
            rowActions: null as Record<string, TabulatorAction> | null,
            enableFullscreenToggle: true,
        },

        initialize: function () {
            $.proxyAll(this, /_/);

            if (!this.options.config) {
                ckan.tablesToast({ message: ckan.i18n._("No config provided for tabulator"), type: "danger", title: ckan.i18n._("Tables") });
                return;
            }

            this._initAssignVariables();
            this._initTabulatorInstance();
            this._initAddTableEvents();
            this._updateClearButtonsState();

            this.sandbox.subscribe("tables:tabulator:refresh", this._refreshData);
        },

        _initAssignVariables: function () {
            this.filtersContainer = document.getElementById("filters-container");
            this.applyFiltersBtn = document.getElementById("apply-filters");
            this.clearFiltersModalBtn = document.getElementById("clear-filters");
            this.clearFiltersBtn = document.getElementById("clear-all-filters");
            this.filterTemplate = document.getElementById("filter-template");
            this.addFilterBtn = document.getElementById("add-filter");
            this.closeFiltersBtn = document.getElementById("close-filters");
            this.filtersCounter = document.getElementById("filters-counter");
            this.bulkActionsMenu = document.getElementById("bulk-actions-menu");
            this.tableActionsMenu = document.getElementById("table-actions-menu");
            this.tableExportersMenu = document.getElementById("table-exporters-menu");
            this.tableWrapper = document.querySelector(".tabulator-wrapper");
            this.tableFilters = this._updateTableFilters();
        },

        _initTabulatorInstance: function () {
            if (this.options.rowActions) {
                const rowActions = this.options.rowActions as Record<string, TabulatorAction>;
                this.options.config.rowContextMenu = Object.values(rowActions).map((action: TabulatorAction) => {
                    return {
                        label: `${action.icon ? `<i class='${action.icon} me-1'></i> ` : ''}${action.label}`,
                        action: this._rowActionCallback.bind(this, action)
                    };
                });
            }

            if (this.options.config.rowHeader) {
                this.options.config.rowHeader.cellClick = function (e: Event, cell: any) {
                    cell.getRow().toggleSelect();
                }
            }

            this.table = new Tabulator(this.el[0], {
                ...this.options.config,
                paginationInitialPage: parseInt(getQueryParam("page") || "1"),
                footerElement: this.templates.footerElement,
                ajaxParams: () => {
                    return {
                        filters: JSON.stringify(this.tableFilters)
                    }
                }
            });
        },

        _rowActionCallback: function (action: TabulatorAction, e: Event, row: TabulatorRow) {
            if (!action.with_confirmation) {
                return this._onRowActionConfirm(action, row);
            }

            ckan.tablesConfirm({
                message: ckan.i18n._(`Are you sure you want to perform this action: <b>${action.label}</b>?`),
                onConfirm: () => this._onRowActionConfirm(action, row)
            });
        },

        _onRowActionConfirm: function (action: TabulatorAction, row: TabulatorRow) {
            const form = new FormData();

            form.append("row_action", action.name);
            form.append("row", JSON.stringify(row.getData()));

            fetch(this.sandbox.client.url(this.options.config.ajaxURL), {
                method: "POST",
                body: form,
                headers: {
                    'X-CSRFToken': this._getCSRFToken()
                }
            })
                .then(resp => resp.json())
                .then(resp => {
                    if (!resp.success) {
                        ckan.tablesToast({ message: resp.error, type: "danger", title: ckan.i18n._("Tables") });
                    } else {
                        if (resp.redirect) {
                            window.location.href = resp.redirect;
                            return;
                        }

                        this._refreshData()

                        let message = resp.message || ckan.i18n._(`Row action completed: <b>${action.label}</b>`);

                        ckan.tablesToast({
                            message: message,
                            title: ckan.i18n._("Tables"),
                        });
                    }
                }).catch(error => {
                    ckan.tablesToast({ message: error.message, type: "danger", title: ckan.i18n._("Tables") });
                });
        },

        _initAddTableEvents: function () {
            this.applyFiltersBtn.addEventListener("click", this._onApplyFilters);
            this.clearFiltersModalBtn.addEventListener("click", this._onClearFilters);
            this.clearFiltersBtn.addEventListener("click", this._onClearFilters);
            this.addFilterBtn.addEventListener("click", this._onAddFilter);
            this.closeFiltersBtn.addEventListener("click", this._onCloseFilters);
            this.filtersContainer.addEventListener("click", (e: Event) => {
                let targetElement = e.target as HTMLElement;
                const removeBtn = targetElement.closest(".btn-remove-filter");

                if (removeBtn && this.filtersContainer.contains(removeBtn)) {
                    this._onFilterItemRemove(removeBtn);
                }
            });

            if (this.bulkActionsMenu) {
                this.bulkActionsMenu.querySelectorAll("button").forEach((button: HTMLButtonElement) => {
                    button.addEventListener("click", this._onApplyBulkAction);
                });
            }

            if (this.tableActionsMenu) {
                this.tableActionsMenu.querySelectorAll("button").forEach((button: HTMLButtonElement) => {
                    button.addEventListener("click", this._onApplyTableAction);
                });
            };

            if (this.tableExportersMenu) {
                this.tableExportersMenu.querySelectorAll("button").forEach((button: HTMLButtonElement) => {
                    button.addEventListener("click", this._onTableExportClick);
                });
            }

            document.addEventListener("click", (e: Event) => {
                const rowActionsBtn = (e.target as HTMLElement).closest(".btn-row-actions");

                if (rowActionsBtn && this.el[0].contains(rowActionsBtn)) {
                    this._onRowActionsDropdownClick(e);
                }
            });

            // Tabulator events
            this.table.on("tableBuilt", () => {
                if (this.options.enableFullscreenToggle) {
                    this.btnFullscreen = document.getElementById("btn-fullscreen");
                    this.btnFullscreen.addEventListener("click", this._onFullscreen);
                }
            });

            this.table.on("renderComplete", function (this: any) {
                htmx.process(this.element);

                const pageSizeSelect = document.querySelector(".tabulator-page-size");

                if (pageSizeSelect) {
                    pageSizeSelect.classList.add("form-select");
                }
            });

            this.table.on("pageLoaded", (pageno: number) => {
                const url = new URL(window.location.href);
                url.searchParams.set("page", pageno.toString());
                window.history.replaceState({}, "", url);
            });
        },

        _onRowActionsDropdownClick: function (e: Event) {
            e.preventDefault();

            const targetEl = e.target as HTMLElement;
            const rowEl = targetEl.closest(".tabulator-row");

            if (!rowEl) return;

            // Place the fake right-click at the button position
            const rect = targetEl.getBoundingClientRect();

            rowEl.dispatchEvent(new MouseEvent("contextmenu", {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: rect.left + rect.width / 2,
                clientY: rect.bottom,
                button: 2   // right click
            }));
        },

        _onApplyFilters: function () {
            this._updateTableFilters();
            this._removeUnfilledFilters();
            this._updateClearButtonsState();
            this._updateUrl();
            this._refreshData();
        },

        _updateClearButtonsState: function () {
            const hasFilters = this.tableFilters.length > 0;
            this.clearFiltersBtn.classList.toggle("btn-table-disabled", !hasFilters);
            this.clearFiltersModalBtn.classList.toggle("btn-table-disabled", !hasFilters);
        },

        _updateTableFilters: function () {
            const filters: Array<TableFilter> = [];

            this.filtersContainer.querySelectorAll(".filter-item").forEach(function (item: HTMLElement) {
                const fieldElement = item.querySelector(".filter-field") as HTMLSelectElement;
                const operatorElement = item.querySelector(".filter-operator") as HTMLSelectElement;
                const valueElement = item.querySelector(".filter-value") as HTMLInputElement;

                const field = fieldElement?.value;
                const operator = operatorElement?.value;
                const value = valueElement?.value;

                if (field && operator && value) {
                    filters.push({ field, operator, value });
                }
            });

            this.tableFilters = filters;
            this.filtersCounter.textContent = filters.length.toString();
            this.filtersCounter.classList.toggle("d-none", filters.length === 0);

            return filters;
        },

        _removeUnfilledFilters: function () {
            this.filtersContainer.querySelectorAll(".filter-item").forEach(function (item: HTMLElement) {
                const fieldElement = item.querySelector(".filter-field") as HTMLSelectElement;
                const operatorElement = item.querySelector(".filter-operator") as HTMLSelectElement;
                const valueElement = item.querySelector(".filter-value") as HTMLInputElement;

                const field = fieldElement?.value;
                const operator = operatorElement?.value;
                const value = valueElement?.value;

                if (!field || !operator || !value) {
                    item.remove();
                }
            });
        },

        _onClearFilters: function () {
            this.filtersContainer.innerHTML = "";

            this._updateTableFilters();
            this._updateClearButtonsState();
            this._updateUrl();
            this._refreshData();
        },

        _onAddFilter: function () {
            const newFilter = this.filterTemplate.cloneNode(true);
            newFilter.style.display = "block";

            this.filtersContainer.appendChild(newFilter);
        },

        _onFilterItemRemove: function (filterEl: Element) {
            const parent = filterEl.closest(".filter-item");

            if (parent) {
                parent.remove();
            }
        },

        _onCloseFilters: function () {
            this._recreateFilters();
        },

        _recreateFilters: function () {
            this.filtersContainer.innerHTML = "";

            this.tableFilters.forEach((filter: TableFilter) => {
                const newFilter = this.filterTemplate.cloneNode(true);
                newFilter.style.display = "block";

                newFilter.querySelector(".filter-field").value = filter.field;
                newFilter.querySelector(".filter-operator").value = filter.operator;
                newFilter.querySelector(".filter-value").value = filter.value;

                this.filtersContainer.appendChild(newFilter);
            });

            this._updateUrl();
        },

        /**
         * Update the URL with the current applied filters
         */
        _updateUrl: function () {
            const url = new URL(window.location.href);

            // Clear existing filter parameters
            Array.from(url.searchParams.keys()).forEach(key => {
                if (key.startsWith('field') || key.startsWith('operator') || key.startsWith('q')) {
                    url.searchParams.delete(key);
                }
            });

            // Add current filters
            this.tableFilters.forEach((filter: TableFilter) => {
                url.searchParams.append('field', filter.field);
                url.searchParams.append('operator', filter.operator);
                url.searchParams.append('q', filter.value);
            });

            window.history.replaceState({}, "", url);
        },

        /**
         * Apply the row action to the selected rows
         */
        _onApplyBulkAction: function (e: Event) {
            const target = e.currentTarget as HTMLElement | null;
            const bulkAction = target?.dataset?.action;
            const label = target?.textContent?.trim() || "";

            if (!bulkAction) {
                return;
            }

            ckan.tablesConfirm({
                message: ckan.i18n._(`Are you sure you want to perform this action: <b>${label}</b>?`),
                onConfirm: () => this._onBulkActionConfirm(bulkAction, label)
            });
        },

        _onBulkActionConfirm: function (bulkAction: string, label: string) {
            const selectedData = this.table.getSelectedData();

            if (!selectedData.length) {
                return;
            }

            // exclude 'actions' column
            const data = selectedData.map((row: Record<string, any>) => {
                const { actions, ...rest } = row;
                return rest;
            });

            const form = new FormData();

            form.append("bulk_action", bulkAction);
            form.append("rows", JSON.stringify(data));

            fetch(this.sandbox.client.url(this.options.config.ajaxURL), {
                method: "POST",
                body: form,
                headers: {
                    'X-CSRFToken': this._getCSRFToken()
                }
            })
                .then(resp => resp.json())
                .then(resp => {
                    if (!resp.success) {
                        ckan.tablesToast({ message: resp.errors[0], type: "danger", title: ckan.i18n._("Tables") });

                        if (resp.errors.length > 1) {
                            ckan.tablesToast({
                                message: ckan.i18n._("Multiple errors occurred and were suppressed"),
                                type: "error",
                                title: ckan.i18n._("Tables"),
                            });
                        }
                    } else {
                        this._refreshData()
                        ckan.tablesToast({
                            message: ckan.i18n._(`Bulk action completed: <b>${label}</b>`),
                            title: ckan.i18n._("Tables"),
                        });
                    }
                }).catch(error => {
                    ckan.tablesToast({ message: error.message, type: "danger", title: ckan.i18n._("Tables") });
                });
        },

        _onApplyTableAction: function (e: Event) {
            const target = e.currentTarget as HTMLElement;
            const action = target.dataset.action;
            const label = target.textContent;

            if (!action) {
                return;
            }

            ckan.tablesConfirm({
                message: ckan.i18n._(`Are you sure you want to perform this action: <b>${label}</b>?`),
                onConfirm: () => this._onTableActionConfirm(action, label)
            });
        },

        _onTableActionConfirm: function (action: string, label: string) {
            const form = new FormData();

            form.append("table_action", action);

            fetch(this.sandbox.client.url(this.options.config.ajaxURL), {
                method: "POST",
                body: form,
                headers: {
                    'X-CSRFToken': this._getCSRFToken()
                }
            })
                .then(resp => resp.json())
                .then(resp => {
                    if (!resp.success) {
                        ckan.tablesToast({ message: resp.error, type: "danger", title: ckan.i18n._("Tables") });
                    } else {
                        if (resp.redirect) {
                            window.location.href = resp.redirect;
                            return;
                        }

                        this._refreshData()

                        let message = resp.message || ckan.i18n._(`Table action completed: <b>${label}</b>`);

                        ckan.tablesToast({
                            message: message,
                            title: ckan.i18n._("Tables"),
                        });
                    }
                }).catch(error => {
                    ckan.tablesToast({ message: error.message, type: "danger", title: ckan.i18n._("Tables") });
                });
        },

        _onTableExportClick: function (e: Event) {
            const exporter = (e.target as HTMLElement).dataset.exporter;

            if (!exporter) {
                return;
            }

            const a = document.createElement('a');
            const url = new URL(window.location.href)

            url.searchParams.set("exporter", exporter);
            url.searchParams.set("filters", JSON.stringify(this.tableFilters));

            this.table.getSorters().forEach((element: { field: string; dir: string }) => {
                url.searchParams.set(`sort[0][field]`, element.field);
                url.searchParams.set(`sort[0][dir]`, element.dir);
            });

            a.href = this.sandbox.client.url(this.options.config.exportURL) + url.search;
            a.download = `${this.options.config.tableId || 'table'}.${exporter}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        },

        _refreshData: function () {
            this.table.replaceData();
        },

        _onFullscreen: function () {
            this.tableWrapper.classList.toggle("fullscreen");
        },

        _getCSRFToken: function () {
            const csrf_field = document.querySelector('meta[name="csrf_field_name"]')?.getAttribute('content');
            const csrf_token = document.querySelector(`meta[name="${csrf_field}"]`)?.getAttribute('content');

            return csrf_token;
        }
    };
});

/**
 * Retrieves the value of a specified query string parameter from the current URL.
 *
 * @param {string} name The name of the query parameter whose value you want to retrieve.
 * @returns {string|null} The value of the first query parameter with the specified name, or null if the parameter is not found.
*/
function getQueryParam(name: string): string | null {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
}
