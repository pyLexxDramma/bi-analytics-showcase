"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { Config, Data, Layout } from "plotly.js";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => <div className="h-[520px]" />,
});

/** Цвета серий БДДС/БДР из [main] (`_renderers.py`). */
export const PLAN_COLOR = "#2E86AB";
export const FACT_COLOR = "#A23B72";
export const DEV_BAR_RED = "#e74c3c";
export const DEV_BAR_GREEN = "#27ae60";
const DEV_LABEL_RED = "hsl(348,100%,63%)";
const DEV_LABEL_GREEN = "hsl(148,100%,63%)";

const GRID_COLOR = "rgba(148, 163, 184, 0.45)";
const AXIS_LINE_COLOR = "rgba(100, 116, 139, 0.65)";

export type FinanceBarPoint = {
  period: string;
  plan: number;
  fact: number;
  deviation: number;
};

/** «955.0 млн. руб.» — как `_finance_bar_text_mln_rub` в [main]. */
function barLabel(value: number, minAbs: number): string {
  if (!Number.isFinite(value) || Math.abs(value) < minAbs) return "";
  return `${value.toFixed(1)} млн. руб.`;
}

function hoverLabel(value: number): string {
  return `${value.toFixed(1)} млн. руб.`;
}

function useDarkTheme(): boolean {
  const [dark, setDark] = useState(true);
  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setDark(root.classList.contains("dark"));
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => observer.disconnect();
  }, []);
  return dark;
}

function useViewportSize(enabled: boolean): { width: number; height: number } {
  const [size, setSize] = useState({ width: 1440, height: 900 });
  useEffect(() => {
    if (!enabled) return;
    const sync = () =>
      setSize({ width: window.innerWidth, height: window.innerHeight });
    sync();
    window.addEventListener("resize", sync);
    return () => window.removeEventListener("resize", sync);
  }, [enabled]);
  return size;
}

/**
 * Столбчатый график план/факт(/отклонение) как на финансовых вкладках [main]:
 * подписи значений над столбцами, легенда под графиком, наклонные подписи
 * периодов и полная панель инструментов Plotly.
 */
export function FinanceBarChart({
  rows,
  planName,
  factName,
  showDeviation = false,
  xAxisTitle,
  yAxisTitle = "млн рублей",
  emptyText = "Нет периодов для графика",
  fullscreen = false,
}: {
  rows: FinanceBarPoint[];
  planName: string;
  factName: string;
  showDeviation?: boolean;
  xAxisTitle: string;
  yAxisTitle?: string;
  emptyText?: string;
  /** Зум: график занимает весь экран, столбцы шире, подписи крупнее. */
  fullscreen?: boolean;
}) {
  const dark = useDarkTheme();
  const textColor = dark ? "#f0f4f8" : "#111827";
  const viewport = useViewportSize(fullscreen);

  const height = fullscreen ? Math.max(520, viewport.height - 32) : 620;
  // Полоса на период: в зуме столбцы не сжимаются, а уезжают в горизонтальный скролл.
  const width = fullscreen
    ? Math.max(viewport.width - 32, rows.length * 150 + 180)
    : undefined;

  const { data, layout } = useMemo(() => {
    const periods = rows.map((row) => row.period);
    const plans = rows.map((row) => row.plan);
    const facts = rows.map((row) => row.fact);
    const count = rows.length || 1;
    const baseFont = count > 32 ? 9 : count > 20 ? 10 : count > 12 ? 11 : 12;
    const fontSize = fullscreen ? Math.max(14, baseFont + 4) : baseFont;

    const traces: Data[] = [];
    if (plans.some((value) => Math.abs(value) >= 0.5)) {
      traces.push({
        type: "bar",
        x: periods,
        y: plans,
        name: planName,
        marker: { color: PLAN_COLOR },
        text: plans.map((value) => barLabel(value, 0.005)),
        textposition: "outside",
        textfont: { size: fontSize, color: textColor },
        cliponaxis: false,
        customdata: plans.map(hoverLabel),
        hovertemplate: `<b>%{x}</b><br>${planName}: %{customdata}<extra></extra>`,
      });
    }
    traces.push({
      type: "bar",
      x: periods,
      y: facts,
      name: factName,
      marker: { color: FACT_COLOR },
      text: facts.map((value) => barLabel(value, 0.005)),
      textposition: "outside",
      textfont: { size: fontSize, color: textColor },
      cliponaxis: false,
      customdata: facts.map(hoverLabel),
      hovertemplate: `<b>%{x}</b><br>${factName}: %{customdata}<extra></extra>`,
    });

    if (showDeviation) {
      // В [main] отклонение = факт − план: минус красным, плюс зелёным (две серии).
      const under = rows.map((row) => (row.deviation < -0.01 ? row.deviation : null));
      const over = rows.map((row) => (row.deviation > 0.01 ? row.deviation : null));
      if (under.some((value) => value !== null)) {
        traces.push({
          type: "bar",
          x: periods,
          y: under,
          name: "Отклонение (факт < план)",
          marker: { color: DEV_BAR_RED },
          text: under.map((value) => (value === null ? "" : `-${Math.abs(value).toFixed(1)} млн. руб.`)),
          textposition: "outside",
          textfont: { size: fontSize, color: DEV_LABEL_RED },
          cliponaxis: false,
          hovertemplate: "<b>%{x}</b><br>Отклонение: %{y:.1f} млн. руб.<extra></extra>",
        });
      }
      if (over.some((value) => value !== null)) {
        traces.push({
          type: "bar",
          x: periods,
          y: over,
          name: "Отклонение (факт > план)",
          marker: { color: DEV_BAR_GREEN },
          text: over.map((value) => (value === null ? "" : `+${value.toFixed(1)} млн. руб.`)),
          textposition: "outside",
          textfont: { size: fontSize, color: DEV_LABEL_GREEN },
          cliponaxis: false,
          hovertemplate: "<b>%{x}</b><br>Отклонение: %{y:.1f} млн. руб.<extra></extra>",
        });
      }
    }

    const tickAngle = fullscreen ? -35 : count <= 18 ? -45 : count <= 36 ? -50 : -55;
    const figureLayout: Partial<Layout> = {
      barmode: "group",
      bargap: fullscreen ? 0.24 : count <= 12 ? 0.28 : 0.18,
      bargroupgap: 0.08,
      paper_bgcolor: "rgba(0,0,0,0)",
      plot_bgcolor: "rgba(0,0,0,0)",
      font: { color: textColor, size: fullscreen ? 15 : 12 },
      margin: fullscreen
        ? { l: 88, r: 40, t: 64, b: 190 }
        : { l: 64, r: 24, t: 48, b: 168 },
      hovermode: "closest",
      showlegend: true,
      legend: {
        orientation: "h",
        yanchor: "top",
        y: fullscreen ? -0.3 : -0.42,
        xanchor: "center",
        x: 0.5,
        font: { color: textColor, size: fullscreen ? 15 : 12 },
      },
      xaxis: {
        title: {
          text: xAxisTitle,
          standoff: 28,
          font: { color: textColor, size: fullscreen ? 17 : 13 },
        },
        tickangle: tickAngle,
        tickfont: {
          color: textColor,
          size: fullscreen ? 14 : count > 32 ? 10 : 11,
        },
        gridcolor: GRID_COLOR,
        linecolor: AXIS_LINE_COLOR,
        automargin: true,
      },
      yaxis: {
        title: { text: yAxisTitle, font: { color: textColor, size: fullscreen ? 17 : 13 } },
        tickfont: { color: textColor, size: fullscreen ? 14 : 11 },
        gridcolor: GRID_COLOR,
        linecolor: AXIS_LINE_COLOR,
        zerolinecolor: "rgba(100, 116, 139, 0.55)",
        automargin: true,
      },
    };
    return { data: traces, layout: figureLayout };
  }, [
    rows,
    planName,
    factName,
    showDeviation,
    xAxisTitle,
    yAxisTitle,
    textColor,
    fullscreen,
  ]);

  // Панель инструментов как в [main] (`_PLOTLY_CONFIG`): PNG, зум, панорама,
  // выделение, автомасштаб, сброс; без логотипа Plotly.
  const config: Partial<Config> = {
    responsive: true,
    displayModeBar: true,
    displaylogo: false,
    scrollZoom: true,
    toImageButtonOptions: { format: "png", filename: "bdds", scale: 2 },
  };

  if (!rows.length) {
    return (
      <div className="flex h-[520px] items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        {emptyText}
      </div>
    );
  }

  return (
    <div className={fullscreen ? "h-full w-full overflow-x-auto" : "w-full"}>
      <div style={{ width: width ?? "100%", height }}>
        <PlotlyFigure
          data={data}
          layout={layout}
          config={config}
          className="w-full"
          style={{ width: "100%", height: "100%" }}
          useResizeHandler
        />
      </div>
    </div>
  );
}
