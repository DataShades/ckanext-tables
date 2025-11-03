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
                this._showToast(ckan.i18n._("No config provided for tabulator"), "danger");
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
                this.options.config.rowContextMenu = Object.values(rowActions).map((action) => ({
                    label: `${action.icon ? `<i class='${action.icon} me-1'></i> ` : ''}${action.label}`,
                    action: this._rowActionCallback.bind(this, action)
                }));
            }
            if (this.options.config.rowHeader) {
                this.options.config.rowHeader.cellClick = function (e, cell) {
                    cell.getRow().toggleSelect();
                };
            }
            let initialPage = new URLSearchParams(window.location.search).get("page");
            this.table = new Tabulator(this.el[0], {
                ...this.options.config,
                paginationInitialPage: parseInt(initialPage || "1"),
                footerElement: this.templates.footerElement,
                ajaxParams: () => ({ filters: JSON.stringify(this.tableFilters) })
            });
        },
        _showToast: function (message, type = "default") {
            ckan.tablesToast({
                message,
                type,
                title: ckan.i18n._("Tables"),
            });
        },
        _confirmAction: function (label, callback) {
            ckan.tablesConfirm({
                message: ckan.i18n._(`Are you sure you want to perform this action: <b>${label}</b>?`),
                onConfirm: callback
            });
        },
        _rowActionCallback: function (action, e, row) {
            if (action.with_confirmation) {
                this._confirmAction(action.label, () => this._onRowActionConfirm(action, row));
            }
            else {
                this._onRowActionConfirm(action, row);
            }
        },
        _onRowActionConfirm: function (action, row) {
            const form = new FormData();
            form.append("row_action", action.name);
            form.append("row", JSON.stringify(row.getData()));
            this._sendActionRequest(form, ckan.i18n._(`Row action completed: <b>${action.label}</b>`));
        },
        _sendActionRequest: function (form, successMessage) {
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
                        this._showToast(ckan.i18n._("Multiple errors occurred and were suppressed"), "error");
                    }
                }
                else {
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
        _initAddTableEvents: function () {
            this.applyFiltersBtn.addEventListener("click", this._onApplyFilters);
            this.clearFiltersModalBtn.addEventListener("click", this._onClearFilters);
            this.clearFiltersBtn.addEventListener("click", this._onClearFilters);
            this.addFilterBtn.addEventListener("click", this._onAddFilter);
            this.closeFiltersBtn.addEventListener("click", this._onCloseFilters);
            this.filtersContainer.addEventListener("click", (e) => {
                const removeBtn = e.target.closest(".btn-remove-filter");
                if (removeBtn && this.filtersContainer.contains(removeBtn)) {
                    this._onFilterItemRemove(removeBtn);
                }
            });
            const bindMenuButtons = (menu, handler) => {
                if (menu) {
                    menu.querySelectorAll("button").forEach((btn) => {
                        btn.addEventListener("click", handler);
                    });
                }
            };
            bindMenuButtons(this.bulkActionsMenu, this._onApplyBulkAction);
            bindMenuButtons(this.tableActionsMenu, this._onApplyTableAction);
            bindMenuButtons(this.tableExportersMenu, this._onTableExportClick);
            document.addEventListener("click", (e) => {
                const rowActionsBtn = e.target.closest(".btn-row-actions");
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
            this.table.on("renderComplete", function () {
                htmx.process(this.element);
                const pageSizeSelect = document.querySelector(".tabulator-page-size");
                if (pageSizeSelect)
                    pageSizeSelect.classList.add("form-select");
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
        _collectValidFilters: function () {
            const filters = [];
            this.filtersContainer.querySelectorAll(".filter-item").forEach((item) => {
                const field = item.querySelector(".filter-field")?.value;
                const operator = item.querySelector(".filter-operator")?.value;
                const value = item.querySelector(".filter-value")?.value;
                if (field && operator && value)
                    filters.push({ field, operator, value });
            });
            return filters;
        },
        _updateTableFilters: function () {
            this.tableFilters = this._collectValidFilters();
            this.filtersCounter.textContent = this.tableFilters.length.toString();
            this.filtersCounter.classList.toggle("d-none", this.tableFilters.length === 0);
            return this.tableFilters;
        },
        _removeUnfilledFilters: function () {
            this.filtersContainer.querySelectorAll(".filter-item").forEach((item) => {
                const field = item.querySelector(".filter-field")?.value;
                const operator = item.querySelector(".filter-operator")?.value;
                const value = item.querySelector(".filter-value")?.value;
                if (!field || !operator || !value)
                    item.remove();
            });
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
            if (parent)
                parent.remove();
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
        _updateUrl: function () {
            const url = new URL(window.location.href);
            Array.from(url.searchParams.keys()).forEach(key => {
                if (key.startsWith('field') || key.startsWith('operator') || key.startsWith('q')) {
                    url.searchParams.delete(key);
                }
            });
            this.tableFilters.forEach((filter) => {
                url.searchParams.append('field', filter.field);
                url.searchParams.append('operator', filter.operator);
                url.searchParams.append('q', filter.value);
            });
            window.history.replaceState({}, "", url);
        },
        _onApplyBulkAction: function (e) {
            const target = e.currentTarget;
            const action = target.dataset.action;
            const label = target.textContent?.trim() || "";
            if (!action)
                return;
            this._confirmAction(label, () => this._onBulkActionConfirm(action, label));
        },
        _onBulkActionConfirm: function (bulkAction, label) {
            const selectedData = this.table.getSelectedData();
            if (!selectedData.length)
                return;
            const data = selectedData.map(({ actions, ...rest }) => rest);
            const form = new FormData();
            form.append("bulk_action", bulkAction);
            form.append("rows", JSON.stringify(data));
            this._sendActionRequest(form, ckan.i18n._(`Bulk action completed: <b>${label}</b>`));
        },
        _onApplyTableAction: function (e) {
            const target = e.currentTarget;
            const action = target.dataset.action;
            const label = target.textContent?.trim() || "";
            if (!action)
                return;
            this._confirmAction(label, () => this._onTableActionConfirm(action, label));
        },
        _onTableActionConfirm: function (action, label) {
            const form = new FormData();
            form.append("table_action", action);
            this._sendActionRequest(form, ckan.i18n._(`Table action completed: <b>${label}</b>`));
        },
        _onTableExportClick: function (e) {
            const exporter = e.target.dataset.exporter;
            if (!exporter)
                return;
            const a = document.createElement('a');
            const url = new URL(window.location.href);
            url.searchParams.set("exporter", exporter);
            url.searchParams.set("filters", JSON.stringify(this.tableFilters));
            this.table.getSorters().forEach((s) => {
                url.searchParams.set(`sort[0][field]`, s.field);
                url.searchParams.set(`sort[0][dir]`, s.dir);
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
            return document.querySelector(`meta[name="${csrf_field}"]`)?.getAttribute('content') || null;
        }
    };
});
//# sourceMappingURL=data:application/json;base64,eyJ2ZXJzaW9uIjozLCJmaWxlIjoidGFibGVzLXRhYnVsYXRvci5qcyIsInNvdXJjZVJvb3QiOiIiLCJzb3VyY2VzIjpbIi4uL3RzL3RhYmxlcy10YWJ1bGF0b3IudHMiXSwibmFtZXMiOltdLCJtYXBwaW5ncyI6IkFBQUE7Ozs7Ozs7RUFPRTtBQUVGLElBQVUsSUFBSSxDQVNiO0FBVEQsV0FBVSxJQUFJO0FBU2QsQ0FBQyxFQVRTLElBQUksS0FBSixJQUFJLFFBU2I7QUF3QkQsSUFBSSxDQUFDLE1BQU0sQ0FBQyxrQkFBa0IsRUFBRSxVQUFVLENBQUM7SUFDdkMsWUFBWSxDQUFDO0lBQ2IsT0FBTztRQUNILFNBQVMsRUFBRTtZQUNQLGFBQWEsRUFBRTs7bUJBRVI7U0FDVjtRQUNELE9BQU8sRUFBRTtZQUNMLE1BQU0sRUFBRSxJQUFXO1lBQ25CLFVBQVUsRUFBRSxJQUE4QztZQUMxRCxzQkFBc0IsRUFBRSxJQUFJO1NBQy9CO1FBRUQsVUFBVSxFQUFFO1lBQ1IsQ0FBQyxDQUFDLFFBQVEsQ0FBQyxJQUFJLEVBQUUsR0FBRyxDQUFDLENBQUM7WUFFdEIsSUFBSSxDQUFDLElBQUksQ0FBQyxPQUFPLENBQUMsTUFBTSxFQUFFLENBQUM7Z0JBQ3ZCLElBQUksQ0FBQyxVQUFVLENBQUMsSUFBSSxDQUFDLElBQUksQ0FBQyxDQUFDLENBQUMsa0NBQWtDLENBQUMsRUFBRSxRQUFRLENBQUMsQ0FBQztnQkFDM0UsT0FBTztZQUNYLENBQUM7WUFFRCxJQUFJLENBQUMsb0JBQW9CLEVBQUUsQ0FBQztZQUM1QixJQUFJLENBQUMsc0JBQXNCLEVBQUUsQ0FBQztZQUM5QixJQUFJLENBQUMsbUJBQW1CLEVBQUUsQ0FBQztZQUMzQixJQUFJLENBQUMsd0JBQXdCLEVBQUUsQ0FBQztZQUVoQyxJQUFJLENBQUMsT0FBTyxDQUFDLFNBQVMsQ0FBQywwQkFBMEIsRUFBRSxJQUFJLENBQUMsWUFBWSxDQUFDLENBQUM7UUFDMUUsQ0FBQztRQUVELG9CQUFvQixFQUFFO1lBQ2xCLElBQUksQ0FBQyxnQkFBZ0IsR0FBRyxRQUFR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QUFDO1lBQzdCLENBQUMsQ0FBQyxLQUFLLEVBQUUsQ0FBQztZQUNWLFFBQVEsQ0FBQyxJQUFJLENBQUMsV0FBVyxDQUFDLENBQUMsQ0FBQyxDQUFDO1FBQ2pDLENBQUM7UUFFRCxZQUFZLEVBQUU7WUFDVixJQUFJLENBQUMsS0FBSyxDQUFDLFdBQVcsRUFBRSxDQUFDO1FBQzdCLENBQUM7UUFFRCxhQUFhLEVBQUU7WUFDWCxJQUFJLENBQUMsWUFBWSxDQUFDLFNBQVMsQ0FBQyxNQUFNLENBQUMsWUFBWSxDQUFDLENBQUM7UUFDckQsQ0FBQztRQUVELGFBQWEsRUFBRTtZQUNYLE1BQU0sVUFBVSxHQUFHLFFBQVEsQ0FBQyxhQUFhLENBQUMsOEJBQThCLENBQUMsRUFBRSxZQUFZLENBQUMsU0FBUyxDQUFDLENBQUM7WUFDbkcsT0FBTyxRQUFRLENBQUMsYUFBYSxDQUFDLGNBQWMsVUFBVSxJQUFJLENBQUMsRUFBRSxZQUFZLENBQUMsU0FBUyxDQUFDLElBQUksSUFBSSxDQUFDO1FBQ2pHLENBQUM7S0FDSixDQUFDO0FBQ04sQ0FBQyxDQUFDLENBQUMiLCJzb3VyY2VzQ29udGVudCI6WyIvKipcbiAqIFRhYnVsYXRvciBpbnRlZ3JhdGlvbiBmb3IgY2thbmV4dC10YWJsZXNcbiAqXG4gKiBOb3RlOlxuICogIFJlcGxhY2UgdGhlIGBja2FuLnRhYmxlc0NvbmZpcm1gIGFuZCBgY2thbi50YWJsZXNUb2FzdGAgZnVuY3Rpb25zIHdpdGggdGhlIGBja2FuLmNvbmZpcm1gIGFuZCBgY2thbi50b2FzdGAgZnJvbSBDS0FOIGNvcmVcbiAqICB3aGVuIENLQU4gMi4xMiBpcyB0aGUgbWluaW11bSBzdXBwb3J0ZWQgdmVyc2lvbi5cbiAqXG4qL1xuXG5uYW1lc3BhY2UgY2thbiB7XG4gICAgZXhwb3J0IHZhciBzYW5kYm94OiBhbnk7XG4gICAgZXhwb3J0IHZhciBwdWJzdWI6IGFueTtcbiAgICBleHBvcnQgdmFyIG1vZHVsZTogKG5hbWU6IHN0cmluZywgaW5pdGlhbGl6ZXI6ICgkOiBhbnkpID0+IGFueSkgPT4gYW55O1xuICAgIGV4cG9ydCB2YXIgaTE4bjoge1xuICAgICAgICBfOiAobXNnaWQ6IHN0cmluZykgPT4gc3RyaW5nO1xuICAgIH07XG4gICAgZXhwb3J0IHZhciB0YWJsZXNUb2FzdDogKG9wdGlvbnM6IHsgbWVzc2FnZTogc3RyaW5nOyB0eXBlPzogc3RyaW5nOyB0aXRsZT86IHN0cmluZyB9KSA9PiB2b2lkO1xuICAgIGV4cG9ydCB2YXIgdGFibGVzQ29uZmlybTogKG9wdGlvbnM6IHsgbWVzc2FnZTogc3RyaW5nOyBvbkNvbmZpcm06ICgpID0+IHZvaWQgfSkgPT4gdm9pZDtcbn1cblxudHlwZSBUYWJsZUZpbHRlciA9IHtcbiAgICBmaWVsZDogc3RyaW5nO1xuICAgIG9wZXJhdG9yOiBzdHJpbmc7XG4gICAgdmFsdWU6IHN0cmluZztcbn07XG5cbnR5cGUgVGFidWxhdG9yUm93ID0ge1xuICAgIGdldERhdGE6ICgpID0+IFJlY29yZDxzdHJpbmcsIGFueT47XG59O1xuXG50eXBlIFRhYnVsYXRvckFjdGlvbiA9IHtcbiAgICBuYW1lOiBzdHJpbmc7XG4gICAgbGFiZWw6IHN0cmluZztcbiAgICBpY29uPzogc3RyaW5nO1xuICAgIHdpdGhfY29uZmlybWF0aW9uPzogYm9vbGVhbjtcbn07XG5cbmRlY2xhcmUgdmFyIFRhYnVsYXRvcjogYW55O1xuZGVjbGFyZSB2YXIgaHRteDoge1xuICAgIHByb2Nlc3M6IChlbGVtZW50OiBIVE1MRWxlbWVudCkgPT4gdm9pZDtcbn07XG5cbmNrYW4ubW9kdWxlKFwidGFibGVzLXRhYnVsYXRvclwiLCBmdW5jdGlvbiAoJCkge1xuICAgIFwidXNlIHN0cmljdFwiO1xuICAgIHJldHVybiB7XG4gICAgICAgIHRlbXBsYXRlczoge1xuICAgICAgICAgICAgZm9vdGVyRWxlbWVudDogYDxkaXYgY2xhc3M9J2QtZmxleCBqdXN0aWZ5LWNvbnRlbnQtYmV0d2VlbiBhbGlnbi1pdGVtcy1jZW50ZXIgZ2FwLTInPlxuICAgICAgICAgICAgICAgIDxhIGNsYXNzPSdidG4gYnRuLWxpZ2h0IGQtbm9uZSBkLXNtLWlubGluZS1ibG9jaycgaWQ9J2J0bi1mdWxsc2NyZWVuJyB0aXRsZT0nRnVsbHNjcmVlbiB0b2dnbGUnPjxpIGNsYXNzPSdmYSBmYS1leHBhbmQnPjwvaT48L2E+XG4gICAgICAgICAgICA8L2Rpdj5gLFxuICAgICAgICB9LFxuICAgICAgICBvcHRpb25zOiB7XG4gICAgICAgICAgICBjb25maWc6IG51bGwgYXMgYW55LFxuICAgICAgICAgICAgcm93QWN0aW9uczogbnVsbCBhcyBSZWNvcmQ8c3RyaW5nLCBUYWJ1bGF0b3JBY3Rpb24+IHwgbnVsbCxcbiAgICAgICAgICAgIGVuYWJsZUZ1bGxzY3JlZW5Ub2dnbGU6IHRydWUsXG4gICAgICAgIH0sXG5cbiAgICAgICAgaW5pdGlhbGl6ZTogZnVuY3Rpb24gKCk6IHZvaWQge1xuICAgICAgICAgICAgJC5wcm94eUFsbCh0aGlzLCAvXy8pO1xuXG4gICAgICAgICAgICBpZiAoIXRoaXMub3B0aW9ucy5jb25maWcpIHtcbiAgICAgICAgICAgICAgICB0aGlzLl9zaG93VG9hc3QoY2thbi5pMThuLl8oXCJObyBjb25maWcgcHJvdmlkZWQgZm9yIHRhYnVsYXRvclwiKSwgXCJkYW5nZXJcIik7XG4gICAgICAgICAgICAgICAgcmV0dXJuO1xuICAgICAgICAgICAgfVxuXG4gICAgICAgICAgICB0aGlzLl9pbml0QXNzaWduVmFyaWFibGVzKCk7XG4gICAgICAgICAgICB0aGlzLl9pbml0VGFidWxhdG9ySW5zdGFuY2UoKTtcbiAgICAgICAgICAgIHRoaXMuX2luaXRBZGRUYWJsZUV2ZW50cygpO1xuICAgICAgICAgICAgdGhpcy5fdXBkYXRlQ2xlYXJCdXR0b25zU3RhdGUoKTtcblxuICAgICAgICAgICAgdGhpcy5zYW5kYm94LnN1YnNjcmliZShcInRhYmxlczp0YWJ1bGF0b3I6cmVmcmVzaFwiLCB0aGlzLl9yZWZyZXNoRGF0YSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX2luaXRBc3NpZ25WYXJpYWJsZXM6IGZ1bmN0aW9uICgpOiB2b2lkIHtcbiAgICAgICAgICAgIHRoaXMuZmlsdGVyc0NvbnRhaW5lciA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiZmlsdGVycy1jb250YWluZXJcIik7XG4gICAgICAgICAgICB0aGlzLmFwcGx5RmlsdGVyc0J0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiYXBwbHktZmlsdGVyc1wiKTtcbiAgICAgICAgICAgIHRoaXMuY2xlYXJGaWx0ZXJzTW9kYWxCdG4gPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChcImNsZWFyLWZpbHRlcnNcIik7XG4gICAgICAgICAgICB0aGlzLmNsZWFyRmlsdGVyc0J0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiY2xlYXItYWxsLWZpbHRlcnNcIik7XG4gICAgICAgICAgICB0aGlzLmZpbHRlclRlbXBsYXRlID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJmaWx0ZXItdGVtcGxhdGVcIik7XG4gICAgICAgICAgICB0aGlzLmFkZEZpbHRlckJ0biA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiYWRkLWZpbHRlclwiKTtcbiAgICAgICAgICAgIHRoaXMuY2xvc2VGaWx0ZXJzQnRuID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJjbG9zZS1maWx0ZXJzXCIpO1xuICAgICAgICAgICAgdGhpcy5maWx0ZXJzQ291bnRlciA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiZmlsdGVycy1jb3VudGVyXCIpO1xuICAgICAgICAgICAgdGhpcy5idWxrQWN0aW9uc01lbnUgPSBkb2N1bWVudC5nZXRFbGVtZW50QnlJZChcImJ1bGstYWN0aW9ucy1tZW51XCIpO1xuICAgICAgICAgICAgdGhpcy50YWJsZUFjdGlvbnNNZW51ID0gZG9jdW1lbnQuZ2V0RWxlbWVudEJ5SWQoXCJ0YWJsZS1hY3Rpb25zLW1lbnVcIik7XG4gICAgICAgICAgICB0aGlzLnRhYmxlRXhwb3J0ZXJzTWVudSA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwidGFibGUtZXhwb3J0ZXJzLW1lbnVcIik7XG4gICAgICAgICAgICB0aGlzLnRhYmxlV3JhcHBlciA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoXCIudGFidWxhdG9yLXdyYXBwZXJcIik7XG4gICAgICAgICAgICB0aGlzLnRhYmxlRmlsdGVycyA9IHRoaXMuX3VwZGF0ZVRhYmxlRmlsdGVycygpO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9pbml0VGFidWxhdG9ySW5zdGFuY2U6IGZ1bmN0aW9uICgpOiB2b2lkIHtcbiAgICAgICAgICAgIGlmICh0aGlzLm9wdGlvbnMucm93QWN0aW9ucykge1xuICAgICAgICAgICAgICAgIGNvbnN0IHJvd0FjdGlvbnMgPSB0aGlzLm9wdGlvbnMucm93QWN0aW9ucyBhcyBSZWNvcmQ8c3RyaW5nLCBUYWJ1bGF0b3JBY3Rpb24+O1xuICAgICAgICAgICAgICAgIHRoaXMub3B0aW9ucy5jb25maWcucm93Q29udGV4dE1lbnUgPSBPYmplY3QudmFsdWVzKHJvd0FjdGlvbnMpLm1hcCgoYWN0aW9uOiBUYWJ1bGF0b3JBY3Rpb24pID0+ICh7XG4gICAgICAgICAgICAgICAgICAgIGxhYmVsOiBgJHthY3Rpb24uaWNvbiA/IGA8aSBjbGFzcz0nJHthY3Rpb24uaWNvbn0gbWUtMSc+PC9pPiBgIDogJyd9JHthY3Rpb24ubGFiZWx9YCxcbiAgICAgICAgICAgICAgICAgICAgYWN0aW9uOiB0aGlzLl9yb3dBY3Rpb25DYWxsYmFjay5iaW5kKHRoaXMsIGFjdGlvbilcbiAgICAgICAgICAgICAgICB9KSk7XG4gICAgICAgICAgICB9XG5cbiAgICAgICAgICAgIGlmICh0aGlzLm9wdGlvbnMuY29uZmlnLnJvd0hlYWRlcikge1xuICAgICAgICAgICAgICAgIHRoaXMub3B0aW9ucy5jb25maWcucm93SGVhZGVyLmNlbGxDbGljayA9IGZ1bmN0aW9uIChlOiBFdmVudCwgY2VsbDogYW55KSB7XG4gICAgICAgICAgICAgICAgICAgIGNlbGwuZ2V0Um93KCkudG9nZ2xlU2VsZWN0KCk7XG4gICAgICAgICAgICAgICAgfTtcbiAgICAgICAgICAgIH1cblxuICAgICAgICAgICAgbGV0IGluaXRpYWxQYWdlID0gbmV3IFVSTFNlYXJjaFBhcmFtcyh3aW5kb3cubG9jYXRpb24uc2VhcmNoKS5nZXQoXCJwYWdlXCIpO1xuXG4gICAgICAgICAgICB0aGlzLnRhYmxlID0gbmV3IFRhYnVsYXRvcih0aGlzLmVsWzBdLCB7XG4gICAgICAgICAgICAgICAgLi4udGhpcy5vcHRpb25zLmNvbmZpZyxcbiAgICAgICAgICAgICAgICBwYWdpbmF0aW9uSW5pdGlhbFBhZ2U6IHBhcnNlSW50KGluaXRpYWxQYWdlIHx8IFwiMVwiKSxcbiAgICAgICAgICAgICAgICBmb290ZXJFbGVtZW50OiB0aGlzLnRlbXBsYXRlcy5mb290ZXJFbGVtZW50LFxuICAgICAgICAgICAgICAgIGFqYXhQYXJhbXM6ICgpID0+ICh7IGZpbHRlcnM6IEpTT04uc3RyaW5naWZ5KHRoaXMudGFibGVGaWx0ZXJzKSB9KVxuICAgICAgICAgICAgfSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX3Nob3dUb2FzdDogZnVuY3Rpb24gKG1lc3NhZ2U6IHN0cmluZywgdHlwZTogc3RyaW5nID0gXCJkZWZhdWx0XCIpOiB2b2lkIHtcbiAgICAgICAgICAgIGNrYW4udGFibGVzVG9hc3Qoe1xuICAgICAgICAgICAgICAgIG1lc3NhZ2UsXG4gICAgICAgICAgICAgICAgdHlwZSxcbiAgICAgICAgICAgICAgICB0aXRsZTogY2thbi5pMThuLl8oXCJUYWJsZXNcIiksXG4gICAgICAgICAgICB9KTtcbiAgICAgICAgfSxcblxuICAgICAgICBfY29uZmlybUFjdGlvbjogZnVuY3Rpb24gKGxhYmVsOiBzdHJpbmcsIGNhbGxiYWNrOiAoKSA9PiB2b2lkKTogdm9pZCB7XG4gICAgICAgICAgICBja2FuLnRhYmxlc0NvbmZpcm0oe1xuICAgICAgICAgICAgICAgIG1lc3NhZ2U6IGNrYW4uaTE4bi5fKGBBcmUgeW91IHN1cmUgeW91IHdhbnQgdG8gcGVyZm9ybSB0aGlzIGFjdGlvbjogPGI+JHtsYWJlbH08L2I+P2ApLFxuICAgICAgICAgICAgICAgIG9uQ29uZmlybTogY2FsbGJhY2tcbiAgICAgICAgICAgIH0pO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9yb3dBY3Rpb25DYWxsYmFjazogZnVuY3Rpb24gKGFjdGlvbjogVGFidWxhdG9yQWN0aW9uLCBlOiBFdmVudCwgcm93OiBUYWJ1bGF0b3JSb3cpOiB2b2lkIHtcbiAgICAgICAgICAgIGlmIChhY3Rpb24ud2l0aF9jb25maXJtYXRpb24pIHtcbiAgICAgICAgICAgICAgICB0aGlzLl9jb25maXJtQWN0aW9uKGFjdGlvbi5sYWJlbCwgKCkgPT4gdGhpcy5fb25Sb3dBY3Rpb25Db25maXJtKGFjdGlvbiwgcm93KSk7XG4gICAgICAgICAgICB9IGVsc2Uge1xuICAgICAgICAgICAgICAgIHRoaXMuX29uUm93QWN0aW9uQ29uZmlybShhY3Rpb24sIHJvdyk7XG4gICAgICAgICAgICB9XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uUm93QWN0aW9uQ29uZmlybTogZnVuY3Rpb24gKGFjdGlvbjogVGFidWxhdG9yQWN0aW9uLCByb3c6IFRhYnVsYXRvclJvdyk6IHZvaWQge1xuICAgICAgICAgICAgY29uc3QgZm9ybSA9IG5ldyBGb3JtRGF0YSgpO1xuICAgICAgICAgICAgZm9ybS5hcHBlbmQoXCJyb3dfYWN0aW9uXCIsIGFjdGlvbi5uYW1lKTtcbiAgICAgICAgICAgIGZvcm0uYXBwZW5kKFwicm93XCIsIEpTT04uc3RyaW5naWZ5KHJvdy5nZXREYXRhKCkpKTtcbiAgICAgICAgICAgIHRoaXMuX3NlbmRBY3Rpb25SZXF1ZXN0KGZvcm0sIGNrYW4uaTE4bi5fKGBSb3cgYWN0aW9uIGNvbXBsZXRlZDogPGI+JHthY3Rpb24ubGFiZWx9PC9iPmApKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfc2VuZEFjdGlvblJlcXVlc3Q6IGZ1bmN0aW9uIChmb3JtOiBGb3JtRGF0YSwgc3VjY2Vzc01lc3NhZ2U6IHN0cmluZyk6IFByb21pc2U8dm9pZD4ge1xuICAgICAgICAgICAgcmV0dXJuIGZldGNoKHRoaXMuc2FuZGJveC5jbGllbnQudXJsKHRoaXMub3B0aW9ucy5jb25maWcuYWpheFVSTCksIHtcbiAgICAgICAgICAgICAgICBtZXRob2Q6IFwiUE9TVFwiLFxuICAgICAgICAgICAgICAgIGJvZHk6IGZvcm0sXG4gICAgICAgICAgICAgICAgaGVhZGVyczogeyAnWC1DU1JGVG9rZW4nOiB0aGlzLl9nZXRDU1JGVG9rZW4oKSB9XG4gICAgICAgICAgICB9KVxuICAgICAgICAgICAgICAgIC50aGVuKHJlc3AgPT4gcmVzcC5qc29uKCkpXG4gICAgICAgICAgICAgICAgLnRoZW4ocmVzcCA9PiB7XG4gICAgICAgICAgICAgICAgICAgIGlmICghcmVzcC5zdWNjZXNzKSB7XG4gICAgICAgICAgICAgICAgICAgICAgICBjb25zdCBlcnIgPSByZXNwLmVycm9yIHx8IHJlc3AuZXJyb3JzPy5bMF0gfHwgXCJVbmtub3duIGVycm9yXCI7XG4gICAgICAgICAgICAgICAgICAgICAgICB0aGlzLl9zaG93VG9hc3QoZXJyLCBcImRhbmdlclwiKTtcbiAgICAgICAgICAgICAgICAgICAgICAgIGlmIChyZXNwLmVycm9ycz8ubGVuZ3RoID4gMSkge1xuICAgICAgICAgICAgICAgICAgICAgICAgICAgIHRoaXMuX3Nob3dUb2FzdChcbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgY2thbi5pMThuLl8oXCJNdWx0aXBsZSBlcnJvcnMgb2NjdXJyZWQgYW5kIHdlcmUgc3VwcHJlc3NlZFwiKSxcbiAgICAgICAgICAgICAgICAgICAgICAgICAgICAgICAgXCJlcnJvclwiXG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgKTtcbiAgICAgICAgICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICAgICAgfSBlbHNlIHtcbiAgICAgICAgICAgICAgICAgICAgICAgIGlmIChyZXNwLnJlZGlyZWN0KSB7XG4gICAgICAgICAgICAgICAgICAgICAgICAgICAgd2luZG93LmxvY2F0aW9uLmhyZWYgPSByZXNwLnJlZGlyZWN0O1xuICAgICAgICAgICAgICAgICAgICAgICAgICAgIHJldHVybjtcbiAgICAgICAgICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgICAgICAgICAgICAgIHRoaXMuX3JlZnJlc2hEYXRhKCk7XG4gICAgICAgICAgICAgICAgICAgICAgICB0aGlzLl9zaG93VG9hc3QocmVzcC5tZXNzYWdlIHx8IHN1Y2Nlc3NNZXNzYWdlKTtcbiAgICAgICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgICAgIH0pXG4gICAgICAgICAgICAgICAgLmNhdGNoKGVycm9yID0+IHRoaXMuX3Nob3dUb2FzdChlcnJvci5tZXNzYWdlLCBcImRhbmdlclwiKSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX2luaXRBZGRUYWJsZUV2ZW50czogZnVuY3Rpb24gKCk6IHZvaWQge1xuICAgICAgICAgICAgdGhpcy5hcHBseUZpbHRlcnNCdG4uYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsIHRoaXMuX29uQXBwbHlGaWx0ZXJzKTtcbiAgICAgICAgICAgIHRoaXMuY2xlYXJGaWx0ZXJzTW9kYWxCdG4uYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsIHRoaXMuX29uQ2xlYXJGaWx0ZXJzKTtcbiAgICAgICAgICAgIHRoaXMuY2xlYXJGaWx0ZXJzQnRuLmFkZEV2ZW50TGlzdGVuZXIoXCJjbGlja1wiLCB0aGlzLl9vbkNsZWFyRmlsdGVycyk7XG4gICAgICAgICAgICB0aGlzLmFkZEZpbHRlckJ0bi5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgdGhpcy5fb25BZGRGaWx0ZXIpO1xuICAgICAgICAgICAgdGhpcy5jbG9zZUZpbHRlcnNCdG4uYWRkRXZlbnRMaXN0ZW5lcihcImNsaWNrXCIsIHRoaXMuX29uQ2xvc2VGaWx0ZXJzKTtcblxuICAgICAgICAgICAgdGhpcy5maWx0ZXJzQ29udGFpbmVyLmFkZEV2ZW50TGlzdGVuZXIoXCJjbGlja1wiLCAoZTogRXZlbnQpID0+IHtcbiAgICAgICAgICAgICAgICBjb25zdCByZW1vdmVCdG4gPSAoZS50YXJnZXQgYXMgSFRNTEVsZW1lbnQpLmNsb3Nlc3QoXCIuYnRuLXJlbW92ZS1maWx0ZXJcIik7XG4gICAgICAgICAgICAgICAgaWYgKHJlbW92ZUJ0biAmJiB0aGlzLmZpbHRlcnNDb250YWluZXIuY29udGFpbnMocmVtb3ZlQnRuKSkge1xuICAgICAgICAgICAgICAgICAgICB0aGlzLl9vbkZpbHRlckl0ZW1SZW1vdmUocmVtb3ZlQnRuKTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICB9KTtcblxuICAgICAgICAgICAgY29uc3QgYmluZE1lbnVCdXR0b25zID0gKG1lbnU6IEhUTUxFbGVtZW50LCBoYW5kbGVyOiAoZTogRXZlbnQpID0+IHZvaWQpID0+IHtcbiAgICAgICAgICAgICAgICBpZiAobWVudSkge1xuICAgICAgICAgICAgICAgICAgICBtZW51LnF1ZXJ5U2VsZWN0b3JBbGwoXCJidXR0b25cIikuZm9yRWFjaCgoYnRuOiBIVE1MQnV0dG9uRWxlbWVudCkgPT4ge1xuICAgICAgICAgICAgICAgICAgICAgICAgYnRuLmFkZEV2ZW50TGlzdGVuZXIoXCJjbGlja1wiLCBoYW5kbGVyKTtcbiAgICAgICAgICAgICAgICAgICAgfSk7XG4gICAgICAgICAgICAgICAgfVxuICAgICAgICAgICAgfTtcblxuICAgICAgICAgICAgYmluZE1lbnVCdXR0b25zKHRoaXMuYnVsa0FjdGlvbnNNZW51LCB0aGlzLl9vbkFwcGx5QnVsa0FjdGlvbik7XG4gICAgICAgICAgICBiaW5kTWVudUJ1dHRvbnModGhpcy50YWJsZUFjdGlvbnNNZW51LCB0aGlzLl9vbkFwcGx5VGFibGVBY3Rpb24pO1xuICAgICAgICAgICAgYmluZE1lbnVCdXR0b25zKHRoaXMudGFibGVFeHBvcnRlcnNNZW51LCB0aGlzLl9vblRhYmxlRXhwb3J0Q2xpY2spO1xuXG4gICAgICAgICAgICBkb2N1bWVudC5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgKGU6IEV2ZW50KSA9PiB7XG4gICAgICAgICAgICAgICAgY29uc3Qgcm93QWN0aW9uc0J0biA9IChlLnRhcmdldCBhcyBIVE1MRWxlbWVudCkuY2xvc2VzdChcIi5idG4tcm93LWFjdGlvbnNcIik7XG4gICAgICAgICAgICAgICAgaWYgKHJvd0FjdGlvbnNCdG4gJiYgdGhpcy5lbFswXS5jb250YWlucyhyb3dBY3Rpb25zQnRuKSkge1xuICAgICAgICAgICAgICAgICAgICB0aGlzLl9vblJvd0FjdGlvbnNEcm9wZG93bkNsaWNrKGUpO1xuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgIH0pO1xuXG4gICAgICAgICAgICB0aGlzLnRhYmxlLm9uKFwidGFibGVCdWlsdFwiLCAoKSA9PiB7XG4gICAgICAgICAgICAgICAgaWYgKHRoaXMub3B0aW9ucy5lbmFibGVGdWxsc2NyZWVuVG9nZ2xlKSB7XG4gICAgICAgICAgICAgICAgICAgIHRoaXMuYnRuRnVsbHNjcmVlbiA9IGRvY3VtZW50LmdldEVsZW1lbnRCeUlkKFwiYnRuLWZ1bGxzY3JlZW5cIik7XG4gICAgICAgICAgICAgICAgICAgIHRoaXMuYnRuRnVsbHNjcmVlbi5hZGRFdmVudExpc3RlbmVyKFwiY2xpY2tcIiwgdGhpcy5fb25GdWxsc2NyZWVuKTtcbiAgICAgICAgICAgICAgICB9XG4gICAgICAgICAgICB9KTtcblxuICAgICAgICAgICAgdGhpcy50YWJsZS5vbihcInJlbmRlckNvbXBsZXRlXCIsIGZ1bmN0aW9uICh0aGlzOiBhbnkpIHtcbiAgICAgICAgICAgICAgICBodG14LnByb2Nlc3ModGhpcy5lbGVtZW50KTtcbiAgICAgICAgICAgICAgICBjb25zdCBwYWdlU2l6ZVNlbGVjdCA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoXCIudGFidWxhdG9yLXBhZ2Utc2l6ZVwiKTtcbiAgICAgICAgICAgICAgICBpZiAocGFnZVNpemVTZWxlY3QpIHBhZ2VTaXplU2VsZWN0LmNsYXNzTGlzdC5hZGQoXCJmb3JtLXNlbGVjdFwiKTtcbiAgICAgICAgICAgIH0pO1xuXG4gICAgICAgICAgICB0aGlzLnRhYmxlLm9uKFwicGFnZUxvYWRlZFwiLCAocGFnZW5vOiBudW1iZXIpID0+IHtcbiAgICAgICAgICAgICAgICBjb25zdCB1cmwgPSBuZXcgVVJMKHdpbmRvdy5sb2NhdGlvbi5ocmVmKTtcbiAgICAgICAgICAgICAgICB1cmwuc2VhcmNoUGFyYW1zLnNldChcInBhZ2VcIiwgcGFnZW5vLnRvU3RyaW5nKCkpO1xuICAgICAgICAgICAgICAgIHdpbmRvdy5oaXN0b3J5LnJlcGxhY2VTdGF0ZSh7fSwgXCJcIiwgdXJsKTtcbiAgICAgICAgICAgIH0pO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9vblJvd0FjdGlvbnNEcm9wZG93bkNsaWNrOiBmdW5jdGlvbiAoZTogRXZlbnQpOiB2b2lkIHtcbiAgICAgICAgICAgIGUucHJldmVudERlZmF1bHQoKTtcbiAgICAgICAgICAgIGNvbnN0IHRhcmdldEVsID0gZS50YXJnZXQgYXMgSFRNTEVsZW1lbnQ7XG4gICAgICAgICAgICBjb25zdCByb3dFbCA9IHRhcmdldEVsLmNsb3Nlc3QoXCIudGFidWxhdG9yLXJvd1wiKTtcbiAgICAgICAgICAgIGlmICghcm93RWwpIHJldHVybjtcblxuICAgICAgICAgICAgY29uc3QgcmVjdCA9IHRhcmdldEVsLmdldEJvdW5kaW5nQ2xpZW50UmVjdCgpO1xuICAgICAgICAgICAgcm93RWwuZGlzcGF0Y2hFdmVudChuZXcgTW91c2VFdmVudChcImNvbnRleHRtZW51XCIsIHtcbiAgICAgICAgICAgICAgICBidWJibGVzOiB0cnVlLFxuICAgICAgICAgICAgICAgIGNhbmNlbGFibGU6IHRydWUsXG4gICAgICAgICAgICAgICAgdmlldzogd2luZG93LFxuICAgICAgICAgICAgICAgIGNsaWVudFg6IHJlY3QubGVmdCArIHJlY3Qud2lkdGggLyAyLFxuICAgICAgICAgICAgICAgIGNsaWVudFk6IHJlY3QuYm90dG9tLFxuICAgICAgICAgICAgICAgIGJ1dHRvbjogMlxuICAgICAgICAgICAgfSkpO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9jb2xsZWN0VmFsaWRGaWx0ZXJzOiBmdW5jdGlvbiAoKTogVGFibGVGaWx0ZXJbXSB7XG4gICAgICAgICAgICBjb25zdCBmaWx0ZXJzOiBUYWJsZUZpbHRlcltdID0gW107XG4gICAgICAgICAgICB0aGlzLmZpbHRlcnNDb250YWluZXIucXVlcnlTZWxlY3RvckFsbChcIi5maWx0ZXItaXRlbVwiKS5mb3JFYWNoKChpdGVtOiBIVE1MRWxlbWVudCkgPT4ge1xuICAgICAgICAgICAgICAgIGNvbnN0IGZpZWxkID0gKGl0ZW0ucXVlcnlTZWxlY3RvcihcIi5maWx0ZXItZmllbGRcIikgYXMgSFRNTFNlbGVjdEVsZW1lbnQpPy52YWx1ZTtcbiAgICAgICAgICAgICAgICBjb25zdCBvcGVyYXRvciA9IChpdGVtLnF1ZXJ5U2VsZWN0b3IoXCIuZmlsdGVyLW9wZXJhdG9yXCIpIGFzIEhUTUxTZWxlY3RFbGVtZW50KT8udmFsdWU7XG4gICAgICAgICAgICAgICAgY29uc3QgdmFsdWUgPSAoaXRlbS5xdWVyeVNlbGVjdG9yKFwiLmZpbHRlci12YWx1ZVwiKSBhcyBIVE1MSW5wdXRFbGVtZW50KT8udmFsdWU7XG4gICAgICAgICAgICAgICAgaWYgKGZpZWxkICYmIG9wZXJhdG9yICYmIHZhbHVlKSBmaWx0ZXJzLnB1c2goeyBmaWVsZCwgb3BlcmF0b3IsIHZhbHVlIH0pO1xuICAgICAgICAgICAgfSk7XG4gICAgICAgICAgICByZXR1cm4gZmlsdGVycztcbiAgICAgICAgfSxcblxuICAgICAgICBfdXBkYXRlVGFibGVGaWx0ZXJzOiBmdW5jdGlvbiAoKTogVGFibGVGaWx0ZXJbXSB7XG4gICAgICAgICAgICB0aGlzLnRhYmxlRmlsdGVycyA9IHRoaXMuX2NvbGxlY3RWYWxpZEZpbHRlcnMoKTtcbiAgICAgICAgICAgIHRoaXMuZmlsdGVyc0NvdW50ZXIudGV4dENvbnRlbnQgPSB0aGlzLnRhYmxlRmlsdGVycy5sZW5ndGgudG9TdHJpbmcoKTtcbiAgICAgICAgICAgIHRoaXMuZmlsdGVyc0NvdW50ZXIuY2xhc3NMaXN0LnRvZ2dsZShcImQtbm9uZVwiLCB0aGlzLnRhYmxlRmlsdGVycy5sZW5ndGggPT09IDApO1xuICAgICAgICAgICAgcmV0dXJuIHRoaXMudGFibGVGaWx0ZXJzO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9yZW1vdmVVbmZpbGxlZEZpbHRlcnM6IGZ1bmN0aW9uICgpOiB2b2lkIHtcbiAgICAgICAgICAgIHRoaXMuZmlsdGVyc0NvbnRhaW5lci5xdWVyeVNlbGVjdG9yQWxsKFwiLmZpbHRlci1pdGVtXCIpLmZvckVhY2goKGl0ZW06IEhUTUxFbGVtZW50KSA9PiB7XG4gICAgICAgICAgICAgICAgY29uc3QgZmllbGQgPSAoaXRlbS5xdWVyeVNlbGVjdG9yKFwiLmZpbHRlci1maWVsZFwiKSBhcyBIVE1MU2VsZWN0RWxlbWVudCk/LnZhbHVlO1xuICAgICAgICAgICAgICAgIGNvbnN0IG9wZXJhdG9yID0gKGl0ZW0ucXVlcnlTZWxlY3RvcihcIi5maWx0ZXItb3BlcmF0b3JcIikgYXMgSFRNTFNlbGVjdEVsZW1lbnQpPy52YWx1ZTtcbiAgICAgICAgICAgICAgICBjb25zdCB2YWx1ZSA9IChpdGVtLnF1ZXJ5U2VsZWN0b3IoXCIuZmlsdGVyLXZhbHVlXCIpIGFzIEhUTUxJbnB1dEVsZW1lbnQpPy52YWx1ZTtcbiAgICAgICAgICAgICAgICBpZiAoIWZpZWxkIHx8ICFvcGVyYXRvciB8fCAhdmFsdWUpIGl0ZW0ucmVtb3ZlKCk7XG4gICAgICAgICAgICB9KTtcbiAgICAgICAgfSxcblxuICAgICAgICBfb25BcHBseUZpbHRlcnM6IGZ1bmN0aW9uICgpOiB2b2lkIHtcbiAgICAgICAgICAgIHRoaXMuX3VwZGF0ZVRhYmxlRmlsdGVycygpO1xuICAgICAgICAgICAgdGhpcy5fcmVtb3ZlVW5maWxsZWRGaWx0ZXJzKCk7XG4gICAgICAgICAgICB0aGlzLl91cGRhdGVDbGVhckJ1dHRvbnNTdGF0ZSgpO1xuICAgICAgICAgICAgdGhpcy5fdXBkYXRlVXJsKCk7XG4gICAgICAgICAgICB0aGlzLl9yZWZyZXNoRGF0YSgpO1xuICAgICAgICB9LFxuXG4gICAgICAgIF91cGRhdGVDbGVhckJ1dHRvbnNTdGF0ZTogZnVuY3Rpb24gKCk6IHZvaWQge1xuICAgICAgICAgICAgY29uc3QgaGFzRmlsdGVycyA9IHRoaXMudGFibGVGaWx0ZXJzLmxlbmd0aCA+IDA7XG4gICAgICAgICAgICB0aGlzLmNsZWFyRmlsdGVyc0J0bi5jbGFzc0xpc3QudG9nZ2xlKFwiYnRuLXRhYmxlLWRpc2FibGVkXCIsICFoYXNGaWx0ZXJzKTtcbiAgICAgICAgICAgIHRoaXMuY2xlYXJGaWx0ZXJzTW9kYWxCdG4uY2xhc3NMaXN0LnRvZ2dsZShcImJ0bi10YWJsZS1kaXNhYmxlZFwiLCAhaGFzRmlsdGVycyk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uQ2xlYXJGaWx0ZXJzOiBmdW5jdGlvbiAoKTogdm9pZCB7XG4gICAgICAgICAgICB0aGlzLmZpbHRlcnNDb250YWluZXIuaW5uZXJIVE1MID0gXCJcIjtcbiAgICAgICAgICAgIHRoaXMuX3VwZGF0ZVRhYmxlRmlsdGVycygpO1xuICAgICAgICAgICAgdGhpcy5fdXBkYXRlQ2xlYXJCdXR0b25zU3RhdGUoKTtcbiAgICAgICAgICAgIHRoaXMuX3VwZGF0ZVVybCgpO1xuICAgICAgICAgICAgdGhpcy5fcmVmcmVzaERhdGEoKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfb25BZGRGaWx0ZXI6IGZ1bmN0aW9uICgpOiB2b2lkIHtcbiAgICAgICAgICAgIGNvbnN0IG5ld0ZpbHRlciA9IHRoaXMuZmlsdGVyVGVtcGxhdGUuY2xvbmVOb2RlKHRydWUpIGFzIEhUTUxFbGVtZW50O1xuICAgICAgICAgICAgbmV3RmlsdGVyLnN0eWxlLmRpc3BsYXkgPSBcImJsb2NrXCI7XG4gICAgICAgICAgICB0aGlzLmZpbHRlcnNDb250YWluZXIuYXBwZW5kQ2hpbGQobmV3RmlsdGVyKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfb25GaWx0ZXJJdGVtUmVtb3ZlOiBmdW5jdGlvbiAoZmlsdGVyRWw6IEVsZW1lbnQpOiB2b2lkIHtcbiAgICAgICAgICAgIGNvbnN0IHBhcmVudCA9IGZpbHRlckVsLmNsb3Nlc3QoXCIuZmlsdGVyLWl0ZW1cIik7XG4gICAgICAgICAgICBpZiAocGFyZW50KSBwYXJlbnQucmVtb3ZlKCk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uQ2xvc2VGaWx0ZXJzOiBmdW5jdGlvbiAoKTogdm9pZCB7XG4gICAgICAgICAgICB0aGlzLl9yZWNyZWF0ZUZpbHRlcnMoKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfcmVjcmVhdGVGaWx0ZXJzOiBmdW5jdGlvbiAoKTogdm9pZCB7XG4gICAgICAgICAgICB0aGlzLmZpbHRlcnNDb250YWluZXIuaW5uZXJIVE1MID0gXCJcIjtcbiAgICAgICAgICAgIHRoaXMudGFibGVGaWx0ZXJzLmZvckVhY2goKGZpbHRlcjogVGFibGVGaWx0ZXIpID0+IHtcbiAgICAgICAgICAgICAgICBjb25zdCBuZXdGaWx0ZXIgPSB0aGlzLmZpbHRlclRlbXBsYXRlLmNsb25lTm9kZSh0cnVlKSBhcyBIVE1MRWxlbWVudDtcbiAgICAgICAgICAgICAgICBuZXdGaWx0ZXIuc3R5bGUuZGlzcGxheSA9IFwiYmxvY2tcIjtcbiAgICAgICAgICAgICAgICAobmV3RmlsdGVyLnF1ZXJ5U2VsZWN0b3IoXCIuZmlsdGVyLWZpZWxkXCIpIGFzIEhUTUxTZWxlY3RFbGVtZW50KS52YWx1ZSA9IGZpbHRlci5maWVsZDtcbiAgICAgICAgICAgICAgICAobmV3RmlsdGVyLnF1ZXJ5U2VsZWN0b3IoXCIuZmlsdGVyLW9wZXJhdG9yXCIpIGFzIEhUTUxTZWxlY3RFbGVtZW50KS52YWx1ZSA9IGZpbHRlci5vcGVyYXRvcjtcbiAgICAgICAgICAgICAgICAobmV3RmlsdGVyLnF1ZXJ5U2VsZWN0b3IoXCIuZmlsdGVyLXZhbHVlXCIpIGFzIEhUTUxJbnB1dEVsZW1lbnQpLnZhbHVlID0gZmlsdGVyLnZhbHVlO1xuICAgICAgICAgICAgICAgIHRoaXMuZmlsdGVyc0NvbnRhaW5lci5hcHBlbmRDaGlsZChuZXdGaWx0ZXIpO1xuICAgICAgICAgICAgfSk7XG4gICAgICAgICAgICB0aGlzLl91cGRhdGVVcmwoKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfdXBkYXRlVXJsOiBmdW5jdGlvbiAoKTogdm9pZCB7XG4gICAgICAgICAgICBjb25zdCB1cmwgPSBuZXcgVVJMKHdpbmRvdy5sb2NhdGlvbi5ocmVmKTtcbiAgICAgICAgICAgIEFycmF5LmZyb20odXJsLnNlYXJjaFBhcmFtcy5rZXlzKCkpLmZvckVhY2goa2V5ID0+IHtcbiAgICAgICAgICAgICAgICBpZiAoa2V5LnN0YXJ0c1dpdGgoJ2ZpZWxkJykgfHwga2V5LnN0YXJ0c1dpdGgoJ29wZXJhdG9yJykgfHwga2V5LnN0YXJ0c1dpdGgoJ3EnKSkge1xuICAgICAgICAgICAgICAgICAgICB1cmwuc2VhcmNoUGFyYW1zLmRlbGV0ZShrZXkpO1xuICAgICAgICAgICAgICAgIH1cbiAgICAgICAgICAgIH0pO1xuICAgICAgICAgICAgdGhpcy50YWJsZUZpbHRlcnMuZm9yRWFjaCgoZmlsdGVyOiBUYWJsZUZpbHRlcikgPT4ge1xuICAgICAgICAgICAgICAgIHVybC5zZWFyY2hQYXJhbXMuYXBwZW5kKCdmaWVsZCcsIGZpbHRlci5maWVsZCk7XG4gICAgICAgICAgICAgICAgdXJsLnNlYXJjaFBhcmFtcy5hcHBlbmQoJ29wZXJhdG9yJywgZmlsdGVyLm9wZXJhdG9yKTtcbiAgICAgICAgICAgICAgICB1cmwuc2VhcmNoUGFyYW1zLmFwcGVuZCgncScsIGZpbHRlci52YWx1ZSk7XG4gICAgICAgICAgICB9KTtcbiAgICAgICAgICAgIHdpbmRvdy5oaXN0b3J5LnJlcGxhY2VTdGF0ZSh7fSwgXCJcIiwgdXJsKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfb25BcHBseUJ1bGtBY3Rpb246IGZ1bmN0aW9uIChlOiBFdmVudCk6IHZvaWQge1xuICAgICAgICAgICAgY29uc3QgdGFyZ2V0ID0gZS5jdXJyZW50VGFyZ2V0IGFzIEhUTUxFbGVtZW50O1xuICAgICAgICAgICAgY29uc3QgYWN0aW9uID0gdGFyZ2V0LmRhdGFzZXQuYWN0aW9uO1xuICAgICAgICAgICAgY29uc3QgbGFiZWwgPSB0YXJnZXQudGV4dENvbnRlbnQ/LnRyaW0oKSB8fCBcIlwiO1xuICAgICAgICAgICAgaWYgKCFhY3Rpb24pIHJldHVybjtcbiAgICAgICAgICAgIHRoaXMuX2NvbmZpcm1BY3Rpb24obGFiZWwsICgpID0+IHRoaXMuX29uQnVsa0FjdGlvbkNvbmZpcm0oYWN0aW9uLCBsYWJlbCkpO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9vbkJ1bGtBY3Rpb25Db25maXJtOiBmdW5jdGlvbiAoYnVsa0FjdGlvbjogc3RyaW5nLCBsYWJlbDogc3RyaW5nKTogdm9pZCB7XG4gICAgICAgICAgICBjb25zdCBzZWxlY3RlZERhdGEgPSB0aGlzLnRhYmxlLmdldFNlbGVjdGVkRGF0YSgpO1xuICAgICAgICAgICAgaWYgKCFzZWxlY3RlZERhdGEubGVuZ3RoKSByZXR1cm47XG4gICAgICAgICAgICBjb25zdCBkYXRhID0gc2VsZWN0ZWREYXRhLm1hcCgoeyBhY3Rpb25zLCAuLi5yZXN0IH06IFJlY29yZDxzdHJpbmcsIGFueT4pID0+IHJlc3QpO1xuICAgICAgICAgICAgY29uc3QgZm9ybSA9IG5ldyBGb3JtRGF0YSgpO1xuICAgICAgICAgICAgZm9ybS5hcHBlbmQoXCJidWxrX2FjdGlvblwiLCBidWxrQWN0aW9uKTtcbiAgICAgICAgICAgIGZvcm0uYXBwZW5kKFwicm93c1wiLCBKU09OLnN0cmluZ2lmeShkYXRhKSk7XG4gICAgICAgICAgICB0aGlzLl9zZW5kQWN0aW9uUmVxdWVzdChmb3JtLCBja2FuLmkxOG4uXyhgQnVsayBhY3Rpb24gY29tcGxldGVkOiA8Yj4ke2xhYmVsfTwvYj5gKSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uQXBwbHlUYWJsZUFjdGlvbjogZnVuY3Rpb24gKGU6IEV2ZW50KTogdm9pZCB7XG4gICAgICAgICAgICBjb25zdCB0YXJnZXQgPSBlLmN1cnJlbnRUYXJnZXQgYXMgSFRNTEVsZW1lbnQ7XG4gICAgICAgICAgICBjb25zdCBhY3Rpb24gPSB0YXJnZXQuZGF0YXNldC5hY3Rpb247XG4gICAgICAgICAgICBjb25zdCBsYWJlbCA9IHRhcmdldC50ZXh0Q29udGVudD8udHJpbSgpIHx8IFwiXCI7XG4gICAgICAgICAgICBpZiAoIWFjdGlvbikgcmV0dXJuO1xuICAgICAgICAgICAgdGhpcy5fY29uZmlybUFjdGlvbihsYWJlbCwgKCkgPT4gdGhpcy5fb25UYWJsZUFjdGlvbkNvbmZpcm0oYWN0aW9uLCBsYWJlbCkpO1xuICAgICAgICB9LFxuXG4gICAgICAgIF9vblRhYmxlQWN0aW9uQ29uZmlybTogZnVuY3Rpb24gKGFjdGlvbjogc3RyaW5nLCBsYWJlbDogc3RyaW5nKTogdm9pZCB7XG4gICAgICAgICAgICBjb25zdCBmb3JtID0gbmV3IEZvcm1EYXRhKCk7XG4gICAgICAgICAgICBmb3JtLmFwcGVuZChcInRhYmxlX2FjdGlvblwiLCBhY3Rpb24pO1xuICAgICAgICAgICAgdGhpcy5fc2VuZEFjdGlvblJlcXVlc3QoZm9ybSwgY2thbi5pMThuLl8oYFRhYmxlIGFjdGlvbiBjb21wbGV0ZWQ6IDxiPiR7bGFiZWx9PC9iPmApKTtcbiAgICAgICAgfSxcblxuICAgICAgICBfb25UYWJsZUV4cG9ydENsaWNrOiBmdW5jdGlvbiAoZTogRXZlbnQpOiB2b2lkIHtcbiAgICAgICAgICAgIGNvbnN0IGV4cG9ydGVyID0gKGUudGFyZ2V0IGFzIEhUTUxFbGVtZW50KS5kYXRhc2V0LmV4cG9ydGVyO1xuICAgICAgICAgICAgaWYgKCFleHBvcnRlcikgcmV0dXJuO1xuXG4gICAgICAgICAgICBjb25zdCBhID0gZG9jdW1lbnQuY3JlYXRlRWxlbWVudCgnYScpO1xuICAgICAgICAgICAgY29uc3QgdXJsID0gbmV3IFVSTCh3aW5kb3cubG9jYXRpb24uaHJlZik7XG4gICAgICAgICAgICB1cmwuc2VhcmNoUGFyYW1zLnNldChcImV4cG9ydGVyXCIsIGV4cG9ydGVyKTtcbiAgICAgICAgICAgIHVybC5zZWFyY2hQYXJhbXMuc2V0KFwiZmlsdGVyc1wiLCBKU09OLnN0cmluZ2lmeSh0aGlzLnRhYmxlRmlsdGVycykpO1xuICAgICAgICAgICAgdGhpcy50YWJsZS5nZXRTb3J0ZXJzKCkuZm9yRWFjaCgoczogeyBmaWVsZDogc3RyaW5nOyBkaXI6IHN0cmluZyB9KSA9PiB7XG4gICAgICAgICAgICAgICAgdXJsLnNlYXJjaFBhcmFtcy5zZXQoYHNvcnRbMF1bZmllbGRdYCwgcy5maWVsZCk7XG4gICAgICAgICAgICAgICAgdXJsLnNlYXJjaFBhcmFtcy5zZXQoYHNvcnRbMF1bZGlyXWAsIHMuZGlyKTtcbiAgICAgICAgICAgIH0pO1xuICAgICAgICAgICAgYS5ocmVmID0gdGhpcy5zYW5kYm94LmNsaWVudC51cmwodGhpcy5vcHRpb25zLmNvbmZpZy5leHBvcnRVUkwpICsgdXJsLnNlYXJjaDtcbiAgICAgICAgICAgIGEuZG93bmxvYWQgPSBgJHt0aGlzLm9wdGlvbnMuY29uZmlnLnRhYmxlSWQgfHwgJ3RhYmxlJ30uJHtleHBvcnRlcn1gO1xuICAgICAgICAgICAgZG9jdW1lbnQuYm9keS5hcHBlbmRDaGlsZChhKTtcbiAgICAgICAgICAgIGEuY2xpY2soKTtcbiAgICAgICAgICAgIGRvY3VtZW50LmJvZHkucmVtb3ZlQ2hpbGQoYSk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX3JlZnJlc2hEYXRhOiBmdW5jdGlvbiAoKTogdm9pZCB7XG4gICAgICAgICAgICB0aGlzLnRhYmxlLnJlcGxhY2VEYXRhKCk7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX29uRnVsbHNjcmVlbjogZnVuY3Rpb24gKCk6IHZvaWQge1xuICAgICAgICAgICAgdGhpcy50YWJsZVdyYXBwZXIuY2xhc3NMaXN0LnRvZ2dsZShcImZ1bGxzY3JlZW5cIik7XG4gICAgICAgIH0sXG5cbiAgICAgICAgX2dldENTUkZUb2tlbjogZnVuY3Rpb24gKCk6IHN0cmluZyB8IG51bGwge1xuICAgICAgICAgICAgY29uc3QgY3NyZl9maWVsZCA9IGRvY3VtZW50LnF1ZXJ5U2VsZWN0b3IoJ21ldGFbbmFtZT1cImNzcmZfZmllbGRfbmFtZVwiXScpPy5nZXRBdHRyaWJ1dGUoJ2NvbnRlbnQnKTtcbiAgICAgICAgICAgIHJldHVybiBkb2N1bWVudC5xdWVyeVNlbGVjdG9yKGBtZXRhW25hbWU9XCIke2NzcmZfZmllbGR9XCJdYCk/LmdldEF0dHJpYnV0ZSgnY29udGVudCcpIHx8IG51bGw7XG4gICAgICAgIH1cbiAgICB9O1xufSk7XG4iXX0=