import type { ReactNode } from "react";

/** Status pills in the spirit of the customer presentation mock. */

export type StatusPillTone = "ok" | "warn" | "bad" | "neutral";

const TONE: Record<StatusPillTone, string> = {
  ok: "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-300",
  warn: "bg-orange-100 text-orange-800 dark:bg-orange-950/40 dark:text-orange-300",
  bad: "bg-rose-100 text-rose-800 dark:bg-rose-950/50 dark:text-rose-300",
  neutral: "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300",
};

const DOT: Record<StatusPillTone, string> = {
  ok: "bg-emerald-600 dark:bg-emerald-400",
  warn: "bg-orange-500 dark:bg-orange-400",
  bad: "bg-rose-600 dark:bg-rose-400",
  neutral: "bg-slate-400",
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
      <span className={`h-2 w-2 shrink-0 rounded-full ${DOT[tone]}`} aria-hidden />
      {children}
    </span>
  );
}
