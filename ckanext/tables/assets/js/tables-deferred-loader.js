ckan.module("tables-deferred-loader", function ($, _) {
    "use strict";

    return {
        initialize: function () {
            $.proxyAll(this, /_/);

            document.body.addEventListener("htmx:oobAfterSwap", this._htmx_initialize_tables);
            document.body.addEventListener("htmx:afterSwap", this._htmx_initialize_tables);
        },

        _htmx_initialize_tables: function (event) {
            var target = event.detail.target;
            var containers = target.matches && target.matches(".tabulator-container")
                ? [target]
                : target.querySelectorAll(".tabulator-container");

            containers.forEach(function (el) {
                if (el.getAttribute("dm-initialized")) {
                    return;
                }

                ckan.module.initializeElement(el);
                el.setAttribute("dm-initialized", true)
            });
        }
    };
});
