import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeInstance } from "./support/fixture";

beforeEach(() => {
    document.body.innerHTML = "";
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
});

describe("_showToast", () => {
    it("forwards message/type/stacking to ckan.tablesToast with the Tables title", () => {
        const tablesToast = vi.fn();
        const instance = makeInstance({}, undefined, { tablesToast });

        instance._showToast("Saved", "danger", false);

        expect(tablesToast).toHaveBeenCalledWith({
            message: "Saved",
            type: "danger",
            title: "Tables",
            stacking: false,
        });
    });

    it("defaults to type 'default' and stacking true", () => {
        const tablesToast = vi.fn();
        const instance = makeInstance({}, undefined, { tablesToast });

        instance._showToast("Saved");

        expect(tablesToast).toHaveBeenCalledWith(expect.objectContaining({ type: "default", stacking: true }));
    });
});

describe("_confirmAction", () => {
    it("asks ckan.tablesConfirm and forwards onConfirm", () => {
        const tablesConfirm = vi.fn();
        const onConfirm = vi.fn();
        const instance = makeInstance({}, undefined, { tablesConfirm });

        instance._confirmAction("Delete row", onConfirm);

        expect(tablesConfirm).toHaveBeenCalledTimes(1);
        const call = tablesConfirm.mock.calls[0][0];
        expect(call.message).toContain("Delete row");

        call.onConfirm();
        expect(onConfirm).toHaveBeenCalled();
    });
});

describe("_rowActionCallback", () => {
    it("confirms first when the action requires confirmation", () => {
        const instance = makeInstance();
        const confirmAction = vi.spyOn(instance, "_confirmAction").mockImplementation(() => {});
        const onRowActionConfirm = vi.spyOn(instance, "_onRowActionConfirm").mockImplementation(() => {});

        const action = { name: "delete", label: "Delete", with_confirmation: true };
        const row = { getData: () => ({ id: 1 }) };
        instance._rowActionCallback(action, new Event("click"), row);

        expect(confirmAction).toHaveBeenCalledWith("Delete", expect.any(Function));
        expect(onRowActionConfirm).not.toHaveBeenCalled();

        // Simulate the user accepting the confirmation dialog.
        confirmAction.mock.calls[0][1]();
        expect(onRowActionConfirm).toHaveBeenCalledWith(action, row);
    });

    it("runs immediately when no confirmation is required", () => {
        const instance = makeInstance();
        const onRowActionConfirm = vi.spyOn(instance, "_onRowActionConfirm").mockImplementation(() => {});

        const action = { name: "view", label: "View" };
        const row = { getData: () => ({ id: 1 }) };
        instance._rowActionCallback(action, new Event("click"), row);

        expect(onRowActionConfirm).toHaveBeenCalledWith(action, row);
    });
});

describe("_onRowActionConfirm", () => {
    it("posts the row action name and serialized row data", () => {
        const sendActionRequest = vi.fn();
        const instance = makeInstance({ _sendActionRequest: sendActionRequest });

        const action = { name: "delete", label: "Delete" };
        const row = { getData: () => ({ id: 7, name: "x" }) };
        instance._onRowActionConfirm(action, row);

        expect(sendActionRequest).toHaveBeenCalledTimes(1);
        const [form, message] = sendActionRequest.mock.calls[0];
        expect(form.get("row_action")).toBe("delete");
        expect(JSON.parse(form.get("row") as string)).toEqual({ id: 7, name: "x" });
        expect(message).toContain("Delete");
    });
});

describe("_sendActionRequest", () => {
    function setup() {
        const refreshData = vi.fn().mockResolvedValue(undefined);
        const showToast = vi.fn();
        const instance = makeInstance({
            sandbox: { client: { url: (u: string) => u } },
            options: { config: { ajaxURL: "/table" } },
            _refreshData: refreshData,
            _showToast: showToast,
            _getCSRFToken: () => "token-123",
        });
        return { instance, refreshData, showToast };
    }

    it("refreshes the table and shows the success message on success", async () => {
        const { instance, refreshData, showToast } = setup();
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: () => Promise.resolve({ success: true }) }));

        await instance._sendActionRequest(new FormData(), "Done!");

        expect(fetch).toHaveBeenCalledWith(
            "/table",
            expect.objectContaining({ method: "POST", headers: { "X-CSRFToken": "token-123" } })
        );
        expect(refreshData).toHaveBeenCalled();
        expect(showToast).toHaveBeenCalledWith("Done!");
    });

    it("prefers the server-provided message over the default on success", async () => {
        const { instance, showToast } = setup();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({ json: () => Promise.resolve({ success: true, message: "Server said hi" }) })
        );

        await instance._sendActionRequest(new FormData(), "Default message");

        expect(showToast).toHaveBeenCalledWith("Server said hi");
    });

    it("redirects instead of refreshing when the response asks for it", async () => {
        const { instance, refreshData } = setup();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({ json: () => Promise.resolve({ success: true, redirect: "/somewhere" }) })
        );

        // jsdom doesn't implement real navigation: assigning location.href throws,
        // which the source's own .catch() already handles, so this resolves
        // normally — the assertion below is what matters. jsdom's virtual
        // console separately logs an "Error: Not implemented: navigation" line
        // for this regardless of the exception being caught; that's expected
        // noise from this one test, not a failure (it doesn't affect the exit
        // code), and isn't reachable from here to suppress.
        await instance._sendActionRequest(new FormData(), "Done!");

        expect(refreshData).not.toHaveBeenCalled();
    });

    it("shows the server error message in full and does not refresh", async () => {
        const { instance, showToast, refreshData } = setup();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({
                json: () => Promise.resolve({ success: false, error: "bad field" }),
            })
        );

        await instance._sendActionRequest(new FormData(), "Done!");

        expect(showToast).toHaveBeenCalledWith("bad field", "danger");
        expect(refreshData).not.toHaveBeenCalled();
    });

    it("falls back to 'Unknown error' when the response gives no error detail", async () => {
        const { instance, showToast } = setup();
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ json: () => Promise.resolve({ success: false }) }));

        await instance._sendActionRequest(new FormData(), "Done!");

        expect(showToast).toHaveBeenCalledWith("Unknown error", "danger");
    });

    it("shows a toast when the request itself rejects", async () => {
        const { instance, showToast } = setup();
        vi.stubGlobal("fetch", vi.fn().mockRejectedValue(new Error("network down")));

        await instance._sendActionRequest(new FormData(), "Done!");

        expect(showToast).toHaveBeenCalledWith("network down", "danger");
    });
});

describe("_onApplyBulkAction / _onApplyTableAction", () => {
    it("bulk action confirms by default and reads action/label from dataset", () => {
        const instance = makeInstance();
        const confirmAction = vi.spyOn(instance, "_confirmAction").mockImplementation(() => {});

        const target = document.createElement("button");
        target.dataset.action = "delete";
        target.textContent = "Delete selected";

        instance._onApplyBulkAction({ currentTarget: target } as unknown as Event);

        expect(confirmAction).toHaveBeenCalledWith("Delete selected", expect.any(Function));
    });

    it("bulk action skips confirmation when data-with-confirmation is 'false'", () => {
        const instance = makeInstance();
        const confirmAction = vi.spyOn(instance, "_confirmAction").mockImplementation(() => {});
        const onBulkActionConfirm = vi.spyOn(instance, "_onBulkActionConfirm").mockImplementation(() => {});

        const target = document.createElement("button");
        target.dataset.action = "export";
        target.dataset.withConfirmation = "false";
        target.textContent = "Export";

        instance._onApplyBulkAction({ currentTarget: target } as unknown as Event);

        expect(confirmAction).not.toHaveBeenCalled();
        expect(onBulkActionConfirm).toHaveBeenCalledWith("export", "Export");
    });

    it("does nothing when the button has no data-action", () => {
        const instance = makeInstance();
        const confirmAction = vi.spyOn(instance, "_confirmAction").mockImplementation(() => {});

        const target = document.createElement("button");
        instance._onApplyBulkAction({ currentTarget: target } as unknown as Event);

        expect(confirmAction).not.toHaveBeenCalled();
    });

    it("table action confirms by default and reads action/label from dataset", () => {
        const instance = makeInstance();
        const confirmAction = vi.spyOn(instance, "_confirmAction").mockImplementation(() => {});

        const target = document.createElement("button");
        target.dataset.action = "recalculate";
        target.textContent = "Recalculate";

        instance._onApplyTableAction({ currentTarget: target } as unknown as Event);

        expect(confirmAction).toHaveBeenCalledWith("Recalculate", expect.any(Function));
    });

    it("table action skips confirmation when data-with-confirmation is 'false'", () => {
        const instance = makeInstance();
        const confirmAction = vi.spyOn(instance, "_confirmAction").mockImplementation(() => {});
        const onTableActionConfirm = vi.spyOn(instance, "_onTableActionConfirm").mockImplementation(() => {});

        const target = document.createElement("button");
        target.dataset.action = "recalculate";
        target.dataset.withConfirmation = "false";
        target.textContent = "Recalculate";

        instance._onApplyTableAction({ currentTarget: target } as unknown as Event);

        expect(confirmAction).not.toHaveBeenCalled();
        expect(onTableActionConfirm).toHaveBeenCalledWith("recalculate", "Recalculate");
    });

    it("table action posts table_action and the action name", () => {
        const sendActionRequest = vi.fn();
        const instance = makeInstance({ _sendActionRequest: sendActionRequest });

        instance._onTableActionConfirm("recalculate", "Recalculate");

        const [form, message] = sendActionRequest.mock.calls[0];
        expect(form.get("table_action")).toBe("recalculate");
        expect(message).toContain("Recalculate");
    });
});

describe("_onRowActionsDropdownClick", () => {
    // jsdom's real MouseEvent constructor rejects `view: window` here — `window
    // instanceof Window` is false under this jsdom/vitest combination even for
    // plain jsdom globals, unrelated to anything this module does. A lenient
    // stand-in lets the source's real `new MouseEvent(...)` call succeed so we
    // can still verify what gets dispatched.
    class LenientMouseEvent extends Event {
        button: number;
        clientX: number;
        clientY: number;
        constructor(type: string, init: MouseEventInit = {}) {
            super(type, init);
            this.button = init.button ?? 0;
            this.clientX = init.clientX ?? 0;
            this.clientY = init.clientY ?? 0;
        }
    }

    beforeEach(() => {
        vi.stubGlobal("MouseEvent", LenientMouseEvent);
    });

    it("dispatches a synthetic contextmenu event on the row under the click", () => {
        const row = document.createElement("div");
        row.className = "tabulator-row";
        const btn = document.createElement("button");
        row.appendChild(btn);
        document.body.appendChild(row);

        const contextMenuHandler = vi.fn();
        row.addEventListener("contextmenu", contextMenuHandler);

        const instance = makeInstance();
        const clickEvent = new MouseEvent("click", { bubbles: true, cancelable: true });
        Object.defineProperty(clickEvent, "target", { value: btn });
        const preventDefault = vi.spyOn(clickEvent, "preventDefault");

        instance._onRowActionsDropdownClick(clickEvent);

        expect(preventDefault).toHaveBeenCalled();
        expect(contextMenuHandler).toHaveBeenCalledTimes(1);
        const dispatched = contextMenuHandler.mock.calls[0][0] as MouseEvent;
        expect(dispatched.button).toBe(2);
    });

    it("does nothing when the click target isn't inside a row", () => {
        const instance = makeInstance();
        const clickEvent = new MouseEvent("click");
        Object.defineProperty(clickEvent, "target", { value: document.createElement("button") });

        expect(() => instance._onRowActionsDropdownClick(clickEvent)).not.toThrow();
    });
});
