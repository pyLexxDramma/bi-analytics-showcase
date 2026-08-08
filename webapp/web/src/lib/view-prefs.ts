"use client";

/** Настройки полотна: живут в браузере пользователя, на данные не влияют. */

const WIDE_KEY = "bi_showcase_wide_canvas_v1";
const DENSITY_KEY = "bi_showcase_density_v1";

export type Density = "comfortable" | "compact";

export function readWideCanvas(): boolean {
  try {
    return localStorage.getItem(WIDE_KEY) === "1";
  } catch {
    return false;
  }
}

export function writeWideCanvas(value: boolean): void {
  try {
    localStorage.setItem(WIDE_KEY, value ? "1" : "0");
  } catch {
    /* приватный режим — настройка живёт до перезагрузки */
  }
}

export function readDensity(): Density {
  try {
    return localStorage.getItem(DENSITY_KEY) === "compact"
      ? "compact"
      : "comfortable";
  } catch {
    return "comfortable";
  }
}

export function writeDensity(value: Density): void {
  try {
    localStorage.setItem(DENSITY_KEY, value);
  } catch {
    /* см. writeWideCanvas */
  }
}
