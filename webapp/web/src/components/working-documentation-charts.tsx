"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { WorkingDocumentationPayload } from "@/lib/api";
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

const RD_PLAN = "#2E86AB";
const RD_FACT = "#F39C12";
const RD_MONTH_PLAN = "#F39C12";
const RD_MONTH_FACT = "#27AE60";

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
}: {
  rows: DynamicsRow[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const height = fullscreen
      ? Math.max(520, Math.min(window.innerHeight * 0.62, 760))
      : 420;
    const x = rows.map((r) => r.period_label || r.period);
    const plan = rows.map((r) => r.plan);
    const fact = rows.map((r) => r.fact);
    const yMax = Math.max(1, ...plan, ...fact);
    const yHead = Math.max(yMax * 0.1, 4);
    const mk = (
      y: number[],
      name: string,
      color: string,
    ): Record<string, unknown> => ({
      type: "scatter",
      mode: "lines+markers+text",
      name,
      x,
      y,
      text: y.map(pointLabel),
      textposition: "top center",
      textfont: { color, size: 10 },
      line: { color, width: 2.5 },
      marker: { size: 8, color, line: { width: 1, color: "#fff" } },
      cliponaxis: false,
      hovertemplate: `<b>%{x}</b><br>${name}: %{y}<extra></extra>`,
    });
    return {
      data: [mk(plan, CHART_RU.plan, RD_PLAN), mk(fact, CHART_RU.fact, RD_FACT)],
      layout: {
        height,
        margin: { l: 56, r: 36, t: 72, b: 88 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        hovermode: "x unified" as const,
        legend: {
          orientation: "h" as const,
          y: 1.14,
          x: 0.5,
          xanchor: "center" as const,
          font: { size: 13, color: theme.axis },
        },
        xaxis: {
          title: {
            text: "Период",
            standoff: 18,
            font: { size: 12, color: theme.axis },
          },
          tickangle: -35,
          tickfont: { size: 12, color: theme.axis },
          gridcolor: theme.grid,
          automargin: true,
        },
        yaxis: {
          title: {
            text: "Количество разделов РД",
            font: { size: 12, color: theme.axis },
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
    };
  }, [rows, fullscreen, theme]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет точек динамики.
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

/** Горизонтальные overlay-бары «Динамика по месяцам» как main / PD. */
export function RdMonthlyCumulativeChart({
  rows,
  fullscreen = false,
}: {
  rows: MonthlyRow[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const chronological = [...rows].sort((a, b) => a.month.localeCompare(b.month));
    const labels = chronological.map((r) => r.month_label);
    const plan = chronological.map((r) => r.plan);
    const fact = chronological.map((r) => r.fact);
    const factInc = chronological.map((r, i) => {
      if (r.fact_inc != null && Number.isFinite(r.fact_inc)) return r.fact_inc;
      return i === 0 ? r.fact : Math.max(0, r.fact - chronological[i - 1].fact);
    });
    const yIdx = chronological.map((_, i) => i);
    const xMax = Math.max(1, ...plan, ...fact);
    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.55, 680))
      : Math.max(320, 56 + chronological.length * 48);

    const incTxt = factInc.map((v) => (v > 0 ? `+${Math.round(v)}` : ""));
    const planLonger = plan.map((p, i) => p >= fact[i]);
    const planText = incTxt.map((t, i) => (planLonger[i] ? t : ""));
    const factText = incTxt.map((t, i) => (planLonger[i] ? "" : t));

    const barBase = {
      type: "bar" as const,
      orientation: "h" as const,
      y: yIdx,
      textposition: "outside" as const,
      textfont: { size: 15, color: theme.label },
      cliponaxis: false,
      constraintext: "none" as const,
      hovertemplate: "<b>%{customdata}</b><br>%{fullData.name}: %{x}<extra></extra>",
    };

    return {
      data: [
        {
          ...barBase,
          name: CHART_RU.plan,
          x: plan,
          text: planText,
          texttemplate: "%{text}",
          marker: { color: RD_MONTH_PLAN, opacity: 0.92 },
          customdata: labels,
        },
        {
          ...barBase,
          name: CHART_RU.fact,
          x: fact,
          text: factText,
          texttemplate: "%{text}",
          marker: { color: RD_MONTH_FACT, opacity: 0.95 },
          customdata: labels,
        },
      ],
      layout: {
        height,
        barmode: "overlay" as const,
        bargap: 0.28,
        margin: { l: 16, r: 72, t: 48, b: 56 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        legend: {
          orientation: "h" as const,
          y: 1.12,
          x: 0,
          font: { size: 12, color: theme.axis },
        },
        xaxis: {
          title: {
            text: "Количество разделов (накопительно)",
            font: { size: 12, color: theme.axis },
          },
          range: [0, xMax * 1.12],
          tickfont: { size: 11, color: theme.axis },
          gridcolor: theme.grid,
          zeroline: false,
        },
        yaxis: {
          title: { text: "Месяц", font: { size: 12, color: theme.axis } },
          tickmode: "array" as const,
          tickvals: yIdx,
          ticktext: labels,
          tickfont: { size: 11, color: theme.axis },
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
  }, [rows, fullscreen, theme]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет помесячных данных.
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

/** Gantt «Просрочка выдачи РД» — Plotly как PD, легенда РД + «N дн.» на красном. */
export function RdDelayGanttChart({
  rows,
  rangeStart,
  rangeEnd,
  fullscreen = false,
}: {
  rows: GanttRow[];
  rangeStart: string | null;
  rangeEnd: string | null;
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const sorted = [...rows].sort((a, b) => (b.delay_dur || 0) - (a.delay_dur || 0));
    const yLabels = sorted.map((r) => r.label);
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
    const annotations: Array<Record<string, unknown>> = [];

    for (const row of sorted) {
      const y = row.label;
      const startMs = toMs(row.start);
      const bfMs = toMs(row.base_finish);
      const finMs = toMs(row.finish);
      const delayEndMs = toMs(row.delay_end);
      const hasRed = (row.delay_dur || 0) > 0 && delayEndMs != null && bfMs != null;
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
          greenCd.push(row.fact_label || "");
        }
      }

      if (hasRed && bfMs != null) {
        const rLen = barLenMs(row.base_finish, row.delay_end);
        if (rLen != null) {
          redY.push(y);
          redBase.push(bfMs);
          redLen.push(rLen);
          redCd.push(row.fact_label || row.delay_label || "");
        }
      }

      const labelColor = theme.dark ? "#e2e8f0" : "#1a1a1a";
      const annBase = {
        y,
        showarrow: false,
        yanchor: "middle" as const,
        font: { size: 10, color: labelColor },
      };

      if (row.base_label && bfMs != null && !hasRed && (finMs == null || finMs <= bfMs)) {
        annotations.push({
          ...annBase,
          x: bfMs,
          text: row.base_label,
          xanchor: "left",
          xshift: 6,
        });
      } else if (row.base_label && bfMs != null && hasRed) {
        annotations.push({
          ...annBase,
          x: bfMs,
          text: row.base_label,
          xanchor: "right",
          xshift: -6,
        });
      }

      if (hasGreen && row.fact_label && finMs != null && !hasRed) {
        const gapDays =
          bfMs != null && finMs != null ? Math.abs((bfMs - finMs) / DAY_MS) : 99;
        if (gapDays > 5) {
          annotations.push({
            ...annBase,
            x: finMs,
            text: row.fact_label,
            xanchor: "left",
            xshift: 6,
          });
        }
      }

      if (hasRed && delayEndMs != null) {
        const redText = row.delay_label || row.fact_label;
        if (redText) {
          annotations.push({
            ...annBase,
            x: delayEndMs,
            text: redText,
            xanchor: "left",
            xshift: 6,
            font: { size: 10, color: theme.dark ? "#fecaca" : "#7f1d1d" },
          });
        }
      }
    }

    const data: Array<Record<string, unknown>> = [];
    if (yellowY.length) {
      data.push({
        type: "bar",
        orientation: "h",
        name: "Дата по договору",
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
        name: "Прогноз / факт",
        y: greenY,
        x: greenLen,
        base: greenBase,
        marker: { color: RD_GANTT_GREEN },
        width: 0.48,
        customdata: greenCd,
        hovertemplate: "%{y}<br>Прогноз / факт: %{customdata}<extra></extra>",
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
        hovertemplate: "%{y}<br>Просрочка: %{customdata}<extra></extra>",
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
      const pad = Math.max((rangeHi - rangeLo) * 0.08, 6 * DAY_MS);
      xRange = [rangeLo - pad, rangeHi + pad];
    }

    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.62, 780))
      : Math.max(280, 120 + sorted.length * 52);

    return {
      data,
      layout: {
        height,
        barmode: "overlay" as const,
        bargap: 0.44,
        margin: { l: 16, r: 140, t: 56, b: 56 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        showlegend: true,
        legend: {
          orientation: "h" as const,
          y: 1.12,
          x: 0,
          font: { size: 12, color: theme.axis },
        },
        annotations,
        xaxis: {
          type: "date" as const,
          title: { text: "Период", font: { size: 12, color: theme.axis } },
          tickformat: "%d.%m.%Y",
          tickfont: { size: 11, color: theme.axis },
          gridcolor: theme.grid,
          automargin: true,
          ...(xRange ? { range: xRange } : {}),
        },
        yaxis: {
          categoryorder: "array" as const,
          categoryarray: categoryOrder,
          tickmode: "array" as const,
          tickvals: yLabels,
          ticktext: yLabels,
          tickfont: { size: 11, color: theme.axis },
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
  }, [rows, rangeStart, rangeEnd, fullscreen, theme]);

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
