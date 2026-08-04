"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { Text } from "@tremor/react";
import type { ProjectSchedulePayload } from "@/lib/api";
import { PLOTLY_CONFIG } from "@/lib/plotly-config";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Загрузка диаграммы…
    </div>
  ),
});

const PLAN = "#14b8a6";
const FACT = "#fb923c";
const SCROLL_VISIBLE_ROWS = 18;
const ROW_PX = 48;
const BAR_WIDTH = 0.12;
const LANE_GAP = 0.03;
/** Верх/низ как у Plotly margin — чтобы строки совпали с полосами. */
const MARGIN_TOP = 20;
const MARGIN_BOTTOM = 64;
const DAY_MS = 24 * 3600 * 1000;
/** Отступ подписи даты от ромба (desktop ковенанты). */
const COVENANT_LABEL_GAP_MS = 14 * DAY_MS;
/** Колонка имён ≈ 1/4 (линии шире ~3×). */
const LABEL_COL_PCT = 24;

function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

/** Перенос в ≤2 строки для HTML-колонки имён. */
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

function laneOffset(lane: "plan" | "fact", hasFact: boolean): number {
  if (!hasFact) return 0;
  const idx = lane === "plan" ? 0 : 1;
  return (idx - 0.5) * (BAR_WIDTH + LANE_GAP) * 2;
}

function sameDay(
  a: string | null | undefined,
  b: string | null | undefined,
): boolean {
  if (!a || !b) return false;
  return a.slice(0, 10) === b.slice(0, 10);
}

function useCompactViewport() {
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const sync = () => setCompact(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return compact;
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
  const compact = useCompactViewport();
  const showAxisDateLabels = fullscreen || !compact;

  const built = useMemo(() => {
    if (!rows.length) return null;

    const labelLines = rows.map((row) =>
      wrapTaskLabelLines(row.label, fullscreen ? 34 : 28, 2),
    );
    const n = rows.length;
    const hasFact = true;
    const taskFont = fullscreen ? 13 : 11;
    const labelFont = fullscreen ? 12 : 11;

    const planY = rows.map((_, i) => i + laneOffset("plan", hasFact && !labelPct && !covenantMode));
    const factY = rows.map((_, i) => i + laneOffset("fact", hasFact));

    const traces: Array<Record<string, unknown>> = [];

    if (covenantMode) {
      // Main `_build_covenants_points_figure`: ромбы план/факт по дате окончания.
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
          size: 11,
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
          size: 11,
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

      rows.forEach((row, i) => {
        const pe = toMs(row.baseline.end);
        const fe = toMs(row.current.end);
        const planLeft = pe != null && fe != null ? pe <= fe : true;
        if (showAxisDateLabels && pe != null && row.baseline.end_label) {
          traces.push({
            type: "scatter",
            mode: "text",
            x: [planLeft ? pe - COVENANT_LABEL_GAP_MS : pe + COVENANT_LABEL_GAP_MS],
            y: [i],
            text: [planLeft ? `${row.baseline.end_label}\u00a0` : `\u00a0${row.baseline.end_label}`],
            textposition: planLeft ? "middle left" : "middle right",
            textfont: { size: labelFont, color: planColor, family: "Arial" },
            hoverinfo: "skip",
            showlegend: false,
            cliponaxis: false,
          });
        }
        if (showAxisDateLabels && fe != null && row.current.end_label) {
          const factLeft = pe != null && fe != null ? fe < pe : false;
          traces.push({
            type: "scatter",
            mode: "text",
            x: [factLeft ? fe - COVENANT_LABEL_GAP_MS : fe + COVENANT_LABEL_GAP_MS],
            y: [i],
            text: [factLeft ? `${row.current.end_label}\u00a0` : `\u00a0${row.current.end_label}`],
            textposition: factLeft ? "middle left" : "middle right",
            textfont: { size: labelFont, color: factColor, family: "Arial" },
            hoverinfo: "skip",
            showlegend: false,
            cliponaxis: false,
          });
        }
      });
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
          width: BAR_WIDTH,
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
        width: BAR_WIDTH,
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

      type EdgeBucket = { x: number[]; y: number[]; text: string[] };
      const buckets: Record<string, EdgeBucket> = {};
      const pushEdge = (
        key: string,
        x: number | null,
        y: number,
        text: string,
      ) => {
        if (!showAxisDateLabels || x == null || !text) return;
        if (!buckets[key]) buckets[key] = { x: [], y: [], text: [] };
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

        if (!labelPct) {
          pushEdge("plan|start", ps, py, row.baseline.start_label || "");
          pushEdge("plan|end", pe, py, row.baseline.end_label || "");
        }
        if (!sameDay(row.current.start, row.baseline.start) || labelPct) {
          pushEdge("fact|start", fs, fy, row.current.start_label || "");
        }
        if (!sameDay(row.current.end, row.baseline.end) || labelPct) {
          pushEdge("fact|end", fe, fy, row.current.end_label || "");
        }
        if (labelPct && row.pct_complete != null && fe != null) {
          pushEdge("fact|pct", fe, fy, `${row.pct_complete}%`);
        }
      });

      (Object.entries(buckets) as Array<[string, EdgeBucket]>).forEach(([key, bucket]) => {
        if (!bucket.x.length) return;
        const [, edge] = key.split("|");
        const color = key.startsWith("fact") ? factColor : planColor;
        traces.push({
          type: "scatter",
          mode: "text",
          x: bucket.x,
          y: bucket.y,
          text: bucket.text,
          textposition: edge === "end" || edge === "pct" ? "middle right" : "middle left",
          textfont: { size: labelFont, color, family: "Arial" },
          hoverinfo: "skip",
          showlegend: false,
          cliponaxis: true,
        });
      });
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
    const xRange =
      lo != null && hi != null
        ? [lo - Math.max(45 * DAY_MS, span * 0.08), hi + Math.max(30 * DAY_MS, span * 0.06)]
        : undefined;

    const plotHeight = Math.max(280, n * ROW_PX);
    const chartHeight = plotHeight + MARGIN_TOP + MARGIN_BOTTOM;
    const lanePad = 0.4;

    return {
      labelLines,
      taskFont,
      data: traces,
      layout: {
        barmode: "overlay",
        bargap: 0.78,
        bargroupgap: LANE_GAP,
        height: chartHeight,
        autosize: true,
        margin: { l: 8, r: 40, t: MARGIN_TOP, b: MARGIN_BOTTOM },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        showlegend: false,
        hovermode: false,
        dragmode: "zoom",
        xaxis: {
          type: "date",
          title: { text: "Период", standoff: 8 },
          range: xRange,
          tickformat: "%d-%m-%y",
          tickangle: -35,
          showgrid: true,
          gridcolor: "rgba(148,163,184,0.25)",
          automargin: false,
          fixedrange: false,
          domain: [0, 1],
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
        font: { color: "#94a3b8", size: taskFont },
      },
      config: {
        ...PLOTLY_CONFIG,
        scrollZoom: false,
      },
      chartHeight,
      plotHeight,
      viewportHeight: Math.min(
        chartHeight,
        Math.min(n, SCROLL_VISIBLE_ROWS) * ROW_PX + MARGIN_TOP + MARGIN_BOTTOM,
      ),
    };
  }, [
    rows,
    planColor,
    factColor,
    labelPct,
    covenantMode,
    compact,
    showAxisDateLabels,
    fullscreen,
    data.gantt.range_start,
    data.gantt.range_end,
  ]);

  if (!built) {
    return (
      <div className="py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет задач для отображения на ганте.
      </div>
    );
  }

  const viewportMax = fullscreen
    ? "calc(100vh - 96px)"
    : `${built.viewportHeight}px`;

  return (
    <div className="w-full min-w-0">
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
      {compact && !fullscreen ? (
        <Text className="mb-2 text-[11px] text-tremor-content dark:text-dark-tremor-content">
          На телефоне даты у точек скрыты — смотрите подсказку по ромбу и карточки таблицы.
        </Text>
      ) : null}
      <div
        className="gantt-schedule-scroll-wrap overflow-y-auto overflow-x-hidden rounded-md border border-tremor-border dark:border-dark-tremor-border"
        style={{ maxHeight: viewportMax }}
      >
        <div className="flex w-full" style={{ minHeight: built.chartHeight }}>
          {/* Имена: отдельная колонка, прижаты к левому краю — без пересечения с линиями. */}
          <div
            className="shrink-0 border-r border-tremor-border dark:border-dark-tremor-border"
            style={{
              width: `${LABEL_COL_PCT}%`,
              paddingTop: MARGIN_TOP,
              paddingBottom: MARGIN_BOTTOM,
            }}
          >
            {built.labelLines.map((lines, i) => (
              <div
                key={`${rows[i]?.label ?? i}-${i}`}
                className="flex items-center justify-start overflow-hidden px-2 text-left leading-tight text-tremor-content dark:text-dark-tremor-content"
                style={{
                  height: ROW_PX,
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
              </div>
            ))}
          </div>
          <div className="min-w-0 flex-1" style={{ width: `${100 - LABEL_COL_PCT}%` }}>
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
    </div>
  );
}
