"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { DeviationReasonsPayload } from "@/lib/api";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Загрузка диаграммы…
    </div>
  ),
});

type ByReason = DeviationReasonsPayload["tremor"]["by_reason"][number];
type ReasonMix = DeviationReasonsPayload["tremor"]["reason_mix"][number];

function wrapLabel(text: string, width = 15): string {
  const words = String(text || "")
    .trim()
    .split(/\s+/)
    .filter(Boolean);
  if (!words.length) return "";
  const lines: string[] = [];
  let cur = "";
  for (const word of words) {
    const next = cur ? `${cur} ${word}` : word;
    if (next.length <= width || !cur) {
      cur = next;
      continue;
    }
    lines.push(cur);
    cur = word;
  }
  if (cur) lines.push(cur);
  return lines.join("<br>");
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
    label: dark ? "#e2e8f0" : "#111827",
    paper: "rgba(0,0,0,0)",
    plot: "rgba(0,0,0,0)",
    grid: dark ? "rgba(148,163,184,0.22)" : "rgba(148,163,184,0.35)",
  };
}

export function DeviationReasonsBarChart({
  rows,
  fullscreen = false,
}: {
  rows: ByReason[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const n = rows.length;
    const ymax = Math.max(...rows.map((r) => r.count), 0);
    const yTop = Math.max(ymax * 1.55, ymax + 1.25, 1);
    const height = fullscreen
      ? Math.max(640, Math.min(window.innerHeight * 0.72, 960))
      : Math.max(520, Math.min(720, 360 + n * 80));
    const x = rows.map((r) => r.reason);
    const y = rows.map((r) => r.count);
    const text = rows.map((r) => r.label);
    const ticktext =
      n > 6 ? x : rows.map((r) => wrapLabel(r.reason_full || r.reason, 15));
    return {
      data: [
        {
          type: "bar" as const,
          x,
          y,
          text,
          textposition: "outside" as const,
          textfont: { size: fullscreen ? 22 : 16, color: theme.label },
          marker: { color: "#26c6da" },
          hovertemplate: "<b>%{x}</b><br>Количество: %{y}<extra></extra>",
          cliponaxis: false,
          ...(n === 1 ? { width: 0.36 } : {}),
        },
      ],
      layout: {
        height,
        margin: { l: 48, r: 28, t: 88, b: n > 6 ? 160 : 120 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        title: {
          text: "Причины отклонений (за отчетный период)",
          x: 0.5,
          xanchor: "center" as const,
          font: { size: 18, color: theme.axis },
        },
        yaxis: {
          title: { text: "Количество", font: { size: 14, color: theme.axis } },
          range: [0, yTop],
          automargin: true,
          tickfont: { size: 13, color: theme.axis },
          gridcolor: theme.grid,
          zeroline: false,
          dtick: ymax <= 8 ? 1 : undefined,
        },
        xaxis: {
          title: {
            text: "Причина отклонений",
            font: { size: 14, color: theme.axis },
            standoff: 28,
          },
          automargin: true,
          tickangle: n > 6 ? -45 : 0,
          tickmode: "array" as const,
          tickvals: x,
          ticktext,
          tickfont: { size: 13, color: theme.axis },
        },
        bargap: n === 1 ? 0.72 : n <= 4 ? 0.45 : 0.28,
        showlegend: false,
      },
      config: {
        displayModeBar: true,
        responsive: true,
        locale: "ru",
      },
    };
  }, [rows, fullscreen, theme]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет данных по причинам.
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

export function DeviationReasonsPieChart({
  rows,
  fullscreen = false,
}: {
  rows: ReasonMix[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const n = rows.length;
    const height = fullscreen
      ? Math.max(520, Math.min(window.innerHeight * 0.65, 800))
      : Math.max(480, 400 + Math.min(n, 12) * 16);
    const labels = rows.map((r) => r.name);
    const values = rows.map((r) => r.value);
    const colors = rows.map(
      (r, i) =>
        r.color ||
        ["#26c6da", "#ff9800", "#8bc34a", "#e91e63", "#9e9e9e", "#5c6bc0"][i % 6],
    );
    const fontSize = n <= 8 ? 15 : n <= 12 ? 13 : 12;
    return {
      data: [
        {
          type: "pie" as const,
          labels,
          values,
          sort: false,
          direction: "clockwise" as const,
          hole: 0,
          pull: rows.map(() => 0.03),
          marker: { colors },
          texttemplate: "<b>%{value:.0f}</b> (%{percent:.1%})",
          textinfo: "text" as const,
          textposition: "auto" as const,
          insidetextorientation: "horizontal" as const,
          textfont: {
            size: fontSize,
            color: "#ffffff",
            family: "Inter, system-ui, Arial, sans-serif",
          },
          outsidetextfont: {
            size: 13,
            color: theme.label,
            family: "Inter, system-ui, Arial, sans-serif",
          },
          hovertemplate:
            "<b>%{label}</b><br>Количество: %{value}<br>Доля: %{percent:.1%}<extra></extra>",
        },
      ],
      layout: {
        height,
        margin: { l: 24, r: 24, t: 24, b: 80 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        showlegend: true,
        legend: {
          orientation: "h" as const,
          x: 0.5,
          xanchor: "center" as const,
          y: -0.08,
          yanchor: "top" as const,
          font: { size: 12, color: theme.axis },
        },
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
      },
      config: {
        displayModeBar: true,
        responsive: true,
        locale: "ru",
      },
    };
  }, [rows, fullscreen, theme]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет данных по долям.
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
