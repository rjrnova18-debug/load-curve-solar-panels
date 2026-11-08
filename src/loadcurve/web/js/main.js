import { analyseStudy, ApiError, sampleLoads } from "./api.js";
import { language, pickLanguage, savedLanguage, setLanguage, t } from "./i18n.js";
import { createStore, isAnalysable } from "./state.js";
import { initTheme } from "./theme.js";
import { createHero } from "./views/hero.js";
import { createLoadTable } from "./views/loadTable.js";
import { createLocation } from "./views/location.js";
import { createResults } from "./views/results.js";
import { createSettings } from "./views/settings.js";

const ANALYSIS_DELAY_MS = 300;

const store = createStore();

/**
 * Keep the result in step with the Study: every change to the Study schedules one
 * analysis request; a newer change cancels the pending one, and an answer to an
 * older request is ignored.
 */
function runAnalysisOnChange() {
  let lastStudy = null;
  let timer = null;
  let latestRequest = 0;

  store.subscribe((state) => {
    if (state.study === lastStudy) return;
    lastStudy = state.study;
    clearTimeout(timer);
    if (!isAnalysable(state.study)) {
      store.update({ result: null, status: "idle", error: null });
      return;
    }
    timer = setTimeout(async () => {
      const request = ++latestRequest;
      store.update({ status: "loading" });
      try {
        const result = await analyseStudy(state.study);
        if (request === latestRequest) store.update({ result, status: "idle", error: null });
      } catch (error) {
        if (request !== latestRequest) return;
        store.update({ status: "error", error: error instanceof ApiError ? error : new ApiError("generic") });
      }
    }, ANALYSIS_DELAY_MS);
  });
}

function setLoads(loads) {
  store.update((state) => ({
    study: { ...state.study, load_table: { loads } },
  }));
}

function wireSampleButton() {
  document.querySelector('[data-action="use-sample"]').addEventListener("click", async () => {
    try {
      setLoads(await sampleLoads());
    } catch (error) {
      store.update({ status: "error", error });
    }
  });
}

function wireLanguageToggle(onChange) {
  const buttons = document.querySelectorAll("[data-language]");
  const markActive = () => {
    for (const button of buttons) {
      button.setAttribute("aria-pressed", String(button.dataset.language === language()));
    }
  };
  for (const button of buttons) {
    button.addEventListener("click", async () => {
      await setLanguage(button.dataset.language);
      markActive();
      onChange();
      store.update({}); // views re-render their dynamic texts in the new language
    });
  }
  markActive();
}

function wireThemeToggle() {
  const button = document.querySelector("[data-theme-toggle]");
  const theme = initTheme((active) => {
    button.setAttribute(
      "aria-label",
      t(active === "dark" ? "header.theme_to_light" : "header.theme_to_dark"),
    );
    store.update({}); // charts read their colours from CSS, so they redraw
  });
  button.addEventListener("click", () => theme.toggle());
}

async function start() {
  await setLanguage(pickLanguage(savedLanguage(), navigator.languages));
  const hero = createHero(document.querySelector("#hero"));
  const loadTable = createLoadTable(document.querySelector("#loads"), store);
  const settings = createSettings(document.querySelector("#day"), store);
  const location = createLocation(document.querySelector("#location"), store);
  const results = createResults(document.querySelector("#results"));

  wireLanguageToggle(() => loadTable.retranslate());
  wireThemeToggle();
  wireSampleButton();

  store.subscribe((state) => {
    hero.render(state);
    loadTable.render(state);
    settings.render(state);
    location.render(state);
    results.render(state);
  });
  runAnalysisOnChange();
  store.update({}); // first paint
}

start();
