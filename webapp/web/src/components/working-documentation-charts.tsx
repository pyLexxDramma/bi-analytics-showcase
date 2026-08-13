"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { WorkingDocumentationPayload } from "@/lib/api";
import { ChartHtmlLegend } from "@/components/chart-html-legend";
import { stripProjectPrefixIfSingle, uniquePlotCategories } from "@/lib/chart-labels";
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

const RD_PLAN = "#2E86AB";
const RD_FACT = "#F39C12";
const RD_FCST = "#9B59B6";
const RD_MONTH_PLAN = "#F39C12";
const RD_MONTH_FACT = "#27AE60";
const RD_MONTH_OVERDUE = "#C0392B";

const RD_PIE_COLORS: Record<string, string> = {
  "Выдано в производство работ": "#27AE60",
  "На рассмотрении у ГИП": "#F1C40F",
  "Возвращено на доработку": "#C0392B",
  "Не выдано": "#F5A9C0",
};

const DAY_MS = 86_400_000;
const RD_GANTT_YELLOW = "#F1C40F";
const RD_GANTT_GREEN = "#27AE60";
const RD_GANTT_RED = "#C0392B";

type StatusMix = WorkingDocumentationPayload["tremor"]["status_mix"][number];
type DynamicsRow = WorkingDocumentationPayload["tremor"]["dynamics"][number];
type MonthlyRow = WorkingDocumentationPayload["tremor"]["monthly"][number];
type GanttRow = WorkingDocumentationPayload["delay"]["gantt"]["rows"][number];

function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function barLenMs(startIso: string | null | undefined, endIso: string | null | undefined): number | null {
  const s = toMs(startIso);
  const e = toMs(endIso);
  if (s == null || e == null || e < s) return null;
  const ms = e - s;
  return ms > 0 ? ms : DAY_MS;
}

function useChartTheme() {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setDark(root.classList.contains("dark"));
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return {
    dark,
    axis: dark ? "#cbd5e1" : "#334155",
    label: dark ? "#e8eef5" : "#111827",
    paper: "rgba(0,0,0,0)",
    plot: "rgba(0,0,0,0)",
    grid: dark ? "rgba(148,163,184,0.22)" : "rgba(148,163,184,0.35)",
  };
}

function pointLabel(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v) || v === 0) return "";
  return String(Math.round(v));
}

function pieColor(name: string, fallback?: string, index = 0): string {
  if (fallback) return fallback;
  for (const [key, color] of Object.entries(RD_PIE_COLORS)) {
    if (name.includes(key.slice(0, 12)) || name === key) return color;
  }
  if (name.includes("производств")) return "#27AE60";
  if (name.includes("рассмотр") || name.includes("ГИП")) return "#F1C40F";
  if (name.includes("доработ")) return "#C0392B";
  if (name.includes("Не выдан")) return "#F5A9C0";
  return ["#27AE60", "#F1C40F", "#C0392B", "#F5A9C0"][index % 4];
}

/** Pie «Исполнение РД» как main Plotly (hole=0, %). */
export function RdExecutionPieChart({
  rows,
  fullscreen = false,
}: {
  rows: StatusMix[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const height = fullscreen
      ? Math.max(520, Math.min(window.innerHeight * 0.6, 720))
      : 420;
    const labels = rows.map((r) => r.name);
    const values = rows.map((r) => r.value);
    const colors = rows.map((r, i) => pieColor(r.name, r.color, i));
    return {
      data: [
        {
          type: "pie" as const,
          labels,
          values,
          sort: false,
          direction: "clockwise" as const,
          hole: 0,
          marker: { colors, line: { color: "#fff", width: 1 } },
          textinfo: "percent" as const,
          textposition: "inside" as const,
          insidetextorientation: "horizontal" as const,
          textfont: { size: fullscreen ? 18 : 15, color: "#ffffff" },
          hovertemplate:
            "<b>%{label}</b><br>Количество: %{value}<br>Доля: %{percent}<extra></extra>",
          showlegend: false,
        },
      ],
      layout: {
        height,
        margin: { l: 8, r: 8, t: 8, b: 8 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        showlegend: false,
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG, scrollZoom: false },
    };
  }, [rows, fullscreen, theme]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет данных по исполнению.
      </div>
    );
  }

  return (
    <PlotlyFigure
      data={figure.data}
      layout={figure.layout}
      config={figure.config}
      useResizeHandler
      style={{ width: "100%", height: "100%" }}
    />
  );
}

/** Line «Динамика выдачи РД»: lines+markers+text, План #2E86AB / Факт #F39C12. */
export function RdDynamicsLineChart({
  rows,
  fullscreen = false,
  showForecast = true,
}: {
  rows: DynamicsRow[];
  fullscreen?: boolean;
  showForecast?: boolean;
}) {
  const theme = useChartTheme();
  const mobile = useIsMobileViewport();
  const compact = mobile && !fullscreen;
  const figure = useMemo(() => {
    const height = fullscreen
      ? Math.max(520, Math.min(window.innerHeight * 0.62, 760))
      : compact
        ? 360
        : 420;
    const x = rows.map((r) => r.period_label || r.period);
    const plan = rows.map((r) => r.plan);
    const fact = rows.map((r) => r.fact);
    const forecast = rows.map((r) =>
      r.forecast == null || Number.isNaN(Number(r.forecast))
        ? null
        : Number(r.forecast),
    );
    const hasForecast =
      showForecast && forecast.some((v) => v != null && Number.isFinite(v));
    const yMax = Math.max(
      1,
      ...plan,
      ...fact,
      ...forecast.map((v) => (v == null ? 0 : v)),
    );
    const yHead = Math.max(yMax * (compact ? 0.08 : 0.1), 4);
    // Прореживание подписей оси X как main (~≤12 тиков), без наложения месяцев.
    const tickStep = Math.max(1, Math.ceil(x.length / (compact ? 8 : 12)));
    const tickvals: string[] = [];
    const ticktext: string[] = [];
    for (let i = 0; i < x.length; i += tickStep) {
      tickvals.push(x[i]);
      ticktext.push(x[i]);
    }
    if (x.length && tickvals[tickvals.length - 1] !== x[x.length - 1]) {
      tickvals.push(x[x.length - 1]);
      ticktext.push(x[x.length - 1]);
    }
    /** Mobile: без text на точках — иначе плато и легенда сверху слипаются. */
    const mk = (
      y: Array<number | null>,
      name: string,
      color: string,
      opts?: { dash?: string; width?: number },
    ): Record<string, unknown> => ({
      type: "scatter",
      mode: compact ? "lines+markers" : "lines+markers+text",
      name,
      x,
      y,
      connectgaps: false,
      ...(compact
        ? {}
        : {
            text: y.map((v) => (v == null ? "" : pointLabel(v))),
            textposition: "top center",
            textfont: { color, size: 10 },
          }),
      line: {
        color,
        width: opts?.width ?? 2.5,
        ...(opts?.dash ? { dash: opts.dash } : {}),
      },
      marker: { size: compact ? 7 : 8, color, line: { width: 1, color: "#fff" } },
      cliponaxis: false,
      hovertemplate: `<b>%{x}</b><br>${name}: %{y}<extra></extra>`,
    });
    const data: Array<Record<string, unknown>> = [
      mk(plan, CHART_RU.plan, RD_PLAN),
      mk(fact, CHART_RU.fact, RD_FACT),
    ];
    if (hasForecast) {
      data.push(
        mk(forecast, CHART_RU.forecastRd, RD_FCST, {
          dash: "dash",
          width: 2.8,
        }),
      );
    }
    return {
      data,
      layout: {
        height,
        margin: compact
          ? { l: 44, r: 16, t: 24, b: 72 }
          : { l: 56, r: 28, t: 40, b: 80 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        hovermode: false as const,
        showlegend: false,
        xaxis: {
          title: {
            text: compact ? "" : "Период",
            standoff: 14,
            font: { size: 12, color: theme.axis },
          },
          tickmode: "array" as const,
          tickvals,
          ticktext,
          tickangle: -35,
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          gridcolor: theme.grid,
          automargin: true,
        },
        yaxis: {
          title: {
            text: compact ? "Разделы РД" : "Количество разделов РД",
            font: { size: compact ? 11 : 12, color: theme.axis },
          },
          tickfont: { size: 10, color: theme.axis },
          gridcolor: theme.grid,
          zeroline: false,
          range: [0, yMax + yHead],
        },
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG },
      legendItems: [
        { name: CHART_RU.plan, color: RD_PLAN },
        { name: CHART_RU.fact, color: RD_FACT },
        ...(hasForecast
          ? [{ name: CHART_RU.forecastRd, color: RD_FCST }]
          : []),
      ],
    };
  }, [rows, fullscreen, theme, compact, showForecast]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет точек динамики.
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <PlotlyFigure
        data={figure.data}
        layout={figure.layout}
        config={figure.config}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
      <ChartHtmlLegend items={figure.legendItems} compact={compact} />
    </div>
  );
}

/** Накопительный стек «Динамика по месяцам»: выполнено / просрочено / остаток плана. */
export function RdMonthlyCumulativeChart({
  rows,
  fullscreen = false,
}: {
  rows: MonthlyRow[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const mobile = useIsMobileViewport();
  const compact = mobile && !fullscreen;
  const figure = useMemo(() => {
    const chronological = [...rows].sort((a, b) => a.month.localeCompare(b.month));
    const labels = chronological.map((r) => r.month_label);
    const plan = chronological.map((r) => Number(r.plan) || 0);
    const overdue = chronological.map((r) => Math.max(0, Number(r.overdue) || 0));
    const done = chronological.map((r, i) => {
      if (r.done != null) return Math.max(0, Number(r.done) || 0);
      const fact = Math.max(0, Number(r.fact) || 0);
      return Math.max(0, fact - overdue[i]);
    });
    const rest = chronological.map((r, i) => {
      if (r.rest != null) return Math.max(0, Number(r.rest) || 0);
      return Math.max(0, plan[i] - done[i] - overdue[i]);
    });
    // delta: выдано − план_к_дате (≥0 зелёный / <0 красный просрок)
    const deltas = chronological.map((r, i) => {
      if (r.delta != null && Number.isFinite(Number(r.delta))) return Number(r.delta);
      return -overdue[i];
    });
    const yIdx = chronological.map((_, i) => i);
    const totals = done.map((d, i) => d + overdue[i] + rest[i]);
    const xMax = Math.max(1, ...plan, ...totals);
    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.55, 680))
      : Math.max(compact ? 360 : 320, (compact ? 72 : 56) + chronological.length * (compact ? 52 : 48));

    const barBase = {
      type: "bar" as const,
      orientation: "h" as const,
      y: yIdx,
      cliponaxis: false,
      constraintext: "none" as const,
      hovertemplate: "<b>%{customdata}</b><br>%{fullData.name}: %{x}<extra></extra>",
      textposition: "none" as const,
    };

    const annotations = chronological
      .map((_, i) => {
        const d = Math.round(deltas[i]);
        const total = totals[i];
        if (total <= 0) return null;
        const label = d > 0 ? `+${d}` : `${d}`;
        return {
          x: total,
          y: i,
          xref: "x" as const,
          yref: "y" as const,
          text: `<b>${label}</b>`,
          showarrow: false,
          xanchor: "left" as const,
          yanchor: "middle" as const,
          xshift: compact ? 4 : 8,
          font: {
            size: compact ? 11 : 14,
            color: d < 0 ? RD_MONTH_OVERDUE : "#15803d",
          },
        };
      })
      .filter(Boolean);

    return {
      data: [
        {
          ...barBase,
          name: "Выполнено",
          x: done,
          marker: { color: RD_MONTH_FACT, opacity: 0.95 },
          customdata: labels,
        },
        {
          ...barBase,
          name: CHART_RU.overdue,
          x: overdue,
          marker: { color: RD_MONTH_OVERDUE, opacity: 0.95 },
          customdata: labels,
        },
        {
          ...barBase,
          name: "План (остаток)",
          x: rest,
          marker: { color: RD_MONTH_PLAN, opacity: 0.92 },
          customdata: labels,
        },
      ],
      layout: {
        height,
        barmode: "stack" as const,
        bargap: 0.28,
        margin: compact
          ? { l: 8, r: 52, t: 12, b: 96 }
          : { l: 16, r: 64, t: 48, b: 96 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        legend: plotlyLegendUnderLeft({
          fontSize: compact ? 11 : 12,
          labelColor: theme.axis,
          y: compact ? -0.28 : -0.12,
        }),
        annotations,
        xaxis: {
          title: {
            text: compact ? "" : "Количество разделов (накопительно)",
            font: { size: 12, color: theme.axis },
          },
          range: [0, xMax * (compact ? 1.28 : 1.16)],
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          gridcolor: theme.grid,
          zeroline: false,
          nticks: compact ? 5 : undefined,
        },
        yaxis: {
          title: {
            text: compact ? "" : "Месяц",
            font: { size: 12, color: theme.axis },
          },
          tickmode: "array" as const,
          tickvals: yIdx,
          ticktext: labels,
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          automargin: true,
        },
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG },
    };
  }, [rows, fullscreen, theme, compact]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет помесячных данных.
      </div>
    );
  }

  return (
    <div className="min-w-0 overflow-x-hidden">
      <PlotlyFigure
        data={figure.data}
        layout={figure.layout}
        config={figure.config}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
    </div>
  );
}

/** Gantt «Просрочка выдачи РД» — Plotly как PD, легенда РД + «N дн.» на красном. */
export function RdDelayGanttChart({
  rows,
  rangeStart,
  rangeEnd,
  fullscreen = false,
  hideProjectPrefix = false,
}: {
  rows: GanttRow[];
  rangeStart: string | null;
  rangeEnd: string | null;
  fullscreen?: boolean;
  /** Один проект в фильтре — без префикса «Проект | ». */
  hideProjectPrefix?: boolean;
}) {
  const theme = useChartTheme();
  const mobile = useIsMobileViewport();
  const compact = mobile && !fullscreen;
  const figure = useMemo(() => {
    const sorted = [...rows].sort((a, b) => (b.delay_dur || 0) - (a.delay_dur || 0));
    const displayLabels = sorted.map((r) =>
      stripProjectPrefixIfSingle(r.label, hideProjectPrefix),
    );
    const { keys: yLabels, texts: yTickTexts } = uniquePlotCategories(displayLabels);
    const categoryOrder = [...yLabels].reverse();

    const yellowY: string[] = [];
    const yellowBase: number[] = [];
    const yellowLen: number[] = [];
    const yellowCd: string[] = [];
    const greenY: string[] = [];
    const greenBase: number[] = [];
    const greenLen: number[] = [];
    const greenCd: string[] = [];
    const redY: string[] = [];
    const redBase: number[] = [];
    const redLen: number[] = [];
    const redCd: string[] = [];
    const arrowY: string[] = [];
    const arrowX: number[] = [];
    const arrowCd: string[] = [];
    const annotations: Array<Record<string, unknown>> = [];
    const labelFont = compact ? 9 : 10;
    const dateLabelFont = Math.max(11, Math.round(labelFont * 1.5));
    const minLabelGapDays = compact ? 55 : 12;

    for (let i = 0; i < sorted.length; i++) {
      const row = sorted[i];
      const y = yLabels[i];
      const startMs = toMs(row.start);
      const bfMs = toMs(row.base_finish);
      const finMs = toMs(row.finish);
      const delayEndMs = toMs(row.delay_end);
      const lateComplete =
        Boolean(row.late_complete) ||
        (Boolean(row.finish) &&
          Boolean(row.delay_end) &&
          row.finish === row.delay_end &&
          (row.fact_dur || 0) <= 0 &&
          (row.delay_dur || 0) > 0);
      const hasRed = (row.delay_dur || 0) > 0 && delayEndMs != null && bfMs != null;
      // Зелёная полоса только при выдаче в срок/раньше (не при late-complete).
      const hasGreen =
        (row.fact_dur || 0) > 0 && Boolean(row.finish) && !row.delay_end && startMs != null;

      const yLen = barLenMs(row.start, row.base_finish);
      if (yLen != null && startMs != null) {
        yellowY.push(y);
        yellowBase.push(startMs);
        yellowLen.push(yLen);
        yellowCd.push(row.base_label || "");
      }

      if (hasGreen) {
        const gLen = barLenMs(row.start, row.finish);
        if (gLen != null && startMs != null) {
          greenY.push(y);
          greenBase.push(startMs);
          greenLen.push(gLen);
          greenCd.push(row.fact_label || row.base_label || "");
        }
      }

      if (hasRed && bfMs != null) {
        const rLen = barLenMs(row.base_finish, row.delay_end);
        if (rLen != null) {
          redY.push(y);
          redBase.push(bfMs);
          redLen.push(rLen);
          redCd.push(row.delay_label || "");
        }
      }

      const arrowMs = lateComplete ? finMs ?? delayEndMs : null;
      if (arrowMs != null) {
        arrowY.push(y);
        arrowX.push(arrowMs);
        arrowCd.push(
          row.delay_label
            ? `Выдано с опозданием: ${row.delay_label}`
            : "Выдано с опозданием",
        );
      }

      const labelColor = theme.dark ? "#e2e8f0" : "#1a1a1a";
      const annBase = {
        y,
        showarrow: false,
        yanchor: "middle" as const,
        font: { size: dateLabelFont, color: labelColor },
      };
      const placedXs: number[] = [];
      const farEnough = (ms: number) =>
        placedXs.every((p) => Math.abs(ms - p) / DAY_MS >= minLabelGapDays);
      const place = (ms: number, text: string, xanchor: "left" | "right", xshift: number) => {
        if (!text || !farEnough(ms)) return;
        placedXs.push(ms);
        annotations.push({
          ...annBase,
          x: ms,
          text,
          xanchor,
          xshift,
        });
      };

      // По окончанию каждого цвета — дата (референс).
      if (compact) {
        if (hasRed && row.delay_label && delayEndMs != null) {
          place(delayEndMs, row.delay_label, "left", lateComplete ? 18 : 6);
        } else if (hasGreen && row.fact_label && finMs != null) {
          place(finMs, row.fact_label, "left", 6);
        } else if (row.base_label && bfMs != null) {
          place(bfMs, row.base_label, "left", 6);
        }
      } else if (hasRed) {
        if (row.base_label && bfMs != null) {
          place(bfMs, row.base_label, "right", -6);
        }
        if (delayEndMs != null) {
          const tip =
            row.delay_label ||
            ((row.delay_dur || 0) > 0 ? `${Math.round(row.delay_dur)} дн.` : "");
          place(delayEndMs, tip, "left", lateComplete ? 20 : 8);
        }
      } else if (hasGreen && finMs != null) {
        const ahead = bfMs != null && finMs < bfMs - DAY_MS;
        if (ahead) {
          if (row.fact_label) place(finMs, row.fact_label, "right", -4);
          if (row.base_label && bfMs != null) place(bfMs, row.base_label, "left", 6);
        } else {
          place(finMs, row.fact_label || row.base_label || "", "left", 6);
        }
      } else if (row.base_label && bfMs != null) {
        place(bfMs, row.base_label, "left", 6);
      }
    }

    const data: Array<Record<string, unknown>> = [];
    if (yellowY.length) {
      data.push({
        type: "bar",
        orientation: "h",
        name: compact ? "Договор" : "Дата по договору",
        y: yellowY,
        x: yellowLen,
        base: yellowBase,
        marker: { color: RD_GANTT_YELLOW },
        width: 0.48,
        customdata: yellowCd,
        hovertemplate: "%{y}<br>Дата по договору: %{customdata}<extra></extra>",
      });
    }
    if (greenY.length) {
      data.push({
        type: "bar",
        orientation: "h",
        name: compact ? "Выдано" : "Выдано в производство",
        y: greenY,
        x: greenLen,
        base: greenBase,
        marker: { color: RD_GANTT_GREEN },
        width: 0.48,
        customdata: greenCd,
        hovertemplate: "%{y}<br>Выдано: %{customdata}<extra></extra>",
      });
    }
    if (redY.length) {
      data.push({
        type: "bar",
        orientation: "h",
        name: "Просрочка",
        y: redY,
        x: redLen,
        base: redBase,
        marker: { color: RD_GANTT_RED },
        width: 0.48,
        customdata: redCd,
        hovertemplate: "%{y}<br>Просрочка до %{customdata}<extra></extra>",
      });
    }
    if (arrowY.length) {
      data.push({
        type: "scatter",
        mode: "markers",
        name: "Выдано с опозданием",
        y: arrowY,
        x: arrowX,
        marker: {
          symbol: "triangle-right",
          size: compact ? 14 : 16,
          color: RD_GANTT_GREEN,
          line: { width: 1, color: "#1e8449" },
        },
        customdata: arrowCd,
        hovertemplate: "%{y}<br>%{customdata}<extra></extra>",
        cliponaxis: false,
      });
    }

    const xs: number[] = [];
    for (const row of sorted) {
      for (const v of [row.start, row.base_finish, row.finish, row.delay_end]) {
        const ms = toMs(v);
        if (ms != null) xs.push(ms);
      }
    }
    const rangeLo = rangeStart ? toMs(rangeStart) : xs.length ? Math.min(...xs) : null;
    const rangeHi = rangeEnd ? toMs(rangeEnd) : xs.length ? Math.max(...xs) : null;
    let xRange: [number, number] | undefined;
    if (rangeLo != null && rangeHi != null) {
      const pad = Math.max((rangeHi - rangeLo) * (compact ? 0.12 : 0.08), 6 * DAY_MS);
      xRange = [rangeLo - pad, rangeHi + pad];
    }

    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.62, 780))
      : Math.max(compact ? 320 : 280, (compact ? 160 : 120) + sorted.length * (compact ? 48 : 52));

    return {
      data,
      layout: {
        height,
        barmode: "overlay" as const,
        bargap: 0.44,
        // Запас снизу: тики + легенда в 2 ряда, без «Дата Периодвору»
        margin: compact
          ? { l: 8, r: 80, t: 16, b: 168 }
          : { l: 16, r: 180, t: 40, b: 88 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        showlegend: true,
        legend: plotlyLegendUnderLeft({
          fontSize: compact ? 10 : 12,
          labelColor: theme.axis,
          y: compact ? -0.42 : -0.14,
        }),
        annotations,
        xaxis: {
          type: "date" as const,
          title: {
            text: compact ? "" : "Период",
            font: { size: 12, color: theme.axis },
            standoff: 18,
          },
          tickformat: "%d.%m.%y",
          tickangle: compact ? -45 : 0,
          nticks: compact ? 5 : 8,
          tickfont: { size: compact ? 9 : 11, color: theme.axis },
          gridcolor: theme.grid,
          automargin: !compact,
          ...(xRange ? { range: xRange } : {}),
        },
        yaxis: {
          categoryorder: "array" as const,
          categoryarray: categoryOrder,
          tickmode: "array" as const,
          tickvals: yLabels,
          ticktext: yTickTexts,
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          automargin: true,
        },
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG },
    };
  }, [rows, rangeStart, rangeEnd, fullscreen, theme, compact, hideProjectPrefix]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет данных для графика просрочки.
      </div>
    );
  }

  return (
    <PlotlyFigure
      data={figure.data}
      layout={figure.layout}
      config={figure.config}
      useResizeHandler
      style={{ width: "100%", height: "100%" }}
    />
  );
}
