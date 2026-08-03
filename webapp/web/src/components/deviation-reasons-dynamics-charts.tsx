"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { DeviationReasonsPayload } from "@/lib/api";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => (
    <div className="flex h-56 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Загрузка диаграммы…
    </div>
  ),
});

type Facet = DeviationReasonsPayload["tremor"]["dynamics"]["by_project_charts"][number];

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
    axis: dark ? "#cbd5e1" : "#334155",
    label: dark ? "#e2e8f0" : "#111827",
    paper: "rgba(0,0,0,0)",
    plot: "rgba(0,0,0,0)",
    grid: dark ? "rgba(148,163,184,0.22)" : "rgba(148,163,184,0.35)",
  };
}

const FALLBACK = ["#26c6da", "#ff9800", "#8bc34a", "#e91e63", "#5c6bc0", "#9e9e9e"];

export function DeviationFacetChart({
  facet,
  periodLabel,
  fullscreen = false,
}: {
  facet: Facet;
  periodLabel: string;
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const periods = facet.rows.map((r) => String(r.period));
    const totals = facet.rows.map((r) => Number(r.total ?? 0));
    const hi = Math.max(...totals, 0);
    const yTop = hi > 0 ? Math.max(hi * 1.45, hi + 0.85, 1) : 1;
    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.55, 720))
      : Math.max(360, 280 + Math.min(periods.length, 10) * 28);
    const nz = periods.map((_, i) => {
      let c = 0;
      for (const cat of facet.categories) {
        if (Number(facet.rows[i]?.[cat] ?? 0) > 0) c += 1;
      }
      return c;
    });
    const data = facet.categories.map((cat, ci) => {
      const ys = facet.rows.map((r) => Number(r[cat] ?? 0));
      const text = ys.map((v, i) => {
        if (!v) return "";
        if (nz[i] <= 1) return "";
        return String(Math.round(v));
      });
      return {
        type: "bar" as const,
        name: cat,
        x: periods,
        y: ys,
        text,
        textposition: "inside" as const,
        insidetextanchor: "middle" as const,
        cliponaxis: false,
        marker: {
          color: facet.colors?.[cat] || FALLBACK[ci % FALLBACK.length],
        },
        hovertemplate: `<b>${cat}</b><br>%{x}: %{y}<extra></extra>`,
      };
    });
    data.push({
      type: "scatter" as const,
      name: "_total",
      x: periods,
      y: totals,
      mode: "text" as const,
      text: totals.map((v) => (v > 0 ? String(Math.round(v)) : "")),
      textposition: "top center" as const,
      textfont: { size: 13, color: theme.label },
      hoverinfo: "skip" as const,
      showlegend: false,
    } as never);
    return {
      data,
      layout: {
        barmode: "stack" as const,
        height,
        margin: { l: 56, r: 140, t: 72, b: 72 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        title: {
          text: facet.project,
          x: 0.5,
          xanchor: "center" as const,
          font: { size: 18, color: theme.label },
        },
        yaxis: {
          title: {
            text: "Количество отклонений",
            font: { size: 12, color: theme.axis },
          },
          range: [0, yTop],
          gridcolor: theme.grid,
          tickfont: { size: 11, color: theme.axis },
          zeroline: false,
        },
        xaxis: {
          title: {
            text: periodLabel || "Период (месяц)",
            font: { size: 12, color: theme.axis },
          },
          tickfont: { size: 11, color: theme.axis },
          automargin: true,
        },
        legend: {
          orientation: "v" as const,
          yanchor: "top" as const,
          y: 1,
          xanchor: "left" as const,
          x: 1.02,
          title: { text: "Причина отклонения", font: { size: 12 } },
          font: { size: 11, color: theme.axis },
          bgcolor: "rgba(0,0,0,0)",
        },
        bargap: periods.length <= 4 ? 0.45 : 0.28,
        showlegend: true,
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { displayModeBar: true, responsive: true, locale: "ru" },
    };
  }, [facet, periodLabel, fullscreen, theme]);

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

export function DeviationStackChart({
  rows,
  projects,
  colors,
  fullscreen = false,
}: {
  rows: Array<Record<string, string | number>>;
  projects: string[];
  colors: Record<string, string>;
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const periods = rows.map((r) => String(r.period));
    const totals = rows.map((r) => Number(r.total ?? 0));
    const hi = Math.max(...totals, 0);
    const yTop = hi > 0 ? Math.max(hi * 1.45, hi + 0.85, 1) : 1;
    const height = fullscreen
      ? Math.max(520, Math.min(window.innerHeight * 0.65, 860))
      : Math.max(480, 360 + Math.min(periods.length, 14) * 24);
    const nz = periods.map((_, i) => {
      let c = 0;
      for (const p of projects) {
        if (Number(rows[i]?.[p] ?? 0) > 0) c += 1;
      }
      return c;
    });
    const data = projects.map((pname, i) => {
      const ys = rows.map((r) => Number(r[pname] ?? 0));
      const text = ys.map((v, idx) => {
        if (!v) return "";
        if (nz[idx] <= 1) return "";
        return String(Math.round(v));
      });
      return {
        type: "bar" as const,
        name: pname,
        x: periods,
        y: ys,
        text,
        textposition: "inside" as const,
        insidetextanchor: "middle" as const,
        cliponaxis: false,
        marker: { color: colors[pname] || FALLBACK[i % FALLBACK.length] },
        hovertemplate: `<b>${pname}</b><br>Период: %{x}<br>Количество: %{y}<extra></extra>`,
      };
    });
    data.push({
      type: "scatter" as const,
      name: "_total",
      x: periods,
      y: totals,
      mode: "text" as const,
      text: totals.map((v) => (v > 0 ? String(Math.round(v)) : "")),
      textposition: "top center" as const,
      textfont: { size: 13, color: theme.label },
      hoverinfo: "skip" as const,
      showlegend: false,
    } as never);
    return {
      data,
      layout: {
        barmode: "stack" as const,
        height,
        margin: {
          l: 56,
          r: Math.min(300, Math.max(140, 100 + projects.length * 18)),
          t: 56,
          b: 90,
        },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        yaxis: {
          title: {
            text: "Количество отклонений",
            font: { size: 13, color: theme.axis },
          },
          range: [0, yTop],
          gridcolor: theme.grid,
          tickfont: { size: 11, color: theme.axis },
          zeroline: false,
        },
        xaxis: {
          title: { text: "Период", font: { size: 13, color: theme.axis } },
          tickfont: { size: 11, color: theme.axis },
          automargin: true,
        },
        legend: {
          orientation: "v" as const,
          yanchor: "top" as const,
          y: 1,
          xanchor: "left" as const,
          x: 1.02,
          title: { text: "Проект", font: { size: 12 } },
          font: { size: 11, color: theme.axis },
          bgcolor: "rgba(0,0,0,0)",
        },
        bargap: periods.length <= 4 ? 0.64 : 0.5,
        showlegend: true,
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { displayModeBar: true, responsive: true, locale: "ru" },
    };
  }, [rows, projects, colors, fullscreen, theme]);

  if (!rows.length || !projects.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет ненулевых отклонений по проектам.
      </div>
    );
  }

  return (
    <>
      <PlotlyFigure
        data={figure.data}
        layout={figure.layout}
        config={figure.config}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
      <p className="mt-2 text-center text-xs text-tremor-content dark:text-dark-tremor-content">
        Количество отклонений по периоду и проекту (данные как в таблице выше; один
        столбец на месяц)
      </p>
    </>
  );
}
