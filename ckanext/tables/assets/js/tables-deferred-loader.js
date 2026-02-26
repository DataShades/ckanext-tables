document.addEventListener("htmx:afterSwap", function (ev) {
    var parent = ev.detail.target.parentNode;
    if (!parent) {
        return;
    }

    parent.querySelectorAll("[data-module]").forEach(function (el) {
        if (el.getAttribute("data-module-initialized")) {
            return;
        }
        el.setAttribute("data-module-initialized", "true");
        ckan.module.initializeElement(el);
    });
});
