"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import { Text } from "@tremor/react";
import type { BaselineDeviationPayload } from "@/lib/api";
import { DashboardEmptyState } from "@/components/dashboard-empty-state";
import { CHART_RU } from "@/lib/chart-ru";
import { PLOTLY_CONFIG, plotlyLegendUnderLeft } from "@/lib/plotly-config";
import { useIsMobileViewport } from "@/lib/use-is-mobile";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Загрузка диаграммы…
    </div>
  ),
});

const SCROLL_VISIBLE_ROWS = 18;
const ROW_PX = 44;
const BAR_WIDTH = 0.14;
const LANE_GAP = 0.04;
const MARGIN_TOP = 28;
const MARGIN_BOTTOM = 110;
const DAY_MS = 24 * 3600 * 1000;
const LABEL_COL_PCT_DESKTOP = 42;
const LABEL_COL_PCT_MOBILE = 48;
const LABEL_MAX_LINES = 4;

function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function fmtLabel(iso: string | null | undefined, fallback?: string | null): string {
  if (fallback) return fallback;
  if (!iso) return "";
  const d = new Date(iso);
  if (!Number.isFinite(d.getTime())) return "";
  const dd = String(d.getUTCDate()).padStart(2, "0");
  const mm = String(d.getUTCMonth() + 1).padStart(2, "0");
  const yyyy = d.getUTCFullYear();
  return `${dd}.${mm}.${yyyy}`;
}

function wrapLineCount(name: string, widthChars: number, maxLines: number): number {
  const s = String(name || "").trim();
  if (!s) return 1;
  const words = s.split(/\s+/);
  let lines = 1;
  let cur = 0;
  for (const word of words) {
    const add = cur ? word.length + 1 : word.length;
    if (cur && cur + add > widthChars) {
      lines += 1;
      cur = word.length;
      if (lines >= maxLines) return maxLines;
      continue;
    }
    cur += add;
  }
  return lines;
}

function taskLabelOnly(
  label: string,
  project: string | null | undefined,
): string {
  const raw = String(label || "").trim();
  const proj = String(project || "").trim();
  if (!proj) {
    // legacy "task (project)" or "project: task"
    const mColon = raw.match(/^[^:]+:\s*(.+)$/);
    if (mColon) return mColon[1].trim();
    const mParen = raw.match(/^(.*?)\s*\([^)]+\)\s*$/);
    if (mParen) return mParen[1].trim();
    return raw;
  }
  if (raw.startsWith(`${proj}:`)) return raw.slice(proj.length + 1).trim() || raw;
  if (raw.endsWith(`(${proj})`)) {
    return raw.slice(0, raw.length - proj.length - 2).trim() || raw;
  }
  return raw;
}

function chartLegend(fullscreen: boolean) {
  return plotlyLegendUnderLeft({
    fontSize: fullscreen ? 13 : 12,
    y: -0.16,
  });
}

function laneOffset(lane: "base" | "plan", hasPlan: boolean): number {
  if (!hasPlan) return 0;
  const idx = lane === "base" ? 0 : 1;
  return (idx - 0.5) * (BAR_WIDTH + LANE_GAP) * 2;
}

export function BaselineDeviationChart({
  data,
  fullscreen = false,
}: {
  data: BaselineDeviationPayload;
  fullscreen?: boolean;
}) {
  const mobile = useIsMobileViewport();
  const labelColPct = mobile ? LABEL_COL_PCT_MOBILE : LABEL_COL_PCT_DESKTOP;
  const rows = data.chart.rows;
  const baseColor = data.chart.base_color || "#14b8a6";
  const planColor = data.chart.plan_color || "#fb923c";

  const built = useMemo(() => {
    if (!rows.length) return null;
    const isCovenant = data.chart.kind === "covenant_points";
    const n = rows.length;
    const distinctProjects = new Set(
      rows.map((row) => String(row.project || "").trim()).filter(Boolean),
    );
    const showProjectPrefix = distinctProjects.size > 1;
    const charsPerLine = fullscreen ? 52 : mobile ? 28 : 44;
    const taskNames = rows.map((row) => taskLabelOnly(row.label, row.project));
    const lineCounts = taskNames.map((name) =>
      wrapLineCount(name, charsPerLine, LABEL_MAX_LINES),
    );
    const maxNameLines = Math.max(1, ...lineCounts);
    const labelFont = fullscreen ? 12 : 10;
    const taskFont = fullscreen ? 13 : mobile ? 11 : 12;
    const nameBlockPx = Math.ceil(maxNameLines * taskFont * 1.3);
    const rowPx = Math.max(ROW_PX, (showProjectPrefix ? 20 : 8) + nameBlockPx);

    if (isCovenant) {
      const y = rows.map((_, i) => i);
      const mkScatter = (
        key: "base_start" | "base_end" | "plan_start" | "plan_end",
        name: string,
        color: string,
        symbol: string,
        textColor: string,
      ) => {
        const x = rows.map((row) => {
          const iso = row[key];
          return iso ? toMs(iso) : Number.NaN;
        });
        const text = rows.map((row) => {
          const iso = row[key];
          if (!iso) return "";
          const lbl =
            key === "base_start"
              ? row.base_start_label
              : key === "base_end"
                ? row.base_end_label
                : key === "plan_start"
                  ? row.plan_start_label
                  : row.plan_end_label;
          return fmtLabel(iso, lbl);
        });
        if (!x.some((v) => Number.isFinite(v))) return null;
        return {
          type: "scatter" as const,
          mode: "markers+text" as const,
          name,
          x,
          y,
          text,
          textposition: "top center" as const,
          textfont: { size: 9, color: textColor },
          cliponaxis: false,
          marker: {
            size: 11,
            color,
            symbol,
            line: { width: 1, color: "#fff" },
          },
          customdata: rows.map((row) => row.label),
          hovertemplate: `%{customdata}<br>${name}: %{text}<extra></extra>`,
        };
      };
      const traces = [
        mkScatter("base_start", "Базовое начало", "#3B82F6", "circle-open", "#93c5fd"),
        mkScatter("base_end", "Базовое окончание", "#14b8a6", "diamond", "#5eead4"),
        mkScatter("plan_start", "Начало", "#fb923c", "circle", "#fdba74"),
        mkScatter("plan_end", "Окончание", "#EF4444", "diamond-open", "#fca5a5"),
      ].filter(Boolean) as Array<Record<string, unknown>>;

      const xs = traces.flatMap((t) => (t.x as number[]).filter((v) => Number.isFinite(v)));
      if (!xs.length) return null;
      const xMin = Math.min(...xs) - 14 * DAY_MS;
      const xMax = Math.max(...xs) + 21 * DAY_MS;
      const shapes: Array<Record<string, unknown>> = [];
      for (let si = 0; si < n - 1; si += 1) {
        shapes.push({
          type: "line",
          xref: "paper",
          yref: "y",
          x0: 0,
          x1: 1,
          y0: si + 0.5,
          y1: si + 0.5,
          line: { color: "rgba(148,163,184,0.22)", width: 1, dash: "dot" },
        });
      }
      const plotHeight = Math.max(320, n * rowPx);
      const labelRowH = plotHeight / n;
      const chartHeight = plotHeight + MARGIN_TOP + MARGIN_BOTTOM;
      return {
        taskNames,
        taskFont,
        rowPx,
        labelRowH,
        showProjectPrefix,
        data: traces,
        layout: {
          height: chartHeight,
          autosize: true,
          margin: { l: 4, r: 96, t: MARGIN_TOP, b: MARGIN_BOTTOM },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          shapes,
          showlegend: true,
          legend: chartLegend(fullscreen),
          xaxis: {
            type: "date",
            tickformat: "%d.%m.%Y",
            range: [xMin, xMax],
            automargin: true,
            title: { text: "Дата", standoff: 12, font: { size: 12 } },
            gridcolor: "rgba(148,163,184,0.25)",
            zeroline: false,
          },
          yaxis: {
            autorange: "reversed",
            range: [-0.55, n - 0.45],
            tickmode: "array",
            tickvals: y,
            ticktext: rows.map(() => ""),
            showticklabels: false,
            zeroline: false,
            showgrid: false,
          },
        },
        chartHeight,
        plotHeight,
      };
    }

    const origins: number[] = [];
    rows.forEach((row) => {
      const be = toMs(row.base_end);
      const pe = toMs(row.plan_end);
      if (be != null) origins.push(be);
      if (pe != null) origins.push(pe);
    });
    if (!origins.length) return null;
    // Сдвиг начала шкалы влево: иначе самый ранний срок даёт длину 0 и столбец
    // пропадает при фильтре одного проекта (при «Все» origin обычно раньше).
    const minBarMs = DAY_MS;
    const originPadMs = 14 * DAY_MS;
    const originMs = Math.min(...origins) - originPadMs;

    const hasPlan = rows.some((row) => toMs(row.plan_end) != null);

    const baseY = rows.map((_, i) => i + laneOffset("base", hasPlan));
    const planY = rows.map((_, i) => i + laneOffset("plan", hasPlan));

    const baseLen = rows.map((row) => {
      const end = toMs(row.base_end);
      if (end == null) return Number.NaN;
      return Math.max(end - originMs, minBarMs);
    });
    const planLen = rows.map((row) => {
      const end = toMs(row.plan_end);
      if (end == null) return Number.NaN;
      return Math.max(end - originMs, minBarMs);
    });
    const baseBase = rows.map((row) => (toMs(row.base_end) == null ? Number.NaN : originMs));
    const planBase = rows.map((row) => (toMs(row.plan_end) == null ? Number.NaN : originMs));

    const baseTxt = rows.map((row) => {
      if (toMs(row.base_end) == null) return "";
      return fmtLabel(row.base_end, row.base_end_label);
    });
    const planTxt = rows.map((row) => {
      if (toMs(row.plan_end) == null) return "";
      return fmtLabel(row.plan_end, row.plan_end_label);
    });

    let xMax = originMs;
    baseLen.forEach((len, i) => {
      if (Number.isFinite(len) && Number.isFinite(baseBase[i])) {
        xMax = Math.max(xMax, baseBase[i] + len);
      }
    });
    planLen.forEach((len, i) => {
      if (Number.isFinite(len) && Number.isFinite(planBase[i])) {
        xMax = Math.max(xMax, planBase[i] + len);
      }
    });
    const xPad = 28 * DAY_MS;

    const traces: Array<Record<string, unknown>> = [
      {
        type: "bar",
        orientation: "h",
        name: CHART_RU.baseEnd,
        y: baseY,
        base: baseBase,
        x: baseLen,
        marker: { color: baseColor },
        width: BAR_WIDTH,
        text: baseTxt,
        textposition: "outside",
        textfont: { size: labelFont, color: baseColor, family: "Arial" },
        constraintext: "none",
        cliponaxis: false,
        hovertemplate: `%{customdata[0]}<br>${CHART_RU.baseEnd}: %{customdata[1]}<extra></extra>`,
        customdata: rows.map((row) => [
          row.label,
          fmtLabel(row.base_end, row.base_end_label) || "—",
        ]),
      },
      {
        type: "bar",
        orientation: "h",
        name: CHART_RU.planEnd,
        y: planY,
        base: planBase,
        x: planLen,
        marker: { color: planColor },
        width: BAR_WIDTH,
        text: planTxt,
        textposition: "outside",
        textfont: { size: labelFont, color: planColor, family: "Arial" },
        constraintext: "none",
        cliponaxis: false,
        hovertemplate: `%{customdata[0]}<br>${CHART_RU.planEnd}: %{customdata[1]}<extra></extra>`,
        customdata: rows.map((row) => [
          row.label,
          fmtLabel(row.plan_end, row.plan_end_label) || "—",
        ]),
      },
    ];

    const shapes = [];
    for (let si = 0; si < n - 1; si += 1) {
      shapes.push({
        type: "line",
        xref: "paper",
        yref: "y",
        x0: 0,
        x1: 1,
        y0: si + 0.5,
        y1: si + 0.5,
        line: { color: "rgba(148,163,184,0.22)", width: 1, dash: "dot" },
      });
    }

    const plotHeight = Math.max(280, n * rowPx);
    const labelRowH = plotHeight / n;
    const chartHeight = plotHeight + MARGIN_TOP + MARGIN_BOTTOM;

    return {
      taskNames,
      taskFont,
      rowPx,
      labelRowH,
      showProjectPrefix,
      data: traces,
      layout: {
        barmode: "overlay",
        bargap: 0.35,
        bargroupgap: 0.45,
        height: chartHeight,
        autosize: true,
        margin: { l: 4, r: 96, t: MARGIN_TOP, b: MARGIN_BOTTOM },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        shapes,
        showlegend: true,
        legend: chartLegend(fullscreen),
        xaxis: {
          type: "date",
          tickformat: "%d.%m.%Y",
          range: [originMs, xMax + xPad],
          automargin: true,
          title: {
            text: "Дата",
            standoff: 12,
            font: { size: 12 },
          },
          gridcolor: "rgba(148,163,184,0.25)",
          zeroline: false,
        },
        yaxis: {
          autorange: "reversed",
          range: [-0.55, n - 0.45],
          tickmode: "array",
          tickvals: rows.map((_, i) => i),
          ticktext: rows.map(() => ""),
          showticklabels: false,
          zeroline: false,
          showgrid: false,
        },
      },
      chartHeight,
      plotHeight,
    };
  }, [rows, baseColor, planColor, fullscreen, data.chart.kind, mobile]);

  if (!built) {
    return <DashboardEmptyState message="Нет задач для графика." />;
  }

  const visibleH = Math.min(
    built.chartHeight,
    SCROLL_VISIBLE_ROWS * (built.rowPx ?? ROW_PX) + MARGIN_TOP + MARGIN_BOTTOM,
  );
  const needScroll = built.chartHeight > visibleH + 8;
  const scrollH = fullscreen ? built.chartHeight : visibleH;

  return (
    <div className="space-y-2">
      <div
        className={needScroll && !fullscreen ? "overflow-auto" : undefined}
        style={needScroll && !fullscreen ? { maxHeight: scrollH } : undefined}
      >
        <div
          className="flex w-full"
          style={{ minHeight: built.plotHeight + MARGIN_TOP + MARGIN_BOTTOM }}
        >
          <div
            className="shrink-0 border-r border-tremor-border pr-2 dark:border-dark-tremor-border"
            style={{
              width: `${labelColPct}%`,
              paddingTop: MARGIN_TOP,
              paddingBottom: MARGIN_BOTTOM,
              paddingLeft: fullscreen ? 12 : 4,
            }}
          >
            {built.taskNames.map((name, i) => (
              <div
                key={`${rows[i]?.label}-${i}`}
                className="flex items-center border-b border-dashed border-slate-200/80 dark:border-slate-600/50"
                style={{ height: built.labelRowH ?? built.rowPx ?? ROW_PX }}
              >
                <div className="min-w-0 w-full py-0.5 pr-1">
                  {built.showProjectPrefix && rows[i]?.project ? (
                    <div className="mb-0.5 truncate text-[10px] font-semibold uppercase tracking-wide text-teal-700 dark:text-teal-300">
                      {rows[i].project}
                    </div>
                  ) : null}
                  <span
                    className="block break-words text-tremor-content-strong dark:text-dark-tremor-content-strong"
                    style={{
                      fontSize: built.taskFont,
                      lineHeight: 1.3,
                      display: "-webkit-box",
                      WebkitBoxOrient: "vertical" as const,
                      WebkitLineClamp: LABEL_MAX_LINES,
                      overflow: "hidden",
                    }}
                    title={
                      rows[i]?.project
                        ? `${rows[i].project}: ${name}`
                        : name
                    }
                  >
                    {name}
                  </span>
                </div>
              </div>
            ))}
          </div>
          <div className="min-w-0 flex-1" style={{ width: `${100 - labelColPct}%` }}>
            <PlotlyFigure
              data={built.data as never}
              layout={built.layout as never}
              config={{
                ...PLOTLY_CONFIG,
                scrollZoom: false,
              }}
              style={{ width: "100%", height: built.chartHeight }}
              useResizeHandler
            />
          </div>
        </div>
      </div>
      {data.chart.caption ? (
        <Text className="text-xs text-tremor-content dark:text-dark-tremor-content">
          {data.chart.caption}
          {data.chart.capped ? " · график ограничен 400 строками" : ""}
        </Text>
      ) : null}
    </div>
  );
}
