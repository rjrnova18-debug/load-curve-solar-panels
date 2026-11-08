// Light/dark theme. With no saved choice the page follows the operating system;
// once the user picks one, data-theme on <html> overrides it.

const STORAGE_KEY = "loadcurve.theme";

/** "light" | "dark": the saved choice, otherwise the system preference. */
export function pickTheme(saved, systemPrefersDark) {
  if (saved === "light" || saved === "dark") return saved;
  return systemPrefersDark ? "dark" : "light";
}

export function initTheme(onChange = () => {}) {
  const media = window.matchMedia("(prefers-color-scheme: dark)");
  let saved = null;
  try {
    saved = localStorage.getItem(STORAGE_KEY);
  } catch {
    // Storage unavailable: follow the system.
  }
  if (saved) document.documentElement.dataset.theme = saved;
  const sync = () => {
    const active = pickTheme(document.documentElement.dataset.theme, media.matches);
    document.documentElement.dataset.activeTheme = active;
    onChange(active);
  };
  media.addEventListener("change", sync);
  sync();
  return {
    toggle() {
      const next = activeTheme() === "dark" ? "light" : "dark";
      document.documentElement.dataset.theme = next;
      try {
        localStorage.setItem(STORAGE_KEY, next);
      } catch {
        // Not remembered, still applied.
      }
      sync();
    },
  };
}

export function activeTheme() {
  return document.documentElement.dataset.activeTheme ?? "light";
}
