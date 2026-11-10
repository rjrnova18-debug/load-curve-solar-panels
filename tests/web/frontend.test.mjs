// Unit tests for the pure frontend modules. Run with: node --test "tests/web/*.test.mjs"
import assert from "node:assert/strict";
import { readFileSync } from "node:fs";
import { test } from "node:test";

import { keepResultInSync } from "../../src/loadcurve/web/js/analysisSync.js";
import { ApiError, parseErrorBody } from "../../src/loadcurve/web/js/api.js";
import { daytimeHours, isDaytime, nighttimeHours } from "../../src/loadcurve/web/js/daytime.js";
import { messageKey } from "../../src/loadcurve/web/js/errors.js";
import { expressionMathML, stepMathML, symbolsUsed } from "../../src/loadcurve/web/js/formula.js";
import { formatEnergy, formatHour, formatPercent, formatPower } from "../../src/loadcurve/web/js/format.js";
import { pickLanguage, translate } from "../../src/loadcurve/web/js/i18n.js";
import { createStore, emptyStudy, initialState, isAnalysable } from "../../src/loadcurve/web/js/state.js";
import { parseStudyFile, serializeStudy } from "../../src/loadcurve/web/js/studyFile.js";
import { fieldShows, syncField } from "../../src/loadcurve/web/js/syncField.js";
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

// ---------- Study files ----------

function stateWithStudy() {
  const state = initialState();
  state.study.load_table.loads.push({
    name: "Fridge",
    rated_power_w: 350,
    usage_factor: 0.4,
    schedule: Array(24).fill(1),
  });
  state.study.solar_resource = { peak_sun_hours: Array(12).fill(4.5) };
  state.study.assumptions.panel_power_w = 400;
  state.location = { ...state.location, latitude: 4.711, longitude: -74.072, source: "pvgis" };
  return state;
}

test("a saved study opens back unchanged", () => {
  const state = stateWithStudy();

  const opened = parseStudyFile(serializeStudy(state, new Date("2026-11-08T12:00:00Z")));

  assert.deepEqual(opened.study, state.study);
  assert.equal(opened.location.latitude, 4.711);
  assert.equal(opened.location.source, "pvgis");
  assert.equal(opened.location.status, "idle");
});

test("missing settings and assumptions fall back to their defaults", () => {
  const file = JSON.stringify({ format: "load-curve-study", version: 1, study: { load_table: { loads: [] } } });

  const { study, location } = parseStudyFile(file);

  assert.deepEqual(study.settings, emptyStudy().settings);
  assert.deepEqual(study.assumptions, emptyStudy().assumptions);
  assert.equal(study.solar_resource, null);
  assert.equal(location.latitude, null);
});

test("files that are not study files are rejected with a code", () => {
  const codeOf = (text) => {
    try {
      parseStudyFile(text);
      return "accepted";
    } catch (error) {
      return error.code;
    }
  };
  assert.equal(codeOf("{ not json"), "json_invalid");
  assert.equal(codeOf(JSON.stringify({ loads: [] })), "study_file_invalid");
  assert.equal(
    codeOf(JSON.stringify({ format: "load-curve-study", version: 1, study: { load_table: {} } })),
    "study_file_invalid",
  );
  assert.equal(
    codeOf(JSON.stringify({ format: "load-curve-study", version: 2, study: { load_table: { loads: [] } } })),
    "study_file_newer",
  );
});

// ---------- Daytime window (shared cases with the Python DaytimeWindow tests) ----------

const DAYTIME_CASES = JSON.parse(
  readFileSync(new URL("../fixtures/daytime_cases.json", import.meta.url), "utf-8"),
).cases;

for (const { start, end, daytime, nighttime } of DAYTIME_CASES) {
  test(`daytime window ${start}-${end} agrees with the Python domain`, () => {
    const window = { start_hour: start, end_hour: end };
    assert.deepEqual(daytimeHours(window), daytime);
    assert.deepEqual(nighttimeHours(window), nighttime);
    for (let hour = 0; hour < 24; hour += 1) {
      assert.equal(isDaytime(window, hour), daytime.includes(hour), `hour ${hour}`);
    }
  });
}

// ---------- Formulas (MathML from the sizing module's expression trees) ----------

const v = (symbol, value, unit = "", qualifier = null) => ({ kind: "value", symbol, qualifier, value, unit });
const ARRAY_EXPRESSION = {
  kind: "fraction",
  numerator: {
    kind: "sum",
    terms: [v("daytime_energy", 87.62, "kWh"), { kind: "fraction", numerator: v("nighttime_energy", 65.04, "kWh"), denominator: v("battery_efficiency", 0.95) }],
  },
  denominator: { kind: "product", terms: [v("peak_sun_hours", 4.5, "h", "year"), v("performance_ratio", 0.75)] },
};
const MATH_OPTIONS = {
  symbol: (key, qualifier) => ({ base: key.slice(0, 1).toUpperCase(), sub: qualifier ?? "" }),
  number: (value) => String(value),
};

test("formulas draw fractions, subscripts and units", () => {
  const symbolic = expressionMathML(ARRAY_EXPRESSION, { ...MATH_OPTIONS, numbers: false });
  const numeric = expressionMathML(ARRAY_EXPRESSION, { ...MATH_OPTIONS, numbers: true });

  assert.equal((symbolic.match(/<mfrac>/g) ?? []).length, 2);
  assert.match(symbolic, /<msub><mi>P<\/mi><mtext>year<\/mtext><\/msub>/);
  assert.match(numeric, /<mn>87\.62<\/mn><mspace width="0.2em"><\/mspace><mtext>kWh<\/mtext>/);
  assert.doesNotMatch(numeric, /<msub>/);
});

test("a sum inside a product gets parentheses; constants stay numbers", () => {
  const expression = {
    kind: "product",
    terms: [{ kind: "sum", terms: [v("a", 1), v("b", 2)] }, { kind: "value", symbol: null, qualifier: null, value: 1000, unit: "" }],
  };
  const markup = expressionMathML(expression, { ...MATH_OPTIONS, numbers: false });

  assert.match(markup, /^<mrow><mo>\(<\/mo>.*<mo>\)<\/mo><\/mrow><mo>×<\/mo><mn>1000<\/mn>$/);
});

test("a step shows the result only on the line with numbers, and text is escaped", () => {
  const step = { quantity: "array_power", expression: ARRAY_EXPRESSION, result: 46.25, unit: "kWp" };

  const { symbolic, numeric } = stepMathML(step, { ...MATH_OPTIONS, label: 'Array "power" <1>' });

  assert.doesNotMatch(symbolic, /46\.25/);
  assert.match(numeric, /<mo>=<\/mo><mn>46\.25<\/mn><mspace width="0.2em"><\/mspace><mtext>kWp<\/mtext><\/math>$/);
  assert.match(symbolic, /aria-label="Array &quot;power&quot; &lt;1&gt;"/);
});

test("the legend lists each symbol once, in reading order", () => {
  assert.deepEqual(
    symbolsUsed(ARRAY_EXPRESSION).map(({ key, qualifier }) => `${key}|${qualifier ?? ""}`),
    ["daytime_energy|", "nighttime_energy|", "battery_efficiency|", "peak_sun_hours|year", "performance_ratio|"],
  );
});

// ---------- analysisSync ----------

/** A fake analyse whose answers the test releases one by one. */
function fakeAnalyse() {
  const calls = [];
  const analyse = (study) =>
    new Promise((resolve, reject) => calls.push({ study, resolve, reject }));
  return { analyse, calls };
}

function studyWithLoads(count) {
  const study = emptyStudy();
  const load = { name: "Fridge", rated_power_w: 350, usage_factor: 0.4, schedule: Array(24).fill(1) };
  study.load_table.loads = Array.from({ length: count }, (_, i) => ({ ...load, name: `Load ${i}` }));
  return study;
}

const settle = () => new Promise((resolve) => setImmediate(resolve));

function syncedStore(t) {
  t.mock.timers.enable({ apis: ["setTimeout"] });
  const store = createStore();
  const fake = fakeAnalyse();
  keepResultInSync(store, fake.analyse, 300);
  return { store, ...fake };
}

test("analysis waits for the delay and sends one request for a burst of changes", (t) => {
  const { store, calls } = syncedStore(t);
  store.update({ study: studyWithLoads(1) });
  t.mock.timers.tick(200);
  store.update({ study: studyWithLoads(2) });
  t.mock.timers.tick(299);
  assert.equal(calls.length, 0);
  t.mock.timers.tick(1);
  assert.equal(calls.length, 1);
  assert.equal(calls[0].study.load_table.loads.length, 2);
  assert.equal(store.get().status, "loading");
});

test("analysis ignores changes that leave the Study untouched", (t) => {
  const { store, calls } = syncedStore(t);
  store.update({ study: studyWithLoads(1) });
  t.mock.timers.tick(300);
  store.update({ status: "idle" }); // e.g. a language change re-rendering the page
  t.mock.timers.tick(300);
  assert.equal(calls.length, 1);
});

test("analysis stores the answer and drops an older one that arrives late", async (t) => {
  const { store, calls } = syncedStore(t);
  store.update({ study: studyWithLoads(1) });
  t.mock.timers.tick(300);
  store.update({ study: studyWithLoads(2) });
  t.mock.timers.tick(300);
  calls[1].resolve({ answer: "new" });
  await settle();
  calls[0].resolve({ answer: "old" });
  await settle();
  assert.deepEqual(store.get().result, { answer: "new" });
  assert.equal(store.get().status, "idle");
});

test("analysis drops an answer to a Study that has since been emptied", async (t) => {
  const { store, calls } = syncedStore(t);
  store.update({ study: studyWithLoads(1) });
  t.mock.timers.tick(300);
  store.update({ study: emptyStudy() });
  calls[0].resolve({ answer: "stale" });
  await settle();
  assert.equal(store.get().result, null);
  assert.equal(store.get().status, "idle");
});

test("analysis errors keep their code; anything else becomes generic", async (t) => {
  const { store, calls } = syncedStore(t);
  store.update({ study: studyWithLoads(1) });
  t.mock.timers.tick(300);
  calls[0].reject(new ApiError("invalid_study"));
  await settle();
  assert.equal(store.get().status, "error");
  assert.equal(store.get().error.code, "invalid_study");

  store.update({ study: studyWithLoads(2) });
  t.mock.timers.tick(300);
  calls[1].reject(new TypeError("Failed to fetch"));
  await settle();
  assert.equal(store.get().error.code, "generic");
});

// ---------- syncField ----------

/** Just enough of an <input> for syncField: a value, focus and an invalid mark. */
function fakeField() {
  const page = { activeElement: null };
  const attributes = new Map();
  const field = {
    ownerDocument: page,
    value: "",
    focus: () => (page.activeElement = field),
    blur: () => (page.activeElement = null),
    setAttribute: (name, value) => attributes.set(name, value),
    removeAttribute: (name) => attributes.delete(name),
    invalid: () => attributes.get("aria-invalid") === "true",
  };
  return field;
}

test("syncField shows the state value, formatted", () => {
  const field = fakeField();
  syncField(field, 0.75);
  assert.equal(field.value, "0.75");
  syncField(field, null, (value) => (value === null ? "" : String(value)));
  assert.equal(field.value, "");
});

test("syncField never writes into the field the user is typing in", () => {
  const field = fakeField();
  syncField(field, 1);
  field.focus();
  field.value = "0.";
  syncField(field, 2);
  assert.equal(field.value, "0.");
  field.blur();
  syncField(field, 2);
  assert.equal(field.value, "2");
});

test("syncField keeps an invalid entry until the state changes", () => {
  const field = fakeField();
  syncField(field, 0.75);
  field.value = "5";
  field.setAttribute("aria-invalid", "true");
  syncField(field, 0.75); // e.g. another field changed
  assert.equal(field.value, "5");
  assert.ok(field.invalid());
  syncField(field, 0.8); // e.g. a study was opened
  assert.equal(field.value, "0.8");
  assert.ok(!field.invalid());
});

test("syncField keeps text the user typed for the value they meant", () => {
  const field = fakeField();
  syncField(field, null, String);
  field.value = "4.70";
  fieldShows(field, 4.7);
  syncField(field, 4.7);
  assert.equal(field.value, "4.70");
});
