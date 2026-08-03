"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { PLOTLY_CONFIG } from "@/lib/plotly-config";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Загрузка диаграммы…
    </div>
  ),
});

type PlanFactRow = {
  name: string;
  plan: number;
  fact: number;
  deviation: number;
};

type PieRow = { name: string; value: number };

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
    label: dark ? "#e2e8f0" : "#111827",
    grid: dark ? "rgba(148,163,184,0.22)" : "#e5e7eb",
    paper: "rgba(0,0,0,0)",
  };
}

function signed(value: number): string {
  const rounded = Math.round(value);
  return rounded > 0 ? `+${rounded}` : String(rounded);
}

function empty(message: string) {
  return (
    <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      {message}
    </div>
  );
}

export function GdrsGroupedBarChart({
  rows,
  contractors = false,
  fullscreen = false,
}: {
  rows: PlanFactRow[];
  contractors?: boolean;
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const labels = rows.map((row) => row.name);
    const deviations = rows.map((row) => Math.abs(row.deviation));
    const devColors = rows.map((row) =>
      row.deviation < 0 ? "#b91c1c" : row.deviation > 0 ? "#15803d" : "#6b7280",
    );
    const light = !theme.dark;
    const axisSz = contractors ? (light ? 22 : 16) : light ? 22 : 12;
    const xTickSz = contractors ? (light ? 18 : 14) : light ? 44 : 34;
    const labelSz = contractors ? (light ? 21 : 16) : light ? 18 : 14;
    const chartWidth = contractors ? Math.max(1180, rows.length * 128) : undefined;
    const height = contractors
      ? fullscreen
        ? Math.max(680, Math.min(window.innerHeight - 32, 1500))
        : light
          ? 1500
          : 1320
      : fullscreen
        ? Math.max(560, Math.min(window.innerHeight - 32, 760))
        : 560;
    return {
      data: [
        {
          type: "bar" as const,
          name: "План",
          x: labels,
          y: rows.map((row) => row.plan),
          text: rows.map((row) => String(Math.round(row.plan))),
          textposition: "outside" as const,
          textfont: { color: "#1e3a8a", size: labelSz },
          marker: { color: "#2563eb" },
          cliponaxis: false,
          hovertemplate: "<b>%{x}</b><br>План: %{y}<extra></extra>",
        },
        {
          type: "bar" as const,
          name: "Факт",
          x: labels,
          y: rows.map((row) => row.fact),
          text: rows.map((row) => String(Math.round(row.fact))),
          textposition: "outside" as const,
          textfont: { color: "#14532d", size: labelSz },
          marker: { color: "#15803d" },
          cliponaxis: false,
          hovertemplate: "<b>%{x}</b><br>Факт: %{y}<extra></extra>",
        },
        {
          type: "bar" as const,
          name: "Отклонение (факт − план)",
          x: labels,
          y: deviations,
          text: rows.map((row) => signed(row.deviation)),
          textposition: "outside" as const,
          textfont: { color: devColors, size: labelSz },
          marker: { color: devColors },
          cliponaxis: false,
          hovertemplate: "<b>%{x}</b><br>Отклонение: %{text}<extra></extra>",
        },
      ],
      layout: {
        width: chartWidth,
        height,
        barmode: "group" as const,
        bargap: 0.22,
        bargroupgap: 0.08,
        margin: {
          l: contractors ? 64 : 56,
          r: 28,
          t: 88,
          b: contractors ? (labels.length > 8 ? 200 : 160) : light ? 120 : 100,
        },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        font: { family: "Inter, system-ui, sans-serif", color: theme.label },
        legend: {
          orientation: "h" as const,
          x: 0.5,
          xanchor: "center" as const,
          y: -0.18,
          font: { color: theme.label, size: contractors ? 16 : 13 },
        },
        xaxis: {
          tickangle: contractors && labels.length > 8 ? -45 : 0,
          tickfont: {
            size: xTickSz,
            color: theme.label,
            family: "Inter, sans-serif",
          },
          ticklabelstandoff: contractors && labels.length > 8 ? 6 : 14,
          showgrid: false,
          automargin: true,
        },
        yaxis: {
          gridcolor: theme.grid,
          zeroline: false,
          tickfont: { size: axisSz, color: theme.label },
          automargin: true,
        },
        modebar: { bgcolor: "rgba(0,0,0,0)", color: theme.axis, activecolor: "#0f766e" },
      },
      config: { ...PLOTLY_CONFIG },
    };
  }, [contractors, fullscreen, rows, theme]);

  if (!rows.length) return empty("Нет данных для графика.");
  return (
    <div className={contractors ? "overflow-x-auto" : ""}>
      <PlotlyFigure
        data={figure.data}
        layout={figure.layout}
        config={figure.config}
        useResizeHandler
        style={{ width: contractors ? "max-content" : "100%", height: "100%" }}
      />
    </div>
  );
}

export function GdrsContractorsPieChart({
  rows,
  fullscreen = false,
}: {
  rows: PieRow[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const values = rows.map((row) => Number(row.value) || 0);
    const total = values.reduce((s, v) => s + v, 0);
    const labels = rows.map((row) => row.name);
    const insideMin = 0.08;
    const texts: string[] = [];
    const positions: Array<"inside" | "outside"> = [];
    let hasOutside = false;
    for (const val of values) {
      if (total <= 0) {
        texts.push("");
        positions.push("inside");
        continue;
      }
      const frac = val / total;
      const pct =
        frac > 0 && frac < 0.03
          ? `${(frac * 100).toFixed(1)}%`
          : `${Math.round(frac * 100)}%`;
      if (frac >= insideMin) {
        texts.push(`${Math.round(val)}<br>${pct}`);
        positions.push("inside");
      } else {
        texts.push(pct);
        positions.push("outside");
        hasOutside = true;
      }
    }
    const n = rows.length;
    const baseTxt = Math.max(15, Math.min(21, 23 - Math.floor(n / 2)));
    const txtIn = Math.round(baseTxt * 1.5);
    const txtOut = Math.round((baseTxt - 1) * 1.5);
    const height = fullscreen
      ? Math.max(720, Math.min(window.innerHeight - 32, 980))
      : hasOutside
        ? 820
        : 780;
    return {
      data: [
        {
          type: "pie" as const,
          labels,
          values,
          hole: 0.28,
          sort: false,
          direction: "clockwise" as const,
          pull: 0,
          text: texts,
          textinfo: "text" as const,
          textposition: positions,
          insidetextorientation: "horizontal" as const,
          automargin: false,
          marker: {
            colors: [
              "#2563eb",
              "#15803d",
              "#ea580c",
              "#7c3aed",
              "#db2777",
              "#0891b2",
              "#ca8a04",
              "#4f46e5",
              "#65a30d",
              "#dc2626",
              "#64748b",
            ],
            line: { color: theme.dark ? "rgba(15,23,42,0.9)" : "#ffffff", width: 1 },
          },
          textfont: { color: "#ffffff", size: txtIn },
          outsidetextfont: { color: theme.label, size: txtOut },
          hovertemplate:
            "<b>%{label}</b><br>Факт: %{value}<br>Доля: %{percent}<extra></extra>",
        },
      ],
      layout: {
        height,
        margin: { l: 8, r: 8, t: 24, b: 120 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        font: { family: "Inter, system-ui, sans-serif", color: theme.label },
        showlegend: true,
        legend: {
          orientation: "h" as const,
          x: 0.5,
          xanchor: "center" as const,
          y: -0.08,
          font: { color: theme.label, size: 12 },
        },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG },
    };
  }, [fullscreen, rows, theme]);

  if (!rows.length) return empty("Нет данных по контрагентам.");
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

export function GdrsDynamicsLineChart({
  rows,
  fullscreen = false,
}: {
  rows: Array<{ period: string; plan: number; fact: number }>;
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const x = rows.map((row) => row.period);
    const plan = rows.map((row) => row.plan);
    const fact = rows.map((row) => row.fact);
    const maximum = Math.max(1, ...plan, ...fact);
    return {
      data: [
        {
          type: "scatter" as const,
          mode: "lines+markers+text" as const,
          name: "План",
          x,
          y: plan,
          text: plan.map((value) => String(Math.round(value))),
          textposition: "top center" as const,
          textfont: { color: "#2563eb", size: 10 },
          line: { color: "#2563eb", width: 2.5 },
          marker: { color: "#2563eb", size: 8, line: { color: "#ffffff", width: 1 } },
          cliponaxis: false,
          hovertemplate: "<b>%{x}</b><br>План: %{y}<extra></extra>",
        },
        {
          type: "scatter" as const,
          mode: "lines+markers+text" as const,
          name: "Факт",
          x,
          y: fact,
          text: fact.map((value) => String(Math.round(value))),
          textposition: "top center" as const,
          textfont: { color: "#ea580c", size: 10 },
          line: { color: "#ea580c", width: 2.5 },
          marker: { color: "#ea580c", size: 8, line: { color: "#ffffff", width: 1 } },
          cliponaxis: false,
          hovertemplate: "<b>%{x}</b><br>Факт: %{y}<extra></extra>",
        },
      ],
      layout: {
        height: fullscreen ? Math.max(520, Math.min(window.innerHeight - 32, 760)) : 440,
        margin: { l: 56, r: 36, t: 76, b: 110 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        hovermode: "x unified" as const,
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        legend: { orientation: "h" as const, y: 1.15, x: 0.5, xanchor: "center" as const },
        xaxis: { title: "Период", tickangle: -35, tickfont: { size: 11, color: theme.axis }, gridcolor: theme.grid, automargin: true },
        yaxis: { title: "Среднее число в день", range: [0, maximum * 1.16], tickfont: { size: 11, color: theme.axis }, gridcolor: theme.grid, zeroline: false },
        modebar: { bgcolor: "rgba(0,0,0,0)", color: theme.axis, activecolor: "#0f766e" },
      },
      config: { ...PLOTLY_CONFIG },
    };
  }, [fullscreen, rows, theme]);

  if (!rows.length) return empty("Нет точек динамики.");
  return <PlotlyFigure data={figure.data} layout={figure.layout} config={figure.config} useResizeHandler style={{ width: "100%", height: "100%" }} />;
}
