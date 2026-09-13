import { beforeEach, describe, expect, it } from "vitest";
import { makeInstance } from "./support/fixture";

beforeEach(() => {
    document.body.innerHTML = "";
    document.body.className = "";
});

describe("_onFullscreen", () => {
    it("toggles the wrapper and body classes on", () => {
        const wrapperEl = document.createElement("div");
        wrapperEl.className = "table-wrapper";
        document.body.appendChild(wrapperEl);

        const instance = makeInstance({ wrapperEl });
        instance._onFullscreen();

        expect(wrapperEl.classList.contains("table-fullscreen")).toBe(true);
        expect(document.body.classList.contains("tables-fullscreen")).toBe(true);
    });

    it("toggles back off, and only removes the body class once no wrapper is fullscreen", () => {
        const wrapperEl = document.createElement("div");
        wrapperEl.className = "table-wrapper";
        document.body.appendChild(wrapperEl);

        const instance = makeInstance({ wrapperEl });
        instance._onFullscreen(); // on
        instance._onFullscreen(); // off

        expect(wrapperEl.classList.contains("table-fullscreen")).toBe(false);
        expect(document.body.classList.contains("tables-fullscreen")).toBe(false);
    });

    it("keeps the body class while a different table is still fullscreen", () => {
        const wrapperA = document.createElement("div");
        wrapperA.className = "table-wrapper table-fullscreen";
        const wrapperB = document.createElement("div");
        wrapperB.className = "table-wrapper";
        document.body.append(wrapperA, wrapperB);

        const instance = makeInstance({ wrapperEl: wrapperB });
        instance._onFullscreen();

        expect(wrapperB.classList.contains("table-fullscreen")).toBe(true);
        expect(document.body.classList.contains("tables-fullscreen")).toBe(true);

        instance._onFullscreen();
        expect(wrapperB.classList.contains("table-fullscreen")).toBe(false);
        // wrapperA is still fullscreen, so the body-level class must stay.
        expect(document.body.classList.contains("tables-fullscreen")).toBe(true);
    });
});
