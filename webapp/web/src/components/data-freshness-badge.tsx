"use client";

import { useState } from "react";
import { useDataStatus, loadDataStatus } from "@/lib/data-status-store";

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
 * на какую дату построен отчёт. Клик — обновить статус (без version_id в UI).
 */
export function DataFreshnessBadge({ inline = false }: { inline?: boolean }) {
  const status = useDataStatus();
  const [detail, setDetail] = useState(false);
  const freshness = status?.freshness;
  if (!freshness) return null;

  const stamp = freshness.active_version_created_at
    ? formatStamp(freshness.active_version_created_at)
    : null;
  const files = status?.files;
  const text = stamp ? `данные на ${stamp}` : freshness.label;
  if (!text) return null;

  const tone = freshness.stale
    ? "border-amber-300 bg-amber-50 text-amber-900 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-200"
    : "border-tremor-border bg-tremor-background-subtle text-tremor-content dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content";

  return (
    <span className={`relative inline-block ${inline ? "mx-auto min-w-0 max-w-full" : "mt-1.5"}`}>
      <button
        type="button"
        data-walk-mask="freshness"
        title={freshness.stale ? "Данные устарели — нажмите для деталей" : freshness.label}
        onClick={() => {
          void loadDataStatus(true);
          setDetail((v) => !v);
        }}
        className={`inline-flex max-w-full items-center gap-1.5 rounded-full border px-2.5 py-1 text-xs ${tone} ${inline ? "min-w-0" : ""}`}
      >
        <span aria-hidden className="shrink-0">{freshness.stale ? "⚠" : "🕘"}</span>
        <span className={inline ? "truncate" : undefined}>{text}</span>
      </button>
      {detail ? (
        <span
          role="tooltip"
          className="absolute left-0 top-full z-20 mt-1 min-w-[12rem] rounded-lg border border-tremor-border bg-tremor-background px-3 py-2 text-xs shadow-lg dark:border-dark-tremor-border dark:bg-dark-tremor-background"
        >
          {files != null ? <span className="block">Файлов в web/: {files}</span> : null}
          <span className="block opacity-80">{freshness.label}</span>
        </span>
      ) : null}
    </span>
  );
}
