// document.body.addEventListener("htmx:oobAfterSwap", htmx_initialize_tables);
// document.body.addEventListener("htmx:afterSwap", htmx_initialize_tables);

// function htmx_initialize_tables(event) {
//     console.log("htmx_initialize_tables", event);

//     var el = event.detail.target.querySelector(".tabulator-container");

//     if (el.getAttribute("dm-initialized")) {
//         return;
//     }

//     ckan.module.initializeElement(el);
//     el.setAttribute("dm-initialized", true)
// }
