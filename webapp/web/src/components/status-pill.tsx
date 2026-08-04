import type { ReactNode } from "react";

/** Status pills in the spirit of the customer presentation mock. */

export type StatusPillTone = "ok" | "warn" | "bad" | "neutral";

/** Непрозрачные пары фон/текст: полупрозрачные тинты на тёмной теме теряли контраст. */
const TONE: Record<StatusPillTone, string> = {
  ok: "bg-emerald-100 text-emerald-900 dark:bg-emerald-900 dark:text-emerald-50",
  warn: "bg-orange-100 text-orange-900 dark:bg-orange-900 dark:text-orange-50",
  bad: "bg-rose-100 text-rose-900 dark:bg-rose-900 dark:text-rose-50",
  neutral: "bg-slate-100 text-slate-800 dark:bg-slate-700 dark:text-slate-50",
};

/** Знак дублирует цвет: статус читается и при дальтонизме, и на ярком солнце. */
const GLYPH: Record<StatusPillTone, string> = {
  ok: "✓",
  warn: "!",
  bad: "✕",
  neutral: "·",
};

export function StatusPill({
  tone,
  children,
}: {
  tone: StatusPillTone;
  children: ReactNode;
}) {
  return (
    <span
      className={`inline-flex items-center gap-1.5 rounded-full px-2.5 py-1 text-[11px] font-bold ${TONE[tone]}`}
    >
      <span className="shrink-0 text-[10px] leading-none" aria-hidden>
        {GLYPH[tone]}
      </span>
      {children}
    </span>
  );
}
