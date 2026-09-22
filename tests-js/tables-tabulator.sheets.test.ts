import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeInstance } from "./support/fixture";

/**
 * A toggle button + sheets `<ul>`, shaped like `render_table.html`'s real
 * `table_sheets` block: the active sheet is a non-interactive `<span>` (nothing
 * to switch to), every other sheet is an `<a data-sheet>` carrying the
 * server-rendered (possibly stale) `href`/`data-deferred-url` a switch relies on
 * — exactly what `_refreshSheetLinkAttrs`/`_initSheetLinks`/`_onSheetLinkClick` walk.
 */
function buildSheetsControl(sheets: { name: string; active?: boolean }[]) {
    const wrapperEl = document.createElement("div");
    wrapperEl.className = "table-wrapper";

    const toggle = document.createElement("button");
    toggle.innerHTML = '<i class="fa fa-table-cells"></i>';

    const tableSheetsMenu = document.createElement("ul");
    tableSheetsMenu.innerHTML = sheets
        .map((sheet, index) => {
            if (sheet.active) {
                return `<li><span class="dropdown-item active" aria-current="true">${sheet.name}</span></li>`;
            }
            return (
                `<li><a class="dropdown-item" data-sheet="${index}" href="?sheet=${index}"` +
                ` data-deferred-url="/resource-table-deferred/res-1/view-1?sheet=${index}">${sheet.name}</a></li>`
            );
        })
        .join("");

    wrapperEl.append(toggle, tableSheetsMenu);
    document.body.appendChild(wrapperEl);

    return { wrapperEl, toggle, tableSheetsMenu };
}

function links(menu: HTMLElement): HTMLAnchorElement[] {
    return Array.from(menu.querySelectorAll("a[data-sheet]"));
}

function clickEvent(target: HTMLElement, overrides: Record<string, unknown> = {}) {
    return {
        target,
        button: 0,
        ctrlKey: false,
        metaKey: false,
        shiftKey: false,
        altKey: false,
        preventDefault: vi.fn(),
        ...overrides,
    };
}

beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/dataset/resource/view");
    (globalThis as any).bootstrap = { Dropdown: { getInstance: vi.fn(() => ({ hide: vi.fn() })) } };
    (globalThis as any).htmx = { ajax: vi.fn() };
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

describe("_refreshSheetLinkAttrs", () => {
    it("points href at the current page URL, with sheet swapped", () => {
        const { tableSheetsMenu } = buildSheetsControl([{ name: "Sheet1", active: true }, { name: "Sheet2" }]);
        const instance = makeInstance({ tableSheetsMenu });

        instance._refreshSheetLinkAttrs();

        const [link] = links(tableSheetsMenu);
        expect(link.href).toBe("http://localhost:3000/dataset/resource/view?sheet=1");
    });

    it("keeps the page's other query params, on both href and data-deferred-url", () => {
        window.history.replaceState({}, "", "/dataset/resource/view?view_id=abc&sheet=0&page-my-table=3");
        const { tableSheetsMenu } = buildSheetsControl([{ name: "Sheet1", active: true }, { name: "Sheet2" }]);
        const instance = makeInstance({ tableSheetsMenu });

        instance._refreshSheetLinkAttrs();

        const [link] = links(tableSheetsMenu);
        const href = new URL(link.href);
        expect(href.searchParams.get("sheet")).toBe("1");
        expect(href.searchParams.get("view_id")).toBe("abc");
        expect(href.searchParams.get("page-my-table")).toBe("3");

        const deferred = new URL(link.dataset.deferredUrl || "", window.location.origin);
        expect(deferred.pathname).toBe("/resource-table-deferred/res-1/view-1");
        expect(deferred.searchParams.get("sheet")).toBe("1");
        expect(deferred.searchParams.get("view_id")).toBe("abc");
        expect(deferred.searchParams.get("page-my-table")).toBe("3");
    });

    it("leaves a link with no data-deferred-url untouched (a switch URL wasn't rendered for it)", () => {
        const { tableSheetsMenu } = buildSheetsControl([{ name: "Sheet1", active: true }, { name: "Sheet2" }]);
        const [link] = links(tableSheetsMenu);
        link.removeAttribute("data-deferred-url");

        const instance = makeInstance({ tableSheetsMenu });
        expect(() => instance._refreshSheetLinkAttrs()).not.toThrow();
        expect(link.dataset.deferredUrl).toBeUndefined();
    });

    it("does nothing when the table has no sheet selector", () => {
        const instance = makeInstance({ tableSheetsMenu: null });

        expect(() => instance._refreshSheetLinkAttrs()).not.toThrow();
    });
});

describe("_initSheetLinks", () => {
    it("refreshes the links once up front", () => {
        const { tableSheetsMenu } = buildSheetsControl([{ name: "Sheet1", active: true }, { name: "Sheet2" }]);
        const instance = makeInstance({ tableSheetsMenu });

        instance._initSheetLinks();

        const [link] = links(tableSheetsMenu);
        expect(link.href).toBe("http://localhost:3000/dataset/resource/view?sheet=1");
    });

    it("wires a click listener on the menu, and the toggle's show.bs.dropdown to re-run the refresh", () => {
        const { tableSheetsMenu, toggle } = buildSheetsControl([{ name: "Sheet1", active: true }, { name: "Sheet2" }]);
        const menuAddSpy = vi.spyOn(tableSheetsMenu, "addEventListener");
        const toggleAddSpy = vi.spyOn(toggle, "addEventListener");
        const instance = makeInstance({ tableSheetsMenu });

        instance._initSheetLinks();

        expect(menuAddSpy).toHaveBeenCalledWith("click", instance._onSheetLinkClick);
        expect(toggleAddSpy).toHaveBeenCalledWith("show.bs.dropdown", instance._refreshSheetLinkAttrs);
    });

    it("does nothing when the table has no sheet selector", () => {
        const instance = makeInstance({ tableSheetsMenu: null });

        expect(() => instance._initSheetLinks()).not.toThrow();
    });
});

describe("_onSheetLinkClick", () => {
    it("ignores a click that didn't land on a sheet link", () => {
        const { tableSheetsMenu } = buildSheetsControl([{ name: "Sheet1" }]);
        const instance = makeInstance({ tableSheetsMenu });

        const event = clickEvent(tableSheetsMenu);
        instance._onSheetLinkClick(event);

        expect(event.preventDefault).not.toHaveBeenCalled();
        expect((globalThis as any).htmx.ajax).not.toHaveBeenCalled();
    });

    it("ignores a link with no data-deferred-url (a switch URL wasn't rendered for it)", () => {
        const { tableSheetsMenu } = buildSheetsControl([{ name: "Sheet1", active: true }, { name: "Sheet2" }]);
        const [link] = links(tableSheetsMenu);
        link.removeAttribute("data-deferred-url");
        const instance = makeInstance({ tableSheetsMenu });

        const event = clickEvent(link);
        instance._onSheetLinkClick(event);

        expect(event.preventDefault).not.toHaveBeenCalled();
        expect((globalThis as any).htmx.ajax).not.toHaveBeenCalled();
    });

    it.each([
        ["ctrl-click", { ctrlKey: true }],
        ["cmd-click", { metaKey: true }],
        ["shift-click", { shiftKey: true }],
        ["alt-click", { altKey: true }],
        ["a middle-click", { button: 1 }],
    ])("leaves %s to the browser's own handling of the real href", (_label, overrides) => {
        const { tableSheetsMenu } = buildSheetsControl([{ name: "Sheet1", active: true }, { name: "Sheet2" }]);
        const [link] = links(tableSheetsMenu);
        const instance = makeInstance({ tableSheetsMenu });

        const event = clickEvent(link, overrides);
        instance._onSheetLinkClick(event);

        expect(event.preventDefault).not.toHaveBeenCalled();
        expect((globalThis as any).htmx.ajax).not.toHaveBeenCalled();
    });

    it("drives the switch through htmx.ajax for a plain left-click, and closes the dropdown", () => {
        const { tableSheetsMenu, toggle } = buildSheetsControl([{ name: "Sheet1", active: true }, { name: "Sheet2" }]);
        const [link] = links(tableSheetsMenu);
        const hide = vi.fn();
        (globalThis as any).bootstrap.Dropdown.getInstance = vi.fn((el: Element | null) =>
            el === toggle ? { hide } : null
        );
        const instance = makeInstance({ tableSheetsMenu });

        const event = clickEvent(link);
        instance._onSheetLinkClick(event);

        expect(event.preventDefault).toHaveBeenCalled();
        expect(hide).toHaveBeenCalledTimes(1);
        expect((globalThis as any).htmx.ajax).toHaveBeenCalledWith("GET", link.dataset.deferredUrl, {
            target: "#tables-deferred-loader",
            swap: "innerHTML",
            source: link,
            push: link.href,
        });
    });
});

describe("teardown", () => {
    it("unsubscribes from the refresh topic, removes the document row-actions listener, and destroys the tabulator instance", () => {
        const unsubscribe = vi.fn();
        const destroy = vi.fn();
        const documentRemoveSpy = vi.spyOn(document, "removeEventListener");
        const instance = makeInstance({
            sandbox: { unsubscribe },
            table: { destroy },
        });

        instance.teardown();

        expect(unsubscribe).toHaveBeenCalledWith("tables:tabulator:refresh", instance._refreshData);
        expect(documentRemoveSpy).toHaveBeenCalledWith("click", instance._onDocumentRowActionsClick);
        expect(destroy).toHaveBeenCalledTimes(1);
    });

    it("does not throw when there is no tabulator instance yet", () => {
        const instance = makeInstance({ sandbox: { unsubscribe: vi.fn() }, table: undefined });

        expect(() => instance.teardown()).not.toThrow();
    });
});
