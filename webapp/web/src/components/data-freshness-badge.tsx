"use client";

import { useDataStatus } from "@/lib/data-status-store";

/** "2026-07-30 14:04:15" → "30.07.2026 14:04" (как подпись версии в сайдбаре). */
function formatStamp(raw: string): string {
  const match = raw
    .trim()
    .match(/^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::\d{2})?/);
  return match
    ? `${match[3]}.${match[2]}.${match[1]} ${match[4]}:${match[5]}`
    : raw.trim();
}

/**
 * Свежесть данных рядом с заголовком: на скриншоте отчёта должно быть видно,
 * на какую дату и какой снимок он построен. Источник тот же, что у сайдбара.
 */
export function DataFreshnessBadge() {
  const status = useDataStatus();
  const freshness = status?.freshness;
  if (!freshness) return null;

  const stamp = freshness.active_version_created_at
    ? formatStamp(freshness.active_version_created_at)
    : null;
  const version = freshness.active_version_id;
  const text = stamp
    ? `данные на ${stamp}${version != null ? ` · снимок #${version}` : ""}`
    : freshness.label;
  if (!text) return null;

  const tone = freshness.stale
    ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200"
    : "border-tremor-border bg-tremor-background-subtle text-tremor-content dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content";

  return (
    <span
      title={freshness.stale ? "Данные устарели — обновите БД в меню" : freshness.label}
      className={`mt-2 hidden items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs lg:inline-flex ${tone}`}
    >
      <span aria-hidden>{freshness.stale ? "⚠" : "🕘"}</span>
      {text}
    </span>
  );
}
