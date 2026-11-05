import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeFakeEl, makeFakeTabulatorClass, makeInstance } from "./support/fixture";

/**
 * A table rendered with every optional control turned off (``show_filters``,
 * ``show_columns``, ``show_refresh``, ``show_fullscreen``, ``show_total_count``),
 * plus a search input and one quick filter select.
 */
function buildBareTableDom(tableId: string) {
    const wrapperEl = document.createElement("div");
    wrapperEl.className = "table-wrapper";
    wrapperEl.innerHTML = `
        <div class="table-control">
            <input type="search" id="table-search-${tableId}">
            <div id="quick-filters-${tableId}">
                <select class="table-quick-filter" data-field="theme" data-operator="=">
                    <option value="">All themes</option>
                    <option value="economy">Economy</option>
                    <option value="health">Health</option>
                </select>
            </div>
        </div>
        <div id="${tableId}"></div>
    `;
    document.body.appendChild(wrapperEl);

    return {
        wrapperEl,
        tableEl: document.getElementById(tableId) as HTMLElement,
        searchInput: document.getElementById(`table-search-${tableId}`) as HTMLInputElement,
        select: wrapperEl.querySelector(".table-quick-filter") as HTMLSelectElement,
    };
}

function initBareTable(tableId: string, options: Record<string, any> = {}) {
    const dom = buildBareTableDom(tableId);
    const { FakeTabulator, instances } = makeFakeTabulatorClass();
    (globalThis as any).Tabulator = FakeTabulator;

    const instance = makeInstance({
        el: makeFakeEl(dom.tableEl),
        sandbox: { subscribe: vi.fn(), client: { url: (u: string) => u } },
        options: { config: { tableName: "subs" }, rowActions: null, enableFullscreenToggle: false, ...options },
    });

    instance.initialize();

    const table = instances[0];
    table.setPage = vi.fn();
    table.trigger("tableBuilt");

    return { dom, instance, table };
}

beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/dashboard/subscriptions");
    delete (globalThis as any).Tabulator;
});

afterEach(() => {
    vi.useRealTimers();
});

describe("a table without the optional controls", () => {
    it("initializes without the filters, columns and fullscreen elements", () => {
        const { instance, table } = initBareTable("bare-1");

        expect(instance.tableFilters).toEqual([]);
        expect(table.config.ajaxParams()).toEqual({ filters: "[]" });
    });
});

describe("search input", () => {
    it("debounces the query into the ajax params and the URL, back to page 1", () => {
        vi.useFakeTimers();
        const { dom, instance, table } = initBareTable("search-1");

        dom.searchInput.value = "  survey ";
        dom.searchInput.dispatchEvent(new Event("input"));

        expect(table.setPage).not.toHaveBeenCalled();
        vi.advanceTimersByTime(instance._SEARCH_DEBOUNCE_MS);

        expect(table.setPage).toHaveBeenCalledWith(1);
        expect(table.config.ajaxParams()).toEqual({ filters: "[]", q: "survey" });
        expect(new URL(window.location.href).searchParams.get("q-subs")).toBe("survey");
    });

    it("restores the query from the URL", () => {
        window.history.replaceState({}, "", "/dashboard/subscriptions?q-subs=household");
        const { dom, table } = initBareTable("search-2");

        expect(dom.searchInput.value).toBe("household");
        expect(table.config.ajaxParams().q).toBe("household");
    });

    it("doesn't reload for an unchanged query", () => {
        vi.useFakeTimers();
        const { dom, instance, table } = initBareTable("search-3");

        dom.searchInput.value = "  ";
        dom.searchInput.dispatchEvent(new Event("input"));
        vi.advanceTimersByTime(instance._SEARCH_DEBOUNCE_MS);

        expect(table.setPage).not.toHaveBeenCalled();
    });
});

describe("quick filters", () => {
    it("sends the chosen value as a filter and keeps it in the URL", () => {
        const { dom, table } = initBareTable("quick-1");

        dom.select.value = "health";
        dom.select.dispatchEvent(new Event("change"));

        expect(table.setPage).toHaveBeenCalledWith(1);
        expect(JSON.parse(table.config.ajaxParams().filters)).toEqual([
            { field: "theme", operator: "=", value: "health" },
        ]);
        expect(new URL(window.location.href).searchParams.get("quick_filter_theme-subs")).toBe("health");

        dom.select.value = "";
        dom.select.dispatchEvent(new Event("change"));

        expect(JSON.parse(table.config.ajaxParams().filters)).toEqual([]);
        expect(new URL(window.location.href).searchParams.has("quick_filter_theme-subs")).toBe(false);
    });

    it("fires the sync event when the table sets the value itself", () => {
        window.history.replaceState({}, "", "/dashboard/subscriptions?quick_filter_theme-subs=economy");
        const dom = buildBareTableDom("quick-sync");
        const synced: string[] = [];
        dom.select.addEventListener("tables:quick-filter:sync", () => synced.push(dom.select.value));
        document.body.innerHTML = "";
        document.body.appendChild(dom.wrapperEl);

        const { FakeTabulator, instances } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;
        const instance = makeInstance({
            el: makeFakeEl(dom.tableEl),
            sandbox: { subscribe: vi.fn(), client: { url: (u: string) => u } },
            options: { config: { tableName: "subs" }, rowActions: null, enableFullscreenToggle: false },
        });
        instance.initialize();
        instances[0].setPage = vi.fn();

        // a user change doesn't sync: the widget made it
        dom.select.value = "health";
        dom.select.dispatchEvent(new Event("change"));

        expect(synced).toEqual(["economy"]);
    });

    it("restores an offered value from the URL and ignores any other", () => {
        window.history.replaceState({}, "", "/dashboard/subscriptions?quick_filter_theme-subs=economy");
        const restored = initBareTable("quick-2");

        expect(restored.dom.select.value).toBe("economy");
        expect(JSON.parse(restored.table.config.ajaxParams().filters)).toEqual([
            { field: "theme", operator: "=", value: "economy" },
        ]);

        document.body.innerHTML = "";
        window.history.replaceState({}, "", "/dashboard/subscriptions?quick_filter_theme-subs=unknown");
        const ignored = initBareTable("quick-3");

        expect(ignored.dom.select.value).toBe("");
        expect(JSON.parse(ignored.table.config.ajaxParams().filters)).toEqual([]);
    });
});

describe("inline row actions", () => {
    const rowActions = {
        unfollow: { name: "unfollow", label: "Unfollow", icon: "fa fa-bookmark", with_confirmation: false },
    };

    function addRow(tableEl: HTMLElement, disabled = false) {
        const rowEl = document.createElement("div");
        rowEl.className = "tabulator-row";
        rowEl.innerHTML = `<button class="btn-row-action" data-row-action="unfollow" ${disabled ? "disabled" : ""}><i></i></button>`;
        tableEl.appendChild(rowEl);

        return {
            rowEl,
            button: rowEl.querySelector("button") as HTMLButtonElement,
            row: { getData: () => ({ id: "pkg-1" }), getElement: () => rowEl },
        };
    }

    it("doesn't replace the browser context menu", () => {
        const { table } = initBareTable("inline-1", { rowActions, rowActionsDisplay: "inline" });

        expect(table.config.rowContextMenu).toBeUndefined();
    });

    it("runs the clicked action for its row", () => {
        const { dom, instance, table } = initBareTable("inline-2", { rowActions, rowActionsDisplay: "inline" });
        const { button, row } = addRow(dom.tableEl);
        table.getRows = () => [row];
        instance._rowActionCallback = vi.fn();

        button.querySelector("i")!.dispatchEvent(new MouseEvent("click", { bubbles: true }));

        expect(instance._rowActionCallback).toHaveBeenCalledWith(rowActions.unfollow, expect.any(Event), row);
    });

    it("ignores a disabled action", () => {
        const { dom, instance, table } = initBareTable("inline-3", { rowActions, rowActionsDisplay: "inline" });
        const { button, row } = addRow(dom.tableEl, true);
        table.getRows = () => [row];
        instance._rowActionCallback = vi.fn();

        instance._onInlineRowActionClick(new MouseEvent("click"), button);

        expect(instance._rowActionCallback).not.toHaveBeenCalled();
    });
});
