/**
 * Loads a `ckan.module("name", function ($) { ... return {...} })` source
 * file for unit testing.
 *
 * The source under test is a classic (non-ESM) script: it declares
 * `namespace ckan { export var module: ...; }`, which TypeScript compiles to
 * a bare `var ckan; ckan || (ckan = {})`. In a real page that `var` merges
 * with the global `window.ckan` that CKAN core sets up. If we `import` the
 * file normally, Vite/Vitest evaluates it as its own ES module, so that
 * `var ckan` is scoped to the module instead of the page global and shadows
 * whatever we put on `globalThis.ckan` — `ckan.module` is never our mock,
 * and the call throws.
 *
 * To preserve the "classic script" behaviour, this transpiles the file with
 * the TypeScript compiler (module: "none", same as this repo's own `tsc`
 * build) and runs the result via indirect eval, which executes in true
 * global scope. `var` redeclaration there binds to the `globalThis.ckan`
 * stub installed beforehand instead of resetting it.
 */
import fs from "node:fs";
import path from "node:path";
import ts from "typescript";

const indirectEval = (0, eval);

// Re-reading + re-transpiling on every call would add up across a large
// suite for zero benefit — the compiled output for a given source file
// never changes within a test run.
const transpileCache = new Map<string, string>();

function transpile(sourcePath: string): string {
    const absolutePath = path.resolve(sourcePath);
    const cached = transpileCache.get(absolutePath);
    if (cached) return cached;

    const source = fs.readFileSync(absolutePath, "utf-8");
    const { outputText } = ts.transpileModule(source, {
        compilerOptions: {
            target: ts.ScriptTarget.ES2020,
            module: ts.ModuleKind.None,
        },
        fileName: absolutePath,
    });

    transpileCache.set(absolutePath, outputText);
    return outputText;
}

export function loadCkanModule(
    sourcePath: string,
    moduleName: string,
    fakeJQuery: any,
    ckanOverrides: Record<string, any> = {}
): any {
    const outputText = transpile(sourcePath);

    let captured: ((jq: any) => any) | undefined;

    (globalThis as any).ckan = {
        module: (name: string, initializer: (jq: any) => any) => {
            if (name === moduleName) captured = initializer;
        },
        sandbox: {},
        i18n: {
            // Mirrors CKAN's real %(name)s interpolation closely enough for
            // assertions on the resulting message to make sense.
            _: (msgid: string, values?: Record<string, string | number>) =>
                values ? msgid.replace(/%\(([^)]+)\)[sd]/g, (_match, key) => String(values[key] ?? "")) : msgid,
            ngettext: (
                singular: string,
                plural: string,
                num: number,
                values?: Record<string, string | number>
            ) => {
                const msgid = num === 1 ? singular : plural;
                return values
                    ? msgid.replace(/%\(([^)]+)\)[sd]/g, (_match, key) => String(values[key] ?? ""))
                    : msgid;
            },
        },
        tablesToast: () => {},
        tablesConfirm: (options: { onConfirm: () => void }) => options.onConfirm(),
        ...ckanOverrides,
    };

    indirectEval(outputText);

    if (!captured) {
        throw new Error(`ckan.module("${moduleName}", ...) was never called by ${sourcePath}`);
    }

    return captured(fakeJQuery);
}
