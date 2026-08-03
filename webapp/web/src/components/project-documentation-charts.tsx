"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { ProjectDocumentationPayload } from "@/lib/api";
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

/** Цвета линий как main (`GDRS_THEME_DARK` + `_PD_FACT_LINE_COLOR`). */
const PD_PLAN = "#29b6f6";
const PD_FCST = "#ff8c2d";
const PD_FACT = "#27AE60";
const PD_MONTH_PLAN = "#F39C12";
const PD_MONTH_FACT = "#27AE60";

type StatusMix = ProjectDocumentationPayload["tremor"]["status_mix"][number];
type DynamicsRow = ProjectDocumentationPayload["tremor"]["dynamics"][number];
type MonthlyRow = ProjectDocumentationPayload["tremor"]["monthly"][number];

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

/** Pie «Исполнение ПД» как main Plotly (%, легенда слева через внешний UI). */
export function PdExecutionPieChart({
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
    const colors = rows.map((r, i) => {
      if (r.color) return r.color;
      if (r.name.includes("Заверш")) return "#2E86AB";
      if (r.name.includes("работ")) return "#F59E0B";
      return ["#E74C3C", "#94a3b8", "#8bc34a"][i % 3];
    });
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

/** Line «Динамика выдачи ПД»: lines+markers+text как main. */
export function PdDynamicsLineChart({
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
    const ys = [
      rows.map((r) => r.plan_bp),
      rows.map((r) => r.forecast),
      rows.map((r) => r.fact ?? 0),
    ];
    const yMax = Math.max(1, ...ys.flat().map((v) => Number(v) || 0));
    const yHead = Math.max(yMax * 0.1, 4);
    const mk = (
      y: number[],
      name: string,
      color: string,
      width: number,
      markerSize: number,
    ): Record<string, unknown> => ({
      type: "scatter",
      mode: "lines+markers+text",
      name,
      x,
      y,
      text: y.map(pointLabel),
      textposition: "top center",
      textfont: { color, size: 10 },
      line: { color, width },
      marker: { size: markerSize, color, line: { width: 1, color: "#fff" } },
      cliponaxis: false,
      hovertemplate: `<b>%{x}</b><br>${name}: %{y}<extra></extra>`,
    });
    return {
      data: [
        mk(ys[0], CHART_RU.planBp, PD_PLAN, 2.5, 8),
        mk(ys[1], CHART_RU.forecast, PD_FCST, 3, 9),
        mk(ys[2], CHART_RU.factLine, PD_FACT, 2.5, 8),
      ],
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
            text: "Количество разделов ПД",
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

/** Горизонтальные overlay-бары «Динамика по месяцам» как main (жёлтый план / зелёный факт, «+N»). */
export function PdMonthlyCumulativeChart({
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
    const factInc = chronological.map((r, i) =>
      i === 0 ? r.fact : Math.max(0, r.fact - chronological[i - 1].fact),
    );
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
          marker: { color: PD_MONTH_PLAN, opacity: 0.92 },
          customdata: labels,
        },
        {
          ...barBase,
          name: CHART_RU.fact,
          x: fact,
          text: factText,
          texttemplate: "%{text}",
          marker: { color: PD_MONTH_FACT, opacity: 0.95 },
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
