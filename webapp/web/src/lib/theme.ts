const THEME_KEY = "bi_showcase_theme_v3";

export type ThemeMode = "light" | "dark";

/** По умолчанию — светлая. */
export function readTheme(): ThemeMode {
  if (typeof window === "undefined") return "light";
  try {
    const v = window.localStorage.getItem(THEME_KEY);
    if (v === "dark" || v === "light") return v;
  } catch {
    /* ignore */
  }
  return "light";
}

export function writeTheme(mode: ThemeMode): void {
  try {
    window.localStorage.setItem(THEME_KEY, mode);
  } catch {
    /* ignore */
  }
}

export function applyThemeClass(mode: ThemeMode): void {
  const root = document.documentElement;
  if (mode === "dark") root.classList.add("dark");
  else root.classList.remove("dark");
}
