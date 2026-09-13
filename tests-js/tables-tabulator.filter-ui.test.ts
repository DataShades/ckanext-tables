import { beforeEach, describe, expect, it, vi } from "vitest";
import { filterItem, makeInstance } from "./support/fixture";

/**
 * A filter-row template with several real `<option>`s per `<select>` — unlike
 * `filterItem()` (which bakes in exactly one, already-selected option to
 * represent a filled-in row), a template needs multiple choices so that
 * `select.value = "…"` from `_recreateFilters` has something to match.
 */
function emptyFilterTemplate(): HTMLElement {
    const item = document.createElement("div");
    item.className = "filter-item";
    item.innerHTML = `
        <select class="filter-field">
            <option value="">-</option>
            <option value="age">age</option>
            <option value="name">name</option>
        </select>
        <select class="filter-operator">
            <option value="">-</option>
            <option value="=">=</option>
            <option value="like">like</option>
        </select>
        <input class="filter-value" />
    `;
    return item;
}

beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/dataset/resource/view");
});

describe("_onApplyFilters", () => {
    it("recomputes filters, drops unfilled rows, updates the URL, and refreshes", () => {
        const filtersContainer = document.createElement("div");
        filtersContainer.appendChild(filterItem("age", "=", "42"));
        const incomplete = filterItem("", "=", "ignored");
        filtersContainer.appendChild(incomplete);

        const filtersCounter = document.createElement("span");
        const clearFiltersBtn = document.createElement("button");
        const clearFiltersModalBtn = document.createElement("button");
        const refreshData = vi.fn();

        const instance = makeInstance({
            filtersContainer,
            filtersCounter,
            clearFiltersBtn,
            clearFiltersModalBtn,
            tableName: "r",
            _refreshData: refreshData,
        });

        instance._onApplyFilters();

        expect(instance.tableFilters).toEqual([{ field: "age", operator: "=", value: "42" }]);
        expect(filtersContainer.contains(incomplete)).toBe(false);
        expect(clearFiltersBtn.classList.contains("btn-table-disabled")).toBe(false);
        expect(new URL(window.location.href).searchParams.getAll("field-r")).toEqual(["age"]);
        expect(refreshData).toHaveBeenCalled();
    });
});

describe("_updateClearButtonsState", () => {
    it("disables both clear buttons when there are no filters", () => {
        const clearFiltersBtn = document.createElement("button");
        const clearFiltersModalBtn = document.createElement("button");
        const instance = makeInstance({ clearFiltersBtn, clearFiltersModalBtn, tableFilters: [] });

        instance._updateClearButtonsState();

        expect(clearFiltersBtn.classList.contains("btn-table-disabled")).toBe(true);
        expect(clearFiltersModalBtn.classList.contains("btn-table-disabled")).toBe(true);
    });

    it("enables both clear buttons when filters are present", () => {
        const clearFiltersBtn = document.createElement("button");
        clearFiltersBtn.classList.add("btn-table-disabled");
        const clearFiltersModalBtn = document.createElement("button");
        clearFiltersModalBtn.classList.add("btn-table-disabled");

        const instance = makeInstance({
            clearFiltersBtn,
            clearFiltersModalBtn,
            tableFilters: [{ field: "a", operator: "=", value: "1" }],
        });

        instance._updateClearButtonsState();

        expect(clearFiltersBtn.classList.contains("btn-table-disabled")).toBe(false);
        expect(clearFiltersModalBtn.classList.contains("btn-table-disabled")).toBe(false);
    });
});

describe("_onClearFilters", () => {
    it("empties the filters container and re-syncs everything else", () => {
        const filtersContainer = document.createElement("div");
        filtersContainer.appendChild(filterItem("age", "=", "42"));

        const filtersCounter = document.createElement("span");
        const clearFiltersBtn = document.createElement("button");
        const clearFiltersModalBtn = document.createElement("button");
        const refreshData = vi.fn();

        const instance = makeInstance({
            filtersContainer,
            filtersCounter,
            clearFiltersBtn,
            clearFiltersModalBtn,
            tableName: "r",
            _refreshData: refreshData,
        });

        instance._onClearFilters();

        expect(filtersContainer.innerHTML).toBe("");
        expect(instance.tableFilters).toEqual([]);
        expect(clearFiltersBtn.classList.contains("btn-table-disabled")).toBe(true);
        expect(new URL(window.location.href).searchParams.has("field-r")).toBe(false);
        expect(refreshData).toHaveBeenCalled();
    });
});

describe("_onAddFilter / _onFilterItemRemove", () => {
    it("clones the (hidden) template into the container and makes it visible", () => {
        const filterTemplate = emptyFilterTemplate();
        filterTemplate.style.display = "none";
        const filtersContainer = document.createElement("div");

        const instance = makeInstance({ filterTemplate, filtersContainer });
        instance._onAddFilter();

        expect(filtersContainer.children).toHaveLength(1);
        expect((filtersContainer.firstElementChild as HTMLElement).style.display).toBe("block");
        // The original template is untouched.
        expect(filterTemplate.style.display).toBe("none");
    });

    it("removes the enclosing .filter-item for the clicked remove button", () => {
        const filtersContainer = document.createElement("div");
        const item = filterItem("age", "=", "42");
        filtersContainer.appendChild(item);
        const removeBtn = document.createElement("button");
        removeBtn.className = "btn-remove-filter";
        item.appendChild(removeBtn);

        const instance = makeInstance({ filtersContainer });
        instance._onFilterItemRemove(removeBtn);

        expect(filtersContainer.children).toHaveLength(0);
    });
});

describe("_recreateFilters / _onCloseFilters", () => {
    it("rebuilds one filter-item per entry in tableFilters from the template", () => {
        const filterTemplate = emptyFilterTemplate();
        const filtersContainer = document.createElement("div");
        filtersContainer.appendChild(filterItem("stale", "=", "x"));

        const instance = makeInstance({
            filterTemplate,
            filtersContainer,
            tableName: "r",
            tableFilters: [
                { field: "age", operator: "=", value: "42" },
                { field: "name", operator: "like", value: "smith" },
            ],
        });

        instance._recreateFilters();

        const items = Array.from(filtersContainer.querySelectorAll(".filter-item")) as HTMLElement[];
        expect(items).toHaveLength(2);
        expect((items[0].querySelector(".filter-field") as HTMLSelectElement).value).toBe("age");
        expect((items[0].querySelector(".filter-operator") as HTMLSelectElement).value).toBe("=");
        expect((items[0].querySelector(".filter-value") as HTMLInputElement).value).toBe("42");
        expect((items[1].querySelector(".filter-field") as HTMLSelectElement).value).toBe("name");
    });

    it("_onCloseFilters delegates to _recreateFilters", () => {
        const instance = makeInstance();
        const recreateFilters = vi.spyOn(instance, "_recreateFilters").mockImplementation(() => {});

        instance._onCloseFilters();

        expect(recreateFilters).toHaveBeenCalledTimes(1);
    });
});

describe("_removeUnfilledFilters", () => {
    it("removes only rows missing field, operator, or value", () => {
        const filtersContainer = document.createElement("div");
        const complete = filterItem("age", "=", "42");
        const missingField = filterItem("", "=", "42");
        const missingValue = filterItem("age", "=", "");
        filtersContainer.append(complete, missingField, missingValue);

        const instance = makeInstance({ filtersContainer });
        instance._removeUnfilledFilters();

        expect(Array.from(filtersContainer.children)).toEqual([complete]);
    });
});
