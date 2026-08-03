import type { ReactNode } from "react";
import { StatusPill, type StatusPillTone } from "@/components/status-pill";

/** Shared mobile card shell (customer presentation style). */

export function MobileEntityCard({
  title,
  badge,
  badgeTone = "neutral",
  children,
  className = "",
}: {
  title: ReactNode;
  badge?: ReactNode;
  badgeTone?: StatusPillTone;
  children: ReactNode;
  className?: string;
}) {
  return (
    <article
      className={`overflow-hidden rounded-xl border-[3px] border-[#94a3b8] bg-tremor-background shadow-sm dark:border-white dark:bg-dark-tremor-background ${className}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-[#94a3b8] bg-slate-50 px-3 py-2.5 dark:border-white dark:bg-slate-900/40">
        <h3 className="text-sm font-bold leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong">
          {title}
        </h3>
        {badge != null ? (
          typeof badge === "string" || typeof badge === "number" ? (
            <StatusPill tone={badgeTone}>{badge}</StatusPill>
          ) : (
            badge
          )
        ) : null}
      </header>
      <div className="px-3 py-3">{children}</div>
    </article>
  );
}

export function MobileMetricGrid({
  items,
  columns = 3,
}: {
  items: Array<{
    label: string;
    value: ReactNode;
    className?: string;
    /** Desktop-like cell tint: date blue / bad red / ok green */
    highlight?: "none" | "date" | "bad" | "ok";
  }>;
  columns?: 2 | 3 | 4;
}) {
  const cols =
    columns === 2 ? "grid-cols-2" : columns === 4 ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-3";
  return (
    <div className={`grid gap-2 text-center text-[11px] ${cols}`}>
      {items.map((item) => {
        const hl = item.highlight ?? "none";
        const cellTint =
          hl === "date"
            ? "bg-[rgba(156,194,229,0.35)] dark:bg-[rgba(214,234,248,0.14)]"
            : hl === "bad"
              ? "bg-rose-100 dark:bg-rose-950/40"
              : hl === "ok"
                ? "bg-emerald-100 dark:bg-emerald-950/40"
                : "bg-slate-50 dark:bg-slate-900/50";
        return (
          <div
            key={item.label}
            className={`rounded-lg border-2 border-[#cbd5e1] px-1.5 py-2 dark:border-[#5a6f82] ${cellTint}`}
          >
            <div className="mb-1 font-bold uppercase tracking-wide text-tremor-content dark:text-dark-tremor-content">
              {item.label}
            </div>
            <div
              className={`tabular-nums font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong ${item.className ?? ""}`}
            >
              {item.value}
            </div>
          </div>
        );
      })}
    </div>
  );
}

export function MobileCardStack({ children }: { children: ReactNode }) {
  return <div className="flex flex-col gap-3 px-2 pb-2 pt-10 lg:hidden">{children}</div>;
}
