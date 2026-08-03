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

type StatusMix = ProjectDocumentationPayload["tremor"]["status_mix"][number];
type DynamicsRow = ProjectDocumentationPayload["tremor"]["dynamics"][number];

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
    label: dark ? "#e2e8f0" : "#111827",
    paper: "rgba(0,0,0,0)",
    plot: "rgba(0,0,0,0)",
    grid: dark ? "rgba(148,163,184,0.22)" : "rgba(148,163,184,0.35)",
  };
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

/** Line «Динамика выдачи ПД» с точками как main. */
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
      ? Math.max(480, Math.min(window.innerHeight * 0.62, 760))
      : 360;
    const x = rows.map((r) => r.period_label || r.period);
    const mk = (
      y: number[],
      name: string,
      color: string,
    ): Record<string, unknown> => ({
      type: "scatter",
      mode: "lines+markers",
      name,
      x,
      y,
      line: { color, width: 2.5 },
      marker: { size: 8, color, line: { width: 1, color: "#fff" } },
      hovertemplate: `<b>%{x}</b><br>${name}: %{y}<extra></extra>`,
    });
    return {
      data: [
        mk(
          rows.map((r) => r.plan_bp),
          CHART_RU.planBp,
          "#3B82F6",
        ),
        mk(
          rows.map((r) => r.forecast),
          CHART_RU.forecast,
          "#F97316",
        ),
        mk(
          rows.map((r) => r.fact ?? 0),
          CHART_RU.factLine,
          "#10B981",
        ),
      ],
      layout: {
        height,
        margin: { l: 52, r: 24, t: 16, b: 64 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        hovermode: "x unified" as const,
        legend: {
          orientation: "h" as const,
          y: 1.12,
          x: 0,
          font: { size: 12, color: theme.axis },
        },
        xaxis: {
          title: { text: "Период", font: { size: 12, color: theme.axis } },
          tickangle: -25,
          tickfont: { size: 11, color: theme.axis },
          gridcolor: theme.grid,
          automargin: true,
        },
        yaxis: {
          title: {
            text: "Количество разделов ПД",
            font: { size: 12, color: theme.axis },
          },
          tickfont: { size: 11, color: theme.axis },
          gridcolor: theme.grid,
          zeroline: false,
          rangemode: "tozero" as const,
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
