document.addEventListener("htmx:afterSwap", function (ev) {
    ev.detail.target.querySelectorAll("[data-module]").forEach(function (el) {
        if (el.hasAttribute("data-module-initialized")) return;

        el.setAttribute("data-module-initialized", "true");
        ckan.module.initializeElement(el);
    });
});
