ckan.module("tables-deferred-loader", function ($, _) {
    "use strict";

    return {
        initialize: function () {
            $.proxyAll(this, /_/);

            document.body.addEventListener("htmx:oobAfterSwap", this._htmx_initialize_tables);
            document.body.addEventListener("htmx:afterSwap", this._htmx_initialize_tables);
        },

        teardown: function () {
            document.body.removeEventListener("htmx:oobAfterSwap", this._htmx_initialize_tables);
            document.body.removeEventListener("htmx:afterSwap", this._htmx_initialize_tables);
        },

        _htmx_initialize_tables: function (event) {
            // The listeners are global on document.body, so without this check
            // every unrelated htmx swap on the page (toasts, other widgets, etc.)
            // would be processed too. This module only cares about the swap its
            // own `hx-get`/`hx-trigger="load"` drives.
            if (event.detail.target !== this.el[0]) {
                return;
            }

            this.el[0].querySelectorAll(".tabulator-container").forEach(function (el) {
                if (el.getAttribute("dm-initialized")) {
                    return;
                }

                ckan.module.initializeElement(el);
                el.setAttribute("dm-initialized", true)
            });
        }
    };
});
