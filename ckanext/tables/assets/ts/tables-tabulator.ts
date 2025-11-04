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

        initialize: function (): void {
            $.proxyAll(this, /_/);

            if (!this.options.config) {
                this._showToast(ckan.i18n._("No config provided for tabulator"), "danger");
                return;
            }

            this._initAssignVariables();
            this._initTabulatorInstance();
            this._initAddTableEvents();
            this._updateClearButtonsState();

            this.sandbox.subscribe("tables:tabulator:refresh", this._refreshData);
        },

        _initAssignVariables: function (): void {
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

        _initTabulatorInstance: function (): void {
            this.options.config.ajaxURL = window.location.pathname;

            if (this.options.rowActions) {
                const rowActions = this.options.rowActions as Record<string, TabulatorAction>;
                this.options.config.rowContextMenu = Object.values(rowActions).map((action: TabulatorAction) => ({
                    label: `${action.icon ? `<i class='${action.icon} me-1'></i> ` : ''}${action.label}`,
                    action: this._rowActionCallback.bind(this, action)
                }));
            }

            if (this.options.config.rowHeader) {
                this.options.config.rowHeader.cellClick = function (e: Event, cell: any) {
                    cell.getRow().toggleSelect();
                };
            }

            const initialPage = new URLSearchParams(window.location.search).get("page");

            this.table = new Tabulator(this.el[0], {
                ...this.options.config,
                paginationInitialPage: parseInt(initialPage || "1"),
                footerElement: this.templates.footerElement,
                ajaxParams: () => ({ filters: JSON.stringify(this.tableFilters) })
            });
        },

        _showToast: function (message: string, type: string = "default"): void {
            ckan.tablesToast({
                message,
                type,
                title: ckan.i18n._("Tables"),
            });
        },

        _confirmAction: function (label: string, callback: () => void): void {
            ckan.tablesConfirm({
                message: ckan.i18n._(`Are you sure you want to perform this action: <b>${label}</b>?`),
                onConfirm: callback
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
            this._sendActionRequest(form, ckan.i18n._(`Row action completed: <b>${action.label}</b>`));
        },

        _sendActionRequest: function (form: FormData, successMessage: string): Promise<void> {
            return fetch(this.sandbox.client.url(this.options.config.ajaxURL), {
                method: "POST",
                body: form,
                headers: { 'X-CSRFToken': this._getCSRFToken() }
            })
                .then(resp => resp.json())
                .then(resp => {
                    if (!resp.success) {
                        const err = resp.error || resp.errors?.[0] || "Unknown error";
                        this._showToast(err, "danger");
                        if (resp.errors?.length > 1) {
                            this._showToast(
                                ckan.i18n._("Multiple errors occurred and were suppressed"),
                                "error"
                            );
                        }
                    } else {
                        if (resp.redirect) {
                            window.location.href = resp.redirect;
                            return;
                        }
                        this._refreshData();
                        this._showToast(resp.message || successMessage);
                    }
                })
                .catch(error => this._showToast(error.message, "danger"));
        },

        _initAddTableEvents: function (): void {
            this.applyFiltersBtn.addEventListener("click", this._onApplyFilters);
            this.clearFiltersModalBtn.addEventListener("click", this._onClearFilters);
            this.clearFiltersBtn.addEventListener("click", this._onClearFilters);
            this.addFilterBtn.addEventListener("click", this._onAddFilter);
            this.closeFiltersBtn.addEventListener("click", this._onCloseFilters);

            this.filtersContainer.addEventListener("click", (e: Event) => {
                const removeBtn = (e.target as HTMLElement).closest(".btn-remove-filter");
                if (removeBtn && this.filtersContainer.contains(removeBtn)) {
                    this._onFilterItemRemove(removeBtn);
                }
            });

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

            document.addEventListener("click", (e: Event) => {
                const rowActionsBtn = (e.target as HTMLElement).closest(".btn-row-actions");
                if (rowActionsBtn && this.el[0].contains(rowActionsBtn)) {
                    this._onRowActionsDropdownClick(e);
                }
            });

            this.table.on("tableBuilt", () => {
                if (this.options.enableFullscreenToggle) {
                    this.btnFullscreen = document.getElementById("btn-fullscreen");
                    this.btnFullscreen.addEventListener("click", this._onFullscreen);
                }
            });

            this.table.on("renderComplete", function (this: any) {
                htmx.process(this.element);
                const pageSizeSelect = document.querySelector(".tabulator-page-size");
                if (pageSizeSelect) pageSizeSelect.classList.add("form-select");
            });

            this.table.on("pageLoaded", (pageno: number) => {
                const url = new URL(window.location.href);
                url.searchParams.set("page", pageno.toString());
                window.history.replaceState({}, "", url);
            });
        },

        _onRowActionsDropdownClick: function (e: Event): void {
            e.preventDefault();
            const targetEl = e.target as HTMLElement;
            const rowEl = targetEl.closest(".tabulator-row");
            if (!rowEl) return;

            const rect = targetEl.getBoundingClientRect();
            rowEl.dispatchEvent(new MouseEvent("contextmenu", {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: rect.left + rect.width / 2,
                clientY: rect.bottom,
                button: 2
            }));
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
            Array.from(url.searchParams.keys()).forEach(key => {
                if (key.startsWith('field') || key.startsWith('operator') || key.startsWith('value')) {
                    url.searchParams.delete(key);
                }
            });
            this.tableFilters.forEach((filter: TableFilter) => {
                url.searchParams.append('field', filter.field);
                url.searchParams.append('operator', filter.operator);
                url.searchParams.append('value', filter.value);
            });
            window.history.replaceState({}, "", url);
        },

        _onApplyBulkAction: function (e: Event): void {
            const target = e.currentTarget as HTMLElement;
            const action = target.dataset.action;
            const label = target.textContent?.trim() || "";
            if (!action) return;
            this._confirmAction(label, () => this._onBulkActionConfirm(action, label));
        },

        _onBulkActionConfirm: function (bulkAction: string, label: string): void {
            const selectedData = this.table.getSelectedData();
            if (!selectedData.length) return;
            const data = selectedData.map(({ actions, ...rest }: Record<string, any>) => rest);
            const form = new FormData();
            form.append("bulk_action", bulkAction);
            form.append("rows", JSON.stringify(data));
            this._sendActionRequest(form, ckan.i18n._(`Bulk action completed: <b>${label}</b>`));
        },

        _onApplyTableAction: function (e: Event): void {
            const target = e.currentTarget as HTMLElement;
            const action = target.dataset.action;
            const label = target.textContent?.trim() || "";
            if (!action) return;
            this._confirmAction(label, () => this._onTableActionConfirm(action, label));
        },

        _onTableActionConfirm: function (action: string, label: string): void {
            const form = new FormData();
            form.append("table_action", action);
            this._sendActionRequest(form, ckan.i18n._(`Table action completed: <b>${label}</b>`));
        },

        _onTableExportClick: function (e: Event): void {
            const exporter = (e.target as HTMLElement).dataset.exporter;
            if (!exporter) return;

            const a = document.createElement('a');
            const url = new URL(window.location.href);
            url.searchParams.set("exporter", exporter);
            url.searchParams.set("filters", JSON.stringify(this.tableFilters));
            this.table.getSorters().forEach((s: { field: string; dir: string }) => {
                url.searchParams.set(`sort[0][field]`, s.field);
                url.searchParams.set(`sort[0][dir]`, s.dir);
            });
            a.href = this.sandbox.client.url(this.options.config.ajaxURL) + url.search;
            a.download = `${this.options.config.tableId || 'table'}.${exporter}`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
        },

        _refreshData: function (): void {
            this.table.replaceData();
        },

        _onFullscreen: function (): void {
            this.tableWrapper.classList.toggle("fullscreen");
        },

        _getCSRFToken: function (): string | null {
            const csrf_field = document.querySelector('meta[name="csrf_field_name"]')?.getAttribute('content');
            return document.querySelector(`meta[name="${csrf_field}"]`)?.getAttribute('content') || null;
        }
    };
});
