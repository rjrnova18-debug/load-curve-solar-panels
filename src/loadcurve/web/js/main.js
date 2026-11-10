import { keepResultInSync } from "./analysisSync.js";
import { analyseStudy, sampleLoads } from "./api.js";
import { language, pickLanguage, savedLanguage, setLanguage, t } from "./i18n.js";
import { createStore } from "./state.js";
import { initTheme } from "./theme.js";
import { createHero } from "./views/hero.js";
import { createLoadTable } from "./views/loadTable.js";
import { createLocation } from "./views/location.js";
import { createResults } from "./views/results.js";
import { createSettings } from "./views/settings.js";
import { createStudyActions } from "./views/studyActions.js";
import { createSystems } from "./views/systems.js";

const ANALYSIS_DELAY_MS = 300;

const store = createStore();

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
  const systems = createSystems(document.querySelector("#systems"), store);
  const studyActions = createStudyActions(document.querySelector(".study-actions"), store);

  wireLanguageToggle(() => loadTable.retranslate());
  wireThemeToggle();
  wireSampleButton();

  store.subscribe((state) => {
    hero.render(state);
    loadTable.render(state);
    settings.render(state);
    location.render(state);
    results.render(state);
    systems.render(state);
    studyActions.render(state);
  });
  keepResultInSync(store, analyseStudy, ANALYSIS_DELAY_MS);
  store.update({}); // first paint
}

start();
