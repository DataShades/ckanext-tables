import { beforeEach, describe, expect, it, vi } from "vitest";
import { buildTableDom, makeFakeEl, makeFakeTabulatorClass, makeInstance } from "./support/fixture";

const PAGE = { data: [{ a: 1 }], last_page: 3, total: 21 };

/** Stands in for Tabulator's Ajax module, which calls `ajaxRequestFunc` as its own method. */
function makeAjaxModule() {
    const defaultLoaderPromise = vi.fn(() => Promise.resolve({ data: [], last_page: 1 }));

    class AjaxModule {
        static defaultLoaderPromise = defaultLoaderPromise;
        request(func: any, params: any) {
            return func.call(this, "/ajax", { method: "GET" }, params);
        }
    }

    return { ajax: new AjaxModule(), defaultLoaderPromise };
}

function firstPageParams(overrides: Record<string, any> = {}) {
    return { page: 1, size: 10, sort: [], filter: [], filters: "[]", ...overrides };
}

function makeTable(options: Record<string, any>, tableFilters: any[] = []) {
    const dom = buildTableDom("res-1");
    const { FakeTabulator, instances } = makeFakeTabulatorClass();
    (globalThis as any).Tabulator = FakeTabulator;

    const instance = makeInstance({
        el: makeFakeEl(dom.tableEl),
        sandbox: { subscribe: vi.fn(), client: { url: (u: string) => u } },
        options: { config: { tableName: "res-1", paginationSize: 10 }, rowActions: null, ...options },
    });
    instance.initialize();
    instance.tableFilters = tableFilters;

    return instances[0].config;
}

beforeEach(() => {
    document.body.innerHTML = "";
    window.history.replaceState({}, "", "/dataset/resource/view");
    delete (globalThis as any).Tabulator;
});

describe("embedded first page", () => {
    it("keeps Tabulator's own loader when nothing is embedded", () => {
        expect(makeTable({}).ajaxRequestFunc).toBeUndefined();
    });

    it("answers the first unfiltered, unsorted page 1 request from the embedded page", async () => {
        const config = makeTable({ initialPage: PAGE });
        const { ajax, defaultLoaderPromise } = makeAjaxModule();

        await expect(ajax.request(config.ajaxRequestFunc, firstPageParams())).resolves.toBe(PAGE);
        expect(defaultLoaderPromise).not.toHaveBeenCalled();
    });

    it("hands every later request to Tabulator's loader", async () => {
        const config = makeTable({ initialPage: PAGE });
        const { ajax, defaultLoaderPromise } = makeAjaxModule();

        await ajax.request(config.ajaxRequestFunc, firstPageParams());
        await ajax.request(config.ajaxRequestFunc, firstPageParams());

        expect(defaultLoaderPromise).toHaveBeenCalledTimes(1);
        expect(defaultLoaderPromise.mock.contexts[0]).toBe(ajax);
    });

    it.each([
        ["a later page", { page: 2 }],
        ["another page size", { size: 25 }],
        ["a sort", { sort: [{ field: "a", dir: "asc" }] }],
        ["a header filter", { filter: [{ field: "a", type: "like", value: "x" }] }],
    ])("loads normally when the first request asks for %s", async (_label, overrides) => {
        const config = makeTable({ initialPage: PAGE });
        const { ajax, defaultLoaderPromise } = makeAjaxModule();

        await ajax.request(config.ajaxRequestFunc, firstPageParams(overrides));

        expect(defaultLoaderPromise).toHaveBeenCalledTimes(1);
    });

    it("loads normally when filters came from the URL", async () => {
        const config = makeTable({ initialPage: PAGE }, [{ field: "a", operator: "=", value: "1" }]);
        const { ajax, defaultLoaderPromise } = makeAjaxModule();

        await ajax.request(config.ajaxRequestFunc, firstPageParams());

        expect(defaultLoaderPromise).toHaveBeenCalledTimes(1);
    });
});
