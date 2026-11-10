// Step 5: the three System types side by side, with the formulas behind every
// number filled in with the user's own values, and the editable Sizing assumptions.

import { expressionMathML, stepMathML, symbolsUsed } from "../formula.js";
import { formatNumber, monthNames } from "../format.js";
import { language, t } from "../i18n.js";

const SYSTEMS = ["on_grid", "hybrid", "off_grid"];

// Each assumption: how it is shown (percent or plain) and its allowed range.
const ASSUMPTIONS = [
  { key: "performance_ratio", percent: true, min: 0.5, max: 1, step: 1 },
  { key: "panel_power_w", percent: false, min: 100, max: 1000, step: 10 },
  { key: "battery_depth_of_discharge", percent: true, min: 0.1, max: 1, step: 5 },
  { key: "battery_efficiency", percent: true, min: 0.5, max: 1, step: 1 },
  { key: "inverter_safety_factor", percent: false, min: 1, max: 3, step: 0.05 },
  { key: "days_of_autonomy", percent: false, min: 0.5, max: 7, step: 0.5 },
  { key: "on_grid_coverage", percent: true, min: 0.1, max: 1, step: 5 },
];

function element(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) node.setAttribute(key, value);
  node.append(...children);
  return node;
}

// ---------- Comparison table ----------

function comparisonRows(sizing, lang) {
  const n = (value, digits = 1) => formatNumber(value, lang, digits);
  const cell = (system, render) => (system ? render(system) : t("systems.not_feasible_short"));
  return [
    ["systems.row_panels", (s) => t("systems.panels_value", { count: s.panel_count, kwp: n(s.installed_power_kwp) })],
    ["systems.row_batteries", (s) => (s.battery_capacity_kwh > 0 ? `${n(s.battery_capacity_kwh)} kWh` : t("systems.no_batteries"))],
    ["systems.row_inverter", (s) => `${n(s.inverter_power_kw)} kW`],
    ["systems.row_design", (s) => designBasis(s, lang)],
  ].map(([key, render]) =>
    element("tr", {}, [
      element("th", { scope: "row" }, [t(key)]),
      ...SYSTEMS.map((name) => element("td", {}, [cell(sizing[name], render)])),
    ]),
  );
}

function designBasis(system, lang) {
  const when = system.design_month ? monthNames(lang)[system.design_month - 1] : t("systems.year_average");
  return t("systems.design_value", {
    when,
    energy: formatNumber(system.design_daily_energy_kwh, lang, 1),
    psh: formatNumber(system.design_peak_sun_hours, lang, 2),
  });
}

function comparisonTable(sizing, lang) {
  const head = element("tr", {}, [
    element("td", {}),
    ...SYSTEMS.map((name) =>
      element("th", { scope: "col" }, [
        element("span", { class: "system-name" }, [t(`systems.${name}`)]),
        element("span", { class: "system-hint" }, [t(`systems.${name}_hint`)]),
      ]),
    ),
  ]);
  return [element("thead", {}, [head]), element("tbody", {}, comparisonRows(sizing, lang))];
}

// ---------- Formulas ----------

// The steps come from the sizing module (domain/calculation.py): this view only
// draws them, so it cannot show a formula other than the one that was used.

const STEP_TITLES = {
  array_power: "systems.f_array",
  panel_count: "systems.f_panels",
  battery_capacity: "systems.f_battery",
  inverter_power: "systems.f_inverter",
};

function stepSentenceKey(quantity, systemName) {
  if (quantity === "panel_count") return "systems.f_panels_generic";
  if (quantity === "inverter_power") {
    return systemName === "on_grid" ? "systems.f_inverter_on_grid" : "systems.f_inverter_load";
  }
  return `${STEP_TITLES[quantity]}_${systemName}`;
}

/** How symbols and numbers look in the current language. */
function mathOptions(lang) {
  const shortMonths = monthNames(lang);
  return {
    // No thousands separators: in Spanish "1.000" would read as a decimal in a formula.
    number: (value) => formatNumber(value, lang, Number.isInteger(value) ? 0 : 2, { grouping: false }),
    symbol: (key, qualifier) => {
      const base = t(`symbols.${key}.base`);
      const parts = [t(`symbols.${key}.sub`)];
      if (qualifier?.startsWith("month:")) parts.push(shortMonths[Number(qualifier.slice(6)) - 1]);
      else if (qualifier) parts.push(t(`symbols.qualifier_${qualifier}`));
      return { base, sub: parts.filter(Boolean).join(",") };
    },
  };
}

function qualifierNote(qualifier, lang) {
  if (!qualifier) return "";
  if (qualifier.startsWith("month:")) {
    return t("symbols.note_month", { month: monthNames(lang, "long")[Number(qualifier.slice(6)) - 1] });
  }
  return t(`symbols.note_${qualifier}`);
}

function math(markup, modifier = "") {
  const holder = document.createElement("div");
  holder.className = `formula__math ${modifier}`.trim();
  holder.innerHTML = markup; // built by formula.js from numbers and escaped text only
  return holder;
}

function formulasFor(name, system, lang) {
  const block = element("section", { class: "formulas__system" }, [element("h4", {}, [t(`systems.${name}`)])]);
  if (!system) {
    block.append(element("p", {}, [t("systems.not_feasible")]));
    return block;
  }
  const options = mathOptions(lang);
  const legend = new Map();
  for (const calculation of system.steps) {
    const { symbolic, numeric } = stepMathML(calculation, { ...options, label: t(STEP_TITLES[calculation.quantity]) });
    block.append(
      element("div", { class: "formula" }, [
        element("p", { class: "formula__label" }, [t(STEP_TITLES[calculation.quantity])]),
        element("p", { class: "formula__generic" }, [t(stepSentenceKey(calculation.quantity, name))]),
        math(symbolic),
        math(numeric, "formula__math--numbers"),
      ]),
    );
    for (const used of symbolsUsed(calculation.expression)) legend.set(`${used.key}|${used.qualifier ?? ""}`, used);
  }
  const items = [...legend.values()].map(({ key, qualifier }) => {
    const symbolHolder = math(`<math>${expressionMathML({ kind: "value", symbol: key, qualifier, value: 0, unit: "" }, { ...options, numbers: false })}</math>`);
    const note = qualifierNote(qualifier, lang);
    return element("li", {}, [symbolHolder, `${t(`symbols.${key}.name`)}${note ? ` (${note})` : ""}`]);
  });
  block.append(element("ul", { class: "formula-legend", "aria-label": t("systems.legend") }, items));
  return block;
}

// ---------- View ----------

export function createSystems(root, store) {
  const empty = root.querySelector("[data-systems-empty]");
  const needsSun = root.querySelector("[data-systems-need-sun]");
  const panel = root.querySelector("[data-systems]");
  const verdict = root.querySelector("[data-systems-verdict]");
  const table = root.querySelector("[data-systems-table]");
  const formulas = root.querySelector("[data-systems-formulas]");
  const fields = root.querySelector("[data-assumptions]");
  let drawn = null;

  // Assumption inputs are built once; editing one updates the Study.
  const inputs = ASSUMPTIONS.map((spec) => {
    const input = element("input", {
      type: "number",
      inputmode: "decimal",
      min: String(spec.percent ? spec.min * 100 : spec.min),
      max: String(spec.percent ? spec.max * 100 : spec.max),
      step: String(spec.step),
    });
    const label = element("label", { class: "field" }, [
      element("span", { "data-i18n": `systems.a_${spec.key}` }, [t(`systems.a_${spec.key}`)]),
      input,
    ]);
    input.addEventListener("input", () => {
      const raw = Number(input.value);
      const value = spec.percent ? raw / 100 : raw;
      const valid = input.value.trim() !== "" && Number.isFinite(raw) && value >= spec.min && value <= spec.max;
      input.setAttribute("aria-invalid", String(!valid));
      if (!valid) return;
      store.update((state) => ({
        study: { ...state.study, assumptions: { ...state.study.assumptions, [spec.key]: value } },
      }));
    });
    fields.append(label);
    return { spec, input };
  });

  function render(state) {
    const lang = language();
    const hasLoads = state.study.load_table.loads.length > 0;
    const sizing = state.result?.sizing ?? null;
    empty.hidden = hasLoads;
    needsSun.hidden = !hasLoads || Boolean(state.study.solar_resource);
    panel.hidden = !sizing;

    for (const { spec, input } of inputs) {
      if (document.activeElement === input) continue;
      const value = state.study.assumptions[spec.key];
      input.value = String(spec.percent ? Math.round(value * 100) : value);
    }
    if (!sizing) return;

    const key = `${lang}`;
    if (drawn?.sizing === sizing && drawn.key === key) return;
    drawn = { sizing, key };

    table.replaceChildren(...comparisonTable(sizing, lang));
    formulas.replaceChildren(
      ...SYSTEMS.map((name) => formulasFor(name, sizing[name], lang)),
    );
    const hybridBattery = sizing.hybrid.battery_capacity_kwh;
    verdict.textContent = sizing.off_grid
      ? t("systems.verdict", {
          hybrid: formatNumber(hybridBattery, lang, 0),
          extra: formatNumber(sizing.off_grid.battery_capacity_kwh - hybridBattery, lang, 0),
        })
      : t("systems.verdict_no_off_grid", { hybrid: formatNumber(hybridBattery, lang, 0) });
  }

  return { render };
}
