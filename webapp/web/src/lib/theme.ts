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

/** Цвет системной строки браузера на телефоне — по выбранной в приложении теме. */
const BAR_COLOR: Record<ThemeMode, string> = {
  light: "#f8f9fb",
  dark: "#0c1219",
};

export function applyThemeClass(mode: ThemeMode): void {
  const root = document.documentElement;
  if (mode === "dark") root.classList.add("dark");
  else root.classList.remove("dark");

  const meta = document.querySelector<HTMLMetaElement>(
    'meta[name="theme-color"]:not([media])',
  );
  if (meta) {
    meta.content = BAR_COLOR[mode];
  } else {
    const created = document.createElement("meta");
    created.name = "theme-color";
    created.content = BAR_COLOR[mode];
    document.head.appendChild(created);
  }
}
