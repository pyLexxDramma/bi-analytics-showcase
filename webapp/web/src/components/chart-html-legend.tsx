"use client";

export type ChartHtmlLegendItem = {
  name: string;
  color: string;
  short?: string;
};

/** Легенда под графиком слева, вне overflow-x — не уезжает при горизонтальном скролле. */
export function ChartHtmlLegend({
  items,
  className,
  compact = false,
}: {
  items: ChartHtmlLegendItem[];
  className?: string;
  compact?: boolean;
}) {
  if (!items.length) return null;
  return (
    <div
      className={
        className ??
        (compact
          ? "mt-2 flex flex-wrap items-center justify-start gap-x-3 gap-y-1 px-0.5 text-[11px] leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong"
          : "mt-2 flex flex-wrap items-center justify-start gap-x-4 gap-y-1.5 px-1 text-xs text-tremor-content-strong dark:text-dark-tremor-content-strong")
      }
      role="list"
    >
      {items.map((item) => (
        <span
          key={item.name}
          className="inline-flex max-w-full items-center gap-1.5"
          role="listitem"
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
        </span>
      ))}
    </div>
  );
}
