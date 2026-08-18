"use client";

import { useEffect, useReducer, useRef } from "react";
import { chartLegendHostFrom } from "@/lib/chart-legend-host";

export type ChartHtmlLegendItem = {
  name: string;
  color: string;
  short?: string;
};

/** Легенда под графиком слева. Клик скрывает/показывает серию (как у Plotly). */
export function ChartHtmlLegend({
  items,
  className,
  compact = false,
  hidden,
  onToggle,
}: {
  items: ChartHtmlLegendItem[];
  className?: string;
  compact?: boolean;
  hidden?: Set<string>;
  onToggle?: (name: string) => void;
}) {
  const rootRef = useRef<HTMLDivElement | null>(null);
  const [, bump] = useReducer((n: number) => n + 1, 0);

  useEffect(() => {
    if (onToggle) return;
    let unsub: (() => void) | undefined;
    const tryBind = () => {
      const host = chartLegendHostFrom(rootRef.current);
      if (!host || unsub) return;
      unsub = host.subscribe(bump);
      bump();
    };
    tryBind();
    const poll = window.setInterval(tryBind, 200);
    const stop = window.setTimeout(() => window.clearInterval(poll), 5000);
    return () => {
      window.clearInterval(poll);
      window.clearTimeout(stop);
      unsub?.();
    };
  }, [onToggle, items]);

  if (!items.length) return null;

  const host = onToggle ? null : chartLegendHostFrom(rootRef.current);
  const hiddenSet = hidden ?? host?.hidden ?? new Set<string>();

  return (
    <div
      ref={rootRef}
      className={
        className ??
        (compact
          ? "mt-2 flex flex-wrap items-center justify-start gap-x-3 gap-y-1 px-0.5 text-[11px] leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong"
          : "mt-2 flex flex-wrap items-center justify-start gap-x-4 gap-y-1.5 px-1 text-xs text-tremor-content-strong dark:text-dark-tremor-content-strong")
      }
      role="list"
    >
      {items.map((item) => {
        const dimmed = hiddenSet.has(item.name);
        return (
          <button
            key={item.name}
            type="button"
            role="listitem"
            title={dimmed ? "Показать на графике" : "Скрыть на графике"}
            disabled={false}
            onClick={() => {
              if (onToggle) onToggle(item.name);
              else chartLegendHostFrom(rootRef.current)?.toggle(item.name);
            }}
            className={`inline-flex max-w-full items-center gap-1.5 text-left cursor-pointer ${
              dimmed ? "opacity-40 line-through" : ""
            }`}
          >
            <span
              className={
                compact
                  ? "inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                  : "inline-block h-3 w-3 shrink-0 rounded-sm"
              }
              style={{ background: item.color }}
              aria-hidden
            />
            <span className="min-w-0 break-words">
              {compact && item.short ? item.short : item.name}
            </span>
          </button>
        );
      })}
    </div>
  );
}
