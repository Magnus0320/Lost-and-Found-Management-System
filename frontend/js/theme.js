// Colour theme: "system" (follow the OS), "light" or "dark".
//
// A saved choice is applied before first paint by the small inline script in
// each page's <head>; this module only changes it. "system" is stored as the
// absence of a choice, so the CSS falls back to prefers-color-scheme.

const KEY = "lf_theme";
export const THEMES = ["system", "light", "dark"];

export function savedTheme() {
  try {
    const t = localStorage.getItem(KEY);
    return THEMES.includes(t) ? t : "system";
  } catch {
    return "system"; // storage blocked: follow the OS
  }
}

export function applyTheme(theme) {
  const root = document.documentElement;
  if (theme === "light" || theme === "dark") root.dataset.theme = theme;
  else delete root.dataset.theme;
  try {
    if (theme === "light" || theme === "dark") localStorage.setItem(KEY, theme);
    else localStorage.removeItem(KEY);
  } catch {
    /* not remembered, but still applied for this page */
  }
}

export function nextTheme(theme) {
  return THEMES[(THEMES.indexOf(theme) + 1) % THEMES.length];
}
