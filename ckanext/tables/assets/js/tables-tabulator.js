/**
 * Tabulator integration for ckanext-tables
 *
 * Note:
 *  Replace the `ckan.tablesConfirm` and `ckan.tablesToast` functions with the `ckan.confirm` and `ckan.toast` from CKAN core
 *  when CKAN 2.12 is the minimum supported version.
 *
*/

ckan.module("tables-tabulator", function ($, _) {
    "use strict";
    return {
        templates: {
            footerElement: `<div class='d-flex justify-content-between align-items-center gap-2'>
                <a class='btn btn-light d-none d-sm-inline-block' id='btn-fullscreen' title='Fullscreen toggle'><i class='fa fa-expand'></i></a>
            </div>`,
        },
        options: {
            config: null,
            enableFullscreenToggle: true,
            debounceDelay: 300,
        },

        initialize: function () {
            $.proxyAll(this, /_/);

            if (!this.options.config) {
                return console.error("No config provided for tabulator");
            }

            this._initAssignVariables();
            this._initTabulatorInstance();
            this._initAddTableEvents();

            this.sandbox.subscribe("tables:tabulator:refresh", this._refreshData);
        },

        _initAssignVariables: function () {
            this.filterField = document.getElementById("filter-field");
            this.filterOperator = document.getElementById("filter-operator");
            this.filterValue = document.getElementById("filter-value");
            this.filterClear = document.getElementById("filter-clear");
            this.globalAction = document.getElementById("global-action");
            this.applyGlobalAction = document.getElementById("apply-global-action");
            this.tableWrapper = document.querySelector(".tabulator-wrapper");
        },

        _initTabulatorInstance: function () {
            this.table = new Tabulator(this.el[0], {
                ...this.options.config,
                paginationInitialPage: parseInt(getQueryParam("page")) || 1,
                footerElement: this.templates.footerElement,
                ajaxParams: () => {
                    return {
                        field: this.filterField.value,
                        operator: this.filterOperator.value,
                        q: this.filterValue.value,
                    };
                }
            });
        },

        _initAddTableEvents: function () {
            // Update filters on change
            this.filterField.addEventListener("change", this._onUpdateFilter);
            this.filterOperator.addEventListener("change", this._onUpdateFilter);
            this.filterValue.addEventListener("keyup", debounce(this._onUpdateFilter, this.options.debounceDelay));
            this.filterClear.addEventListener("click", this._onClearFilter);

            if (this.applyGlobalAction) {
                this.applyGlobalAction.addEventListener("click", this._onApplyGlobalAction);
            }

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
                url.searchParams.set("page", pageno);
                window.history.replaceState({}, "", url);
            });
        },

        /**
         * Update the filter based on the selected field, operator and value
         */
        _onUpdateFilter: function () {
            this._refreshData();
            this._updateUrl();
        },

        /**
         * Clear the filter
         */
        _onClearFilter: function () {
            this.filterField.value = "";
            this.filterOperator.value = "=";
            this.filterValue.value = "";

            this._refreshData();
            this._updateUrl();
        },

        /**
         * Update the URL with the current filter values
         */
        _updateUrl: function () {
            const url = new URL(window.location.href);
            url.searchParams.set("field", this.filterField.value);
            url.searchParams.set("operator", this.filterOperator.value);
            url.searchParams.set("q", this.filterValue.value);

            window.history.replaceState({}, "", url);
        },

        /**
         * Apply the global action to the selected rows
         */
        _onApplyGlobalAction: function () {
            const globalAction = this.globalAction.options[this.globalAction.selectedIndex].value;

            if (!globalAction) {
                return;
            }

            ckan.tablesConfirm({
                message: ckan.i18n._("Are you sure you want to perform this action?"),
                onConfirm: () => this._onGlobalActionConfirm(globalAction)
            });
        },

        _onGlobalActionConfirm: function (globalAction) {
            const selectedData = this.table.getSelectedData();

            if (!selectedData.length) {
                return;
            }

            // exclude 'actions' column
            const data = selectedData.map(row => {
                const { actions, ...rest } = row;
                return rest;
            });

            const form = new FormData();

            const csrf_field = $('meta[name=csrf_field_name]').attr('content');
            const csrf_token = $('meta[name=' + csrf_field + ']').attr('content');

            form.append("global_action", globalAction);
            form.append("rows", JSON.stringify(data));

            fetch(this.sandbox.client.url(this.options.config.ajaxURL), {
                method: "POST",
                body: form,
                headers: {
                    'X-CSRFToken': csrf_token
                }
            })
                .then(resp => resp.json())
                .then(resp => {
                    if (!resp.success) {
                        ckan.tablesToast({ message: resp.errors[0], type: "danger" });

                        if (resp.errors.length > 1) {
                            ckan.tablesToast({
                                message: ckan.i18n._("Multiple errors occurred and were suppressed"),
                                type: "error"
                            });
                        }
                    } else {
                        this._refreshData()
                        ckan.tablesToast({
                            message: ckan.i18n._("Operation completed"),
                            title: ckan.i18n._("Notification"),
                        });
                    }
                }).catch(error => {
                    console.error("Error:", error);
                });
        },

        _refreshData: function () {
            this.table.replaceData();
        },

        _onFullscreen: function () {
            this.tableWrapper.classList.toggle("fullscreen");
        },
    };
});

/**
 * Creates a debounced function that delays invoking `func` until after `delay`
 * milliseconds have passed since the last time the debounced function was invoked.
 *
 * @param {Function} func The function to debounce.
 * @param {number} delay The number of milliseconds to delay.
 *
 * @returns {Function} Returns the new debounced function.
*/
function debounce(func, delay) {
    let timeout;
    return function (...args) {
        const context = this;
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(context, args), delay);
    };
}

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
