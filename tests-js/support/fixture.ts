import { vi } from "vitest";
import { loadCkanModule } from "./loadCkanModule";

export const SOURCE = "ckanext/tables/assets/ts/tables-tabulator.ts";

/**
 * Minimal jQuery stand-in covering the two APIs the module actually uses:
 * `$.proxyAll(obj, regex)` (binds matching methods to `obj`, CKAN's own
 * module helper) and `$(el).on(event, handler)` (used for the bootstrap
 * modal "hidden.bs.modal" events, wired via plain addEventListener here
 * since jsdom accepts arbitrary event-type strings).
 */
export function makeFakeJQuery(): any {
    const fn: any = (el: any) => ({
        on: (event: string, handler: EventListener) => {
            (Array.isArray(el) ? el[0] : el)?.addEventListener(event, handler);
        },
    });
    fn.proxyAll = (obj: any, regex: RegExp) => {
        // `for...in` (unlike Object.keys) walks the prototype chain, which
        // matters here: instances are built via `Object.create(moduleDef)`,
        // so the `_`-prefixed methods live on the prototype, not as the
        // instance's own properties. Real jQuery's `$.proxyAll` binds them
        // as new own properties on the instance, same as this does.
        for (const key in obj) {
            if (regex.test(key) && typeof obj[key] === "function") {
                obj[key] = obj[key].bind(obj);
            }
        }
    };
    return fn;
}

export function loadModuleDef(fakeJQuery: any = makeFakeJQuery(), ckanOverrides: Record<string, any> = {}): any {
    return loadCkanModule(SOURCE, "tables-tabulator", fakeJQuery, ckanOverrides);
}

/**
 * Builds a testable instance of the module's returned object.
 *
 * `ckanOverrides` (e.g. `{ tablesToast: vi.fn() }`) must be passed here
 * rather than mutated on `globalThis.ckan` afterwards — loading the module
 * replaces `globalThis.ckan` with a fresh mock every time, so anything set
 * beforehand (or after, without going through this) is invisible to the
 * `ckan` the compiled script actually closes over.
 */
export function makeInstance(
    overrides: Record<string, any> = {},
    fakeJQuery?: any,
    ckanOverrides?: Record<string, any>
): any {
    return Object.assign(Object.create(loadModuleDef(fakeJQuery, ckanOverrides)), overrides);
}

export function filterItem(field: string, operator: string, value: string): HTMLElement {
    const item = document.createElement("div");
    item.className = "filter-item";
    item.innerHTML = `
        <select class="filter-field"><option value="${field}" selected>${field}</option></select>
        <select class="filter-operator"><option value="${operator}" selected>${operator}</option></select>
        <input class="filter-value" value="${value}" />
    `;
    return item;
}

/** A `Tabulator`-shaped stub: records the constructor call and no-ops `.on`. */
export function makeFakeTabulatorClass() {
    const instances: any[] = [];

    class FakeTabulator {
        element: any;
        config: any;
        _handlers: Record<string, ((...args: any[]) => void)[]> = {};

        constructor(element: any, config: any) {
            this.element = element;
            this.config = config;
            instances.push(this);
        }

        on(event: string, handler: (...args: any[]) => void) {
            (this._handlers[event] ??= []).push(handler);
        }

        trigger(event: string, ...args: any[]) {
            (this._handlers[event] || []).forEach((h) => h.call(this, ...args));
        }

        getSelectedData = vi.fn(() => []);
        getSorters = vi.fn(() => []);
        replaceData = vi.fn(() => Promise.resolve());
        redraw = vi.fn();
        showColumn = vi.fn();
        hideColumn = vi.fn();
        getColumn = vi.fn();
    }

    return { FakeTabulator, instances };
}

/**
 * Builds the DOM `_initAssignVariables`/`_initAddTableEvents` require for
 * `initialize()` to run end to end without throwing, namespaced by
 * `tableId`. Returns the element refs a test is likely to want to assert
 * against or interact with.
 */
export function buildTableDom(tableId: string) {
    const id = (base: string) => `${base}-${tableId}`;

    const wrapperEl = document.createElement("div");
    wrapperEl.className = "table-wrapper";

    const tableEl = document.createElement("div");
    tableEl.id = tableId;
    wrapperEl.appendChild(tableEl);

    const extra = (idBase: string, tag = "div") => {
        const el = document.createElement(tag);
        el.id = id(idBase);
        wrapperEl.appendChild(el);
        return el;
    };

    const filtersModal = extra("filters-modal");
    const filtersContainer = extra("filters-container");
    const applyFiltersBtn = extra("apply-filters", "button");
    const clearFiltersModalBtn = extra("clear-filters", "button");
    const clearFiltersBtn = extra("clear-all-filters", "button");
    const filterTemplate = extra("filter-template");
    const addFilterBtn = extra("add-filter", "button");
    const filtersCounter = extra("filters-counter", "span");
    const bulkActionsMenu = extra("bulk-actions-menu");
    const tableActionsMenu = extra("table-actions-menu");
    const tableExportersMenu = extra("table-exporters-menu");
    const tableRefreshBtn = extra("refresh-table", "button");
    const totalCountEl = extra("total-count-value", "span");

    const columnsModal = extra("columns-modal");
    const columnsContainer = extra("columns-container");
    const applyColumnsBtn = extra("apply-columns", "button");
    const resetColumnsBtn = extra("reset-columns", "button");
    const selectAllColumnsBtn = extra("select-all-columns", "button");
    const deselectAllColumnsBtn = extra("deselect-all-columns", "button");
    const hiddenColumnsCounter = extra("hidden-columns-counter", "span");
    const hiddenColumnsBadge = extra("hidden-columns-badge", "span");
    const btnFullscreen = extra("btn-fullscreen", "button");

    document.body.appendChild(wrapperEl);

    return {
        tableId,
        wrapperEl,
        tableEl,
        filtersModal,
        filtersContainer,
        applyFiltersBtn,
        clearFiltersModalBtn,
        clearFiltersBtn,
        filterTemplate,
        addFilterBtn,
        filtersCounter,
        bulkActionsMenu,
        tableActionsMenu,
        tableExportersMenu,
        tableRefreshBtn,
        totalCountEl,
        columnsModal,
        columnsContainer,
        applyColumnsBtn,
        resetColumnsBtn,
        selectAllColumnsBtn,
        deselectAllColumnsBtn,
        hiddenColumnsCounter,
        hiddenColumnsBadge,
        btnFullscreen,
    };
}

/** A `this.el`-shaped stand-in: array-like with a jQuery `.closest()`. */
export function makeFakeEl(tableEl: HTMLElement): any {
    const arr: any = [tableEl];
    arr.closest = (selector: string) => [tableEl.closest(selector)];
    return arr;
}
