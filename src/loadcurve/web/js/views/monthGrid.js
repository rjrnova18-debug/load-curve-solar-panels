// Twelve labelled number inputs, one per month, each with a small bar showing its
// value. Used for Seasonal multipliers and for Peak sun hours.

import { monthNames } from "../format.js";
import { MONTHS } from "../state.js";
import { syncField } from "../syncField.js";

/**
 * @param container element to fill
 * @param options {min, max, step, scale, full, onChange}
 *   scale: how many input units one stored unit is (100 for percentages)
 *   full: the stored value that fills a bar; a fixed scale keeps "all months at
 *         90%" looking low instead of full
 *   onChange(values): called with the 12 stored values after any edit
 */
export function createMonthGrid(container, { min, max, step, scale = 1, full = max, onChange }) {
  container.classList.add("month-grid");
  let values = Array(MONTHS).fill(min);

  const cells = Array.from({ length: MONTHS }, (_, month) => {
    const label = document.createElement("label");
    label.className = "month-grid__cell";
    const bar = document.createElement("span");
    bar.className = "month-grid__bar";
    bar.setAttribute("aria-hidden", "true");
    const name = document.createElement("span");
    name.className = "month-grid__name";
    const input = Object.assign(document.createElement("input"), {
      type: "number",
      min: String(min * scale),
      max: String(max * scale),
      step: String(step),
      inputMode: "decimal",
    });
    input.addEventListener("input", () => {
      const number = Number(input.value);
      const valid = input.value.trim() !== "" && Number.isFinite(number);
      input.setAttribute("aria-invalid", String(!valid));
      if (!valid) return;
      const clamped = Math.min(max * scale, Math.max(min * scale, number));
      values = values.with(month, clamped / scale);
      onChange(values);
    });
    label.append(bar, name, input);
    container.append(label);
    return { bar, name, input };
  });

  /** Show values, never overwriting what the user typed (see syncField). */
  function render(nextValues, lang) {
    values = [...nextValues];
    const names = monthNames(lang);
    cells.forEach(({ bar, name, input }, month) => {
      name.textContent = names[month];
      bar.style.setProperty("--fill", String(Math.min(1, values[month] / full)));
      syncField(input, Math.round(values[month] * scale * 100) / 100);
    });
  }

  return { render };
}
