// Step 2: the Daytime window and the Seasonal multipliers.

import { formatHour } from "../format.js";
import { language, t } from "../i18n.js";
import { HOURS } from "../state.js";
import { createMonthGrid } from "./monthGrid.js";

const MULTIPLIER_MIN = 0;
const MULTIPLIER_MAX = 3;

export function createSettings(root, store) {
  const startSelect = root.querySelector("[data-day-start]");
  const endSelect = root.querySelector("[data-day-end]");
  const strip = root.querySelector("[data-day-strip]");
  const windowError = root.querySelector("[data-day-error]");
  const sameForAll = root.querySelector("[data-season-all]");

  for (const select of [startSelect, endSelect]) {
    select.replaceChildren(
      ...Array.from({ length: HOURS }, (_, hour) => new Option(formatHour(hour), String(hour))),
    );
  }
  const stripCells = Array.from({ length: HOURS }, () => strip.appendChild(document.createElement("span")));

  const settings = () => store.get().study.settings;
  const saveSettings = (patch) =>
    store.update((state) => ({
      study: { ...state.study, settings: { ...state.study.settings, ...patch } },
    }));

  function onWindowChange() {
    const start = Number(startSelect.value);
    const end = Number(endSelect.value);
    // Equal hours would leave no day or no night; the API rejects it, so stop here.
    windowError.hidden = start !== end;
    if (start === end) return;
    saveSettings({ daytime_window: { start_hour: start, end_hour: end } });
  }
  startSelect.addEventListener("change", onWindowChange);
  endSelect.addEventListener("change", onWindowChange);

  const seasons = createMonthGrid(root.querySelector("[data-season-grid]"), {
    min: MULTIPLIER_MIN,
    max: MULTIPLIER_MAX,
    step: 5,
    scale: 100,
    full: 1.5, // 100% fills two thirds of the bar
    onChange: (values) => saveSettings({ seasonal_multipliers: values }),
  });

  sameForAll.addEventListener("change", () => {
    const percent = Number(sameForAll.value);
    if (sameForAll.value.trim() === "" || Number.isNaN(percent)) return;
    const factor = Math.min(MULTIPLIER_MAX, Math.max(MULTIPLIER_MIN, percent / 100));
    saveSettings({ seasonal_multipliers: Array(12).fill(factor) });
    sameForAll.value = "";
  });

  function render(state) {
    const { start_hour: start, end_hour: end } = state.study.settings.daytime_window;
    if (document.activeElement !== startSelect) startSelect.value = String(start);
    if (document.activeElement !== endSelect) endSelect.value = String(end);
    stripCells.forEach((cell, hour) => {
      const isDay = (hour - start + HOURS) % HOURS < (end - start + HOURS) % HOURS;
      cell.className = isDay ? "is-day" : "is-night";
    });
    strip.setAttribute(
      "aria-label",
      t("day.strip", { start: formatHour(start), end: formatHour(end) }),
    );
    seasons.render(settings().seasonal_multipliers, language());
  }

  return { render };
}
