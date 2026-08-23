"use client";

const SHORTCUTS_KEY = "bi_onboarding_shortcuts_v1";

export function shouldShowShortcutsHint(): boolean {
  try {
    return localStorage.getItem(SHORTCUTS_KEY) !== "1";
  } catch {
    return false;
  }
}

export function dismissShortcutsHint(): void {
  try {
    localStorage.setItem(SHORTCUTS_KEY, "1");
  } catch {
    /* private mode */
  }
}
