import { beforeEach, describe, expect, it } from "vitest";
import { makeInstance } from "./support/fixture";

beforeEach(() => {
    window.history.replaceState({}, "", "/dataset/resource/view");
});

describe("_initFiltersFromUrl", () => {
    it("rebuilds tableFilters from matching field/operator/value params and updates the counter", () => {
        window.history.replaceState(
            {},
            "",
            "/x?field-r=age&operator-r=%3D&value-r=42&field-r=name&operator-r=like&value-r=smith"
        );

        const filtersCounter = document.createElement("span");
        filtersCounter.classList.add("d-none");
        const clearFiltersBtn = document.createElement("button");
        const clearFiltersModalBtn = document.createElement("button");

        const instance = makeInstance({ tableName: "r", filtersCounter, clearFiltersBtn, clearFiltersModalBtn });
        instance._initFiltersFromUrl();

        expect(instance.tableFilters).toEqual([
            { field: "age", operator: "=", value: "42" },
            { field: "name", operator: "like", value: "smith" },
        ]);
        expect(filtersCounter.textContent).toBe("2");
        expect(filtersCounter.classList.contains("d-none")).toBe(false);
        expect(clearFiltersBtn.classList.contains("btn-table-disabled")).toBe(false);
    });

    it("leaves tableFilters untouched when the param counts don't line up", () => {
        window.history.replaceState({}, "", "/x?field-r=age&operator-r=%3D");

        const instance = makeInstance({ tableName: "r", tableFilters: "unchanged" as any });
        instance._initFiltersFromUrl();

        expect(instance.tableFilters).toBe("unchanged");
    });

    it("leaves tableFilters untouched when there are no filter params at all", () => {
        const instance = makeInstance({ tableName: "r", tableFilters: "unchanged" as any });
        instance._initFiltersFromUrl();

        expect(instance.tableFilters).toBe("unchanged");
    });
});
