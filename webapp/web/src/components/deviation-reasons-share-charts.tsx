"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { DeviationReasonsPayload } from "@/lib/api";
import { DashboardEmptyState } from "@/components/dashboard-empty-state";
import {
  PLOTLY_AXIS_LINE,
  PLOTLY_CONFIG,
  PLOTLY_ZEROLINE,
  plotlyLegendUnderLeft,
} from "@/lib/plotly-config";
import { useIsMobileViewport, useIsNarrowPhone } from "@/lib/use-is-mobile";

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
  const mobile = useIsMobileViewport();
  const narrow = useIsNarrowPhone();
  const compact = mobile && !fullscreen;
  const figure = useMemo(() => {
    const n = rows.length;
    const ymax = Math.max(...rows.map((r) => r.count), 0);
    const yTop = Math.max(ymax * 1.55, ymax + 1.25, 1);
    const height = fullscreen
      ? Math.max(640, Math.min(window.innerHeight * 0.72, 960))
      : compact
        ? Math.max(420, Math.min(560, 280 + n * 72))
        : Math.max(520, Math.min(720, 360 + n * 80));
    const x = rows.map((r) => r.reason);
    const y = rows.map((r) => r.count);
    const text = rows.map((r) => r.label);
    const wrapW = narrow ? 8 : compact ? 10 : 15;
    const ticktext =
      n > 6 || compact
        ? rows.map((r) => wrapLabel(r.reason_full || r.reason, wrapW))
        : rows.map((r) => wrapLabel(r.reason_full || r.reason, 15));
    const angled = compact || n > 4;
    return {
      data: [
        {
          type: "bar" as const,
          x,
          y,
          text,
          textposition: "outside" as const,
          textfont: {
            size: fullscreen ? 22 : compact ? 12 : 16,
            color: theme.label,
          },
          marker: { color: "#26c6da" },
          hovertemplate: "<b>%{x}</b><br>Количество: %{y}<extra></extra>",
          cliponaxis: false,
          ...(n === 1 ? { width: 0.36 } : {}),
        },
      ],
      layout: {
        height,
        margin: compact
          ? { l: 40, r: 16, t: 28, b: angled ? 150 : 110 }
          : { l: 48, r: 28, t: 88, b: n > 6 ? 160 : 120 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        // На узком экране title Plotly клипится — заголовок в Card снаружи.
        ...(compact
          ? {}
          : {
              title: {
                text: "Причины отклонений (за отчетный период)",
                x: 0.5,
                xanchor: "center" as const,
                font: { size: 18, color: theme.axis },
              },
            }),
        yaxis: {
          title: {
            text: "Количество",
            font: { size: compact ? 12 : 14, color: theme.axis },
          },
          range: [0, yTop],
          automargin: true,
          tickfont: { size: compact ? 11 : 13, color: theme.axis },
          gridcolor: theme.grid,
          ...PLOTLY_ZEROLINE,
          zerolinecolor: theme.dark
            ? "rgba(148, 163, 184, 0.85)"
            : "rgba(100, 116, 139, 0.85)",
          dtick: ymax <= 8 ? 1 : undefined,
        },
        xaxis: {
          title: {
            text: compact ? "" : "Причина отклонений",
            font: { size: 14, color: theme.axis },
            standoff: 28,
          },
          automargin: true,
          tickangle: angled ? -35 : 0,
          tickmode: "array" as const,
          tickvals: x,
          ticktext,
          tickfont: { size: compact ? 10 : 13, color: theme.axis },
          ...PLOTLY_AXIS_LINE,
          linecolor: theme.dark
            ? "rgba(148, 163, 184, 0.85)"
            : "rgba(100, 116, 139, 0.85)",
        },
        bargap: n === 1 ? 0.72 : n <= 4 ? 0.45 : 0.28,
        showlegend: false,
        shapes: [
          {
            type: "line" as const,
            xref: "paper" as const,
            x0: 0,
            x1: 1,
            yref: "y" as const,
            y0: 0,
            y1: 0,
            layer: "below" as const,
            line: {
              color: theme.dark
                ? "rgba(148, 163, 184, 0.9)"
                : "rgba(71, 85, 105, 0.9)",
              width: 1.5,
            },
          },
        ],
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG },
    };
  }, [rows, fullscreen, theme, compact, narrow]);

  if (!rows.length) {
    return <DashboardEmptyState message="Нет данных по причинам." className="h-64" />;
  }

  return (
    <div className="min-w-0 overflow-x-hidden">
      {compact ? (
        <p className="mb-2 px-1 text-center text-sm font-semibold leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong">
          Причины отклонений (за отчетный период)
        </p>
      ) : null}
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
        legend: plotlyLegendUnderLeft({
          fontSize: 12,
          labelColor: theme.axis,
          y: -0.08,
        }),
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
    return <DashboardEmptyState message="Нет данных по долям." className="h-64" />;
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
