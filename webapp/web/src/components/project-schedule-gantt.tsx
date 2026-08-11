"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { Text } from "@tremor/react";
import type { ProjectSchedulePayload } from "@/lib/api";
import { PLOTLY_CONFIG } from "@/lib/plotly-config";
import { useIsLandscape, useIsMobileViewport } from "@/lib/use-is-mobile";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Загрузка диаграммы…
    </div>
  ),
});

function useChartTheme() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setDark(root.classList.contains("dark"));
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return {
    dark,
    axis: dark ? "#cbd5e1" : "#334155",
    grid: dark ? "rgba(148,163,184,0.22)" : "rgba(148,163,184,0.25)",
  };
}

const PLAN = "#14b8a6";
const FACT = "#fb923c";
const SCROLL_VISIBLE_ROWS = 18;
const ROW_PX_DESKTOP = 48;
const ROW_PX_MOBILE_FIT = 64;
const ROW_PX_MOBILE_WIDE = 72;
const BAR_WIDTH_DESKTOP = 0.12;
const BAR_WIDTH_MOBILE = 0.18;
const LANE_GAP_DESKTOP = 0.03;
const LANE_GAP_MOBILE = 0.06;
const MARGIN_TOP = 20;
/** У основного графика ось X скрыта — шкала в отдельной закреплённой полосе. */
const MARGIN_BOTTOM_PLOT = 12;
const AXIS_STRIP_H = 72;
const DAY_MS = 24 * 3600 * 1000;
const COVENANT_LABEL_GAP_MS = 14 * DAY_MS;
const LABEL_COL_DESKTOP = 24;
const LABEL_COL_MOBILE = 28;
const MOBILE_CHART_MIN_PX = 960;

type GanttRow = ProjectSchedulePayload["gantt"]["rows"][number];

function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function wrapTaskLabelLines(name: string, widthChars = 28, maxLines = 2): string[] {
  const s = String(name || "").trim();
  if (!s) return [""];
  if (s.length <= widthChars) return [s];
  const words = s.split(/\s+/);
  const lines: string[] = [];
  let cur = "";
  for (const word of words) {
    const next = cur ? `${cur} ${word}` : word;
    if (next.length <= widthChars || !cur) {
      cur = next;
      continue;
    }
    lines.push(cur);
    cur = word;
    if (lines.length >= maxLines) break;
  }
  if (lines.length < maxLines && cur) lines.push(cur);
  else if (lines.length >= maxLines && cur) {
    const last = lines[lines.length - 1] || "";
    const rest = `${last} ${cur}`.trim();
    lines[lines.length - 1] =
      rest.length > widthChars + 8 ? `${rest.slice(0, widthChars + 6)}…` : rest;
  }
  if (lines.length === 1 && lines[0].length > widthChars) {
    const cut = lines[0];
    return [cut.slice(0, widthChars), cut.slice(widthChars)];
  }
  return lines.slice(0, maxLines);
}

function laneOffset(
  lane: "plan" | "fact",
  hasFact: boolean,
  barWidth: number,
  laneGap: number,
): number {
  if (!hasFact) return 0;
  const idx = lane === "plan" ? 0 : 1;
  return (idx - 0.5) * (barWidth + laneGap) * 2;
}

function sameDay(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  if (!a || !b) return false;
  return a.slice(0, 10) === b.slice(0, 10);
}

/** Одна строка дат под задачей на обычном мобильном виде. */
function rowDateSummary(row: GanttRow, covenantMode: boolean): string {
  if (covenantMode) {
    const p = row.baseline.end_label || "—";
    const f = row.current.end_label || "—";
    return `П ${p} · Ф ${f}`;
  }
  const ps = row.baseline.start_label || "—";
  const pe = row.baseline.end_label || "—";
  const fs = row.current.start_label || "—";
  const fe = row.current.end_label || "—";
  return `П ${ps}→${pe} · Ф ${fs}→${fe}`;
}

function clampPct(value: number): number {
  return Math.max(0, Math.min(100, value));
}

function formatTimelineDate(ms: number): string {
  return new Intl.DateTimeFormat("ru-RU", {
    day: "2-digit",
    month: "2-digit",
    year: "2-digit",
  }).format(new Date(ms));
}

function MobileTimelineLane({
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
  const startMs = toMs(milestone ? end : start);
  const endMs = toMs(end);
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
  row,
  covenantMode,
}: {
  row: GanttRow;
  covenantMode: boolean;
}) {
  const values = [
    toMs(row.baseline.start),
    toMs(row.baseline.end),
    toMs(row.current.start),
    toMs(row.current.end),
  ].filter((value): value is number => value != null);

  if (!values.length) return null;
  const start = Math.min(...values);
  const end = Math.max(...values);
  const days = Math.max(0, Math.round((end - start) / DAY_MS));

  if (covenantMode || start === end) {
    return (
      <div className="mt-2 border-t border-slate-100 pt-2 dark:border-slate-800">
        <div className="flex items-center gap-2 text-[9px] text-tremor-content dark:text-dark-tremor-content">
          <span className="h-2 w-2 shrink-0 rotate-45 rounded-[2px] bg-slate-400" />
          <span>Контрольная дата этапа</span>
          <span className="ml-auto font-semibold tabular-nums">
            {formatTimelineDate(end)}
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
          {formatTimelineDate(start)}
        </span>
        <span className="tabular-nums">
          <span className="font-semibold">Конец этапа</span>{" "}
          {formatTimelineDate(end)}
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

function MobileTaskTimelines({
  rows,
  planColor,
  factColor,
  labelPct,
  covenantMode,
  rangeStart,
  rangeEnd,
}: {
  rows: GanttRow[];
  planColor: string;
  factColor: string;
  labelPct: boolean;
  covenantMode: boolean;
  rangeStart: string | null;
  rangeEnd: string | null;
}) {
  const range = useMemo(() => {
    const dates: number[] = [];
    for (const row of rows) {
      for (const value of [
        row.baseline.start,
        row.baseline.end,
        row.current.start,
        row.current.end,
      ]) {
        const ms = toMs(value);
        if (ms != null) dates.push(ms);
      }
    }
    const apiStart = toMs(rangeStart);
    const apiEnd = toMs(rangeEnd);
    const start = dates.length ? Math.min(...dates) : apiStart ?? Date.now();
    const end = dates.length ? Math.max(...dates) : apiEnd ?? start + DAY_MS;
    return { start, end, span: Math.max(end - start, DAY_MS) };
  }, [rows, rangeStart, rangeEnd]);

  const axisDate = (ms: number) =>
    new Intl.DateTimeFormat("ru-RU", {
      day: "2-digit",
      month: "2-digit",
      year: "2-digit",
    }).format(new Date(ms));

  return (
    <div className="min-w-0">
      <Text className="mb-3 text-[11px] text-tremor-content dark:text-dark-tremor-content">
        Каждая задача показана на общей шкале времени. Даты закреплены у цветных
        дорожек плана и факта.
      </Text>
      <div className="max-h-[70vh] space-y-2 overflow-y-auto overscroll-contain pr-1">
        {rows.map((row, index) => (
          <article
            key={`${row.project ?? ""}-${row.task}-${index}`}
            className="rounded-xl border border-tremor-border bg-tremor-background p-3 shadow-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
          >
            <div className="mb-2 flex items-start justify-between gap-2">
              <div
                className="min-w-0 text-xs font-semibold leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong"
                title={row.label}
              >
                {row.label}
              </div>
              {row.pct_complete != null ? (
                <span className="shrink-0 rounded-full bg-slate-100 px-2 py-0.5 text-[10px] font-semibold tabular-nums text-slate-600 dark:bg-slate-800 dark:text-slate-300">
                  {row.pct_complete}%
                </span>
              ) : null}
            </div>
            <div className="space-y-1">
              {!labelPct ? (
                <MobileTimelineLane
                  label="П"
                  color={planColor}
                  start={row.baseline.start}
                  end={row.baseline.end}
                  startLabel={row.baseline.start_label}
                  endLabel={row.baseline.end_label}
                  rangeStart={range.start}
                  rangeSpan={range.span}
                  milestone={covenantMode}
                />
              ) : null}
              <MobileTimelineLane
                label="Ф"
                color={factColor}
                start={row.current.start}
                end={row.current.end}
                startLabel={labelPct ? "" : row.current.start_label}
                endLabel={
                  labelPct
                    ? row.pct_complete != null &&
                      Number.isFinite(Number(row.pct_complete))
                      ? `${Math.round(Number(row.pct_complete))}%`
                      : "н/д"
                    : row.current.end_label
                }
                rangeStart={range.start}
                rangeSpan={range.span}
                milestone={covenantMode}
              />
            </div>
            <MobileStageScale row={row} covenantMode={covenantMode} />
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
  );
}

export function ProjectScheduleGantt({
  data,
  fullscreen = false,
}: {
  data: ProjectSchedulePayload;
  fullscreen?: boolean;
}) {
  const rows = data.gantt.rows;
  const planColor = data.gantt.plan_color || PLAN;
  const factColor = data.gantt.fact_color || FACT;
  const labelPct = data.gantt.label_pct;
  const covenantMode = Boolean(data.gantt.covenant_mode ?? data.filters?.applied?.covenant_mode);
  const mobile = useIsMobileViewport();
  const landscape = useIsLandscape();
  const theme = useChartTheme();

  /**
   * Широкий режим с датами на полосах и гориз. скроллом —
   * только «Развернуть» + альбом на телефоне. Иначе даты — под именем / в карточках.
   */
  const expandedWide = mobile && fullscreen && landscape;
  const fitMobile = mobile && !expandedWide;
  const showAxisDateLabels = !mobile || expandedWide;

  const rowPx = fitMobile
    ? ROW_PX_MOBILE_FIT
    : mobile
      ? ROW_PX_MOBILE_WIDE
      : ROW_PX_DESKTOP;
  const barWidth = mobile ? BAR_WIDTH_MOBILE : BAR_WIDTH_DESKTOP;
  const laneGap = mobile ? LANE_GAP_MOBILE : LANE_GAP_DESKTOP;
  const labelColPct = fitMobile ? LABEL_COL_MOBILE : mobile ? 20 : LABEL_COL_DESKTOP;

  const built = useMemo(() => {
    if (!rows.length) return null;

    const labelLines = rows.map((row) =>
      wrapTaskLabelLines(
        row.label,
        fullscreen ? 34 : fitMobile ? 22 : mobile ? 18 : 28,
        fitMobile ? 1 : 2,
      ),
    );
    const dateSummaries = rows.map((row) => rowDateSummary(row, covenantMode));
    const n = rows.length;
    const hasFact = true;
    const taskFont = fullscreen ? 13 : fitMobile ? 10 : mobile ? 10 : 11;
    const labelFont = fullscreen ? 12 : 10;

    const planY = rows.map((_, i) =>
      i + laneOffset("plan", hasFact && !labelPct && !covenantMode, barWidth, laneGap),
    );
    const factY = rows.map((_, i) => i + laneOffset("fact", hasFact, barWidth, laneGap));

    const traces: Array<Record<string, unknown>> = [];

    if (covenantMode) {
      const planX = rows.map((row) => toMs(row.baseline.end));
      const factX = rows.map((row) => toMs(row.current.end));
      const yVals = rows.map((_, i) => i);

      traces.push({
        type: "scatter",
        mode: "markers",
        name: "План",
        x: planX,
        y: yVals,
        marker: {
          size: expandedWide ? 13 : 11,
          color: planColor,
          symbol: "diamond",
          line: { width: 1, color: "#ffffff" },
        },
        cliponaxis: false,
        showlegend: false,
        hovertemplate:
          "<b>%{customdata[0]}</b><br>План: %{customdata[1]}<extra></extra>",
        customdata: rows.map((row) => [row.label, row.baseline.end_label || "—"]),
      });
      traces.push({
        type: "scatter",
        mode: "markers",
        name: "Факт",
        x: factX,
        y: yVals,
        marker: {
          size: expandedWide ? 13 : 11,
          color: factColor,
          symbol: "diamond",
          line: { width: 1, color: "#ffffff" },
        },
        cliponaxis: false,
        showlegend: false,
        hovertemplate:
          "<b>%{customdata[0]}</b><br>Факт: %{customdata[1]}<extra></extra>",
        customdata: rows.map((row) => [row.label, row.current.end_label || "—"]),
      });

      if (showAxisDateLabels) {
        rows.forEach((row, i) => {
          const pe = toMs(row.baseline.end);
          const fe = toMs(row.current.end);
          if (pe != null && row.baseline.end_label) {
            if (expandedWide) {
              traces.push({
                type: "scatter",
                mode: "text",
                x: [pe],
                y: [i - 0.22],
                text: [row.baseline.end_label],
                textposition: "top center",
                textfont: { size: labelFont, color: planColor, family: "Arial" },
                hoverinfo: "skip",
                showlegend: false,
                cliponaxis: false,
              });
            } else {
              const planLeft = fe != null ? pe <= fe : true;
              traces.push({
                type: "scatter",
                mode: "text",
                x: [planLeft ? pe - COVENANT_LABEL_GAP_MS : pe + COVENANT_LABEL_GAP_MS],
                y: [i],
                text: [
                  planLeft
                    ? `${row.baseline.end_label}\u00a0`
                    : `\u00a0${row.baseline.end_label}`,
                ],
                textposition: planLeft ? "middle left" : "middle right",
                textfont: { size: labelFont, color: planColor, family: "Arial" },
                hoverinfo: "skip",
                showlegend: false,
                cliponaxis: false,
              });
            }
          }
          if (fe != null && row.current.end_label) {
            if (expandedWide) {
              traces.push({
                type: "scatter",
                mode: "text",
                x: [fe],
                y: [i + 0.22],
                text: [row.current.end_label],
                textposition: "bottom center",
                textfont: { size: labelFont, color: factColor, family: "Arial" },
                hoverinfo: "skip",
                showlegend: false,
                cliponaxis: false,
              });
            } else {
              const factLeft = pe != null ? fe < pe : false;
              traces.push({
                type: "scatter",
                mode: "text",
                x: [factLeft ? fe - COVENANT_LABEL_GAP_MS : fe + COVENANT_LABEL_GAP_MS],
                y: [i],
                text: [
                  factLeft
                    ? `${row.current.end_label}\u00a0`
                    : `\u00a0${row.current.end_label}`,
                ],
                textposition: factLeft ? "middle left" : "middle right",
                textfont: { size: labelFont, color: factColor, family: "Arial" },
                hoverinfo: "skip",
                showlegend: false,
                cliponaxis: false,
              });
            }
          }
        });
      }
    } else {
      const planBase = rows.map((row) => toMs(row.baseline.start));
      const planLen = rows.map((row) => {
        const start = toMs(row.baseline.start);
        const end = toMs(row.baseline.end);
        if (start == null || end == null) return 0;
        return Math.max(end - start, 0);
      });
      const factBase = rows.map((row) => toMs(row.current.start));
      const factLen = rows.map((row) => {
        const start = toMs(row.current.start);
        const end = toMs(row.current.end);
        if (start == null || end == null) return 0;
        return Math.max(end - start, 0);
      });

      if (!labelPct) {
        traces.push({
          type: "bar",
          orientation: "h",
          name: "План",
          y: planY,
          base: planBase,
          x: planLen,
          marker: { color: planColor },
          width: barWidth,
          textposition: "none",
          showlegend: false,
          cliponaxis: true,
          hovertemplate:
            "%{customdata[2]}<br>План: %{customdata[0]} — %{customdata[1]}<extra></extra>",
          customdata: rows.map((row) => [
            row.baseline.start_label || "—",
            row.baseline.end_label || "—",
            row.label,
          ]),
        });
      }

      traces.push({
        type: "bar",
        orientation: "h",
        name: "Факт",
        y: factY,
        base: factBase,
        x: factLen,
        marker: { color: factColor },
        width: barWidth,
        textposition: "none",
        showlegend: false,
        cliponaxis: true,
        hovertemplate: labelPct
          ? "%{customdata[2]}<br>Факт: %{customdata[0]} — %{customdata[1]}<br>%{customdata[3]}%<extra></extra>"
          : "%{customdata[2]}<br>Факт: %{customdata[0]} — %{customdata[1]}<extra></extra>",
        customdata: rows.map((row) => [
          row.current.start_label || "—",
          row.current.end_label || "—",
          row.label,
          row.pct_complete ?? "",
        ]),
      });

      if (showAxisDateLabels) {
        type EdgeBucket = {
          x: number[];
          y: number[];
          text: string[];
          position: string;
        };
        const buckets: Record<string, EdgeBucket> = {};
        const pushEdge = (
          key: string,
          x: number | null,
          y: number,
          text: string,
          position: string,
        ) => {
          if (x == null || !text) return;
          if (!buckets[key]) buckets[key] = { x: [], y: [], text: [], position };
          buckets[key].x.push(x);
          buckets[key].y.push(y);
          buckets[key].text.push(text);
        };

        rows.forEach((row, i) => {
          const py = planY[i];
          const fy = factY[i];
          const ps = toMs(row.baseline.start);
          const pe = toMs(row.baseline.end);
          const fs = toMs(row.current.start);
          const fe = toMs(row.current.end);

          const startPos = expandedWide ? "top center" : "middle left";
          const endPos = expandedWide ? "bottom center" : "middle right";
          const startYShift = expandedWide ? -0.08 : 0;
          const endYShift = expandedWide ? 0.08 : 0;

          if (labelPct) {
            // Как main: только «Факт» + % справа, без дат на концах бара.
            const pctTxt =
              row.pct_complete != null && Number.isFinite(Number(row.pct_complete))
                ? `${Math.round(Number(row.pct_complete))}%`
                : "н/д";
            pushEdge(
              "fact|pct",
              fe,
              fy + endYShift,
              pctTxt,
              expandedWide ? "bottom center" : "middle right",
            );
          } else {
            pushEdge(
              "plan|start",
              ps,
              py + startYShift,
              row.baseline.start_label || "",
              startPos,
            );
            pushEdge(
              "plan|end",
              pe,
              py + endYShift,
              row.baseline.end_label || "",
              endPos,
            );
            if (!sameDay(row.current.start, row.baseline.start)) {
              pushEdge(
                "fact|start",
                fs,
                fy + startYShift,
                row.current.start_label || "",
                startPos,
              );
            }
            if (!sameDay(row.current.end, row.baseline.end)) {
              pushEdge(
                "fact|end",
                fe,
                fy + endYShift,
                row.current.end_label || "",
                endPos,
              );
            }
          }
        });

        (Object.entries(buckets) as Array<[string, EdgeBucket]>).forEach(
          ([key, bucket]) => {
            if (!bucket.x.length) return;
            const color = key.startsWith("fact") ? factColor : planColor;
            traces.push({
              type: "scatter",
              mode: "text",
              x: bucket.x,
              y: bucket.y,
              text: bucket.text,
              textposition: bucket.position,
              textfont: { size: labelFont, color, family: "Arial" },
              hoverinfo: "skip",
              showlegend: false,
              cliponaxis: !expandedWide,
            });
          },
        );
      }
    }

    const barMs: number[] = [];
    rows.forEach((row) => {
      for (const iso of [
        row.baseline.start,
        row.baseline.end,
        row.current.start,
        row.current.end,
      ]) {
        const ms = toMs(iso);
        if (ms != null) barMs.push(ms);
      }
    });
    const apiLo = toMs(data.gantt.range_start);
    const apiHi = toMs(data.gantt.range_end);
    let lo = barMs.length ? Math.min(...barMs) : apiLo;
    let hi = barMs.length ? Math.max(...barMs) : apiHi;
    if (lo == null && apiLo != null) lo = apiLo;
    if (hi == null && apiHi != null) hi = apiHi;
    const span = lo != null && hi != null ? Math.max(hi - lo, DAY_MS) : DAY_MS;
    const padLo = expandedWide
      ? Math.max(55 * DAY_MS, span * 0.1)
      : Math.max(45 * DAY_MS, span * 0.08);
    const padHi = expandedWide
      ? Math.max(45 * DAY_MS, span * 0.1)
      : Math.max(30 * DAY_MS, span * 0.06);
    const xRange =
      lo != null && hi != null ? [lo - padLo, hi + padHi] : undefined;

    const plotHeight = Math.max(280, n * rowPx);
    const chartHeight = plotHeight + MARGIN_TOP + MARGIN_BOTTOM_PLOT;
    const lanePad = expandedWide ? 0.55 : 0.4;
    const marginR = expandedWide ? 28 : 40;
    const marginL = 8;

    const xAxisShared = {
      type: "date" as const,
      range: xRange,
      tickformat: "%d-%m-%y",
      tickangle: -35,
      showgrid: true,
      gridcolor: theme.grid,
      automargin: false,
      fixedrange: true,
      domain: [0, 1],
    };

    return {
      labelLines,
      dateSummaries,
      taskFont,
      rowPx,
      labelColPct,
      showDateUnderLabel: fitMobile,
      chartMinWidth: expandedWide ? MOBILE_CHART_MIN_PX : undefined,
      marginL,
      marginR,
      data: traces,
      layout: {
        barmode: "overlay",
        bargap: 0.78,
        bargroupgap: laneGap,
        height: chartHeight,
        autosize: true,
        margin: {
          l: marginL,
          r: marginR,
          t: MARGIN_TOP,
          b: MARGIN_BOTTOM_PLOT,
        },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        hovermode: false,
        dragmode: mobile ? false : "zoom",
        xaxis: {
          ...xAxisShared,
          // Шкала всегда в полосе снизу — здесь только сетка
          showticklabels: false,
          title: { text: "" },
          ticks: "",
          fixedrange: mobile,
        },
        yaxis: {
          type: "linear",
          tickmode: "array",
          tickvals: rows.map((_, i) => i),
          ticktext: rows.map(() => ""),
          showticklabels: false,
          automargin: false,
          autorange: false,
          range: [n - 0.5 + lanePad, -0.5 - lanePad],
          fixedrange: true,
          side: "left",
          showgrid: false,
          title: "",
          zeroline: false,
        },
        font: { color: theme.axis, size: taskFont },
      },
      axisLayout: {
        height: AXIS_STRIP_H,
        autosize: true,
        // Запас снизу под наклонённые даты; title у оси убран — «Период» слева в колонке
        margin: { l: marginL, r: marginR, t: 2, b: 52 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        hovermode: false,
        dragmode: false,
        xaxis: {
          ...xAxisShared,
          title: { text: "" },
          showticklabels: true,
          ticks: "outside",
          ticklen: 4,
          tickangle: -30,
          tickfont: { size: 11, color: theme.axis },
          tickcolor: theme.axis,
          side: "bottom",
          showgrid: false,
          automargin: false,
        },
        yaxis: {
          visible: false,
          fixedrange: true,
          range: [0, 1],
        },
        font: { color: theme.axis, size: 11 },
      },
      config: {
        ...PLOTLY_CONFIG,
        scrollZoom: false,
        displayModeBar: false,
      },
      chartHeight,
      plotHeight,
      axisHeight: AXIS_STRIP_H,
      viewportHeight: Math.min(
        chartHeight,
        Math.min(n, SCROLL_VISIBLE_ROWS) * rowPx + MARGIN_TOP + MARGIN_BOTTOM_PLOT,
      ),
    };
  }, [
    rows,
    planColor,
    factColor,
    labelPct,
    covenantMode,
    showAxisDateLabels,
    fullscreen,
    mobile,
    fitMobile,
    expandedWide,
    rowPx,
    barWidth,
    laneGap,
    labelColPct,
    data.gantt.range_start,
    data.gantt.range_end,
    theme.axis,
    theme.grid,
  ]);

  if (!built) {
    return (
      <div className="py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет задач для отображения на ганте.
      </div>
    );
  }

  if (fitMobile) {
    return (
      <div className="gantt-root w-full min-w-0">
        <div className="mb-2 flex flex-wrap gap-4 text-sm">
          {!labelPct ? (
            <span className="inline-flex items-center gap-2">
              <span
                className="inline-block h-2.5 w-6 rounded"
                style={{ background: planColor }}
              />
              <Text>План</Text>
            </span>
          ) : null}
          <span className="inline-flex items-center gap-2">
            <span
              className="inline-block h-2.5 w-6 rounded"
              style={{ background: factColor }}
            />
            <Text>Факт</Text>
          </span>
        </div>
        <MobileTaskTimelines
          rows={rows}
          planColor={planColor}
          factColor={factColor}
          labelPct={labelPct}
          covenantMode={covenantMode}
          rangeStart={data.gantt.range_start}
          rangeEnd={data.gantt.range_end}
        />
      </div>
    );
  }

  const viewportMax = fullscreen
    ? undefined
    : `${built.viewportHeight}px`;

  const bodyMinWidth = built.chartMinWidth
    ? `calc(${built.labelColPct}% + ${built.chartMinWidth}px)`
    : "100%";

  return (
    <div
      className={`gantt-root flex w-full min-w-0 flex-col ${
        fullscreen ? "h-full min-h-0" : ""
      }`}
    >
      <div className="mb-2 flex flex-wrap gap-4 text-sm">
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-2.5 w-6 rounded" style={{ background: planColor }} />
          <Text>План</Text>
        </span>
        <span className="inline-flex items-center gap-2">
          <span className="inline-block h-2.5 w-6 rounded" style={{ background: factColor }} />
          <Text>Факт</Text>
        </span>
      </div>
      {fitMobile ? (
        <Text className="mb-2 text-[11px] text-tremor-content dark:text-dark-tremor-content">
          Даты — под названием задачи и в карточках таблицы. Чтобы видеть даты на
          полосах: «Развернуть» и повернуть телефон горизонтально.
        </Text>
      ) : null}
      {expandedWide ? (
        <Text className="mb-2 text-[11px] text-tremor-content dark:text-dark-tremor-content">
          Листайте вверх/вниз и вправо — таймлайн увеличен, даты у начала сверху и у
          конца снизу. Шкала времени закреплена внизу.
        </Text>
      ) : null}

      <div
        className={`min-h-0 flex-1 ${
          expandedWide || fullscreen ? "overflow-x-auto" : "overflow-x-hidden"
        }`}
      >
        <div style={{ minWidth: bodyMinWidth, width: "100%" }}>
          <div
            className="gantt-schedule-scroll-wrap overflow-y-auto overflow-x-hidden rounded-t-md border border-b-0 border-tremor-border dark:border-dark-tremor-border"
            style={viewportMax ? { maxHeight: viewportMax } : undefined}
          >
            <div className="flex" style={{ minHeight: built.chartHeight, width: "100%" }}>
              <div
                className="shrink-0 border-r border-tremor-border bg-tremor-background dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                style={{
                  width: `${built.labelColPct}%`,
                  minWidth: fitMobile ? 108 : undefined,
                  paddingTop: MARGIN_TOP,
                  paddingBottom: MARGIN_BOTTOM_PLOT,
                }}
              >
                {built.labelLines.map((lines, i) => (
                  <div
                    key={`${rows[i]?.label ?? i}-${i}`}
                    className="flex flex-col justify-center overflow-hidden px-1.5 text-left leading-tight text-tremor-content dark:text-dark-tremor-content"
                    style={{
                      height: built.rowPx,
                      fontSize: built.taskFont,
                    }}
                    title={rows[i]?.label}
                  >
                    <span className="block w-full whitespace-normal break-words">
                      {lines.map((line, li) => (
                        <span key={li} className="block truncate">
                          {line}
                        </span>
                      ))}
                    </span>
                    {built.showDateUnderLabel ? (
                      <span
                        className="mt-0.5 block truncate tabular-nums text-[9px] leading-snug opacity-80"
                        title={built.dateSummaries[i]}
                      >
                        {built.dateSummaries[i]}
                      </span>
                    ) : null}
                  </div>
                ))}
              </div>
              <div
                className="min-w-0 flex-1"
                style={{
                  width: `${100 - built.labelColPct}%`,
                  minWidth: built.chartMinWidth,
                }}
              >
                <PlotlyFigure
                  data={built.data as never}
                  layout={built.layout as never}
                  config={built.config as never}
                  useResizeHandler
                  style={{ width: "100%", height: built.chartHeight }}
                />
              </div>
            </div>
          </div>

          <div className="gantt-axis-strip shrink-0 rounded-b-md border border-tremor-border bg-tremor-background dark:border-dark-tremor-border dark:bg-dark-tremor-background">
            <div className="flex w-full">
              <div
                className="flex shrink-0 items-center border-r border-tremor-border px-1.5 text-[10px] font-semibold uppercase tracking-wide text-tremor-content dark:border-dark-tremor-border dark:text-dark-tremor-content"
                style={{
                  width: `${built.labelColPct}%`,
                  minWidth: fitMobile ? 108 : undefined,
                }}
              >
                Период
              </div>
              <div
                className="min-w-0 flex-1"
                style={{
                  width: `${100 - built.labelColPct}%`,
                  minWidth: built.chartMinWidth,
                }}
              >
                <PlotlyFigure
                  data={[] as never}
                  layout={built.axisLayout as never}
                  config={built.config as never}
                  useResizeHandler
                  style={{ width: "100%", height: built.axisHeight }}
                />
              </div>
            </div>
          </div>
        </div>
      </div>
    </div>
  );
}
