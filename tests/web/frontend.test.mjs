// Unit tests for the pure frontend modules. Run with: node --test "tests/web/*.test.mjs"
import assert from "node:assert/strict";
import { test } from "node:test";

import { parseErrorBody } from "../../src/loadcurve/web/js/api.js";
import { messageKey } from "../../src/loadcurve/web/js/errors.js";
import { formatEnergy, formatHour, formatPercent, formatPower } from "../../src/loadcurve/web/js/format.js";
import { pickLanguage, translate } from "../../src/loadcurve/web/js/i18n.js";
import { createStore, emptyStudy, isAnalysable } from "../../src/loadcurve/web/js/state.js";
import { pickTheme } from "../../src/loadcurve/web/js/theme.js";

test("language: saved choice wins, then the browser, then English", () => {
  assert.equal(pickLanguage("es", ["en-US"]), "es");
  assert.equal(pickLanguage(null, ["fr-FR", "es-CO"]), "es");
  assert.equal(pickLanguage("de", ["fr"]), "en");
});

test("translate fills placeholders and falls back to the key", () => {
  const messages = { errors: { missing_columns: "Missing: {columns}." } };
  assert.equal(translate(messages, "errors.missing_columns", { columns: "0, 1" }), "Missing: 0, 1.");
  assert.equal(translate(messages, "errors.unknown"), "errors.unknown");
});

test("theme: saved choice wins over the system preference", () => {
  assert.equal(pickTheme("light", true), "light");
  assert.equal(pickTheme(null, true), "dark");
  assert.equal(pickTheme(undefined, false), "light");
});

test("power and energy use short units in each language", () => {
  assert.equal(formatPower(350, "en"), "350 W");
  assert.equal(formatPower(12400, "en"), "12.4 kW");
  assert.equal(formatPower(12400, "es"), "12,4 kW");
  assert.equal(formatEnergy(152.66, "en"), "152.7 kWh");
  assert.equal(formatEnergy(3.36, "es"), "3,36 kWh");
  assert.equal(formatPercent(0.574, "en"), "57%");
  assert.equal(formatHour(6), "06:00");
});

test("store notifies subscribers with the merged state", () => {
  const store = createStore({ count: 0, label: "a" });
  const seen = [];
  store.subscribe((state) => seen.push(state));

  store.update((state) => ({ count: state.count + 1 }));

  assert.deepEqual(store.get(), { count: 1, label: "a" });
  assert.equal(seen.length, 1);
});

test("API errors become codes: validation type, or detail.code", () => {
  const validation = {
    detail: [{ type: "greater_than", loc: ["body", "load_table"], ctx: { gt: 0 } }],
  };
  assert.deepEqual(parseErrorBody(validation), {
    code: "greater_than",
    details: { gt: 0, location: ["body", "load_table"] },
  });
  assert.deepEqual(parseErrorBody({ detail: { code: "missing_columns", columns: ["0"] } }), {
    code: "missing_columns",
    details: { columns: ["0"] },
  });
  assert.equal(parseErrorBody({}).code, "generic");
  assert.equal(parseErrorBody(null).code, "generic");
});

test("error messages mention the limit only when it is known", () => {
  const keys = new Set(["errors.greater_than", "errors.greater_than_plain", "errors.float_parsing"]);
  const hasKey = (key) => keys.has(key);
  assert.equal(messageKey("greater_than", { gt: 0 }, hasKey), "errors.greater_than");
  assert.equal(messageKey("greater_than", {}, hasKey), "errors.greater_than_plain"); // import issues
  assert.equal(messageKey("float_parsing", {}, hasKey), "errors.float_parsing");
  assert.equal(messageKey("brand_new_code", {}, hasKey), "errors.generic");
});

test("an empty study cannot be analysed until it has a load", () => {
  const study = emptyStudy();
  assert.equal(isAnalysable(study), false);
  study.load_table.loads.push({ name: "Fridge", rated_power_w: 350, schedule: Array(24).fill(1) });
  assert.equal(isAnalysable(study), true);
  assert.equal(study.settings.seasonal_multipliers.length, 12);
});
