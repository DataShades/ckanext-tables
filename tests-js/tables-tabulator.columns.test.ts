import { beforeEach, describe, expect, it, vi } from "vitest";
import { makeInstance } from "./support/fixture";

function columnToggle(field: string, checked: boolean): HTMLInputElement {
    const toggle = document.createElement("input");
    toggle.type = "checkbox";
    toggle.dataset.field = field;
    toggle.checked = checked;
    return toggle;
}

/** A table stub that tracks which columns are hidden, like Tabulator does. */
function fakeTable(hidden: string[] = []) {
    const hiddenFields = new Set(hidden);
    return {
        showColumn: vi.fn((field: string) => hiddenFields.delete(field)),
        hideColumn: vi.fn((field: string) => hiddenFields.add(field)),
        redraw: vi.fn(),
        getColumn: (field: string) => ({ isVisible: () => !hiddenFields.has(field) }),
    };
}

beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/dataset/resource/view");
});

describe("_onApplyColumns", () => {
    it("shows checked columns, hides unchecked ones, and persists hidden fields to the URL", () => {
        const columnToggles = [columnToggle("age", true), columnToggle("name", false)];
        const table = fakeTable();
        const hiddenColumnsCounter = document.createElement("span");
        const hiddenColumnsBadge = document.createElement("span");

        const instance = makeInstance({
            columnToggles,
            table,
            tableName: "r",
            hiddenColumnsCounter,
            hiddenColumnsBadge,
        });

        instance._onApplyColumns();

        expect(table.showColumn).toHaveBeenCalledWith("age");
        expect(table.hideColumn).toHaveBeenCalledWith("name");
        expect(table.redraw).toHaveBeenCalledWith(true);
        expect(new URL(window.location.href).searchParams.getAll("hidden_column-r")).toEqual(["name"]);
        expect(hiddenColumnsCounter.textContent).toBe("1");
        expect(hiddenColumnsBadge.classList.contains("d-none")).toBe(false);
    });

    it("skips toggles that have no data-field", () => {
        const toggle = columnToggle("", true);
        const table = { showColumn: vi.fn(), hideColumn: vi.fn(), redraw: vi.fn() };
        const instance = makeInstance({
            columnToggles: [toggle],
            table,
            tableName: "r",
            hiddenColumnsCounter: document.createElement("span"),
            hiddenColumnsBadge: document.createElement("span"),
        });

        instance._onApplyColumns();

        expect(table.showColumn).not.toHaveBeenCalled();
        expect(table.hideColumn).not.toHaveBeenCalled();
    });
});

describe("_onResetColumns", () => {
    it("re-checks and shows every column, clearing hidden state", () => {
        const columnToggles = [columnToggle("age", false), columnToggle("name", false)];
        const table = fakeTable(["age", "name"]);
        const hiddenColumnsCounter = document.createElement("span");
        const hiddenColumnsBadge = document.createElement("span");

        window.history.replaceState({}, "", "/x?hidden_column-r=age&hidden_column-r=name");

        const instance = makeInstance({
            columnToggles,
            table,
            tableName: "r",
            hiddenColumnsCounter,
            hiddenColumnsBadge,
        });

        instance._onResetColumns();

        expect(columnToggles.every((t) => t.checked)).toBe(true);
        expect(table.showColumn).toHaveBeenCalledWith("age");
        expect(table.showColumn).toHaveBeenCalledWith("name");
        expect(new URL(window.location.href).searchParams.has("hidden_column-r")).toBe(false);
        expect(hiddenColumnsCounter.textContent).toBe("0");
        expect(hiddenColumnsBadge.classList.contains("d-none")).toBe(true);
    });

    it("restores columns that are hidden by default instead of showing them", () => {
        const columnToggles = [columnToggle("age", false), columnToggle("created", true)];
        const table = fakeTable(["age"]);
        const hiddenColumnsCounter = document.createElement("span");
        const hiddenColumnsBadge = document.createElement("span");

        window.history.replaceState({}, "", "/x?hidden_column-r=age");

        const instance = makeInstance({
            columnToggles,
            table,
            tableName: "r",
            hiddenColumnsCounter,
            hiddenColumnsBadge,
            options: { config: { columns: [{ field: "age" }, { field: "created", visible: false }] } },
        });

        instance._onResetColumns();

        expect(columnToggles.map((t) => t.checked)).toEqual([true, false]);
        expect(table.showColumn).toHaveBeenCalledWith("age");
        expect(table.hideColumn).toHaveBeenCalledWith("created");
        expect(new URL(window.location.href).searchParams.has("hidden_column-r")).toBe(false);
        expect(hiddenColumnsCounter.textContent).toBe("1");
        expect(hiddenColumnsBadge.classList.contains("d-none")).toBe(false);
    });
});

describe("_onCloseColumns", () => {
    it("re-syncs checkbox state to the table's actual column visibility", () => {
        const visibleToggle = columnToggle("age", false);
        const hiddenToggle = columnToggle("name", true);
        const table = {
            getColumn: (field: string) => ({
                isVisible: () => field === "age",
            }),
        };

        const instance = makeInstance({ columnToggles: [visibleToggle, hiddenToggle], table });
        instance._onCloseColumns();

        expect(visibleToggle.checked).toBe(true);
        expect(hiddenToggle.checked).toBe(false);
    });

    it("leaves a toggle untouched when the column no longer exists", () => {
        const toggle = columnToggle("ghost", true);
        const table = { getColumn: () => undefined };

        const instance = makeInstance({ columnToggles: [toggle], table });
        expect(() => instance._onCloseColumns()).not.toThrow();
        expect(toggle.checked).toBe(true);
    });
});

describe("_onSelectAllColumns / _onDeselectAllColumns", () => {
    it("checks every toggle", () => {
        const toggles = [columnToggle("a", false), columnToggle("b", false)];
        makeInstance({ columnToggles: toggles })._onSelectAllColumns();
        expect(toggles.every((t) => t.checked)).toBe(true);
    });

    it("unchecks every toggle", () => {
        const toggles = [columnToggle("a", true), columnToggle("b", true)];
        makeInstance({ columnToggles: toggles })._onDeselectAllColumns();
        expect(toggles.every((t) => !t.checked)).toBe(true);
    });
});

describe("_applyColumnVisibilityFromUrl", () => {
    it("hides every column named in hidden_column URL params", () => {
        window.history.replaceState({}, "", "/x?hidden_column-r=age&hidden_column-r=name");
        const table = fakeTable();
        const hiddenColumnsCounter = document.createElement("span");
        const hiddenColumnsBadge = document.createElement("span");

        const instance = makeInstance({
            columnToggles: [columnToggle("age", true), columnToggle("name", true), columnToggle("id", true)],
            table,
            tableName: "r",
            hiddenColumnsCounter,
            hiddenColumnsBadge,
        });
        instance._applyColumnVisibilityFromUrl();

        expect(table.hideColumn).toHaveBeenCalledWith("age");
        expect(table.hideColumn).toHaveBeenCalledWith("name");
        expect(hiddenColumnsCounter.textContent).toBe("2");
    });

    it("swallows errors for columns that no longer exist", () => {
        window.history.replaceState({}, "", "/x?hidden_column-r=ghost");
        const table = {
            hideColumn: vi.fn(() => {
                throw new Error("no such column");
            }),
        };

        const instance = makeInstance({
            columnToggles: [],
            table,
            tableName: "r",
            hiddenColumnsCounter: document.createElement("span"),
            hiddenColumnsBadge: document.createElement("span"),
        });

        expect(() => instance._applyColumnVisibilityFromUrl()).not.toThrow();
    });
});

describe("_updateHiddenColumnsCounter", () => {
    it("shows the badge only when at least one column is hidden", () => {
        const table = fakeTable();
        const hiddenColumnsCounter = document.createElement("span");
        const hiddenColumnsBadge = document.createElement("span");
        const instance = makeInstance({
            columnToggles: [columnToggle("age", true), columnToggle("name", true)],
            table,
            tableName: "r",
            hiddenColumnsCounter,
            hiddenColumnsBadge,
        });

        instance._updateHiddenColumnsCounter();
        expect(hiddenColumnsCounter.textContent).toBe("0");
        expect(hiddenColumnsBadge.classList.contains("d-none")).toBe(true);

        table.hideColumn("age");
        instance._updateHiddenColumnsCounter();
        expect(hiddenColumnsCounter.textContent).toBe("1");
        expect(hiddenColumnsBadge.classList.contains("d-none")).toBe(false);
    });

    it("counts columns hidden by default, with nothing in the URL", () => {
        window.history.replaceState({}, "", "/dataset/resource/view");
        const hiddenColumnsCounter = document.createElement("span");
        const hiddenColumnsBadge = document.createElement("span");
        const instance = makeInstance({
            columnToggles: [columnToggle("age", true), columnToggle("created", false)],
            table: fakeTable(["created"]),
            tableName: "r",
            hiddenColumnsCounter,
            hiddenColumnsBadge,
        });

        instance._updateHiddenColumnsCounter();

        expect(hiddenColumnsCounter.textContent).toBe("1");
        expect(hiddenColumnsBadge.classList.contains("d-none")).toBe(false);
    });

    it("ignores toggles without a field or whose column is gone", () => {
        const hiddenColumnsCounter = document.createElement("span");
        const instance = makeInstance({
            columnToggles: [columnToggle("", false), columnToggle("ghost", false)],
            table: { getColumn: () => false },
            hiddenColumnsCounter,
            hiddenColumnsBadge: document.createElement("span"),
        });

        instance._updateHiddenColumnsCounter();

        expect(hiddenColumnsCounter.textContent).toBe("0");
    });
});

describe("_updateColumnsUrl", () => {
    it("replaces hidden_column params to match the given list", () => {
        window.history.replaceState({}, "", "/x?hidden_column-r=stale");
        const instance = makeInstance({ tableName: "r" });

        instance._updateColumnsUrl(["age", "name"]);

        expect(new URL(window.location.href).searchParams.getAll("hidden_column-r")).toEqual(["age", "name"]);
    });

    it("clears the params entirely for an empty list", () => {
        window.history.replaceState({}, "", "/x?hidden_column-r=stale");
        const instance = makeInstance({ tableName: "r" });

        instance._updateColumnsUrl([]);

        expect(new URL(window.location.href).searchParams.has("hidden_column-r")).toBe(false);
    });
});
