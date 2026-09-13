import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildTableDom, makeFakeEl, makeFakeJQuery, makeFakeTabulatorClass, makeInstance } from "./support/fixture";

beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/dataset/resource/view");
    delete (globalThis as any).Tabulator;
});

describe("initialize", () => {
    it("shows a danger toast and stops early when no config is provided", () => {
        const tablesToast = vi.fn();
        const instance = makeInstance({ options: { config: null } }, undefined, { tablesToast });

        instance.initialize();

        expect(tablesToast).toHaveBeenCalledWith(expect.objectContaining({ type: "danger" }));
        expect(instance.table).toBeUndefined();
    });

    it("wires up the table end to end given a full config and DOM", () => {
        const dom = buildTableDom("res-1");
        const { FakeTabulator, instances } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;

        const sandbox = { subscribe: vi.fn(), client: { url: (u: string) => u } };
        const instance = makeInstance({
            el: makeFakeEl(dom.tableEl),
            sandbox,
            options: { config: { tableName: "res-1" }, rowActions: null, enableFullscreenToggle: true },
        });

        instance.initialize();

        expect(instance.tableId).toBe("res-1");
        expect(instance.tableName).toBe("res-1");
        expect(instance.wrapperEl).toBe(dom.wrapperEl);
        expect(instances).toHaveLength(1);
        expect(instances[0].element).toBe(dom.tableEl);
        expect(instances[0].config.ajaxURL).toBe("/dataset/resource/view");
        expect(sandbox.subscribe).toHaveBeenCalledWith("tables:tabulator:refresh", expect.any(Function));
    });

    it("builds a rowContextMenu entry per configured row action, bound to the action callback", () => {
        const dom = buildTableDom("res-2");
        const { FakeTabulator, instances } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;

        const instance = makeInstance({
            el: makeFakeEl(dom.tableEl),
            sandbox: { subscribe: vi.fn() },
            options: {
                config: { tableName: "res-2" },
                rowActions: {
                    delete: { name: "delete", label: "Delete", icon: "fa fa-trash", with_confirmation: true },
                },
                enableFullscreenToggle: true,
            },
        });

        // `action` below is bound to `this._rowActionCallback` at initialize() time
        // (`.bind(this, action)`), so the spy has to be in place beforehand — a
        // later reassignment of instance._rowActionCallback wouldn't affect an
        // already-bound copy.
        const rowActionCallback = vi.spyOn(instance, "_rowActionCallback").mockImplementation(() => {});
        instance.initialize();

        const menu = instances[0].config.rowContextMenu;
        expect(menu).toHaveLength(1);
        expect(menu[0].label).toContain("Delete");
        expect(menu[0].label).toContain("fa fa-trash");

        const fakeRow = { getData: () => ({}) };
        menu[0].action(new Event("contextmenu"), fakeRow);
        expect(rowActionCallback).toHaveBeenCalledWith(
            expect.objectContaining({ name: "delete" }),
            expect.any(Event),
            fakeRow
        );
    });

    it("wires rowHeader.cellClick to toggle the row's selection", () => {
        const dom = buildTableDom("res-3");
        const { FakeTabulator, instances } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;

        const config: any = { tableName: "res-3", rowHeader: {} };
        const instance = makeInstance({
            el: makeFakeEl(dom.tableEl),
            sandbox: { subscribe: vi.fn() },
            options: { config, enableFullscreenToggle: true },
        });

        instance.initialize();

        const toggleSelect = vi.fn();
        instances[0].config.rowHeader.cellClick(new Event("click"), { getRow: () => ({ toggleSelect }) });
        expect(toggleSelect).toHaveBeenCalled();
    });

    it("seeds paginationInitialPage from the page URL param and reports total via ajaxResponse", () => {
        window.history.replaceState({}, "", "/x?page-res-4=3");

        const dom = buildTableDom("res-4");
        const { FakeTabulator, instances } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;

        const instance = makeInstance({
            el: makeFakeEl(dom.tableEl),
            sandbox: { subscribe: vi.fn() },
            options: { config: { tableName: "res-4" }, enableFullscreenToggle: true },
        });

        instance.initialize();

        expect(instances[0].config.paginationInitialPage).toBe(3);
        expect(instances[0].config.ajaxParams()).toEqual({ filters: JSON.stringify(instance.tableFilters) });

        const response = instances[0].config.ajaxResponse("url", {}, { total: 42 });
        expect(response).toEqual({ total: 42 });
        expect(dom.totalCountEl.innerHTML).toBe("42");
    });

    it("real click on the apply-filters button runs _onApplyFilters with the module as `this`, thanks to $.proxyAll", () => {
        const dom = buildTableDom("res-5");
        const { FakeTabulator } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;

        const instance = makeInstance(
            {
                el: makeFakeEl(dom.tableEl),
                sandbox: { subscribe: vi.fn() },
                options: { config: { tableName: "res-5" }, enableFullscreenToggle: true },
            },
            makeFakeJQuery()
        );

        const onApplyFilters = vi.spyOn(instance, "_onApplyFilters").mockImplementation(function (this: any) {
            // Confirm `this` is the module instance, not the button element.
            expect(this).toBe(instance);
        });

        instance.initialize();
        dom.applyFiltersBtn.dispatchEvent(new Event("click"));

        expect(onApplyFilters).toHaveBeenCalledTimes(1);
    });

    it("wires every button inside the bulk/table/export menus to their handlers", () => {
        const dom = buildTableDom("res-6");
        const { FakeTabulator } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;

        const bulkBtn = document.createElement("button");
        dom.bulkActionsMenu.appendChild(bulkBtn);
        const tableActionBtn = document.createElement("button");
        dom.tableActionsMenu.appendChild(tableActionBtn);
        const exportBtn = document.createElement("button");
        dom.tableExportersMenu.appendChild(exportBtn);

        const instance = makeInstance(
            {
                el: makeFakeEl(dom.tableEl),
                sandbox: { subscribe: vi.fn() },
                options: { config: { tableName: "res-6" }, enableFullscreenToggle: true },
            },
            makeFakeJQuery()
        );

        const onApplyBulkAction = vi.spyOn(instance, "_onApplyBulkAction").mockImplementation(() => {});
        const onApplyTableAction = vi.spyOn(instance, "_onApplyTableAction").mockImplementation(() => {});
        const onTableExportClick = vi.spyOn(instance, "_onTableExportClick").mockImplementation(async () => {});

        instance.initialize();

        bulkBtn.dispatchEvent(new Event("click"));
        tableActionBtn.dispatchEvent(new Event("click"));
        exportBtn.dispatchEvent(new Event("click"));

        expect(onApplyBulkAction).toHaveBeenCalledTimes(1);
        expect(onApplyTableAction).toHaveBeenCalledTimes(1);
        expect(onTableExportClick).toHaveBeenCalledTimes(1);
    });

    it("runs column-visibility/header-filter setup and binds the fullscreen button on tableBuilt", () => {
        const dom = buildTableDom("res-7");
        const { FakeTabulator, instances } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;

        const instance = makeInstance(
            {
                el: makeFakeEl(dom.tableEl),
                sandbox: { subscribe: vi.fn() },
                options: { config: { tableName: "res-7" }, enableFullscreenToggle: true },
            },
            makeFakeJQuery()
        );

        const applyColumnVisibilityFromUrl = vi
            .spyOn(instance, "_applyColumnVisibilityFromUrl")
            .mockImplementation(() => {});
        const initHeaderFilterToggles = vi.spyOn(instance, "_initHeaderFilterToggles").mockImplementation(() => {});
        const onFullscreen = vi.spyOn(instance, "_onFullscreen").mockImplementation(() => {});

        instance.initialize();
        instances[0].trigger("tableBuilt");

        expect(applyColumnVisibilityFromUrl).toHaveBeenCalledTimes(1);
        expect(initHeaderFilterToggles).toHaveBeenCalledTimes(1);

        dom.btnFullscreen.dispatchEvent(new Event("click"));
        expect(onFullscreen).toHaveBeenCalledTimes(1);
    });

    it("does not wire the fullscreen button when enableFullscreenToggle is false", () => {
        const dom = buildTableDom("res-8");
        const { FakeTabulator, instances } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;

        const instance = makeInstance({
            el: makeFakeEl(dom.tableEl),
            sandbox: { subscribe: vi.fn() },
            options: { config: { tableName: "res-8" }, enableFullscreenToggle: false },
        });

        instance.initialize();
        expect(() => instances[0].trigger("tableBuilt")).not.toThrow();
        expect(instance.btnFullscreen).toBeUndefined();
    });

    it("processes htmx and marks the page-size select on renderComplete", () => {
        const dom = buildTableDom("res-9");
        const { FakeTabulator, instances } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;
        const htmxProcess = vi.fn();
        (globalThis as any).htmx = { process: htmxProcess };

        const pageSizeSelect = document.createElement("select");
        pageSizeSelect.className = "tabulator-page-size";
        dom.tableEl.appendChild(pageSizeSelect);

        const instance = makeInstance({
            el: makeFakeEl(dom.tableEl),
            sandbox: { subscribe: vi.fn() },
            options: { config: { tableName: "res-9" }, enableFullscreenToggle: true },
        });

        instance.initialize();
        instances[0].trigger("renderComplete");

        expect(htmxProcess).toHaveBeenCalledWith(dom.tableEl);
        expect(pageSizeSelect.classList.contains("form-select")).toBe(true);
    });

    it("records the current page in the URL on pageLoaded", () => {
        const dom = buildTableDom("res-10");
        const { FakeTabulator, instances } = makeFakeTabulatorClass();
        (globalThis as any).Tabulator = FakeTabulator;

        const instance = makeInstance({
            el: makeFakeEl(dom.tableEl),
            sandbox: { subscribe: vi.fn() },
            options: { config: { tableName: "res-10" }, enableFullscreenToggle: true },
        });

        instance.initialize();
        instances[0].trigger("pageLoaded", 5);

        expect(new URL(window.location.href).searchParams.get("page-res-10")).toBe("5");
    });
});
