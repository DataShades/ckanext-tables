import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";
import { makeInstance } from "./support/fixture";

function buildExportersMenu(exporter: string, label: string) {
    const parent = document.createElement("div");
    const toggle = document.createElement("button");
    const tableExportersMenu = document.createElement("div");
    parent.append(toggle, tableExportersMenu);

    const button = document.createElement("button");
    button.dataset.exporter = exporter;
    button.innerText = label;
    tableExportersMenu.appendChild(button);

    return { toggle, tableExportersMenu, button };
}

beforeEach(() => {
    document.body.innerHTML = "";
    (globalThis as any).bootstrap = { Dropdown: { getInstance: vi.fn(() => ({ hide: vi.fn() })) } };
    vi.stubGlobal("URL", Object.assign(URL, { createObjectURL: vi.fn(() => "blob:fake"), revokeObjectURL: vi.fn() }));
    vi.spyOn(HTMLAnchorElement.prototype, "click").mockImplementation(() => {});
});

afterEach(() => {
    vi.restoreAllMocks();
    vi.unstubAllGlobals();
    vi.useRealTimers();
});

describe("_onTableExportClick", () => {
    it("does nothing when the clicked element has no data-exporter", async () => {
        const instance = makeInstance();
        const fetchSpy = vi.fn();
        vi.stubGlobal("fetch", fetchSpy);

        await instance._onTableExportClick({ target: document.createElement("button") } as unknown as Event);

        expect(fetchSpy).not.toHaveBeenCalled();
    });

    it("fetches the export URL (with filters/sort baked in), downloads the blob, and toasts twice", async () => {
        const { toggle, tableExportersMenu, button } = buildExportersMenu("csv", "CSV");
        const table = { getSorters: () => [{ field: "age", dir: "desc" }] };
        const showToast = vi.fn();
        const blob = new Blob(["a,b\n1,2"], { type: "text/csv" });
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            blob: () => Promise.resolve(blob),
            headers: { get: () => null },
        });
        vi.stubGlobal("fetch", fetchMock);

        window.history.replaceState({}, "", "/dataset/resource/view");

        const instance = makeInstance({
            tableExportersMenu,
            table,
            tableName: "my-resource",
            tableFilters: [{ field: "age", operator: "=", value: "42" }],
            sandbox: { client: { url: (u: string) => u } },
            options: { config: { ajaxURL: "/table" } },
            _showToast: showToast,
        });

        await instance._onTableExportClick({ target: button } as unknown as Event);

        expect(fetchMock).toHaveBeenCalledTimes(1);
        const requestedUrl = new URL(fetchMock.mock.calls[0][0] as string, "http://localhost");
        expect(requestedUrl.searchParams.get("exporter")).toBe("csv");
        expect(JSON.parse(requestedUrl.searchParams.get("filters") as string)).toEqual([
            { field: "age", operator: "=", value: "42" },
        ]);
        expect(requestedUrl.searchParams.get("sort[0][field]")).toBe("age");
        expect(requestedUrl.searchParams.get("sort[0][dir]")).toBe("desc");

        expect((URL.createObjectURL as any)).toHaveBeenCalledWith(blob);
        expect((URL.revokeObjectURL as any)).toHaveBeenCalledWith("blob:fake");
        expect(HTMLAnchorElement.prototype.click).toHaveBeenCalledTimes(1);
        // COR-17: falls back to the table name when there's no Content-Disposition header.
        expect((HTMLAnchorElement.prototype.click as any).mock.contexts[0].download).toBe("my-resource.csv");

        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("CSV"));
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("CSV"), "default", false);

        // Buttons/toggle are disabled during the request and re-enabled after.
        expect(button.disabled).toBe(false);
        expect(toggle.hasAttribute("disabled")).toBe(false);
    });

    it("uses the filename from the server's Content-Disposition header when present", async () => {
        const { tableExportersMenu, button } = buildExportersMenu("csv", "CSV");
        const blob = new Blob(["a,b\n1,2"], { type: "text/csv" });
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            blob: () => Promise.resolve(blob),
            headers: { get: () => 'attachment; filename="my-resource-2026-09-13 14-00-00.csv"' },
        });
        vi.stubGlobal("fetch", fetchMock);

        const instance = makeInstance({
            tableExportersMenu,
            table: { getSorters: () => [] },
            tableName: "my-resource",
            tableFilters: [],
            sandbox: { client: { url: (u: string) => u } },
            options: { config: { ajaxURL: "/table" } },
            _showToast: vi.fn(),
        });

        await instance._onTableExportClick({ target: button } as unknown as Event);

        expect((HTMLAnchorElement.prototype.click as any).mock.contexts[0].download).toBe(
            "my-resource-2026-09-13 14-00-00.csv"
        );
    });

    it("shows a spinner on the toggle icon while exporting and restores it once done", async () => {
        const { toggle, tableExportersMenu, button } = buildExportersMenu("csv", "CSV");
        const icon = document.createElement("i");
        icon.className = "fa fa-download";
        toggle.appendChild(icon);

        const blob = new Blob(["a,b\n1,2"], { type: "text/csv" });
        let resolveFetch: (value: unknown) => void = () => {};
        const fetchMock = vi.fn(() => new Promise((resolve) => (resolveFetch = resolve)));
        vi.stubGlobal("fetch", fetchMock);

        const instance = makeInstance({
            tableExportersMenu,
            table: { getSorters: () => [] },
            tableFilters: [],
            sandbox: { client: { url: (u: string) => u } },
            options: { config: { ajaxURL: "/table" } },
            _showToast: vi.fn(),
        });

        const clickPromise = instance._onTableExportClick({ target: button } as unknown as Event);
        await Promise.resolve();

        expect(icon.className).toBe("fa fa-spinner tables-icon-spin");
        expect(toggle.getAttribute("aria-busy")).toBe("true");

        resolveFetch({ ok: true, blob: () => Promise.resolve(blob), headers: { get: () => null } });
        await clickPromise;

        expect(icon.className).toBe("fa fa-download");
        expect(toggle.hasAttribute("aria-busy")).toBe(false);
    });

    it("shows a toast with a link to the status page for a background export (202), and starts tracking it, without downloading anything itself", async () => {
        const { tableExportersMenu, button } = buildExportersMenu("pdf", "PDF");
        const showToast = vi.fn();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({
                ok: true,
                status: 202,
                json: () => Promise.resolve({ success: true, job_id: "abc123", status_url: "/export-status/abc123" }),
            })
        );

        const instance = makeInstance({
            tableExportersMenu,
            table: { getSorters: () => [] },
            tableFilters: [],
            sandbox: { client: { url: (u: string) => u } },
            options: { config: { ajaxURL: "/table" } },
            _showToast: showToast,
        });
        // The poll loop itself has its own dedicated tests below — stub it out
        // here so this test isn't also on the hook for controlling its timers.
        const pollExportStatus = vi.spyOn(instance, "_pollExportStatus").mockImplementation(() => {});

        await instance._onTableExportClick({ target: button } as unknown as Event);

        expect((URL.createObjectURL as any)).not.toHaveBeenCalled();
        expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();

        const backgroundToastCall = showToast.mock.calls.find((call) => String(call[0]).includes("/export-status/abc123"));
        expect(backgroundToastCall).toBeDefined();
        expect(backgroundToastCall![1]).toBe("default");
        expect(backgroundToastCall![2]).toBe(false);
        expect(backgroundToastCall![3]).toBe(10000);

        expect(pollExportStatus).toHaveBeenCalledWith("/export-status/abc123", "PDF", expect.any(Function));
    });

    it("shows a failure toast and re-enables controls when the response isn't ok", async () => {
        const { tableExportersMenu, button } = buildExportersMenu("xlsx", "XLSX");
        const showToast = vi.fn();
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false, json: () => Promise.resolve({}) }));
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

        const instance = makeInstance({
            tableExportersMenu,
            table: { getSorters: () => [] },
            tableFilters: [],
            sandbox: { client: { url: (u: string) => u } },
            options: { config: { ajaxURL: "/table" } },
            _showToast: showToast,
        });

        await instance._onTableExportClick({ target: button } as unknown as Event);

        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("failed"), "danger", false);
        expect(button.disabled).toBe(false);
        consoleError.mockRestore();
    });

    it("shows the server's error detail (e.g. row cap exceeded) instead of a generic message", async () => {
        const { tableExportersMenu, button } = buildExportersMenu("csv", "CSV");
        const showToast = vi.fn();
        const serverMessage = "Cannot export 15000 rows: the maximum is 10000. Add filters to narrow the result set.";
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({
                ok: false,
                json: () => Promise.resolve({ success: false, error: serverMessage }),
            })
        );
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

        const instance = makeInstance({
            tableExportersMenu,
            table: { getSorters: () => [] },
            tableFilters: [],
            sandbox: { client: { url: (u: string) => u } },
            options: { config: { ajaxURL: "/table" } },
            _showToast: showToast,
        });

        await instance._onTableExportClick({ target: button } as unknown as Event);

        expect(showToast).toHaveBeenCalledWith(serverMessage, "danger", false);
        consoleError.mockRestore();
    });

    it("falls back to a generic message when the error body isn't JSON", async () => {
        const { tableExportersMenu, button } = buildExportersMenu("csv", "CSV");
        const showToast = vi.fn();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({ ok: false, json: () => Promise.reject(new Error("not json")) })
        );
        const consoleError = vi.spyOn(console, "error").mockImplementation(() => {});

        const instance = makeInstance({
            tableExportersMenu,
            table: { getSorters: () => [] },
            tableFilters: [],
            sandbox: { client: { url: (u: string) => u } },
            options: { config: { ajaxURL: "/table" } },
            _showToast: showToast,
        });

        await instance._onTableExportClick({ target: button } as unknown as Event);

        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("failed"), "danger", false);
        consoleError.mockRestore();
    });
});

describe("_pollExportStatus", () => {
    beforeEach(() => {
        vi.useFakeTimers();
    });

    it("auto-downloads and toasts once the job finishes", async () => {
        const showToast = vi.fn();
        const resetUi = vi.fn();
        const fetchMock = vi.fn().mockResolvedValue({
            ok: true,
            json: () =>
                Promise.resolve({ status: "finished", download_url: "/export-download/abc123", error: null }),
        });
        vi.stubGlobal("fetch", fetchMock);

        const instance = makeInstance({ _showToast: showToast });

        instance._pollExportStatus("/export-status/abc123", "PDF", resetUi);
        await vi.advanceTimersByTimeAsync(2000);

        expect(fetchMock).toHaveBeenCalledWith("/export-status/abc123", {
            headers: { "X-Requested-With": "XMLHttpRequest" },
        });
        expect((HTMLAnchorElement.prototype.click as any).mock.contexts[0].href).toContain(
            "/export-download/abc123"
        );
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("PDF"), "default", false);
        expect(resetUi).toHaveBeenCalledTimes(1);

        // Nothing further is scheduled once the job has reached a terminal state.
        fetchMock.mockClear();
        await vi.advanceTimersByTimeAsync(10000);
        expect(fetchMock).not.toHaveBeenCalled();
    });

    it("toasts the server's error and stops when the job fails", async () => {
        const showToast = vi.fn();
        const resetUi = vi.fn();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ status: "failed", download_url: null, error: "Disk full" }),
            })
        );

        const instance = makeInstance({ _showToast: showToast });

        instance._pollExportStatus("/export-status/abc123", "PDF", resetUi);
        await vi.advanceTimersByTimeAsync(2000);

        expect(HTMLAnchorElement.prototype.click).not.toHaveBeenCalled();
        expect(showToast).toHaveBeenCalledWith("Disk full", "danger", false);
        expect(resetUi).toHaveBeenCalledTimes(1);
    });

    it("toasts and stops when the job id is no longer known to the server", async () => {
        const showToast = vi.fn();
        const resetUi = vi.fn();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ status: "not_found", download_url: null, error: null }),
            })
        );

        const instance = makeInstance({ _showToast: showToast });

        instance._pollExportStatus("/export-status/abc123", "PDF", resetUi);
        await vi.advanceTimersByTimeAsync(2000);

        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("PDF"), "danger", false);
        expect(resetUi).toHaveBeenCalledTimes(1);
    });

    it("gives up and toasts a timeout after the max number of attempts", async () => {
        const showToast = vi.fn();
        const resetUi = vi.fn();
        vi.stubGlobal(
            "fetch",
            vi.fn().mockResolvedValue({
                ok: true,
                json: () => Promise.resolve({ status: "started", download_url: null, error: null }),
            })
        );

        const instance = makeInstance({ _showToast: showToast });

        instance._pollExportStatus("/export-status/abc123", "PDF", resetUi);
        await vi.advanceTimersByTimeAsync(instance._EXPORT_POLL_INTERVAL_MS * instance._EXPORT_POLL_MAX_ATTEMPTS);

        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("longer than expected"), "danger", false);
        expect(resetUi).toHaveBeenCalledTimes(1);
    });

    it("keeps polling through a transient network error and finishes on the next tick", async () => {
        const showToast = vi.fn();
        const resetUi = vi.fn();
        const fetchMock = vi
            .fn()
            .mockRejectedValueOnce(new TypeError("Failed to fetch"))
            .mockResolvedValueOnce({
                ok: true,
                json: () =>
                    Promise.resolve({ status: "finished", download_url: "/export-download/abc123", error: null }),
            });
        vi.stubGlobal("fetch", fetchMock);

        const instance = makeInstance({ _showToast: showToast });

        instance._pollExportStatus("/export-status/abc123", "PDF", resetUi);
        await vi.advanceTimersByTimeAsync(2000);
        expect(resetUi).not.toHaveBeenCalled();

        await vi.advanceTimersByTimeAsync(2000);
        expect(fetchMock).toHaveBeenCalledTimes(2);
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("PDF"), "default", false);
        expect(resetUi).toHaveBeenCalledTimes(1);
    });
});

describe("_filenameFromContentDisposition", () => {
    const instance = makeInstance();

    it("returns null for a missing header", () => {
        expect(instance._filenameFromContentDisposition(null)).toBeNull();
        expect(instance._filenameFromContentDisposition(undefined)).toBeNull();
    });

    it("extracts a quoted filename", () => {
        expect(instance._filenameFromContentDisposition('attachment; filename="my table.csv"')).toBe(
            "my table.csv"
        );
    });

    it("extracts an unquoted filename", () => {
        expect(instance._filenameFromContentDisposition("attachment; filename=data.csv")).toBe("data.csv");
    });

    it("decodes an RFC 5987 filename*=UTF-8'' value", () => {
        expect(
            instance._filenameFromContentDisposition("attachment; filename*=UTF-8''caf%C3%A9.csv")
        ).toBe("café.csv");
    });

    it("returns null when the header has no filename parameter", () => {
        expect(instance._filenameFromContentDisposition("attachment")).toBeNull();
    });
});

describe("_onRefreshTable / _refreshData", () => {
    function setup() {
        const tableRefreshBtn = document.createElement("button");
        const replaceData = vi.fn().mockResolvedValue(undefined);
        const showToast = vi.fn();
        const instance = makeInstance({
            tableRefreshBtn,
            table: { replaceData },
            sandbox: { client: { url: (u: string) => u } },
            options: { config: { ajaxURL: "/table" } },
            _showToast: showToast,
            _getCSRFToken: () => "tok",
        });
        return { instance, tableRefreshBtn, replaceData, showToast };
    }

    it("disables the button, refreshes data, and re-enables it on success", async () => {
        const { instance, tableRefreshBtn, replaceData, showToast } = setup();
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: true }));

        // _onRefreshTable doesn't return its internal fetch().then()...finally()
        // chain, so there's nothing to await directly — flush a macrotask to
        // let it settle instead.
        instance._onRefreshTable();
        await new Promise((resolve) => setTimeout(resolve, 0));

        expect(replaceData).toHaveBeenCalled();
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("refreshed"));
        expect(tableRefreshBtn.hasAttribute("disabled")).toBe(false);
    });

    it("shows an error toast and re-enables the button when the response isn't ok", async () => {
        const { instance, tableRefreshBtn, replaceData, showToast } = setup();
        vi.stubGlobal("fetch", vi.fn().mockResolvedValue({ ok: false }));

        instance._onRefreshTable();
        await new Promise((resolve) => setTimeout(resolve, 0));

        expect(replaceData).not.toHaveBeenCalled();
        expect(showToast).toHaveBeenCalledWith(expect.stringContaining("Failed"), "danger");
        expect(tableRefreshBtn.hasAttribute("disabled")).toBe(false);
    });

    it("_refreshData delegates straight to table.replaceData()", () => {
        const replaceData = vi.fn().mockReturnValue("the-promise");
        const instance = makeInstance({ table: { replaceData } });

        expect(instance._refreshData()).toBe("the-promise");
    });
});
