/**
 * Tabulator integration for ckanext-tables
 *
 * Note:
 *  Replace the `ckan.tablesConfirm` and `ckan.tablesToast` functions with the `ckan.confirm` and `ckan.toast` from CKAN core
 *  when CKAN 2.12 is the minimum supported version.
 *
*/
var ckan;
(function (ckan) {
})(ckan || (ckan = {}));
ckan.module("tables-tabulator", function ($) {
    "use strict";
    return {
        templates: {
            footerElement: `<div class='d-flex justify-content-between align-items-center gap-2'>
                <a class='btn btn-light d-none d-sm-inline-block' id='btn-fullscreen' title='Fullscreen toggle'><i class='fa fa-expand'></i></a>
            </div>`,
        },
        options: {
            config: null,
            rowActions: null,
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
                const rowActions = this.options.rowActions;
                this.options.config.rowContextMenu = Object.values(rowActions).map((action) => {
                    return {
                        label: `${action.icon ? `<i class='${action.icon} me-1'></i> ` : ''}${action.label}`,
                        action: this._rowActionCallback.bind(this, action)
                    };
                });
            }
            if (this.options.config.rowHeader) {
                this.options.config.rowHeader.cellClick = function (e, cell) {
                    cell.getRow().toggleSelect();
                };
            }
            this.table = new Tabulator(this.el[0], {
                ...this.options.config,
                paginationInitialPage: parseInt(getQueryParam("page") || "1"),
                footerElement: this.templates.footerElement,
                ajaxParams: () => {
                    return {
                        filters: JSON.stringify(this.tableFilters)
                    };
                }
            });
        },
        _rowActionCallback: function (action, e, row) {
            if (!action.with_confirmation) {
                return this._onRowActionConfirm(action, row);
            }
            ckan.tablesConfirm({
                message: ckan.i18n._(`Are you sure you want to perform this action: <b>${action.label}</b>?`),
                onConfirm: () => this._onRowActionConfirm(action, row)
            });
        },
        _onRowActionConfirm: function (action, row) {
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
                }
                else {
                    if (resp.redirect) {
                        window.location.href = resp.redirect;
                        return;
                    }
                    this._refreshData();
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
            this.filtersContainer.addEventListener("click", (e) => {
                let targetElement = e.target;
                const removeBtn = targetElement.closest(".btn-remove-filter");
                if (removeBtn && this.filtersContainer.contains(removeBtn)) {
                    this._onFilterItemRemove(removeBtn);
                }
            });
            if (this.bulkActionsMenu) {
                this.bulkActionsMenu.querySelectorAll("button").forEach((button) => {
                    button.addEventListener("click", this._onApplyBulkAction);
                });
            }
            if (this.tableActionsMenu) {
                this.tableActionsMenu.querySelectorAll("button").forEach((button) => {
                    button.addEventListener("click", this._onApplyTableAction);
                });
            }
            ;
            if (this.tableExportersMenu) {
                this.tableExportersMenu.querySelectorAll("button").forEach((button) => {
                    button.addEventListener("click", this._onTableExportClick);
                });
            }
            document.addEventListener("click", (e) => {
                const rowActionsBtn = e.target.closest(".btn-row-actions");
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
            this.table.on("renderComplete", function () {
                htmx.process(this.element);
                const pageSizeSelect = document.querySelector(".tabulator-page-size");
                if (pageSizeSelect) {
                    pageSizeSelect.classList.add("form-select");
                }
            });
            this.table.on("pageLoaded", (pageno) => {
                const url = new URL(window.location.href);
                url.searchParams.set("page", pageno.toString());
                window.history.replaceState({}, "", url);
            });
        },
        _onRowActionsDropdownClick: function (e) {
            e.preventDefault();
            const targetEl = e.target;
            const rowEl = targetEl.closest(".tabulator-row");
            if (!rowEl)
                return;
            // Place the fake right-click at the button position
            const rect = targetEl.getBoundingClientRect();
            rowEl.dispatchEvent(new MouseEvent("contextmenu", {
                bubbles: true,
                cancelable: true,
                view: window,
                clientX: rect.left + rect.width / 2,
                clientY: rect.bottom,
                button: 2 // right click
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
            const filters = [];
            this.filtersContainer.querySelectorAll(".filter-item").forEach(function (item) {
                const fieldElement = item.querySelector(".filter-field");
                const operatorElement = item.querySelector(".filter-operator");
                const valueElement = item.querySelector(".filter-value");
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
            this.filtersContainer.querySelectorAll(".filter-item").forEach(function (item) {
                const fieldElement = item.querySelector(".filter-field");
                const operatorElement = item.querySelector(".filter-operator");
                const valueElement = item.querySelector(".filter-value");
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
        _onFilterItemRemove: function (filterEl) {
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
            this.tableFilters.forEach((filter) => {
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
            this.tableFilters.forEach((filter) => {
                url.searchParams.append('field', filter.field);
                url.searchParams.append('operator', filter.operator);
                url.searchParams.append('q', filter.value);
            });
            window.history.replaceState({}, "", url);
        },
        /**
         * Apply the row action to the selected rows
         */
        _onApplyBulkAction: function (e) {
            const target = e.currentTarget;
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
        _onBulkActionConfirm: function (bulkAction, label) {
            const selectedData = this.table.getSelectedData();
            if (!selectedData.length) {
                return;
            }
            // exclude 'actions' column
            const data = selectedData.map((row) => {
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
                }
                else {
                    this._refreshData();
                    ckan.tablesToast({
                        message: ckan.i18n._(`Bulk action completed: <b>${label}</b>`),
                        title: ckan.i18n._("Tables"),
                    });
                }
            }).catch(error => {
                ckan.tablesToast({ message: error.message, type: "danger", title: ckan.i18n._("Tables") });
            });
        },
        _onApplyTableAction: function (e) {
            const target = e.currentTarget;
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
        _onTableActionConfirm: function (action, label) {
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
                }
                else {
                    if (resp.redirect) {
                        window.location.href = resp.redirect;
                        return;
                    }
                    this._refreshData();
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
        _onTableExportClick: function (e) {
            const exporter = e.target.dataset.exporter;
            if (!exporter) {
                return;
            }
            const a = document.createElement('a');
            const url = new URL(window.location.href);
            url.searchParams.set("exporter", exporter);
            url.searchParams.set("filters", JSON.stringify(this.tableFilters));
            this.table.getSorters().forEach((element) => {
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
function getQueryParam(name) {
    const params = new URLSearchParams(window.location.search);
    return params.get(name);
}
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoidGFibGVzLXRhYnVsYXRvci5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIi4uL3RzL3RhYmxlcy10YWJ1bGF0b3IudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7RUFPRTtBQUVGLElBQVUsSUFBSSxDQVNiO0FBVEQsV0FBVSxJQUFJO0FBU2QsQ0FBQyxFQVRTLElBQUksS0FBSixJQUFJLFFBU2I7QUEwQkQsSUFBSSxDQUFDLE1BQU0sQ0FBQyxrQkFBa0IsRUFBRSxVQUFVLENBQUM7SUFDdkMsWUFBWSxDQUFDO0lBQ2IsT0FBTztRQUNILFNBQVMsRUFBRTtZQUNQLGFBQWEsRUFBRTs7bUJBRVI7U0FDVjtRQUNELE9BQU8sRUFBRTtZQUNMLE1BQU0sRUFBRSxJQUFXO1lBQ25CLFVBQVUsRUFBRSxJQUE4QztZQUMxRCxzQkFBc0IsRUFBRSxJQUFJO1NBQy9CO1FBRUQsVUFBVSxFQUFFO1lBQ1IsQ0FBQyxDQUFDLFFBQVEsQ0FBQyxJQUFJLEVBQUUsR0FBRyxDQUFDLENBQUM7WUFFdEIsSUFBSSxDQUFDLElBQUksQ0FBQyxPQUFPLENBQUMsTUFBTSxFQUFFLENBQUM7Z0JBQ3ZCLElBQUksQ0FBQyxXQUFXLENBQUMsRUFBRSxPQUFPLEVBQUUsSUFBSSxDQUFDLElBQUksQ0FBQyxDQUFDLENBQUMsa0NBQWtDLENBQUMsRUFBRSxJQUFJLEVBQUUsUUFBUSxFQUFFLEtBQUssRUFBRSxJQUFJLENBQUMsSUFBSSxDQUFDLENBQUMsQ0FBQyxRQUFRLENBQUMsRUFBRSxDQUFDLENBQUM7Z0JBQzdILE9BQU87WUFDWCxDQUFDO1lBRUQsSUFBSSxDQUFDLG9CQUFvQixFQUFFLENBQUM7WUFDNUIsSUFBSSxDQUFDLHNCQUFzQixFQUFFLENBQUM7WUFDOUIsSUFBSSxDQUFDLG1CQUFtQixFQUFFLENBQUM7WUFDM0IsSUFBSSxDQUFDLHdCQUF3QixFQUFFLENBQUM7WUFFaEMsSUFBSSxDQUFDLE9BQU8sQ0FBQyxTQUFTLENBQUMsMEJBQTBCLEVBQUUs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Q1YsSUFBSSxDQUFDLEtBQUssQ0FBQyxXQUFXLEVBQUUsQ0FBQztRQUM3QixDQUFDO1FBRUQsYUFBYSxFQUFFO1lBQ1gsSUFBSSxDQUFDLFlBQVksQ0FBQyxTQUFTLENBQUMsTUFBTSxDQUFDLFlBQVksQ0FBQyxDQUFDO1FBQ3JELENBQUM7UUFFRCxhQUFhLEVBQUU7WUFDWCxNQUFNLFVBQVUsR0FBRyxRQUFRLENBQUMsYUFBYSxDQUFDLDhCQUE4QixDQUFDLEVBQUUsWUFBWSxDQUFDLFNBQVMsQ0FBQyxDQUFDO1lBQ25HLE1BQU0sVUFBVSxHQUFHLFFBQVEsQ0FBQyxhQUFhLENBQUMsY0FBYyxVQUFVLElBQUksQ0FBQyxFQUFFLFlBQVksQ0FBQyxTQUFTLENBQUMsQ0FBQztZQUVqRyxPQUFPLFVBQVUsQ0FBQztRQUN0QixDQUFDO0tBQ0osQ0FBQztBQUNOLENBQUMsQ0FBQyxDQUFDO0FBRUg7Ozs7O0VBS0U7QUFDRixTQUFTLGFBQWEsQ0FBQyxJQUFZO0lBQy9CLE1BQU0sTUFBTSxHQUFHLElBQUksZUFBZSxDQUFDLE1BQU0sQ0FBQyxRQUFRLENBQUMsTUFBTSxDQUFDLENBQUM7SUFDM0QsT0FBTyxNQUFNLENBQUMsR0FBRyxDQUFDLElBQUksQ0FBQyxDQUFDO0FBQzVCLENBQUMiLCJzb3VyY2VzQ29udGVudCI6WyIvKipcbiAqIFRhYnVsYXRvciBpbnRlZ3JhdGlvbiBmb3IgY2thbmV4dC10YWJsZXNcbiAqXG4gKiBOb3RlOlxuICogIFJlcGxhY2UgdGhlIGBja2FuLnRhYmxlc0NvbmZpcm1gIGFuZCBgY2thbi50YWJsZXNUb2FzdGAgZnVuY3Rpb25zIHdpdGggdGhlIGBja2FuLmNvbmZpcm1gIGFuZCBgY2thbi50b2FzdGAgZnJvbSBDS0FOIGNvcmVcbiAqICB3aGVuIENLQU4gMi4xMiBpcyB0aGUgbWluaW11bSBzdXBwb3J0ZWQgdmVyc2lvbi5cbiAqXG4qL1xuXG5uYW1lc3BhY2UgY2thbiB7XG4gICAgZXhwb3J0IHZhciBzYW5kYm94OiBhbnk7XG4gICAgZXhwb3J0IHZhciBwdWJzdWI6IGFueTtcbiAgICBleHBvcnQgdmFyIG1vZHVsZTogKG5hbWU6IHN0cmluZywgaW5pdGlhbGl6ZXI6ICgkOiBhbnkpID0+IGFueSkgPT4gYW55O1xuICAgIGV4cG9ydCB2YXIgaTE4bjoge1xuICAgICAgICBfOiAobXNnaWQ6IHN0cmluZykgPT4gc3RyaW5nO1xuICAgIH07XG4gICAgZXhwb3J0IHZhciB0YWJsZXNUb2FzdDogKG9wdGlvbnM6IHsgbWVzc2FnZTogc3RyaW5nOyB0eXBlPzogc3RyaW5nOyB0aXRsZT86IHN0cmluZyB9KSA9PiB2b2lkO1xuICAgIGV4cG9ydCB2YXIgdGFibGVzQ29uZmlybTogKG9wdGlvbnM6IHsgbWVzc2FnZTogc3RyaW5nOyBvbkNvbmZpcm06ICgpID0+IHZvaWQgfSkgPT4gdm9pZDtcbn1cblxudHlwZSBUYWJsZUZpbHRlciA9IHtcbiAgICBmaWVsZDogc3RyaW5nO1xuICAgIG9wZXJhdG9yOiBzdHJpbmc7XG4gICAgdmFsdWU6IHN0cmluZztcbn07XG5cblxudHlwZSBUYWJ1bGF0b3JSb3cgPSB7XG4gICAgZ2V0RGF0YTogKCkgPT4gUmVjb3JkPHN0cmluZywgYW55Pjtcbn07XG5cbnR5cGUgVGFidWxhdG9yQWN0aW9uID0ge1xuICAgIG5hbWU6IHN0cmluZztcbiAgICBsYWJlbDogc3RyaW5nO1xuICAgIGljb24/OiBzdHJpbmc7XG4gICAgd2l0aF9jb25maXJtYXRpb24/OiBib29sZWFuO1xufTtcblxuZGVjbGFyZSB2YXIgVGFidWxhdG9yOiBhbnk7XG5kZWNsYXJlIHZhciBodG14OiB7XG4gICAgcHJvY2VzczogKGVsZW1lbnQ6IEhUTUxFbGVtZW50KSA9PiB2b2lkO1xufTtcblxuXG5ja2FuLm1vZHVsZShcInRhYmxlcy10YWJ1bGF0b3JcIiwgZnVuY3Rpb24gKCQpIHtcbiAgICBcInVzZSBzdHJpY3RcIjtcbiAgICByZXR1cm4ge1xuICAgICAgICB0ZW1wbGF0ZXM6IHtcbiAgICAgICAgICAgIGZvb3RlckVsZW1lbnQ6IGA8ZGl2IGNsYXNzPSdkLWZsZXgganVzdGlmeS1jb250ZW50LWJldHdlZW4gYWxpZ24taXRlbXMtY2VudGVyIGdhcC0yJz5cbiAgICAgICAgICAgICAgICA8YSBjbGFzcz0nYnRuIGJ0bi1saWdodCBkLW5vbmUgZC1zbS1pbmxpbmUtYmxvY2snIGlkPSdidG4tZnVsbHNjcmVlbicgdGl0bGU9J0Z1bGxzY3JlZW4gdG9nZ2xlJz48aSBjbGFzcz0nZmEgZmEtZXhwYW5kJz48L2k+PC9hPlxuICAgICAgICAgICAgPC9kaXY+YCxcbiAgICAgICAgfSxcbiAgICAgICAgb3B0aW9uczoge1xuICAgICAgICAgICAgY29uZmlnOiBudWxsIGFzIGFueSxcbiAgICAgICAgICAgIHJvd0FjdGlvbnM6IG51bGwgYXMgUmVjb3JkPHN0cmluZywgVGFidWxhdG9yQWN0aW9uPiB8IG51bGwsXG4gICAgICAgICAgICBlbmFibGVGdWxsc2NyZWVuVG9nZ2xlOiB0cnVlLFxuICAgICAgICB9LFxuXG4gICAgICAgIGluaXRpYWxpemU6IGZ1bmN0aW9uICgpIHtcbiAgICAgICAgICAgICQucHJveHlBbGwodGhpcywgL18vKTtcblxuICAgICAgICAgICAgaWYgKCF0aGlzLm9wdGlvbnMuY29uZmlnKSB7XG4gICAgICAgICAgICAgICAgY2thbi50YWJsZXNUb2FzdCh7IG1lc3NhZ2U6IGNrYW4uaTE4bi5fKFwiTm8gY29uZmlnIHByb3ZpZGVkIGZvciB0YWJ1bGF0b3JcIiksIHR5cGU6IFwiZGFuZ2VyXCIsIHRpdGxlOiBja2FuLmkxOG4uXyhcIlRhYmxlc1wiKSB9KTtcbiAgICAgICAgICAgICAgICByZXR1cm47XG4gICAgICAgICAgICB9XG5cbiAgICAgICAgICAgIHRoaXMuX2luaXRBc3NpZ25WYXJpYWJsZXMoKTtcbiAgICAgICAgICAgIHRoaXMuX2luaXRUYWJ1bGF0b3JJbnN0YW5jZSgpO1xuICAgICAgICAgICAgdGhpcy5faW5pdEFkZFRhYmxlRXZlbnRzKCk7XG4gICAgICAgICAgICB0aGlzLl91cGRhdGVDbGVhckJ1dHRvbnNTdGF0ZSgpO1xuXG4gICAgICAgICAgICB0aGlzLnNhbmRib3guc3Vic2NyaWJlKFwidGFibGVzOnRhYnVsYXRvcjpyZWZyZXNoXCIsIHRoaXMuX3JlZnJlc2hEYXRhKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfaW5pdEFzc2lnblZhcmlhYmxlczogZnVuY3Rpb24gKCkge1xuICAgICAgICAgICAgdGhpcy5maWx0ZXJzQ29udGFpbmVyID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJmaWx0ZXJzLWNvbnRhaW5lclwiKTtcbiAgICAgICAgICAgIHRoaXMuYXBwbHlGaWx0ZXJzQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJhcHBseS1maWx0ZXJzXCIpO1xuICAgICAgICAgICAgdGhpcy5jbGVhckZpbHRlcnNNb2RhbEJ0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiY2xlYXItZmlsdGVyc1wiKTtcbiAgICAgICAgICAgIHRoaXMuY2xlYXJGaWx0ZXJzQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJjbGVhci1hbGwtZmlsdGVyc1wiKTtcbiAgICAgICAgICAgIHRoaXMuZmlsdGVyVGVtcGxhdGUgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChcImZpbHRlci10ZW1wbGF0ZVwiKTtcbiAgICAgICAgICAgIHRoaXMuYWRkRmlsdGVyQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJhZGQtZmlsdGVyXCIpO1xuICAgICAgICAgICAgdGhpcy5jbG9zZUZpbHRlcnNCdG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChcImNsb3NlLWZpbHRlcnNcIik7XG4gICAgICAgICAgICB0aGlzLmZpbHRlcnNDb3VudGVyID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJmaWx0ZXJzLWNvdW50ZXJcIik7XG4gICAgICAgICAgICB0aGlzLmJ1bGtBY3Rpb25zTWVudSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiYnVsay1hY3Rpb25zLW1lbnVcIik7XG4gICAgICAgICAgICB0aGlzLnRhYmxlQWN0aW9uc01lbnUgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChcInRhYmxlLWFjdGlvbnMtbWVudVwiKTtcbiAgICAgICAgICAgIHRoaXMudGFibGVFeHBvcnRlcnNNZW51ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJ0YWJsZS1leHBvcnRlcnMtbWVudVwiKTtcbiAgICAgICAgICAgIHRoaXMudGFibGVXcmFwcGVyID0gZG9jdW1lbnQucXVlcnlTZWxlY3RvcihcIi50YWJ1bGF0b3Itd3JhcHBlclwiKTtcbiAgICAgICAgICAgIHRoaXMudGFibGVGaWx0ZXJzID0gdGhpcy5fdXBkYXRlVGFibGVGaWx0ZXJzKCk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX2luaXRUYWJ1bGF0b3JJbnN0YW5jZTogZnVuY3Rpb24gKCkge1xuICAgICAgICAgICAgaWYgKHRoaXMub3B0aW9ucy5yb3dBY3Rpb25zKSB7XG4gICAgICAgICAgICAgICAgY29uc3Qgcm93QWN0aW9ucyA9IHRoaXMub3B0aW9ucy5yb3dBY3Rpb25zIGFzIFJlY29yZDxzdHJpbmcsIFRhYnVsYXRvckFjdGlvbj47XG4gICAgICAgICAgICAgICAgdGhpcy5vcHRpb25zLmNvbmZpZy5yb3dDb250ZXh0TWVudSA9IE9iamVjdC52YWx1ZXMocm93QWN0aW9ucykubWFwKChhY3Rpb246IFRhYnVsYXRvckFjdGlvbikgPT4ge1xuICAgICAgICAgICAgICAgICAgICByZXR1cm4ge1xuICAgICAgICAgICAgICAgICAgICAgICAgbGFiZWw6IGAke2FjdGlvbi5pY29uID8gYDxpIGNsYXNzPScke2FjdGlvbi5pY29ufSBtZS0xJz48L2k+IGAgOiAnJ30ke2FjdGlvbi5sYWJlbH1gLFxuICAgICAgICAgICAgICAgICAgICAgICAgYWN0aW9uOiB0aGlzLl9yb3dBY3Rpb25DYWxsYmFjay5iaW5kKHRoaXMsIGFjdGlvbilcbiAgICAgICAgICAgICAgICAgICAgfTtcbiAgICAgICAgICAgICAgICB9KTtcbiAgICAgICAgICAgIH1cblxuICAgICAgICAgICAgaWYgKHRoaXMub3B0aW9ucy5jb25maWcucm93SGVhZGVyKSB7XG4gICAgICAgICAgICAgICAgdGhpcy5vcHRpb25zLmNvbmZpZy5yb3dIZWFkZXIuY2VsbENsaWNrID0gZnVuY3Rpb24gKGU6IEV2ZW50LCBjZWxsOiBhbnkpIHtcbiAgICAgICAgICAgICAgICAgICAgY2VsbC5nZXRSb3coKS50b2dnbGVTZWxlY3QoKTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICB9XG5cbiAgICAgICAgICAgIHRoaXMudGFibGUgPSBuZXcgVGFidWxhdG9yKHRoaXMuZWxbMF0sIHtcbiAgICAgICAgICAgICAgICAuLi50aGlzLm9wdGlvbnMuY29uZmlnLFxuICAgICAgICAgICAgICAgIHBhZ2luYXRpb25Jbml0aWFsUGFnZTogcGFyc2VJbnQoZ2V0UXVlcnlQYXJhbShcInBhZ2VcIikgfHwgXCIxXCIpLFxuICAgICAgICAgICAgICAgIGZvb3RlckVsZW1lbnQ6IHRoaXMudGVtcGxhdGVzLmZvb3RlckVsZW1lbnQsXG4gICAgICAgICAgICAgICAgYWpheFBhcmFtczogKCkgPT4ge1xuICAgICAgICAgICAgICAgICAgICByZXR1cm4ge1xuICAgICAgICAgICAgICAgICAgICAgICAgZmlsdGVyczogSlNPTi5zdHJpbmdpZnkodGhpcy50YWJsZUZpbHRlcnMpXG4gICAgICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICB9KTtcbiAgICAgICAgfSxcblxuICAgICAgICBfcm93QWN0aW9uQ2FsbGJhY2s6IGZ1bmN0aW9uIChhY3Rpb246IFRhYnVsYXRvckFjdGlvbiwgZTogRXZlbnQsIHJvdzogVGFidWxhdG9yUm93KSB7XG4gICAgICAgICAgICBpZiAoIWFjdGlvbi53aXRoX2NvbmZpcm1hdGlvbikge1xuICAgICAgICAgICAgICAgIHJldHVybiB0aGlzLl9vblJvd0FjdGlvbkNvbmZpcm0oYWN0aW9uLCByb3cpO1xuICAgICAgICAgICAgfVxuXG4gICAgICAgICAgICBja2FuLnRhYmxlc0NvbmZpcm0oe1xuICAgICAgICAgICAgICAgIG1lc3NhZ2U6IGNrYW4uaTE4bi5fKGBBcmUgeW91IHN1cmUgeW91IHdhbnQgdG8gcGVyZm9ybSB0aGlzIGFjdGlvbjogPGI+JHthY3Rpb24ubGFiZWx9PC9iPj9gKSxcbiAgICAgICAgICAgICAgICBvbkNvbmZpcm06ICgpID0+IHRoaXMuX29uUm93QWN0aW9uQ29uZmlybShhY3Rpb24sIHJvdylcbiAgICAgICAgICAgIH0pO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9vblJvd0FjdGlvbkNvbmZpcm06IGZ1bmN0aW9uIChhY3Rpb246IFRhYnVsYXRvckFjdGlvbiwgcm93OiBUYWJ1bGF0b3JSb3cpIHtcbiAgICAgICAgICAgIGNvbnN0IGZvcm0gPSBuZXcgRm9ybURhdGEoKTtcblxuICAgICAgICAgICAgZm9ybS5hcHBlbmQoXCJyb3dfYWN0aW9uXCIsIGFjdGlvbi5uYW1lKTtcbiAgICAgICAgICAgIGZvcm0uYXBwZW5kKFwicm93XCIsIEpTT04uc3RyaW5naWZ5KHJvdy5nZXREYXRhKCkpKTtcblxuICAgICAgICAgICAgZmV0Y2godGhpcy5zYW5kYm94LmNsaWVudC51cmwodGhpcy5vcHRpb25zLmNvbmZpZy5hamF4VVJMKSwge1xuICAgICAgICAgICAgICAgIG1ldGhvZDogXCJQT1NUXCIsXG4gICAgICAgICAgICAgICAgYm9keTogZm9ybSxcbiAgICAgICAgICAgICAgICBoZWFkZXJzOiB7XG4gICAgICAgICAgICAgICAgICAgICdYLUNTUkZUb2tlbic6IHRoaXMuX2dldENTUkZUb2tlbigpXG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgfSlcbiAgICAgICAgICAgICAgICAudGhlbihyZXNwID0+IHJlc3AuanNvbigpKVxuICAgICAgICAgICAgICAgIC50aGVuKHJlc3AgPT4ge1xuICAgICAgICAgICAgICAgICAgICBpZiAoIXJlc3Auc3VjY2Vzcykge1xuICAgICAgICAgICAgICAgICAgICAgICAgY2thbi50YWJsZXNUb2FzdCh7IG1lc3NhZ2U6IHJlc3AuZXJyb3IsIHR5cGU6IFwiZGFuZ2VyXCIsIHRpdGxlOiBja2FuLmkxOG4uXyhcIlRhYmxlc1wiKSB9KTtcbiAgICAgICAgICAgICAgICAgICAgfSBlbHNlIHtcbiAgICAgICAgICAgICAgICAgICAgICAgIGlmIChyZXNwLnJlZGlyZWN0KSB7XG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgd2luZG93LmxvY2F0aW9uLmhyZWYgPSByZXNwLnJlZGlyZWN0O1xuICAgICAgICAgICAgICAgICAgICAgICAgICAgIHJldHVybjtcbiAgICAgICAgICAgICAgICAgICAgICAgIH1cblxuICAgICAgICAgICAgICAgICAgICAgICAgdGhpcy5fcmVmcmVzaERhdGEoKVxuXG4gICAgICAgICAgICAgICAgICAgICAgICBsZXQgbWVzc2FnZSA9IHJlc3AubWVzc2FnZSB8fCBja2FuLmkxOG4uXyhgUm93IGFjdGlvbiBjb21wbGV0ZWQ6IDxiPiR7YWN0aW9uLmxhYmVsfTwvYj5gKTtcblxuICAgICAgICAgICAgICAgICAgICAgICAgY2thbi50YWJsZXNUb2FzdCh7XG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgbWVzc2FnZTogbWVzc2FnZSxcbiAgICAgICAgICAgICAgICAgICAgICAgICAgICB0aXRsZTogY2thbi5pMThuLl8oXCJUYWJsZXNcIiksXG4gICAgICAgICAgICAgICAgICAgICAgICB9KTtcbiAgICAgICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgICAgIH0pLmNhdGNoKGVycm9yID0+IHtcbiAgICAgICAgICAgICAgICAgICAgY2thbi50YWJsZXNUb2FzdCh7IG1lc3NhZ2U6IGVycm9yLm1lc3NhZ2UsIHR5cGU6IFwiZGFuZ2VyXCIsIHRpdGxlOiBja2FuLmkxOG4uXyhcIlRhYmxlc1wiKSB9KTtcbiAgICAgICAgICAgICAgICB9KTtcbiAgICAgICAgfSxcblxuICAgICAgICBfaW5pdEFkZFRhYmxlRXZlbnRzOiBmdW5jdGlvbiAoKSB7XG4gICAgICAgICAgICB0aGlzLmFwcGx5RmlsdGVyc0J0bi5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgdGhpcy5fb25BcHBseUZpbHRlcnMpO1xuICAgICAgICAgICAgdGhpcy5jbGVhckZpbHRlcnNNb2RhbEJ0bi5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgdGhpcy5fb25DbGVhckZpbHRlcnMpO1xuICAgICAgICAgICAgdGhpcy5jbGVhckZpbHRlcnNCdG4uYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsIHRoaXMuX29uQ2xlYXJGaWx0ZXJzKTtcbiAgICAgICAgICAgIHRoaXMuYWRkRmlsdGVyQnRuLmFkZEV2ZW50TGlzdGVuZXIoXCJjbGlja1wiLCB0aGlzLl9vbkFkZEZpbHRlcik7XG4gICAgICAgICAgICB0aGlzLmNsb3NlRmlsdGVyc0J0bi5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgdGhpcy5fb25DbG9zZUZpbHRlcnMpO1xuICAgICAgICAgICAgdGhpcy5maWx0ZXJzQ29udGFpbmVyLmFkZEV2ZW50TGlzdGVuZXIoXCJjbGlja1wiLCAoZTogRXZlbnQpID0+IHtcbiAgICAgICAgICAgICAgICBsZXQgdGFyZ2V0RWxlbWVudCA9IGUudGFyZ2V0IGFzIEhUTUxFbGVtZW50O1xuICAgICAgICAgICAgICAgIGNvbnN0IHJlbW92ZUJ0biA9IHRhcmdldEVsZW1lbnQuY2xvc2VzdChcIi5idG4tcmVtb3ZlLWZpbHRlclwiKTtcblxuICAgICAgICAgICAgICAgIGlmIChyZW1vdmVCdG4gJiYgdGhpcy5maWx0ZXJzQ29udGFpbmVyLmNvbnRhaW5zKHJlbW92ZUJ0bikpIHtcbiAgICAgICAgICAgICAgICAgICAgdGhpcy5fb25GaWx0ZXJJdGVtUmVtb3ZlKHJlbW92ZUJ0bik7XG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgfSk7XG5cbiAgICAgICAgICAgIGlmICh0aGlzLmJ1bGtBY3Rpb25zTWVudSkge1xuICAgICAgICAgICAgICAgIHRoaXMuYnVsa0FjdGlvbnNNZW51LnF1ZXJ5U2VsZWN0b3JBbGwoXCJidXR0b25cIikuZm9yRWFjaCgoYnV0dG9uOiBIVE1MQnV0dG9uRWxlbWVudCkgPT4ge1xuICAgICAgICAgICAgICAgICAgICBidXR0b24uYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsIHRoaXMuX29uQXBwbHlCdWxrQWN0aW9uKTtcbiAgICAgICAgICAgICAgICB9KTtcbiAgICAgICAgICAgIH1cblxuICAgICAgICAgICAgaWYgKHRoaXMudGFibGVBY3Rpb25zTWVudSkge1xuICAgICAgICAgICAgICAgIHRoaXMudGFibGVBY3Rpb25zTWVudS5xdWVyeVNlbGVjdG9yQWxsKFwiYnV0dG9uXCIpLmZvckVhY2goKGJ1dHRvbjogSFRNTEJ1dHRvbkVsZW1lbnQpID0+IHtcbiAgICAgICAgICAgICAgICAgICAgYnV0dG9uLmFkZEV2ZW50TGlzdGVuZXIoXCJjbGlja1wiLCB0aGlzLl9vbkFwcGx5VGFibGVBY3Rpb24pO1xuICAgICAgICAgICAgICAgIH0pO1xuICAgICAgICAgICAgfTtcblxuICAgICAgICAgICAgaWYgKHRoaXMudGFibGVFeHBvcnRlcnNNZW51KSB7XG4gICAgICAgICAgICAgICAgdGhpcy50YWJsZUV4cG9ydGVyc01lbnUucXVlcnlTZWxlY3RvckFsbChcImJ1dHRvblwiKS5mb3JFYWNoKChidXR0b246IEhUTUxCdXR0b25FbGVtZW50KSA9PiB7XG4gICAgICAgICAgICAgICAgICAgIGJ1dHRvbi5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgdGhpcy5fb25UYWJsZUV4cG9ydENsaWNrKTtcbiAgICAgICAgICAgICAgICB9KTtcbiAgICAgICAgICAgIH1cblxuICAgICAgICAgICAgZG9jdW1lbnQuYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsIChlOiBFdmVudCkgPT4ge1xuICAgICAgICAgICAgICAgIGNvbnN0IHJvd0FjdGlvbnNCdG4gPSAoZS50YXJnZXQgYXMgSFRNTEVsZW1lbnQpLmNsb3Nlc3QoXCIuYnRuLXJvdy1hY3Rpb25zXCIpO1xuXG4gICAgICAgICAgICAgICAgaWYgKHJvd0FjdGlvbnNCdG4gJiYgdGhpcy5lbFswXS5jb250YWlucyhyb3dBY3Rpb25zQnRuKSkge1xuICAgICAgICAgICAgICAgICAgICB0aGlzLl9vblJvd0FjdGlvbnNEcm9wZG93bkNsaWNrKGUpO1xuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgIH0pO1xuXG4gICAgICAgICAgICAvLyBUYWJ1bGF0b3IgZXZlbnRzXG4gICAgICAgICAgICB0aGlzLnRhYmxlLm9uKFwidGFibGVCdWlsdFwiLCAoKSA9PiB7XG4gICAgICAgICAgICAgICAgaWYgKHRoaXMub3B0aW9ucy5lbmFibGVGdWxsc2NyZWVuVG9nZ2xlKSB7XG4gICAgICAgICAgICAgICAgICAgIHRoaXMuYnRuRnVsbHNjcmVlbiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiYnRuLWZ1bGxzY3JlZW5cIik7XG4gICAgICAgICAgICAgICAgICAgIHRoaXMuYnRuRnVsbHNjcmVlbi5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgdGhpcy5fb25GdWxsc2NyZWVuKTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICB9KTtcblxuICAgICAgICAgICAgdGhpcy50YWJsZS5vbihcInJlbmRlckNvbXBsZXRlXCIsIGZ1bmN0aW9uICh0aGlzOiBhbnkpIHtcbiAgICAgICAgICAgICAgICBodG14LnByb2Nlc3ModGhpcy5lbGVtZW50KTtcblxuICAgICAgICAgICAgICAgIGNvbnN0IHBhZ2VTaXplU2VsZWN0ID0gZG9jdW1lbnQucXVlcnlTZWxlY3RvcihcIi50YWJ1bGF0b3ItcGFnZS1zaXplXCIpO1xuXG4gICAgICAgICAgICAgICAgaWYgKHBhZ2VTaXplU2VsZWN0KSB7XG4gICAgICAgICAgICAgICAgICAgIHBhZ2VTaXplU2VsZWN0LmNsYXNzTGlzdC5hZGQoXCJmb3JtLXNlbGVjdFwiKTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICB9KTtcblxuICAgICAgICAgICAgdGhpcy50YWJsZS5vbihcInBhZ2VMb2FkZWRcIiwgKHBhZ2VubzogbnVtYmVyKSA9PiB7XG4gICAgICAgICAgICAgICAgY29uc3QgdXJsID0gbmV3IFVSTCh3aW5kb3cubG9jYXRpb24uaHJlZik7XG4gICAgICAgICAgICAgICAgdXJsLnNlYXJjaFBhcmFtcy5zZXQoXCJwYWdlXCIsIHBhZ2Vuby50b1N0cmluZygpKTtcbiAgICAgICAgICAgICAgICB3aW5kb3cuaGlzdG9yeS5yZXBsYWNlU3RhdGUoe30sIFwiXCIsIHVybCk7XG4gICAgICAgICAgICB9KTtcbiAgICAgICAgfSxcblxuICAgICAgICBfb25Sb3dBY3Rpb25zRHJvcGRvd25DbGljazogZnVuY3Rpb24gKGU6IEV2ZW50KSB7XG4gICAgICAgICAgICBlLnByZXZlbnREZWZhdWx0KCk7XG5cbiAgICAgICAgICAgIGNvbnN0IHRhcmdldEVsID0gZS50YXJnZXQgYXMgSFRNTEVsZW1lbnQ7XG4gICAgICAgICAgICBjb25zdCByb3dFbCA9IHRhcmdldEVsLmNsb3Nlc3QoXCIudGFidWxhdG9yLXJvd1wiKTtcblxuICAgICAgICAgICAgaWYgKCFyb3dFbCkgcmV0dXJuO1xuXG4gICAgICAgICAgICAvLyBQbGFjZSB0aGUgZmFrZSByaWdodC1jbGljayBhdCB0aGUgYnV0dG9uIHBvc2l0aW9uXG4gICAgICAgICAgICBjb25zdCByZWN0ID0gdGFyZ2V0RWwuZ2V0Qm91bmRpbmdDbGllbnRSZWN0KCk7XG5cbiAgICAgICAgICAgIHJvd0VsLmRpc3BhdGNoRXZlbnQobmV3IE1vdXNlRXZlbnQoXCJjb250ZXh0bWVudVwiLCB7XG4gICAgICAgICAgICAgICAgYnViYmxlczogdHJ1ZSxcbiAgICAgICAgICAgICAgICBjYW5jZWxhYmxlOiB0cnVlLFxuICAgICAgICAgICAgICAgIHZpZXc6IHdpbmRvdyxcbiAgICAgICAgICAgICAgICBjbGllbnRYOiByZWN0LmxlZnQgKyByZWN0LndpZHRoIC8gMixcbiAgICAgICAgICAgICAgICBjbGllbnRZOiByZWN0LmJvdHRvbSxcbiAgICAgICAgICAgICAgICBidXR0b246IDIgICAvLyByaWdodCBjbGlja1xuICAgICAgICAgICAgfSkpO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9vbkFwcGx5RmlsdGVyczogZnVuY3Rpb24gKCkge1xuICAgICAgICAgICAgdGhpcy5fdXBkYXRlVGFibGVGaWx0ZXJzKCk7XG4gICAgICAgICAgICB0aGlzLl9yZW1vdmVVbmZpbGxlZEZpbHRlcnMoKTtcbiAgICAgICAgICAgIHRoaXMuX3VwZGF0ZUNsZWFyQnV0dG9uc1N0YXRlKCk7XG4gICAgICAgICAgICB0aGlzLl91cGRhdGVVcmwoKTtcbiAgICAgICAgICAgIHRoaXMuX3JlZnJlc2hEYXRhKCk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX3VwZGF0ZUNsZWFyQnV0dG9uc1N0YXRlOiBmdW5jdGlvbiAoKSB7XG4gICAgICAgICAgICBjb25zdCBoYXNGaWx0ZXJzID0gdGhpcy50YWJsZUZpbHRlcnMubGVuZ3RoID4gMDtcbiAgICAgICAgICAgIHRoaXMuY2xlYXJGaWx0ZXJzQnRuLmNsYXNzTGlzdC50b2dnbGUoXCJidG4tdGFibGUtZGlzYWJsZWRcIiwgIWhhc0ZpbHRlcnMpO1xuICAgICAgICAgICAgdGhpcy5jbGVhckZpbHRlcnNNb2RhbEJ0bi5jbGFzc0xpc3QudG9nZ2xlKFwiYnRuLXRhYmxlLWRpc2FibGVkXCIsICFoYXNGaWx0ZXJzKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfdXBkYXRlVGFibGVGaWx0ZXJzOiBmdW5jdGlvbiAoKSB7XG4gICAgICAgICAgICBjb25zdCBmaWx0ZXJzOiBBcnJheTxUYWJsZUZpbHRlcj4gPSBbXTtcblxuICAgICAgICAgICAgdGhpcy5maWx0ZXJzQ29udGFpbmVyLnF1ZXJ5U2VsZWN0b3JBbGwoXCIuZmlsdGVyLWl0ZW1cIikuZm9yRWFjaChmdW5jdGlvbiAoaXRlbTogSFRNTEVsZW1lbnQpIHtcbiAgICAgICAgICAgICAgICBjb25zdCBmaWVsZEVsZW1lbnQgPSBpdGVtLnF1ZXJ5U2VsZWN0b3IoXCIuZmlsdGVyLWZpZWxkXCIpIGFzIEhUTUxTZWxlY3RFbGVtZW50O1xuICAgICAgICAgICAgICAgIGNvbnN0IG9wZXJhdG9yRWxlbWVudCA9IGl0ZW0ucXVlcnlTZWxlY3RvcihcIi5maWx0ZXItb3BlcmF0b3JcIikgYXMgSFRNTFNlbGVjdEVsZW1lbnQ7XG4gICAgICAgICAgICAgICAgY29uc3QgdmFsdWVFbGVtZW50ID0gaXRlbS5xdWVyeVNlbGVjdG9yKFwiLmZpbHRlci12YWx1ZVwiKSBhcyBIVE1MSW5wdXRFbGVtZW50O1xuXG4gICAgICAgICAgICAgICAgY29uc3QgZmllbGQgPSBmaWVsZEVsZW1lbnQ/LnZhbHVlO1xuICAgICAgICAgICAgICAgIGNvbnN0IG9wZXJhdG9yID0gb3BlcmF0b3JFbGVtZW50Py52YWx1ZTtcbiAgICAgICAgICAgICAgICBjb25zdCB2YWx1ZSA9IHZhbHVlRWxlbWVudD8udmFsdWU7XG5cbiAgICAgICAgICAgICAgICBpZiAoZmllbGQgJiYgb3BlcmF0b3IgJiYgdmFsdWUpIHtcbiAgICAgICAgICAgICAgICAgICAgZmlsdGVycy5wdXNoKHsgZmllbGQsIG9wZXJhdG9yLCB2YWx1ZSB9KTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICB9KTtcblxuICAgICAgICAgICAgdGhpcy50YWJsZUZpbHRlcnMgPSBmaWx0ZXJzO1xuICAgICAgICAgICAgdGhpcy5maWx0ZXJzQ291bnRlci50ZXh0Q29udGVudCA9IGZpbHRlcnMubGVuZ3RoLnRvU3RyaW5nKCk7XG4gICAgICAgICAgICB0aGlzLmZpbHRlcnNDb3VudGVyLmNsYXNzTGlzdC50b2dnbGUoXCJkLW5vbmVcIiwgZmlsdGVycy5sZW5ndGggPT09IDApO1xuXG4gICAgICAgICAgICByZXR1cm4gZmlsdGVycztcbiAgICAgICAgfSxcblxuICAgICAgICBfcmVtb3ZlVW5maWxsZWRGaWx0ZXJzOiBmdW5jdGlvbiAoKSB7XG4gICAgICAgICAgICB0aGlzLmZpbHRlcnNDb250YWluZXIucXVlcnlTZWxlY3RvckFsbChcIi5maWx0ZXItaXRlbVwiKS5mb3JFYWNoKGZ1bmN0aW9uIChpdGVtOiBIVE1MRWxlbWVudCkge1xuICAgICAgICAgICAgICAgIGNvbnN0IGZpZWxkRWxlbWVudCA9IGl0ZW0ucXVlcnlTZWxlY3RvcihcIi5maWx0ZXItZmllbGRcIikgYXMgSFRNTFNlbGVjdEVsZW1lbnQ7XG4gICAgICAgICAgICAgICAgY29uc3Qgb3BlcmF0b3JFbGVtZW50ID0gaXRlbS5xdWVyeVNlbGVjdG9yKFwiLmZpbHRlci1vcGVyYXRvclwiKSBhcyBIVE1MU2VsZWN0RWxlbWVudDtcbiAgICAgICAgICAgICAgICBjb25zdCB2YWx1ZUVsZW1lbnQgPSBpdGVtLnF1ZXJ5U2VsZWN0b3IoXCIuZmlsdGVyLXZhbHVlXCIpIGFzIEhUTUxJbnB1dEVsZW1lbnQ7XG5cbiAgICAgICAgICAgICAgICBjb25zdCBmaWVsZCA9IGZpZWxkRWxlbWVudD8udmFsdWU7XG4gICAgICAgICAgICAgICAgY29uc3Qgb3BlcmF0b3IgPSBvcGVyYXRvckVsZW1lbnQ/LnZhbHVlO1xuICAgICAgICAgICAgICAgIGNvbnN0IHZhbHVlID0gdmFsdWVFbGVtZW50Py52YWx1ZTtcblxuICAgICAgICAgICAgICAgIGlmICghZmllbGQgfHwgIW9wZXJhdG9yIHx8ICF2YWx1ZSkge1xuICAgICAgICAgICAgICAgICAgICBpdGVtLnJlbW92ZSgpO1xuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgIH0pO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9vbkNsZWFyRmlsdGVyczogZnVuY3Rpb24gKCkge1xuICAgICAgICAgICAgdGhpcy5maWx0ZXJzQ29udGFpbmVyLmlubmVySFRNTCA9IFwiXCI7XG5cbiAgICAgICAgICAgIHRoaXMuX3VwZGF0ZVRhYmxlRmlsdGVycygpO1xuICAgICAgICAgICAgdGhpcy5fdXBkYXRlQ2xlYXJCdXR0b25zU3RhdGUoKTtcbiAgICAgICAgICAgIHRoaXMuX3VwZGF0ZVVybCgpO1xuICAgICAgICAgICAgdGhpcy5fcmVmcmVzaERhdGEoKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfb25BZGRGaWx0ZXI6IGZ1bmN0aW9uICgpIHtcbiAgICAgICAgICAgIGNvbnN0IG5ld0ZpbHRlciA9IHRoaXMuZmlsdGVyVGVtcGxhdGUuY2xvbmVOb2RlKHRydWUpO1xuICAgICAgICAgICAgbmV3RmlsdGVyLnN0eWxlLmRpc3BsYXkgPSBcImJsb2NrXCI7XG5cbiAgICAgICAgICAgIHRoaXMuZmlsdGVyc0NvbnRhaW5lci5hcHBlbmRDaGlsZChuZXdGaWx0ZXIpO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9vbkZpbHRlckl0ZW1SZW1vdmU6IGZ1bmN0aW9uIChmaWx0ZXJFbDogRWxlbWVudCkge1xuICAgICAgICAgICAgY29uc3QgcGFyZW50ID0gZmlsdGVyRWwuY2xvc2VzdChcIi5maWx0ZXItaXRlbVwiKTtcblxuICAgICAgICAgICAgaWYgKHBhcmVudCkge1xuICAgICAgICAgICAgICAgIHBhcmVudC5yZW1vdmUoKTtcbiAgICAgICAgICAgIH1cbiAgICAgICAgfSxcblxuICAgICAgICBfb25DbG9zZUZpbHRlcnM6IGZ1bmN0aW9uICgpIHtcbiAgICAgICAgICAgIHRoaXMuX3JlY3JlYXRlRmlsdGVycygpO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9yZWNyZWF0ZUZpbHRlcnM6IGZ1bmN0aW9uICgpIHtcbiAgICAgICAgICAgIHRoaXMuZmlsdGVyc0NvbnRhaW5lci5pbm5lckhUTUwgPSBcIlwiO1xuXG4gICAgICAgICAgICB0aGlzLnRhYmxlRmlsdGVycy5mb3JFYWNoKChmaWx0ZXI6IFRhYmxlRmlsdGVyKSA9PiB7XG4gICAgICAgICAgICAgICAgY29uc3QgbmV3RmlsdGVyID0gdGhpcy5maWx0ZXJUZW1wbGF0ZS5jbG9uZU5vZGUodHJ1ZSk7XG4gICAgICAgICAgICAgICAgbmV3RmlsdGVyLnN0eWxlLmRpc3BsYXkgPSBcImJsb2NrXCI7XG5cbiAgICAgICAgICAgICAgICBuZXdGaWx0ZXIucXVlcnlTZWxlY3RvcihcIi5maWx0ZXItZmllbGRcIikudmFsdWUgPSBmaWx0ZXIuZmllbGQ7XG4gICAgICAgICAgICAgICAgbmV3RmlsdGVyLnF1ZXJ5U2VsZWN0b3IoXCIuZmlsdGVyLW9wZXJhdG9yXCIpLnZhbHVlID0gZmlsdGVyLm9wZXJhdG9yO1xuICAgICAgICAgICAgICAgIG5ld0ZpbHRlci5xdWVyeVNlbGVjdG9yKFwiLmZpbHRlci12YWx1ZVwiKS52YWx1ZSA9IGZpbHRlci52YWx1ZTtcblxuICAgICAgICAgICAgICAgIHRoaXMuZmlsdGVyc0NvbnRhaW5lci5hcHBlbmRDaGlsZChuZXdGaWx0ZXIpO1xuICAgICAgICAgICAgfSk7XG5cbiAgICAgICAgICAgIHRoaXMuX3VwZGF0ZVVybCgpO1xuICAgICAgICB9LFxuXG4gICAgICAgIC8qKlxuICAgICAgICAgKiBVcGRhdGUgdGhlIFVSTCB3aXRoIHRoZSBjdXJyZW50IGFwcGxpZWQgZmlsdGVyc1xuICAgICAgICAgKi9cbiAgICAgICAgX3VwZGF0ZVVybDogZnVuY3Rpb24gKCkge1xuICAgICAgICAgICAgY29uc3QgdXJsID0gbmV3IFVSTCh3aW5kb3cubG9jYXRpb24uaHJlZik7XG5cbiAgICAgICAgICAgIC8vIENsZWFyIGV4aXN0aW5nIGZpbHRlciBwYXJhbWV0ZXJzXG4gICAgICAgICAgICBBcnJheS5mcm9tKHVybC5zZWFyY2hQYXJhbXMua2V5cygpKS5mb3JFYWNoKGtleSA9PiB7XG4gICAgICAgICAgICAgICAgaWYgKGtleS5zdGFydHNXaXRoKCdmaWVsZCcpIHx8IGtleS5zdGFydHNXaXRoKCdvcGVyYXRvcicpIHx8IGtleS5zdGFydHNXaXRoKCdxJykpIHtcbiAgICAgICAgICAgICAgICAgICAgdXJsLnNlYXJjaFBhcmFtcy5kZWxldGUoa2V5KTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICB9KTtcblxuICAgICAgICAgICAgLy8gQWRkIGN1cnJlbnQgZmlsdGVyc1xuICAgICAgICAgICAgdGhpcy50YWJsZUZpbHRlcnMuZm9yRWFjaCgoZmlsdGVyOiBUYWJsZUZpbHRlcikgPT4ge1xuICAgICAgICAgICAgICAgIHVybC5zZWFyY2hQYXJhbXMuYXBwZW5kKCdmaWVsZCcsIGZpbHRlci5maWVsZCk7XG4gICAgICAgICAgICAgICAgdXJsLnNlYXJjaFBhcmFtcy5hcHBlbmQoJ29wZXJhdG9yJywgZmlsdGVyLm9wZXJhdG9yKTtcbiAgICAgICAgICAgICAgICB1cmwuc2VhcmNoUGFyYW1zLmFwcGVuZCgncScsIGZpbHRlci52YWx1ZSk7XG4gICAgICAgICAgICB9KTtcblxuICAgICAgICAgICAgd2luZG93Lmhpc3RvcnkucmVwbGFjZVN0YXRlKHt9LCBcIlwiLCB1cmwpO1xuICAgICAgICB9LFxuXG4gICAgICAgIC8qKlxuICAgICAgICAgKiBBcHBseSB0aGUgcm93IGFjdGlvbiB0byB0aGUgc2VsZWN0ZWQgcm93c1xuICAgICAgICAgKi9cbiAgICAgICAgX29uQXBwbHlCdWxrQWN0aW9uOiBmdW5jdGlvbiAoZTogRXZlbnQpIHtcbiAgICAgICAgICAgIGNvbnN0IHRhcmdldCA9IGUuY3VycmVudFRhcmdldCBhcyBIVE1MRWxlbWVudCB8IG51bGw7XG4gICAgICAgICAgICBjb25zdCBidWxrQWN0aW9uID0gdGFyZ2V0Py5kYXRhc2V0Py5hY3Rpb247XG4gICAgICAgICAgICBjb25zdCBsYWJlbCA9IHRhcmdldD8udGV4dENvbnRlbnQ/LnRyaW0oKSB8fCBcIlwiO1xuXG4gICAgICAgICAgICBpZiAoIWJ1bGtBY3Rpb24pIHtcbiAgICAgICAgICAgICAgICByZXR1cm47XG4gICAgICAgICAgICB9XG5cbiAgICAgICAgICAgIGNrYW4udGFibGVzQ29uZmlybSh7XG4gICAgICAgICAgICAgICAgbWVzc2FnZTogY2thbi5pMThuLl8oYEFyZSB5b3Ugc3VyZSB5b3Ugd2FudCB0byBwZXJmb3JtIHRoaXMgYWN0aW9uOiA8Yj4ke2xhYmVsfTwvYj4/YCksXG4gICAgICAgICAgICAgICAgb25Db25maXJtOiAoKSA9PiB0aGlzLl9vbkJ1bGtBY3Rpb25Db25maXJtKGJ1bGtBY3Rpb24sIGxhYmVsKVxuICAgICAgICAgICAgfSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uQnVsa0FjdGlvbkNvbmZpcm06IGZ1bmN0aW9uIChidWxrQWN0aW9uOiBzdHJpbmcsIGxhYmVsOiBzdHJpbmcpIHtcbiAgICAgICAgICAgIGNvbnN0IHNlbGVjdGVkRGF0YSA9IHRoaXMudGFibGUuZ2V0U2VsZWN0ZWREYXRhKCk7XG5cbiAgICAgICAgICAgIGlmICghc2VsZWN0ZWREYXRhLmxlbmd0aCkge1xuICAgICAgICAgICAgICAgIHJldHVybjtcbiAgICAgICAgICAgIH1cblxuICAgICAgICAgICAgLy8gZXhjbHVkZSAnYWN0aW9ucycgY29sdW1uXG4gICAgICAgICAgICBjb25zdCBkYXRhID0gc2VsZWN0ZWREYXRhLm1hcCgocm93OiBSZWNvcmQ8c3RyaW5nLCBhbnk+KSA9PiB7XG4gICAgICAgICAgICAgICAgY29uc3QgeyBhY3Rpb25zLCAuLi5yZXN0IH0gPSByb3c7XG4gICAgICAgICAgICAgICAgcmV0dXJuIHJlc3Q7XG4gICAgICAgICAgICB9KTtcblxuICAgICAgICAgICAgY29uc3QgZm9ybSA9IG5ldyBGb3JtRGF0YSgpO1xuXG4gICAgICAgICAgICBmb3JtLmFwcGVuZChcImJ1bGtfYWN0aW9uXCIsIGJ1bGtBY3Rpb24pO1xuICAgICAgICAgICAgZm9ybS5hcHBlbmQoXCJyb3dzXCIsIEpTT04uc3RyaW5naWZ5KGRhdGEpKTtcblxuICAgICAgICAgICAgZmV0Y2godGhpcy5zYW5kYm94LmNsaWVudC51cmwodGhpcy5vcHRpb25zLmNvbmZpZy5hamF4VVJMKSwge1xuICAgICAgICAgICAgICAgIG1ldGhvZDogXCJQT1NUXCIsXG4gICAgICAgICAgICAgICAgYm9keTogZm9ybSxcbiAgICAgICAgICAgICAgICBoZWFkZXJzOiB7XG4gICAgICAgICAgICAgICAgICAgICdYLUNTUkZUb2tlbic6IHRoaXMuX2dldENTUkZUb2tlbigpXG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgfSlcbiAgICAgICAgICAgICAgICAudGhlbihyZXNwID0+IHJlc3AuanNvbigpKVxuICAgICAgICAgICAgICAgIC50aGVuKHJlc3AgPT4ge1xuICAgICAgICAgICAgICAgICAgICBpZiAoIXJlc3Auc3VjY2Vzcykge1xuICAgICAgICAgICAgICAgICAgICAgICAgY2thbi50YWJsZXNUb2FzdCh7IG1lc3NhZ2U6IHJlc3AuZXJyb3JzWzBdLCB0eXBlOiBcImRhbmdlclwiLCB0aXRsZTogY2thbi5pMThuLl8oXCJUYWJsZXNcIikgfSk7XG5cbiAgICAgICAgICAgICAgICAgICAgICAgIGlmIChyZXNwLmVycm9ycy5sZW5ndGggPiAxKSB7XG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgY2thbi50YWJsZXNUb2FzdCh7XG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIG1lc3NhZ2U6IGNrYW4uaTE4bi5fKFwiTXVsdGlwbGUgZXJyb3JzIG9jY3VycmVkIGFuZCB3ZXJlIHN1cHByZXNzZWRcIiksXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgIHR5cGU6IFwiZXJyb3JcIixcbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgdGl0bGU6IGNrYW4uaTE4bi5fKFwiVGFibGVzXCIpLFxuICAgICAgICAgICAgICAgICAgICAgICAgICAgIH0pO1xuICAgICAgICAgICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgICAgICAgICB9IGVsc2Uge1xuICAgICAgICAgICAgICAgICAgICAgICAgdGhpcy5fcmVmcmVzaERhdGEoKVxuICAgICAgICAgICAgICAgICAgICAgICAgY2thbi50YWJsZXNUb2FzdCh7XG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgbWVzc2FnZTogY2thbi5pMThuLl8oYEJ1bGsgYWN0aW9uIGNvbXBsZXRlZDogPGI+JHtsYWJlbH08L2I+YCksXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgdGl0bGU6IGNrYW4uaTE4bi5fKFwiVGFibGVzXCIpLFxuICAgICAgICAgICAgICAgICAgICAgICAgfSk7XG4gICAgICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICB9KS5jYXRjaChlcnJvciA9PiB7XG4gICAgICAgICAgICAgICAgICAgIGNrYW4udGFibGVzVG9hc3QoeyBtZXNzYWdlOiBlcnJvci5tZXNzYWdlLCB0eXBlOiBcImRhbmdlclwiLCB0aXRsZTogY2thbi5pMThuLl8oXCJUYWJsZXNcIikgfSk7XG4gICAgICAgICAgICAgICAgfSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uQXBwbHlUYWJsZUFjdGlvbjogZnVuY3Rpb24gKGU6IEV2ZW50KSB7XG4gICAgICAgICAgICBjb25zdCB0YXJnZXQgPSBlLmN1cnJlbnRUYXJnZXQgYXMgSFRNTEVsZW1lbnQ7XG4gICAgICAgICAgICBjb25zdCBhY3Rpb24gPSB0YXJnZXQuZGF0YXNldC5hY3Rpb247XG4gICAgICAgICAgICBjb25zdCBsYWJlbCA9IHRhcmdldC50ZXh0Q29udGVudDtcblxuICAgICAgICAgICAgaWYgKCFhY3Rpb24pIHtcbiAgICAgICAgICAgICAgICByZXR1cm47XG4gICAgICAgICAgICB9XG5cbiAgICAgICAgICAgIGNrYW4udGFibGVzQ29uZmlybSh7XG4gICAgICAgICAgICAgICAgbWVzc2FnZTogY2thbi5pMThuLl8oYEFyZSB5b3Ugc3VyZSB5b3Ugd2FudCB0byBwZXJmb3JtIHRoaXMgYWN0aW9uOiA8Yj4ke2xhYmVsfTwvYj4/YCksXG4gICAgICAgICAgICAgICAgb25Db25maXJtOiAoKSA9PiB0aGlzLl9vblRhYmxlQWN0aW9uQ29uZmlybShhY3Rpb24sIGxhYmVsKVxuICAgICAgICAgICAgfSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uVGFibGVBY3Rpb25Db25maXJtOiBmdW5jdGlvbiAoYWN0aW9uOiBzdHJpbmcsIGxhYmVsOiBzdHJpbmcpIHtcbiAgICAgICAgICAgIGNvbnN0IGZvcm0gPSBuZXcgRm9ybURhdGEoKTtcblxuICAgICAgICAgICAgZm9ybS5hcHBlbmQoXCJ0YWJsZV9hY3Rpb25cIiwgYWN0aW9uKTtcblxuICAgICAgICAgICAgZmV0Y2godGhpcy5zYW5kYm94LmNsaWVudC51cmwodGhpcy5vcHRpb25zLmNvbmZpZy5hamF4VVJMKSwge1xuICAgICAgICAgICAgICAgIG1ldGhvZDogXCJQT1NUXCIsXG4gICAgICAgICAgICAgICAgYm9keTogZm9ybSxcbiAgICAgICAgICAgICAgICBoZWFkZXJzOiB7XG4gICAgICAgICAgICAgICAgICAgICdYLUNTUkZUb2tlbic6IHRoaXMuX2dldENTUkZUb2tlbigpXG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgfSlcbiAgICAgICAgICAgICAgICAudGhlbihyZXNwID0+IHJlc3AuanNvbigpKVxuICAgICAgICAgICAgICAgIC50aGVuKHJlc3AgPT4ge1xuICAgICAgICAgICAgICAgICAgICBpZiAoIXJlc3Auc3VjY2Vzcykge1xuICAgICAgICAgICAgICAgICAgICAgICAgY2thbi50YWJsZXNUb2FzdCh7IG1lc3NhZ2U6IHJlc3AuZXJyb3IsIHR5cGU6IFwiZGFuZ2VyXCIsIHRpdGxlOiBja2FuLmkxOG4uXyhcIlRhYmxlc1wiKSB9KTtcbiAgICAgICAgICAgICAgICAgICAgfSBlbHNlIHtcbiAgICAgICAgICAgICAgICAgICAgICAgIGlmIChyZXNwLnJlZGlyZWN0KSB7XG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgd2luZG93LmxvY2F0aW9uLmhyZWYgPSByZXNwLnJlZGlyZWN0O1xuICAgICAgICAgICAgICAgICAgICAgICAgICAgIHJldHVybjtcbiAgICAgICAgICAgICAgICAgICAgICAgIH1cblxuICAgICAgICAgICAgICAgICAgICAgICAgdGhpcy5fcmVmcmVzaERhdGEoKVxuXG4gICAgICAgICAgICAgICAgICAgICAgICBsZXQgbWVzc2FnZSA9IHJlc3AubWVzc2FnZSB8fCBja2FuLmkxOG4uXyhgVGFibGUgYWN0aW9uIGNvbXBsZXRlZDogPGI+JHtsYWJlbH08L2I+YCk7XG5cbiAgICAgICAgICAgICAgICAgICAgICAgIGNrYW4udGFibGVzVG9hc3Qoe1xuICAgICAgICAgICAgICAgICAgICAgICAgICAgIG1lc3NhZ2U6IG1lc3NhZ2UsXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgdGl0bGU6IGNrYW4uaTE4bi5fKFwiVGFibGVzXCIpLFxuICAgICAgICAgICAgICAgICAgICAgICAgfSk7XG4gICAgICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICB9KS5jYXRjaChlcnJvciA9PiB7XG4gICAgICAgICAgICAgICAgICAgIGNrYW4udGFibGVzVG9hc3QoeyBtZXNzYWdlOiBlcnJvci5tZXNzYWdlLCB0eXBlOiBcImRhbmdlclwiLCB0aXRsZTogY2thbi5pMThuLl8oXCJUYWJsZXNcIikgfSk7XG4gICAgICAgICAgICAgICAgfSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uVGFibGVFeHBvcnRDbGljazogZnVuY3Rpb24gKGU6IEV2ZW50KSB7XG4gICAgICAgICAgICBjb25zdCBleHBvcnRlciA9IChlLnRhcmdldCBhcyBIVE1MRWxlbWVudCkuZGF0YXNldC5leHBvcnRlcjtcblxuICAgICAgICAgICAgaWYgKCFleHBvcnRlcikge1xuICAgICAgICAgICAgICAgIHJldHVybjtcbiAgICAgICAgICAgIH1cblxuICAgICAgICAgICAgY29uc3QgYSA9IGRvY3VtZW50LmNyZWF0ZUVsZW1lbnQoJ2EnKTtcbiAgICAgICAgICAgIGNvbnN0IHVybCA9IG5ldyBVUkwod2luZG93LmxvY2F0aW9uLmhyZWYpXG5cbiAgICAgICAgICAgIHVybC5zZWFyY2hQYXJhbXMuc2V0KFwiZXhwb3J0ZXJcIiwgZXhwb3J0ZXIpO1xuICAgICAgICAgICAgdXJsLnNlYXJjaFBhcmFtcy5zZXQoXCJmaWx0ZXJzXCIsIEpTT04uc3RyaW5naWZ5KHRoaXMudGFibGVGaWx0ZXJzKSk7XG5cbiAgICAgICAgICAgIHRoaXMudGFibGUuZ2V0U29ydGVycygpLmZvckVhY2goKGVsZW1lbnQ6IHsgZmllbGQ6IHN0cmluZzsgZGlyOiBzdHJpbmcgfSkgPT4ge1xuICAgICAgICAgICAgICAgIHVybC5zZWFyY2hQYXJhbXMuc2V0KGBzb3J0WzBdW2ZpZWxkXWAsIGVsZW1lbnQuZmllbGQpO1xuICAgICAgICAgICAgICAgIHVybC5zZWFyY2hQYXJhbXMuc2V0KGBzb3J0WzBdW2Rpcl1gLCBlbGVtZW50LmRpcik7XG4gICAgICAgICAgICB9KTtcblxuICAgICAgICAgICAgYS5ocmVmID0gdGhpcy5zYW5kYm94LmNsaWVudC51cmwodGhpcy5vcHRpb25zLmNvbmZpZy5leHBvcnRVUkwpICsgdXJsLnNlYXJjaDtcbiAgICAgICAgICAgIGEuZG93bmxvYWQgPSBgJHt0aGlzLm9wdGlvbnMuY29uZmlnLnRhYmxlSWQgfHwgJ3RhYmxlJ30uJHtleHBvcnRlcn1gO1xuICAgICAgICAgICAgZG9jdW1lbnQuYm9keS5hcHBlbmRDaGlsZChhKTtcbiAgICAgICAgICAgIGEuY2xpY2soKTtcbiAgICAgICAgICAgIGRvY3VtZW50LmJvZHkucmVtb3ZlQ2hpbGQoYSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX3JlZnJlc2hEYXRhOiBmdW5jdGlvbiAoKSB7XG4gICAgICAgICAgICB0aGlzLnRhYmxlLnJlcGxhY2VEYXRhKCk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uRnVsbHNjcmVlbjogZnVuY3Rpb24gKCkge1xuICAgICAgICAgICAgdGhpcy50YWJsZVdyYXBwZXIuY2xhc3NMaXN0LnRvZ2dsZShcImZ1bGxzY3JlZW5cIik7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX2dldENTUkZUb2tlbjogZnVuY3Rpb24gKCkge1xuICAgICAgICAgICAgY29uc3QgY3NyZl9maWVsZCA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoJ21ldGFbbmFtZT1cImNzcmZfZmllbGRfbmFtZVwiXScpPy5nZXRBdHRyaWJ1dGUoJ2NvbnRlbnQnKTtcbiAgICAgICAgICAgIGNvbnN0IGNzcmZfdG9rZW4gPSBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKGBtZXRhW25hbWU9XCIke2NzcmZfZmllbGR9XCJdYCk/LmdldEF0dHJpYnV0ZSgnY29udGVudCcpO1xuXG4gICAgICAgICAgICByZXR1cm4gY3NyZl90b2tlbjtcbiAgICAgICAgfVxuICAgIH07XG59KTtcblxuLyoqXG4gKiBSZXRyaWV2ZXMgdGhlIHZhbHVlIG9mIGEgc3BlY2lmaWVkIHF1ZXJ5IHN0cmluZyBwYXJhbWV0ZXIgZnJvbSB0aGUgY3VycmVudCBVUkwuXG4gKlxuICogQHBhcmFtIHtzdHJpbmd9IG5hbWUgVGhlIG5hbWUgb2YgdGhlIHF1ZXJ5IHBhcmFtZXRlciB3aG9zZSB2YWx1ZSB5b3Ugd2FudCB0byByZXRyaWV2ZS5cbiAqIEByZXR1cm5zIHtzdHJpbmd8bnVsbH0gVGhlIHZhbHVlIG9mIHRoZSBmaXJzdCBxdWVyeSBwYXJhbWV0ZXIgd2l0aCB0aGUgc3BlY2lmaWVkIG5hbWUsIG9yIG51bGwgaWYgdGhlIHBhcmFtZXRlciBpcyBub3QgZm91bmQuXG4qL1xuZnVuY3Rpb24gZ2V0UXVlcnlQYXJhbShuYW1lOiBzdHJpbmcpOiBzdHJpbmcgfCBudWxsIHtcbiAgICBjb25zdCBwYXJhbXMgPSBuZXcgVVJMU2VhcmNoUGFyYW1zKHdpbmRvdy5sb2NhdGlvbi5zZWFyY2gpO1xuICAgIHJldHVybiBwYXJhbXMuZ2V0KG5hbWUpO1xufVxuIl19