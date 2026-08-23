"use client";

const KEY = "bi_report_favorites_v1";
const MAX = 12;

export function readReportFavorites(): string[] {
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed)
      ? parsed.filter((h): h is string => typeof h === "string").slice(0, MAX)
      : [];
  } catch {
    return [];
  }
}

export function toggleReportFavorite(href: string): string[] {
  const list = readReportFavorites();
  const next = list.includes(href)
    ? list.filter((h) => h !== href)
    : [href, ...list].slice(0, MAX);
  try {
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* private mode */
  }
  return next;
}

export function isReportFavorite(href: string): boolean {
  return readReportFavorites().includes(href);
}
