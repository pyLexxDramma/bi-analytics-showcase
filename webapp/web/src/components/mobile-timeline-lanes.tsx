"use client";

import { useMemo } from "react";
import { Text } from "@tremor/react";

export const MOBILE_TIMELINE_DAY_MS = 24 * 3600 * 1000;

export function mobileTimelineToMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

export function formatMobileTimelineDate(ms: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  }).format(new Date(ms));
}

function clampPct(value: number): number {
  return Math.max(0, Math.min(100, value));
}

export function MobileTimelineLane({
  label,
  color,
  start,
  end,
  startLabel,
  endLabel,
  rangeStart,
  rangeSpan,
  milestone = false,
}: {
  label: string;
  color: string;
  start: string | null | undefined;
  end: string | null | undefined;
  startLabel: string | undefined;
  endLabel: string | undefined;
  rangeStart: number;
  rangeSpan: number;
  milestone?: boolean;
}) {
  const startMs = mobileTimelineToMs(milestone ? end : start);
  const endMs = mobileTimelineToMs(end);
  if (startMs == null && endMs == null) {
    return (
      <div className="grid grid-cols-[1.75rem_1fr] items-center gap-2">
        <span className="text-[10px] font-bold" style={{ color }}>
          {label}
        </span>
        <span className="text-[10px] text-tremor-content dark:text-dark-tremor-content">
          Нет дат
        </span>
      </div>
    );
  }

  const left = clampPct((((startMs ?? endMs ?? rangeStart) - rangeStart) / rangeSpan) * 100);
  const right = clampPct((((endMs ?? startMs ?? rangeStart) - rangeStart) / rangeSpan) * 100);
  const width = milestone ? 0 : Math.max(1.5, right - left);
  const labelCenter = clampPct(Math.max(25, Math.min(75, (left + right) / 2)));
  const dateText = milestone
    ? `Дата ${endLabel || "—"}`
    : !startLabel && endLabel
      ? endLabel
      : `Начало ${startLabel || "—"} · Конец ${endLabel || "—"}`;

  return (
    <div className="grid grid-cols-[1.75rem_1fr] items-end gap-2">
      <span className="mb-1 text-[10px] font-bold" style={{ color }}>
        {label}
      </span>
      <div className="relative h-9 min-w-0">
        <span
          className="absolute top-0 z-10 -translate-x-1/2 whitespace-nowrap rounded-md bg-tremor-background/90 px-1 py-0.5 text-[9px] font-semibold leading-none tabular-nums shadow-sm dark:bg-dark-tremor-background/90"
          style={{ left: `${labelCenter}%`, color }}
        >
          {dateText}
        </span>
        <div className="absolute inset-x-0 bottom-1 h-2 rounded-full bg-slate-100 dark:bg-slate-800">
          <span className="absolute inset-y-0 left-0 w-px bg-slate-300/70 dark:bg-slate-600/70" />
          <span className="absolute inset-y-0 left-1/2 w-px bg-slate-300/70 dark:bg-slate-600/70" />
          <span className="absolute inset-y-0 right-0 w-px bg-slate-300/70 dark:bg-slate-600/70" />
          {milestone ? (
            <span
              className="absolute -top-1 h-4 w-4 -translate-x-1/2 rotate-45 rounded-[3px] border-2 border-white shadow-sm dark:border-slate-900"
              style={{ left: `${right}%`, background: color }}
            />
          ) : (
            <span
              className="absolute inset-y-0 min-w-[5px] rounded-full shadow-sm"
              style={{ left: `${left}%`, width: `${width}%`, background: color }}
            />
          )}
        </div>
      </div>
    </div>
  );
}

function MobileStageScale({
  dates,
  covenantMode,
}: {
  dates: Array<string | null | undefined>;
  covenantMode: boolean;
}) {
  const values = dates
    .map((value) => mobileTimelineToMs(value))
    .filter((value): value is number => value != null);

  if (!values.length) return null;
  const start = Math.min(...values);
  const end = Math.max(...values);
  const days = Math.max(0, Math.round((end - start) / MOBILE_TIMELINE_DAY_MS));

  if (covenantMode || start === end) {
    return (
      <div className="mt-2 border-t border-slate-100 pt-2 dark:border-slate-800">
        <div className="flex items-center gap-2 text-[9px] text-tremor-content dark:text-dark-tremor-content">
          <span className="h-2 w-2 shrink-0 rotate-45 rounded-[2px] bg-slate-400" />
          <span>Контрольная дата этапа</span>
          <span className="ml-auto font-semibold tabular-nums">
            {formatMobileTimelineDate(end)}
          </span>
        </div>
      </div>
    );
  }

  return (
    <div className="mt-2 border-t border-slate-100 pt-2 dark:border-slate-800">
      <div className="mb-1 flex items-center justify-between gap-2 text-[8px] leading-none text-tremor-content dark:text-dark-tremor-content">
        <span className="tabular-nums">
          <span className="font-semibold">Начало этапа</span>{" "}
          {formatMobileTimelineDate(start)}
        </span>
        <span className="tabular-nums">
          <span className="font-semibold">Конец этапа</span>{" "}
          {formatMobileTimelineDate(end)}
        </span>
      </div>
      <div className="relative h-3">
        <span className="absolute left-0 right-0 top-1.5 h-px bg-slate-300 dark:bg-slate-600" />
        <span className="absolute left-0 top-1 h-2 w-2 -translate-x-0.5 rounded-full border-2 border-white bg-slate-500 dark:border-slate-900" />
        <span className="absolute right-0 top-1 h-2 w-2 translate-x-0.5 rounded-full border-2 border-white bg-slate-500 dark:border-slate-900" />
        <span className="absolute left-1/2 top-0 -translate-x-1/2 rounded-full bg-slate-100 px-1.5 py-0.5 text-[8px] font-medium leading-none tabular-nums text-slate-500 dark:bg-slate-800 dark:text-slate-300">
          {days} дн.
        </span>
      </div>
    </div>
  );
}

export type MobileTimelineCardRow = {
  id: string;
  title: string;
  titleHint?: string;
  badge?: string | null;
  badgeClassName?: string;
  primary: {
    start?: string | null;
    end?: string | null;
    startLabel?: string | null;
    endLabel?: string | null;
  };
  secondary: {
    start?: string | null;
    end?: string | null;
    startLabel?: string | null;
    endLabel?: string | null;
  };
  stageDates?: Array<string | null | undefined>;
};

export function MobileTimelineCards({
  rows,
  primaryColor,
  secondaryColor,
  primaryLegend,
  secondaryLegend,
  primaryLaneLabel,
  secondaryLaneLabel,
  showPrimaryLane = true,
  covenantMode = false,
  rangeStart,
  rangeEnd,
  intro = "Каждая задача показана на общей шкале времени. Даты закреплены у цветных дорожек плана и факта.",
}: {
  rows: MobileTimelineCardRow[];
  primaryColor: string;
  secondaryColor: string;
  primaryLegend: string;
  secondaryLegend: string;
  primaryLaneLabel: string;
  secondaryLaneLabel: string;
  showPrimaryLane?: boolean;
  covenantMode?: boolean;
  rangeStart: string | null;
  rangeEnd: string | null;
  intro?: string;
}) {
  const range = useMemo(() => {
    const dates: number[] = [];
    for (const row of rows) {
      for (const value of [
        row.primary.start,
        row.primary.end,
        row.secondary.start,
        row.secondary.end,
        ...(row.stageDates ?? []),
      ]) {
        const ms = mobileTimelineToMs(value);
        if (ms != null) dates.push(ms);
      }
    }
    const apiStart = mobileTimelineToMs(rangeStart);
    const apiEnd = mobileTimelineToMs(rangeEnd);
    const start = dates.length ? Math.min(...dates) : apiStart ?? Date.now();
    const end = dates.length ? Math.max(...dates) : apiEnd ?? start + MOBILE_TIMELINE_DAY_MS;
    return { start, end, span: Math.max(end - start, MOBILE_TIMELINE_DAY_MS) };
  }, [rows, rangeStart, rangeEnd]);

  const axisDate = (ms: number) => formatMobileTimelineDate(ms);

  return (
    <div className="gantt-root w-full min-w-0">
      <div className="mb-2 flex flex-wrap gap-4 text-sm">
        {showPrimaryLane ? (
          <span className="inline-flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-6 rounded"
              style={{ background: primaryColor }}
            />
            <Text>{primaryLegend}</Text>
          </span>
        ) : null}
        <span className="inline-flex items-center gap-2">
          <span
            className="inline-block h-2.5 w-6 rounded"
            style={{ background: secondaryColor }}
          />
          <Text>{secondaryLegend}</Text>
        </span>
      </div>
      <div className="min-w-0">
        <Text className="mb-3 text-[11px] text-tremor-content dark:text-dark-tremor-content">
          {intro}
        </Text>
        <div className="max-h-[70vh] space-y-2 overflow-y-auto overscroll-contain pr-1">
          {rows.map((row) => (
            <article
              key={row.id}
              className="rounded-xl border border-tremor-border bg-tremor-background p-3 shadow-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            >
              <div className="mb-2 flex items-start justify-between gap-2">
                <div
                  className="min-w-0 text-xs font-semibold leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong"
                  title={row.titleHint ?? row.title}
                >
                  {row.title}
                </div>
                {row.badge ? (
                  <span
                    className={
                      row.badgeClassName ??
                      "shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300"
                    }
                  >
                    {row.badge}
                  </span>
                ) : null}
              </div>
              <div className="space-y-1">
                {showPrimaryLane ? (
                  <MobileTimelineLane
                    label={primaryLaneLabel}
                    color={primaryColor}
                    start={row.primary.start}
                    end={row.primary.end}
                    startLabel={row.primary.startLabel ?? undefined}
                    endLabel={row.primary.endLabel ?? undefined}
                    rangeStart={range.start}
                    rangeSpan={range.span}
                    milestone={covenantMode}
                  />
                ) : null}
                <MobileTimelineLane
                  label={secondaryLaneLabel}
                  color={secondaryColor}
                  start={row.secondary.start}
                  end={row.secondary.end}
                  startLabel={row.secondary.startLabel ?? undefined}
                  endLabel={row.secondary.endLabel ?? undefined}
                  rangeStart={range.start}
                  rangeSpan={range.span}
                  milestone={covenantMode}
                />
              </div>
              <MobileStageScale
                dates={
                  row.stageDates ?? [
                    row.primary.start,
                    row.primary.end,
                    row.secondary.start,
                    row.secondary.end,
                  ]
                }
                covenantMode={covenantMode}
              />
            </article>
          ))}
        </div>
        <div className="sticky bottom-0 z-10 mt-2 grid grid-cols-[1.75rem_1fr] gap-2 rounded-lg border border-tremor-border bg-tremor-background/95 px-3 py-2 text-[9px] tabular-nums text-tremor-content shadow-sm backdrop-blur dark:border-dark-tremor-border dark:bg-dark-tremor-background/95 dark:text-dark-tremor-content">
          <span />
          <div className="flex justify-between">
            <span>{axisDate(range.start)}</span>
            <span>{axisDate(range.start + range.span / 2)}</span>
            <span>{axisDate(range.end)}</span>
          </div>
        </div>
      </div>
    </div>
  );
}
