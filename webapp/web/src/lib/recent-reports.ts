const KEY = "bi_showcase_recent_reports_v1";
const LIMIT = 5;

/** Последние открытые отчёты — только для мобильного листа поиска. */
export function readRecentReports(): string[] {
  if (typeof window === "undefined") return [];
  try {
    const raw = localStorage.getItem(KEY);
    if (!raw) return [];
    const parsed: unknown = JSON.parse(raw);
    if (!Array.isArray(parsed)) return [];
    return parsed.filter((h): h is string => typeof h === "string").slice(0, LIMIT);
  } catch {
    return [];
  }
}

export function pushRecentReport(href: string): void {
  if (typeof window === "undefined" || !href) return;
  try {
    const next = [href, ...readRecentReports().filter((h) => h !== href)].slice(
      0,
      LIMIT,
    );
    localStorage.setItem(KEY, JSON.stringify(next));
  } catch {
    /* ignore */
  }
}
