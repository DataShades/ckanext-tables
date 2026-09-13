import { beforeEach, describe, expect, it, vi } from "vitest";
import { filterItem, makeInstance } from "./support/fixture";

beforeEach(() => {
    document.body.innerHTML = "";
    document.head.innerHTML = "";
    window.history.replaceState({}, "", "/dataset/resource/view");
});

describe("_id / _urlKey", () => {
    it("namespaces DOM ids by table id and URL params by table name", () => {
        const instance = makeInstance({ tableId: "abc123", tableName: "my-resource" });

        expect(instance._id("filters-modal")).toBe("filters-modal-abc123");
        expect(instance._urlKey("field")).toBe("field-my-resource");
    });
});

describe("_collectValidFilters", () => {
    it("only includes filter rows where field, operator, and value are all set", () => {
        const filtersContainer = document.createElement("div");
        filtersContainer.appendChild(filterItem("age", "=", "42"));
        filtersContainer.appendChild(filterItem("", "=", "ignored"));
        document.body.appendChild(filtersContainer);

        const instance = makeInstance({ filtersContainer });

        expect(instance._collectValidFilters()).toEqual([{ field: "age", operator: "=", value: "42" }]);
    });
});

describe("_updateTableFilters", () => {
    it("recomputes tableFilters from the DOM and updates the counter badge", () => {
        const filtersContainer = document.createElement("div");
        filtersContainer.appendChild(filterItem("age", "=", "42"));
        filtersContainer.appendChild(filterItem("name", "like", "smith"));

        const filtersCounter = document.createElement("span");
        filtersCounter.classList.add("d-none");

        const instance = makeInstance({ filtersContainer, filtersCounter });

        const result = instance._updateTableFilters();

        expect(result).toHaveLength(2);
        expect(instance.tableFilters).toBe(result);
        expect(filtersCounter.textContent).toBe("2");
        expect(filtersCounter.classList.contains("d-none")).toBe(false);
    });

    it("re-hides the counter badge when there are no filters left", () => {
        const filtersContainer = document.createElement("div");
        const filtersCounter = document.createElement("span");

        const instance = makeInstance({ filtersContainer, filtersCounter });
        instance._updateTableFilters();

        expect(filtersCounter.textContent).toBe("0");
        expect(filtersCounter.classList.contains("d-none")).toBe(true);
    });
});

describe("_updateUrl", () => {
    it("replaces field/operator/value params to match tableFilters", () => {
        const instance = makeInstance({
            tableName: "my-resource",
            tableFilters: [
                { field: "age", operator: "=", value: "42" },
                { field: "name", operator: "like", value: "smith" },
            ],
        });

        instance._updateUrl();

        const url = new URL(window.location.href);
        expect(url.searchParams.getAll("field-my-resource")).toEqual(["age", "name"]);
        expect(url.searchParams.getAll("operator-my-resource")).toEqual(["=", "like"]);
        expect(url.searchParams.getAll("value-my-resource")).toEqual(["42", "smith"]);
    });

    it("clears stale params when there are no filters", () => {
        window.history.replaceState({}, "", "/x?field-r=age&operator-r=%3D&value-r=42");

        const instance = makeInstance({ tableName: "r", tableFilters: [] });
        instance._updateUrl();

        const url = new URL(window.location.href);
        expect(url.searchParams.has("field-r")).toBe(false);
    });
});

describe("_getCSRFToken", () => {
    it("reads the token named by the csrf_field_name meta tag", () => {
        document.head.innerHTML = `
            <meta name="csrf_field_name" content="_csrf_token" />
            <meta name="_csrf_token" content="secret-token" />
        `;

        expect(makeInstance()._getCSRFToken()).toBe("secret-token");
    });

    it("returns null when the meta tags are missing", () => {
        expect(makeInstance()._getCSRFToken()).toBeNull();
    });
});

describe("_onBulkActionConfirm", () => {
    it("strips the row-actions column and posts the remaining fields as JSON", () => {
        const table = {
            getSelectedData: () => [
                { id: 1, name: "a", actions: "<button>" },
                { id: 2, name: "b", actions: "<button>" },
            ],
        };
        const sendActionRequest = vi.fn();

        const instance = makeInstance({ table, _sendActionRequest: sendActionRequest });
        instance._onBulkActionConfirm("delete", "Delete");

        expect(sendActionRequest).toHaveBeenCalledTimes(1);
        const [form] = sendActionRequest.mock.calls[0];
        expect(form.get("bulk_action")).toBe("delete");
        expect(JSON.parse(form.get("rows") as string)).toEqual([
            { id: 1, name: "a" },
            { id: 2, name: "b" },
        ]);
    });

    it("does nothing when no rows are selected", () => {
        const table = { getSelectedData: () => [] };
        const sendActionRequest = vi.fn();

        const instance = makeInstance({ table, _sendActionRequest: sendActionRequest });
        instance._onBulkActionConfirm("delete", "Delete");

        expect(sendActionRequest).not.toHaveBeenCalled();
    });
});

describe("_syncHeaderFilterState", () => {
    it("marks the column active only when the filter input has a value", () => {
        const colEl = document.createElement("div");
        const filterInput = document.createElement("input");
        const btn = document.createElement("button");

        const instance = makeInstance();

        filterInput.value = "  ";
        instance._syncHeaderFilterState(colEl, filterInput, btn);
        expect(colEl.classList.contains("filter-active")).toBe(false);
        expect(btn.classList.contains("active")).toBe(false);

        filterInput.value = "hello";
        instance._syncHeaderFilterState(colEl, filterInput, btn);
        expect(colEl.classList.contains("filter-active")).toBe(true);
        expect(btn.classList.contains("active")).toBe(true);
    });
});
