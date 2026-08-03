"use client";

import dynamic from "next/dynamic";
import { useMemo } from "react";
import { Text } from "@tremor/react";
import type { BaselineDeviationPayload } from "@/lib/api";
import { CHART_RU } from "@/lib/chart-ru";
import { PLOTLY_CONFIG } from "@/lib/plotly-config";

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
const MARGIN_TOP = 12;
const MARGIN_BOTTOM = 72;
const DAY_MS = 24 * 3600 * 1000;
const LABEL_COL_PCT = 28;

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

function wrapTaskLabelLines(name: string, widthChars = 30, maxLines = 2): string[] {
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
  return lines.slice(0, maxLines);
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
  const rows = data.chart.rows;
  const baseColor = data.chart.base_color || "#14b8a6";
  const planColor = data.chart.plan_color || "#fb923c";

  const built = useMemo(() => {
    if (!rows.length) return null;

    const origins: number[] = [];
    rows.forEach((row) => {
      const be = toMs(row.base_end);
      const pe = toMs(row.plan_end);
      if (be != null) origins.push(be);
      if (pe != null) origins.push(pe);
    });
    if (!origins.length) return null;
    const originMs = Math.min(...origins);

    const labelLines = rows.map((row) =>
      wrapTaskLabelLines(row.label, fullscreen ? 36 : 30, 2),
    );
    const n = rows.length;
    const hasPlan = rows.some((row) => toMs(row.plan_end) != null);
    const labelFont = fullscreen ? 12 : 10;
    const taskFont = fullscreen ? 13 : 11;

    const baseY = rows.map((_, i) => i + laneOffset("base", hasPlan));
    const planY = rows.map((_, i) => i + laneOffset("plan", hasPlan));

    const baseLen = rows.map((row) => {
      const end = toMs(row.base_end);
      return end == null ? Number.NaN : Math.max(end - originMs, 0);
    });
    const planLen = rows.map((row) => {
      const end = toMs(row.plan_end);
      return end == null ? Number.NaN : Math.max(end - originMs, 0);
    });
    const baseBase = rows.map((row) => (toMs(row.base_end) == null ? Number.NaN : originMs));
    const planBase = rows.map((row) => (toMs(row.plan_end) == null ? Number.NaN : originMs));

    const minBarMs = 0.5 * DAY_MS;
    const baseTxt = rows.map((row, i) => {
      const len = baseLen[i];
      if (!Number.isFinite(len) || len < minBarMs) return "";
      return fmtLabel(row.base_end, row.base_end_label);
    });
    const planTxt = rows.map((row, i) => {
      const len = planLen[i];
      if (!Number.isFinite(len) || len < minBarMs) return "";
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

    const plotHeight = Math.max(280, n * ROW_PX);
    const chartHeight = plotHeight + MARGIN_TOP + MARGIN_BOTTOM;

    return {
      labelLines,
      taskFont,
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
        legend: {
          orientation: "h",
          yanchor: "top",
          y: -0.08,
          xanchor: "center",
          x: 0.5,
          font: { size: fullscreen ? 13 : 11 },
        },
        xaxis: {
          type: "date",
          tickformat: "%d.%m.%Y",
          range: [originMs, xMax + xPad],
          automargin: true,
          title: {
            text: "Дата (от начала шкалы до окончания)",
            standoff: 18,
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
  }, [rows, baseColor, planColor, fullscreen]);

  if (!built) {
    return (
      <div className="py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет задач для графика.
      </div>
    );
  }

  const visibleH = Math.min(
    built.chartHeight,
    SCROLL_VISIBLE_ROWS * ROW_PX + MARGIN_TOP + MARGIN_BOTTOM,
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
              width: `${LABEL_COL_PCT}%`,
              paddingTop: MARGIN_TOP,
              paddingBottom: MARGIN_BOTTOM,
            }}
          >
            {built.labelLines.map((lines, i) => (
              <div
                key={`${rows[i]?.label}-${i}`}
                className="flex items-center"
                style={{ height: ROW_PX }}
              >
                <span
                  className="line-clamp-2 text-tremor-content-strong dark:text-dark-tremor-content-strong"
                  style={{ fontSize: built.taskFont, lineHeight: 1.25 }}
                  title={rows[i]?.label}
                >
                  {lines.join(" ")}
                </span>
              </div>
            ))}
          </div>
          <div className="min-w-0 flex-1" style={{ width: `${100 - LABEL_COL_PCT}%` }}>
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
