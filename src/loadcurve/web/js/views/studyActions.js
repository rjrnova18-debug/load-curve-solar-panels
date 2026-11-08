// The bar at the end of the page: save and open a study, download the Excel
// report, print. Also prepares the page for printing (light theme, every
// disclosure open) and restores it afterwards.

import { downloadFile, saveBlob } from "../api.js";
import { describeError } from "../errors.js";
import { t } from "../i18n.js";
import { parseStudyFile, serializeStudy } from "../studyFile.js";

const NOTICE_MS = 4000;

export function createStudyActions(root, store) {
  const saveButton = root.querySelector('[data-action="save"]');
  const openButton = root.querySelector('[data-action="open"]');
  const reportButton = root.querySelector('[data-action="report"]');
  const printButton = root.querySelector('[data-action="print"]');
  const fileInput = root.querySelector("[data-study-file]");
  const status = root.querySelector("[data-study-status]");
  const alert = root.querySelector("[data-study-alert]");
  let statusTimer = null;

  function announce(message) {
    alert.hidden = true;
    status.textContent = message;
    clearTimeout(statusTimer);
    statusTimer = setTimeout(() => {
      status.textContent = "";
    }, NOTICE_MS);
  }

  function fail(error) {
    status.textContent = "";
    alert.hidden = false;
    alert.textContent = describeError(error);
  }

  saveButton.addEventListener("click", () => {
    const text = serializeStudy(store.get());
    saveBlob(new Blob([text], { type: "application/json" }), "load-curve-study.json");
    announce(t("actions.saved"));
  });

  openButton.addEventListener("click", () => fileInput.click());
  fileInput.addEventListener("change", async () => {
    const [file] = fileInput.files;
    fileInput.value = "";
    if (!file) return;
    try {
      const { study, location } = parseStudyFile(await file.text());
      store.update({ study, location, result: null, status: "idle", error: null });
      announce(t("actions.opened", { name: file.name }));
    } catch (error) {
      fail(error);
    }
  });

  reportButton.addEventListener("click", async () => {
    reportButton.disabled = true;
    try {
      await downloadFile("/api/report", store.get().study, "load-curve-report.xlsx");
      announce(t("actions.report_ready"));
    } catch (error) {
      fail(error);
    } finally {
      reportButton.disabled = store.get().study.load_table.loads.length === 0;
    }
  });

  printButton.addEventListener("click", () => window.print());
  preparePrinting(store);

  function render(state) {
    const empty = state.study.load_table.loads.length === 0;
    saveButton.disabled = empty;
    reportButton.disabled = empty;
  }

  return { render };
}

/** Print in the light theme with every disclosure open, then put things back. */
function preparePrinting(store) {
  let restore = null;
  window.addEventListener("beforeprint", () => {
    if (restore) return; // already prepared: keep the state to restore from the first call
    const root = document.documentElement;
    const previousTheme = root.dataset.theme;
    const previousActive = root.dataset.activeTheme;
    const closed = [...document.querySelectorAll("details:not([open])")];
    for (const details of closed) details.open = true;
    root.dataset.theme = "light";
    root.dataset.activeTheme = "light";
    store.update({}); // charts redraw with the light colours
    restore = () => {
      for (const details of closed) details.open = false;
      if (previousTheme) root.dataset.theme = previousTheme;
      else delete root.dataset.theme;
      root.dataset.activeTheme = previousActive;
      store.update({});
    };
  });
  window.addEventListener("afterprint", () => {
    restore?.();
    restore = null;
  });
}
