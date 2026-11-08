// Step 1: the Load table editor. Hours are painted by dragging across the cells
// (the legacy app made users pick them one by one).
//
// The view edits the store and keeps the rows it rendered: when the change came
// from this view the rows stay (so focus and typing are not interrupted); when the
// Load table was replaced (sample, import, opened study) the rows are rebuilt.

import { downloadFile, importLoadTable } from "../api.js";
import { describeError } from "../errors.js";
import { formatHour } from "../format.js";
import { t } from "../i18n.js";
import { HOURS } from "../state.js";

const NEW_LOAD_POWER_W = 100;

function element(tag, attributes = {}, children = []) {
  const node = document.createElement(tag);
  for (const [key, value] of Object.entries(attributes)) {
    if (key === "dataset") Object.assign(node.dataset, value);
    else if (value !== undefined && value !== null) node.setAttribute(key, value);
  }
  node.append(...children);
  return node;
}

function daytimeHours(study) {
  const { start_hour: start, end_hour: end } = study.settings.daytime_window;
  return new Set(Array.from({ length: (end - start + HOURS) % HOURS }, (_, i) => (start + i) % HOURS));
}

export function createLoadTable(root, store) {
  const table = root.querySelector("[data-loads-table]");
  const scroller = root.querySelector("[data-loads-scroll]");
  const headRow = table.querySelector("thead tr");
  const body = table.querySelector("tbody");
  const empty = root.querySelector("[data-loads-empty]");
  const note = root.querySelector("[data-loads-note]");
  const issuesBox = root.querySelector("[data-loads-issues]");
  const alertBox = root.querySelector("[data-loads-alert]");
  const fileInput = root.querySelector("[data-loads-file]");
  const exportButton = root.querySelector('[data-action="export-loads"]');

  let renderedLoads = null;
  let painting = null; // the value (0 or 1) being painted while the pointer is down

  const currentLoads = () => store.get().study.load_table.loads;

  /** Save new loads; rebuild the rows only when the table was replaced, not edited. */
  function saveLoads(loads, { rebuild = false } = {}) {
    renderedLoads = rebuild ? null : loads;
    store.update((state) => ({ study: { ...state.study, load_table: { loads } } }));
  }

  function editLoad(index, patch) {
    saveLoads(currentLoads().map((load, i) => (i === index ? { ...load, ...patch } : load)));
  }

  // ---------- Header ----------

  function buildHeader() {
    headRow.replaceChildren(
      element("th", { class: "col-name", scope: "col" }, [t("loads.col_name")]),
      element("th", { class: "col-power", scope: "col" }, [t("loads.col_power")]),
      element("th", { class: "col-use", scope: "col" }, [t("loads.col_use")]),
      ...Array.from({ length: HOURS }, (_, hour) =>
        element("th", { class: "col-hour", scope: "col", dataset: { hour } }, [String(hour)]),
      ),
      element("th", { class: "col-remove" }, [element("span", { class: "visually-hidden" }, [t("loads.remove_column")])]),
    );
  }

  // ---------- Rows ----------

  function buildRow(load, index) {
    const name = load.name ?? "";
    const hours = load.schedule.map((flag, hour) =>
      element("td", { class: "col-hour", dataset: { hour } }, [
        element("button", {
          type: "button",
          class: "hour",
          "aria-pressed": String(flag === 1),
          "aria-label": t("loads.hour_cell", { name, hour: formatHour(hour) }),
          tabindex: hour === 0 ? "0" : "-1",
          dataset: { hour },
        }),
      ]),
    );
    return element("tr", { dataset: { index } }, [
      element("th", { class: "col-name", scope: "row" }, [
        element("input", { type: "text", value: name, "aria-label": t("loads.col_name"), dataset: { field: "name" }, maxlength: 80 }),
      ]),
      element("td", { class: "col-power" }, [
        element("input", {
          type: "number",
          min: 0,
          step: "any",
          inputmode: "decimal",
          value: load.rated_power_w ?? "",
          "aria-label": t("loads.col_power"),
          dataset: { field: "rated_power_w" },
        }),
      ]),
      element("td", { class: "col-use" }, [
        element("input", {
          type: "number",
          min: 0,
          max: 100,
          step: 5,
          inputmode: "numeric",
          value: Math.round((load.usage_factor ?? 1) * 100),
          "aria-label": t("loads.col_use"),
          dataset: { field: "usage_factor" },
        }),
      ]),
      ...hours,
      element("td", { class: "col-remove" }, [
        element("button", { type: "button", class: "remove", "aria-label": t("loads.remove", { name }) }, ["×"]),
      ]),
    ]);
  }

  function rebuildRows(loads) {
    buildHeader();
    body.replaceChildren(...loads.map(buildRow));
    renderedLoads = loads;
  }

  // ---------- Editing ----------

  function readField(input) {
    const raw = input.value.trim();
    switch (input.dataset.field) {
      case "name":
        return input.value;
      case "rated_power_w":
        return raw === "" ? null : Number(raw);
      case "usage_factor": {
        if (raw === "") return 1;
        const percent = Math.min(100, Math.max(0, Number(raw)));
        return percent / 100;
      }
      default:
        return raw;
    }
  }

  body.addEventListener("input", (event) => {
    const input = event.target;
    if (!input.dataset.field) return;
    const index = Number(input.closest("tr").dataset.index);
    editLoad(index, { [input.dataset.field]: readField(input) });
    if (input.dataset.field === "name") relabelRow(input.closest("tr"), input.value);
  });

  function relabelRow(row, name) {
    for (const button of row.querySelectorAll(".hour")) {
      button.setAttribute("aria-label", t("loads.hour_cell", { name, hour: formatHour(Number(button.dataset.hour)) }));
    }
    row.querySelector(".remove").setAttribute("aria-label", t("loads.remove", { name }));
  }

  function setHour(button, value) {
    const index = Number(button.closest("tr").dataset.index);
    const hour = Number(button.dataset.hour);
    const load = currentLoads()[index];
    if (load.schedule[hour] === value) return;
    button.setAttribute("aria-pressed", String(value === 1));
    editLoad(index, { schedule: load.schedule.with(hour, value) });
  }

  // Painting: press on a cell to flip it, then drag to give other cells the same value.
  body.addEventListener("pointerdown", (event) => {
    const button = event.target.closest(".hour");
    if (!button || event.button !== 0) return;
    event.preventDefault(); // no text selection while dragging
    button.releasePointerCapture?.(event.pointerId); // let touch drags reach other cells
    painting = button.getAttribute("aria-pressed") === "true" ? 0 : 1;
    setHour(button, painting);
  });
  body.addEventListener("pointerover", (event) => {
    const button = event.target.closest(".hour");
    if (button && painting !== null) setHour(button, painting);
  });
  for (const type of ["pointerup", "pointercancel"]) {
    window.addEventListener(type, () => {
      painting = null;
    });
  }

  body.addEventListener("click", (event) => {
    const button = event.target.closest(".hour");
    // Pointer clicks were handled on pointerdown; keyboard clicks (detail 0) toggle here.
    if (button && event.detail === 0) setHour(button, button.getAttribute("aria-pressed") === "true" ? 0 : 1);

    const remove = event.target.closest(".remove");
    if (remove) {
      const index = Number(remove.closest("tr").dataset.index);
      saveLoads(currentLoads().filter((_, i) => i !== index), { rebuild: true });
    }
  });

  // Arrow keys move between the hours of a row (one tab stop per row).
  body.addEventListener("keydown", (event) => {
    const button = event.target.closest(".hour");
    if (!button || !["ArrowLeft", "ArrowRight", "Home", "End"].includes(event.key)) return;
    const row = [...button.closest("tr").querySelectorAll(".hour")];
    const at = row.indexOf(button);
    const next = { ArrowLeft: at - 1, ArrowRight: at + 1, Home: 0, End: HOURS - 1 }[event.key];
    if (next < 0 || next >= HOURS) return;
    event.preventDefault();
    button.tabIndex = -1;
    row[next].tabIndex = 0;
    row[next].focus();
  });

  root.querySelector('[data-action="add-load"]').addEventListener("click", () => {
    const loads = currentLoads();
    const schedule = Array(HOURS).fill(0);
    const name = t("loads.new_name", { n: loads.length + 1 });
    saveLoads([...loads, { name, rated_power_w: NEW_LOAD_POWER_W, usage_factor: 1, schedule }], { rebuild: true });
    body.querySelector("tr:last-child input")?.select();
  });

  // ---------- Files ----------

  root.querySelector('[data-action="import-loads"]').addEventListener("click", () => fileInput.click());

  fileInput.addEventListener("change", async () => {
    const [file] = fileInput.files;
    fileInput.value = ""; // choosing the same file again still triggers a change
    if (!file) return;
    if (currentLoads().length > 0 && !window.confirm(t("loads.replace_confirm"))) return;
    showAlert(null);
    try {
      const result = await importLoadTable(file);
      showIssues(result.issues);
      if (result.loads.length > 0) saveLoads(result.loads, { rebuild: true });
    } catch (error) {
      showIssues([]);
      showAlert(describeError(error));
    }
  });

  exportButton.addEventListener("click", async () => {
    try {
      await downloadFile("/api/load-table/export?format=xlsx", { loads: currentLoads() }, "load-table.xlsx");
    } catch (error) {
      showAlert(describeError(error));
    }
  });

  function showIssues(issues) {
    issuesBox.hidden = issues.length === 0;
    if (issues.length === 0) return;
    const items = issues.map((issue) =>
      element("li", {}, [
        t("loads.issue", {
          row: issue.row,
          column: issue.column ?? "",
          message: describeError({ code: issue.code }),
        }),
      ]),
    );
    issuesBox.replaceChildren(
      element("p", {}, [t("loads.issues_title", { count: issues.length })]),
      element("ul", {}, items),
    );
  }

  function showAlert(message) {
    alertBox.hidden = !message;
    alertBox.textContent = message ?? "";
  }

  // ---------- Render ----------

  function markInvalid(error) {
    for (const input of body.querySelectorAll("[aria-invalid]")) input.removeAttribute("aria-invalid");
    // Validation locations look like ["body", "load_table", "loads", 3, "rated_power_w"].
    const location = error?.details?.location ?? [];
    const at = location.indexOf("loads");
    if (at === -1 || typeof location[at + 1] !== "number") return;
    const field = location[at + 2];
    const row = body.querySelector(`tr[data-index="${location[at + 1]}"]`);
    row?.querySelector(`[data-field="${field}"]`)?.setAttribute("aria-invalid", "true");
  }

  function render(state) {
    const loads = state.study.load_table.loads;
    if (loads !== renderedLoads) rebuildRows(loads);

    const hasLoads = loads.length > 0;
    empty.hidden = hasLoads;
    scroller.hidden = !hasLoads;
    note.hidden = !hasLoads;
    exportButton.disabled = !hasLoads;

    const daytime = daytimeHours(state.study);
    for (const cell of table.querySelectorAll(".col-hour")) {
      const isDay = daytime.has(Number(cell.dataset.hour));
      cell.classList.toggle("is-day", isDay);
      cell.classList.toggle("is-night", !isDay);
    }

    const failed = state.status === "error" ? state.error : null;
    markInvalid(failed);
    showAlert(failed ? describeError(failed) : null);
  }

  /** Re-translate the rows' labels after a language change. */
  function retranslate() {
    renderedLoads = null;
  }

  return { render, retranslate };
}
