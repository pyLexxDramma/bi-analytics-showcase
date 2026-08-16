"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { ChartHtmlLegend } from "@/components/chart-html-legend";
import { PLOTLY_CONFIG, plotlyLegendUnderLeft } from "@/lib/plotly-config";

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

const PIE_COLORS = [
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
] as const;

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
  compact = false,
}: {
  rows: PlanFactRow[];
  contractors?: boolean;
  fullscreen?: boolean;
  /** Mobile: ниже холст, крупнее подписи категорий, горизонтальный скролл. */
  compact?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const labels = rows.map((row) => row.name);
    const deviations = rows.map((row) => Math.abs(row.deviation));
    const devColors = rows.map((row) =>
      row.deviation < 0 ? "#b91c1c" : row.deviation > 0 ? "#15803d" : "#6b7280",
    );
    const light = !theme.dark;
    const axisSz = compact
      ? 12
      : contractors
        ? light
          ? 22
          : 16
        : light
          ? 22
          : 12;
    const xTickSz = compact
      ? contractors
        ? 11
        : 13
      : contractors
        ? light
          ? 18
          : 14
        : light
          ? 44
          : 34;
    const labelSz = compact ? 11 : contractors ? (light ? 21 : 16) : light ? 18 : 14;
    const chartWidth = contractors
      ? Math.max(compact ? 820 : 1180, rows.length * (compact ? 112 : 128))
      : undefined;
    const height = compact
      ? contractors
        ? 400
        : 340
      : contractors
        ? fullscreen
          ? Math.max(560, Math.min(typeof window !== "undefined" ? window.innerHeight - 120 : 720, 900))
          : 640
        : fullscreen
          ? Math.max(560, Math.min(typeof window !== "undefined" ? window.innerHeight - 120 : 720, 760))
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
          textfont: { color: theme.dark ? "#93c5fd" : "#1e3a8a", size: labelSz },
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
          textfont: { color: theme.dark ? "#86efac" : "#14532d", size: labelSz },
          marker: { color: "#15803d" },
          cliponaxis: false,
          hovertemplate: "<b>%{x}</b><br>Факт: %{y}<extra></extra>",
        },
        {
          type: "bar" as const,
          name: compact ? "Отклонение" : "Отклонение (факт − план)",
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
          l: compact ? 40 : contractors ? 64 : 56,
          r: 16,
          t: compact ? 28 : 88,
          b: contractors
            ? compact
              ? 100
              : labels.length > 8
                ? 170
                : 130
            : compact
              ? 80
              : light
                ? 90
                : 72,
        },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        font: { family: "Inter, system-ui, sans-serif", color: theme.label },
        showlegend: false,
        legend: plotlyLegendUnderLeft({
          fontSize: compact ? 11 : contractors ? 16 : 13,
          labelColor: theme.label,
          y: -0.18,
        }),
        xaxis: {
          tickangle: contractors || (compact && labels.length > 3) ? -45 : 0,
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
          rangemode: "tozero" as const,
          tickfont: { size: axisSz, color: theme.label },
          automargin: true,
        },
        modebar: { bgcolor: "rgba(0,0,0,0)", color: theme.axis, activecolor: "#0f766e" },
      },
      config: {
        ...PLOTLY_CONFIG,
        ...(compact ? { displayModeBar: false } : {}),
      },
    };
  }, [compact, contractors, fullscreen, rows, theme]);

  if (!rows.length) return empty("Нет данных для графика.");
  return (
    <div>
      <div className={contractors ? "overflow-x-auto" : ""}>
        <PlotlyFigure
          data={figure.data}
          layout={figure.layout}
          config={figure.config}
          useResizeHandler
          style={{ width: contractors ? "max-content" : "100%", height: "100%" }}
        />
      </div>
      <ChartHtmlLegend
        compact={compact}
        items={[
          { name: "План", color: "#2563eb" },
          { name: "Факт", color: "#15803d" },
          {
            name: compact ? "Отклонение" : "Отклонение (факт − план)",
            short: "Отклонение",
            color: "#64748b",
          },
        ]}
      />
    </div>
  );
}

export function GdrsContractorsPieChart({
  rows,
  fullscreen = false,
  compact = false,
}: {
  rows: PieRow[];
  fullscreen?: boolean;
  compact?: boolean;
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
    const baseTxt = Math.max(compact ? 11 : 15, Math.min(compact ? 14 : 21, 23 - Math.floor(n / 2)));
    const txtIn = compact ? baseTxt : Math.round(baseTxt * 1.5);
    const txtOut = compact ? baseTxt - 1 : Math.round((baseTxt - 1) * 1.5);
    const height = compact
      ? 300
      : fullscreen
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
            colors: [...PIE_COLORS],
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
        margin: compact
          ? { l: 8, r: 8, t: 8, b: 8 }
          : { l: 8, r: 8, t: 24, b: 24 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        font: { family: "Inter, system-ui, sans-serif", color: theme.label },
        showlegend: false,
        legend: plotlyLegendUnderLeft({
          fontSize: 12,
          labelColor: theme.label,
          y: -0.08,
        }),
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: {
        ...PLOTLY_CONFIG,
        ...(compact ? { displayModeBar: false } : {}),
      },
    };
  }, [compact, fullscreen, rows, theme]);

  if (!rows.length) return empty("Нет данных по контрагентам.");
  const total = rows.reduce((s, row) => s + (Number(row.value) || 0), 0);
  return (
    <div>
      <PlotlyFigure
        data={figure.data}
        layout={figure.layout}
        config={figure.config}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
      {compact ? (
        <ul className="mt-3 max-h-56 space-y-1.5 overflow-y-auto pr-1 text-sm text-tremor-content-strong dark:text-dark-tremor-content-strong">
          {rows.map((row, i) => {
            const value = Number(row.value) || 0;
            const pct = total > 0 ? Math.round((value / total) * 100) : 0;
            return (
              <li key={`${row.name}-${i}`} className="flex items-start gap-2">
                <span
                  className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full"
                  style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                  aria-hidden
                />
                <span className="min-w-0 flex-1 leading-snug">{row.name}</span>
                <span className="shrink-0 tabular-nums text-tremor-content dark:text-dark-tremor-content">
                  {Math.round(value)} · {pct}%
                </span>
              </li>
            );
          })}
        </ul>
      ) : (
        <ChartHtmlLegend
          items={rows.map((row, i) => ({
            name: row.name,
            color: PIE_COLORS[i % PIE_COLORS.length],
          }))}
        />
      )}
    </div>
  );
}

function shortPeriodLabel(period: string): string {
  // "01.07.2026" → "01.07"; leave week/month labels as-is when short
  const m = period.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (m) return `${m[1]}.${m[2]}`;
  return period;
}

export function GdrsDynamicsLineChart({
  rows,
  fullscreen = false,
  compact = false,
}: {
  rows: Array<{ period: string; plan: number; fact: number }>;
  fullscreen?: boolean;
  /** Mobile: компактный холст, подписи на точках, горизонтальный скролл при «День». */
  compact?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const dense = rows.length > 12;
    // Цифры на точках и на мобиле; при плотном «День» — каждая 2-я
    const labelStep = compact && dense ? 2 : 1;
    const labelFont = compact ? 9 : 10;
    const x = rows.map((row) =>
      compact ? shortPeriodLabel(row.period) : row.period,
    );
    const plan = rows.map((row) => row.plan);
    const fact = rows.map((row) => row.fact);
    const maximum = Math.max(1, ...plan, ...fact);
    const chartWidth =
      compact && dense
        ? Math.max(560, rows.length * 36)
        : undefined;
    const height = compact
      ? 320
      : fullscreen
        ? Math.max(520, Math.min(window.innerHeight - 32, 760))
        : 440;
    const pointText = (values: number[]) =>
      values.map((value, i) =>
        i % labelStep === 0 || i === values.length - 1
          ? String(Math.round(value))
          : "",
      );
    return {
      data: [
        {
          type: "scatter" as const,
          mode: "lines+markers+text" as const,
          name: "План",
          x,
          y: plan,
          text: pointText(plan),
          textposition: "top center" as const,
          textfont: { color: "#2563eb", size: labelFont },
          customdata: rows.map((row) => row.period),
          line: { color: "#2563eb", width: compact ? 2 : 2.5 },
          marker: {
            color: "#2563eb",
            size: compact ? 6 : 8,
            line: { color: "#ffffff", width: 1 },
          },
          cliponaxis: false,
          hovertemplate: "<b>%{customdata}</b><br>План: %{y}<extra></extra>",
        },
        {
          type: "scatter" as const,
          mode: "lines+markers+text" as const,
          name: "Факт",
          x,
          y: fact,
          text: pointText(fact),
          textposition: "bottom center" as const,
          textfont: { color: "#ea580c", size: labelFont },
          customdata: rows.map((row) => row.period),
          line: { color: "#ea580c", width: compact ? 2 : 2.5 },
          marker: {
            color: "#ea580c",
            size: compact ? 6 : 8,
            line: { color: "#ffffff", width: 1 },
          },
          cliponaxis: false,
          hovertemplate: "<b>%{customdata}</b><br>Факт: %{y}<extra></extra>",
        },
      ],
      layout: {
        width: chartWidth,
        height,
        margin: compact
          ? { l: 40, r: 16, t: 28, b: 72 }
          : { l: 56, r: 36, t: 76, b: 72 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        hovermode: false as const,
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        showlegend: false,
        legend: plotlyLegendUnderLeft({
          fontSize: compact ? 11 : 12,
          y: -0.22,
        }),
        xaxis: {
          title: compact ? undefined : "Период",
          tickangle: -45,
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          gridcolor: theme.grid,
          automargin: true,
          ...(compact && !dense
            ? { nticks: Math.min(8, rows.length) }
            : {}),
        },
        yaxis: {
          title: compact ? undefined : "Среднее число в день",
          range: [0, maximum * (compact ? 1.14 : 1.16)],
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          gridcolor: theme.grid,
          zeroline: false,
        },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: {
        ...PLOTLY_CONFIG,
        ...(compact ? { displayModeBar: false } : {}),
      },
    };
  }, [compact, fullscreen, rows, theme]);

  if (!rows.length) return empty("Нет точек динамики.");
  return (
    <div>
      <div className={compact && rows.length > 12 ? "overflow-x-auto" : ""}>
        <PlotlyFigure
          data={figure.data}
          layout={figure.layout}
          config={figure.config}
          useResizeHandler
          style={{
            width: compact && rows.length > 12 ? "max-content" : "100%",
            height: "100%",
          }}
        />
      </div>
      <ChartHtmlLegend
        compact={compact}
        items={[
          { name: "План", color: "#2563eb" },
          { name: "Факт", color: "#ea580c" },
        ]}
      />
    </div>
  );
}
