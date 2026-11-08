// Interface translations. Texts live in /i18n/<lang>.json; the API only sends
// error codes, which are translated here under "errors.<code>".

export const SUPPORTED_LANGUAGES = ["en", "es"];
export const DEFAULT_LANGUAGE = "en";
const STORAGE_KEY = "loadcurve.language";

let dictionary = {};
let currentLanguage = DEFAULT_LANGUAGE;

/** The language to start with: saved choice, then the browser's, then English. */
export function pickLanguage(saved, browserLanguages = []) {
  if (SUPPORTED_LANGUAGES.includes(saved)) return saved;
  for (const tag of browserLanguages) {
    const base = String(tag).toLowerCase().split("-")[0];
    if (SUPPORTED_LANGUAGES.includes(base)) return base;
  }
  return DEFAULT_LANGUAGE;
}

/** Look up a dotted key and fill {placeholders}; unknown keys fall back to the key. */
export function translate(messages, key, vars = {}) {
  const text = key.split(".").reduce((node, part) => node?.[part], messages);
  if (typeof text !== "string") return key;
  return text.replace(/\{(\w+)\}/g, (match, name) => (name in vars ? String(vars[name]) : match));
}

export function t(key, vars) {
  return translate(dictionary, key, vars);
}

export function language() {
  return currentLanguage;
}

export async function setLanguage(lang) {
  const response = await fetch(`/i18n/${lang}.json`);
  dictionary = await response.json();
  currentLanguage = lang;
  document.documentElement.lang = lang;
  try {
    localStorage.setItem(STORAGE_KEY, lang);
  } catch {
    // Storage can be unavailable (private mode); the choice just isn't remembered.
  }
  applyTranslations(document);
}

export function savedLanguage() {
  try {
    return localStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

/**
 * Fill every element marked with data-i18n (text) or data-i18n-attr
 * ("aria-label:key; title:key") under root.
 */
export function applyTranslations(root) {
  for (const element of root.querySelectorAll("[data-i18n]")) {
    element.textContent = t(element.dataset.i18n);
  }
  for (const element of root.querySelectorAll("[data-i18n-attr]")) {
    for (const pair of element.dataset.i18nAttr.split(";")) {
      const [attribute, key] = pair.split(":").map((part) => part.trim());
      if (attribute && key) element.setAttribute(attribute, t(key));
    }
  }
}
