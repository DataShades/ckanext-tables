import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeInstance } from "./support/fixture";

/** A `.tabulator-col[tabulator-field]` header cell shaped like Tabulator renders it. */
function columnHeader(field: string): HTMLElement {
    const col = document.createElement("div");
    col.className = "tabulator-col";
    col.setAttribute("tabulator-field", field);

    const sorter = document.createElement("div");
    sorter.className = "tabulator-col-sorter";
    col.appendChild(sorter);

    const filterWrap = document.createElement("div");
    filterWrap.className = "tabulator-header-filter";
    const input = document.createElement("input");
    filterWrap.appendChild(input);
    col.appendChild(filterWrap);

    return col;
}

beforeEach(() => {
    document.body.innerHTML = "";
});

describe("_initHeaderFilterToggles", () => {
    it("adds a toggle button after the sorter for every filterable column, once", () => {
        const tableEl = document.createElement("div");
        const col = columnHeader("age");
        tableEl.appendChild(col);
        document.body.appendChild(tableEl);

        const instance = makeInstance({ el: [tableEl], tableId: "t1" });
        instance._initHeaderFilterToggles();

        const btn = col.querySelector(".btn-header-filter-toggle");
        expect(btn).not.toBeNull();
        expect(btn?.previousElementSibling?.classList.contains("tabulator-col-sorter")).toBe(true);

        const input = col.querySelector(".tabulator-header-filter input") as HTMLInputElement;
        expect(input.id).toBe("header-filter-age-t1");

        // Calling it again must not add a second button to the same column.
        instance._initHeaderFilterToggles();
        expect(col.querySelectorAll(".btn-header-filter-toggle")).toHaveLength(1);
    });

    it("skips columns without a header-filter input or a sorter element", () => {
        const tableEl = document.createElement("div");
        const bare = document.createElement("div");
        bare.className = "tabulator-col";
        bare.setAttribute("tabulator-field", "name");
        tableEl.appendChild(bare);
        document.body.appendChild(tableEl);

        const instance = makeInstance({ el: [tableEl], tableId: "t1" });
        expect(() => instance._initHeaderFilterToggles()).not.toThrow();
        expect(bare.querySelector(".btn-header-filter-toggle")).toBeNull();
    });

    it("keeps the toggle's active state in sync as the user types", () => {
        const tableEl = document.createElement("div");
        const col = columnHeader("age");
        tableEl.appendChild(col);
        document.body.appendChild(tableEl);

        const instance = makeInstance({ el: [tableEl], tableId: "t1" });
        instance._initHeaderFilterToggles();

        const input = col.querySelector(".tabulator-header-filter input") as HTMLInputElement;
        const btn = col.querySelector(".btn-header-filter-toggle") as HTMLButtonElement;

        input.value = "42";
        input.dispatchEvent(new Event("input"));

        expect(col.classList.contains("filter-active")).toBe(true);
        expect(btn.classList.contains("active")).toBe(true);
        expect(btn.getAttribute("aria-expanded")).toBe("true");
    });
});

describe("_buildFilterToggleButton", () => {
    it("keeps the column visible (doesn't toggle it closed) while the filter has a value", () => {
        const colEl = document.createElement("div");
        const filterInput = document.createElement("input");
        filterInput.id = "header-filter-age";
        filterInput.value = "42";
        colEl.classList.add("filter-visible");

        const table = { redraw: vi.fn() };
        const instance = makeInstance({ table });
        const btn = instance._buildFilterToggleButton(colEl, filterInput);

        btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));

        expect(colEl.classList.contains("filter-visible")).toBe(true);
        expect(table.redraw).not.toHaveBeenCalled();
    });

    it("toggles visibility, redraws, and focuses the input when the filter is empty", () => {
        const colEl = document.createElement("div");
        const filterInput = document.createElement("input");
        filterInput.id = "header-filter-age";
        document.body.append(colEl, filterInput);

        const table = { redraw: vi.fn() };
        const instance = makeInstance({ table });
        const btn = instance._buildFilterToggleButton(colEl, filterInput);
        const focusSpy = vi.spyOn(filterInput, "focus");

        btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));

        expect(colEl.classList.contains("filter-visible")).toBe(true);
        expect(table.redraw).toHaveBeenCalledTimes(1);
        expect(focusSpy).toHaveBeenCalledTimes(1);
        expect(btn.getAttribute("aria-expanded")).toBe("true");

        // Clicking again hides it and doesn't re-focus.
        btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));
        expect(colEl.classList.contains("filter-visible")).toBe(false);
        expect(focusSpy).toHaveBeenCalledTimes(1);
        expect(btn.getAttribute("aria-expanded")).toBe("false");
    });

    it("stops the click from bubbling up to the column header (which would sort it)", () => {
        const colEl = document.createElement("div");
        const filterInput = document.createElement("input");
        const table = { redraw: vi.fn() };
        const instance = makeInstance({ table });
        const btn = instance._buildFilterToggleButton(colEl, filterInput);
        document.body.appendChild(colEl);
        colEl.appendChild(btn);

        const parentHandler = vi.fn();
        colEl.addEventListener("click", parentHandler);
        btn.dispatchEvent(new MouseEvent("click", { bubbles: true }));

        expect(parentHandler).not.toHaveBeenCalled();
    });
});
