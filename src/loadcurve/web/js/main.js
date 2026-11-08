import { language, pickLanguage, savedLanguage, setLanguage, t } from "./i18n.js";
import { createStore } from "./state.js";
import { initTheme } from "./theme.js";

const store = createStore();

function wireLanguageToggle() {
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
  });
  button.addEventListener("click", () => theme.toggle());
}

async function start() {
  await setLanguage(pickLanguage(savedLanguage(), navigator.languages));
  wireLanguageToggle();
  wireThemeToggle();
}

start();

export { store };
