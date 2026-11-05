import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeFakeEl, makeFakeTabulatorClass, makeInstance } from "./support/fixture";

/** A table with a search input, a quick filter and an empty state, without the optional controls. */
function initTable(tableId: string, options: Record<string, any> = {}) {
    const wrapperEl = document.createElement("div");
    wrapperEl.className = "table-wrapper";
    wrapperEl.innerHTML = `
        <input type="search" id="table-search-${tableId}">
        <div id="quick-filters-${tableId}">
            <select class="table-quick-filter" data-field="theme">
                <option value="">All</option>
                <option value="health">Health</option>
            </select>
        </div>
        <div class="table-empty-state d-none" id="empty-state-${tableId}">
            <div data-empty-state="filtered"><button data-table-clear-filters>Clear</button></div>
            <div data-empty-state="empty" class="d-none">Nothing yet</div>
        </div>
        <div class="tabulator-wrapper"><div id="${tableId}"></div></div>
    `;
    document.body.appendChild(wrapperEl);

    const { FakeTabulator, instances } = makeFakeTabulatorClass();
    (globalThis as any).Tabulator = FakeTabulator;

    const instance = makeInstance({
        el: makeFakeEl(document.getElementById(tableId) as HTMLElement),
        sandbox: { subscribe: vi.fn(), client: { url: (u: string) => u } },
        options: { config: { tableName: "t" }, rowActions: null, enableFullscreenToggle: false, ...options },
    });
    instance.initialize();

    const table = instances[0];
    table.setPage = vi.fn();

    const q = (selector: string) => wrapperEl.querySelector(selector) as HTMLElement;

    return {
        instance,
        table,
        emptyState: q(".table-empty-state"),
        filtered: q('[data-empty-state="filtered"]'),
        empty: q('[data-empty-state="empty"]'),
        tabulatorWrapper: q(".tabulator-wrapper"),
        searchInput: q("input") as HTMLInputElement,
        select: q("select") as HTMLSelectElement,
        clearBtn: q("[data-table-clear-filters]"),
    };
}

beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/page");
    delete (globalThis as any).Tabulator;
});

describe("ajaxResponse", () => {
    it("returns the response unchanged", () => {
        const { table } = initTable("resp-1");
        const response = { data: [{}], last_page: 3, total: 25 };

        expect(table.config.ajaxResponse("", {}, { ...response })).toEqual(response);
    });
});

describe("empty state", () => {
    it("replaces the table with its empty part when there is no data", () => {
        const dom = initTable("empty-1");

        dom.table.config.ajaxResponse("", {}, { data: [], last_page: 0, total: 0 });

        expect(dom.emptyState.classList.contains("d-none")).toBe(false);
        expect(dom.tabulatorWrapper.classList.contains("d-none")).toBe(true);
        expect(dom.empty.classList.contains("d-none")).toBe(false);
        expect(dom.filtered.classList.contains("d-none")).toBe(true);
    });

    it("shows its filtered part when the search is active, and the table back with rows", () => {
        const dom = initTable("empty-2");
        dom.instance.searchQuery = "nothing";

        dom.table.config.ajaxResponse("", {}, { data: [], last_page: 0, total: 0 });

        expect(dom.filtered.classList.contains("d-none")).toBe(false);
        expect(dom.empty.classList.contains("d-none")).toBe(true);

        dom.table.config.ajaxResponse("", {}, { data: [{}], last_page: 1, total: 1 });

        expect(dom.emptyState.classList.contains("d-none")).toBe(true);
        expect(dom.tabulatorWrapper.classList.contains("d-none")).toBe(false);
    });

    it("clears the search and quick filters from its clear button", () => {
        window.history.replaceState({}, "", "/page?q-t=nothing&quick_filter_theme-t=health");
        const dom = initTable("empty-3");

        dom.clearBtn.dispatchEvent(new MouseEvent("click", { bubbles: true }));

        expect(dom.searchInput.value).toBe("");
        expect(dom.select.value).toBe("");
        expect(dom.table.config.ajaxParams()).toEqual({ filters: "[]" });
        expect(window.location.search).toBe("");
        expect(dom.table.setPage).toHaveBeenCalledWith(1);
    });

    it("does nothing for a table without an empty state", () => {
        const dom = initTable("empty-4");
        dom.instance.emptyStateEl = null;

        dom.table.config.ajaxResponse("", {}, { data: [], last_page: 0, total: 0 });

        expect(dom.tabulatorWrapper.classList.contains("d-none")).toBe(false);
    });
});

describe("pagination options", () => {
    it("keeps the default label and counter", () => {
        const { table } = initTable("pag-1");

        expect(table.config.paginationCounter).toBe("rows");
        expect(table.config.langs.default.pagination.page_size).toBe("Rows per page");
    });

    it("uses the configured label and the range counter", () => {
        const { table } = initTable("pag-2", { pageSizeLabel: "Items per page", paginationCounter: "range" });

        expect(table.config.langs.default.pagination.page_size).toBe("Items per page");
        expect(table.config.paginationCounter(8, 9, 2, 20, 3)).toBe("9 – 16 of 20");
        expect(table.config.paginationCounter(8, 17, 3, 20, 3)).toBe("17 – 20 of 20");
        expect(table.config.paginationCounter(8, 0, 1, 0, 0)).toBe("0 of 0");
    });

    it("counts the range from the server total, not Tabulator's estimate", () => {
        const { table } = initTable("pag-3", { paginationCounter: "range" });

        table.config.ajaxResponse("", {}, { data: [{}], last_page: 3, total: 18 });

        // Tabulator estimates 24 rows (3 pages of 8) on page 1
        expect(table.config.paginationCounter(8, 1, 1, 24, 3)).toBe("1 – 8 of 18");
    });
});
