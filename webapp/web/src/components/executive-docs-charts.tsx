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

type CountRow = { contractor?: string; status?: string; object?: string; period?: string; count?: number; new_docs?: number };

const STATUS_COLORS: Record<string, string> = {
  "На согласовании": "#ff9800",
  "На доработке": "#ffc107",
  Отказ: "#f44336",
  Подписан: "#4caf50",
  Согласован: "#4caf50",
};

function statusBarColor(status: string | undefined): string {
  const sl = String(status ?? "").trim().toLowerCase();
  if (
    sl.includes("на согласовани") ||
    sl.includes("на подписани") ||
    sl.includes("у заказчик")
  ) {
    return "#ff9800";
  }
  if (sl.includes("доработ")) return "#ffc107";
  if (sl.includes("отказ") || sl.includes("не сдан")) return "#f44336";
  if (sl.includes("подписан") || sl.includes("согласован") || sl.includes("принят")) {
    return "#4caf50";
  }
  return STATUS_COLORS[status ?? ""] ?? "#9e9e9e";
}

function useChartOptions() {
  const [dark, setDark] = useState(false);
  const [compact, setCompact] = useState(false);
  useEffect(() => {
    const root = document.documentElement;
    const query = window.matchMedia("(max-width: 1023px)");
    const sync = () => {
      setDark(root.classList.contains("dark"));
      setCompact(query.matches);
    };
    sync();
    const observer = new MutationObserver(sync);
    observer.observe(root, { attributes: true, attributeFilter: ["class"] });
    query.addEventListener("change", sync);
    return () => {
      observer.disconnect();
      query.removeEventListener("change", sync);
    };
  }, []);
  return {
    compact,
    axis: dark ? "#cbd5e1" : "#334155",
    label: dark ? "#e2e8f0" : "#111827",
    grid: dark ? "rgba(148,163,184,0.22)" : "#e5e7eb",
    paper: "rgba(0,0,0,0)",
  };
}

function EmptyChart() {
  return <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">Нет данных для диаграммы.</div>;
}

function Chart({ data, xTitle, color, rows, horizontal = false }: { data: CountRow[]; xTitle: string; color: string | string[]; rows: CountRow[]; horizontal?: boolean }) {
  const theme = useChartOptions();
  const figure = useMemo(() => {
    const labels = rows.map((row) => row.contractor ?? row.status ?? row.object ?? row.period ?? "—");
    const values = rows.map((row) => Number(row.count ?? row.new_docs ?? 0));
    const height = horizontal
      ? Math.max(theme.compact ? 260 : 280, rows.length * (theme.compact ? 34 : 32) + 120)
      : theme.compact ? 320 : 450;
    return {
      data: [{
        type: "bar" as const,
        orientation: horizontal ? ("h" as const) : ("v" as const),
        x: horizontal ? values : labels,
        y: horizontal ? labels : values,
        marker: { color },
        text: values.map(String),
        textposition: "outside" as const,
        textfont: { size: theme.compact ? 11 : 13, color: theme.label },
        cliponaxis: false,
        hovertemplate: horizontal ? "<b>%{y}</b><br>Количество: %{x}<extra></extra>" : "<b>%{x}</b><br>Количество: %{y}<extra></extra>",
        showlegend: false,
      }],
      layout: {
        height,
        margin: horizontal
          ? { l: theme.compact ? 84 : 120, r: 36, t: 28, b: 48 }
          : { l: 52, r: 28, t: 42, b: theme.compact ? 92 : 120 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        font: { family: "Inter, system-ui, sans-serif", color: theme.label },
        bargap: rows.length <= 4 ? 0.62 : 0.28,
        xaxis: horizontal
          ? { title: "", gridcolor: theme.grid, tickfont: { color: theme.axis }, zeroline: false }
          : { title: xTitle, tickangle: xTitle === "Объект" ? -45 : -35, tickfont: { color: theme.axis, size: theme.compact ? 10 : 12 }, categoryorder: "array" as const, categoryarray: labels },
        yaxis: horizontal
          ? { title: "", tickfont: { color: theme.label, size: theme.compact ? 10 : 12 }, categoryorder: "array" as const, categoryarray: labels }
          : { title: "Количество", gridcolor: theme.grid, tickfont: { color: theme.axis }, rangemode: "tozero" as const },
        modebar: { bgcolor: "rgba(0,0,0,0)", color: theme.axis, activecolor: "#0f766e" },
      },
      config: { ...PLOTLY_CONFIG, ...(theme.compact ? { displayModeBar: false } : {}) },
    };
  }, [color, horizontal, rows, theme]);
  if (!data.length) return <EmptyChart />;
  return <PlotlyFigure data={figure.data} layout={figure.layout} config={figure.config} useResizeHandler style={{ width: "100%", height: "100%" }} />;
}

export function ExecutiveOverdueChart({ rows, customer }: { rows: CountRow[]; customer?: boolean }) {
  return <Chart data={rows} rows={rows} xTitle="Количество" color={customer ? "#fbbf24" : "#f87171"} horizontal />;
}

export function ExecutiveStatusChart({ rows }: { rows: CountRow[] }) {
  return (
    <Chart
      data={rows}
      rows={rows}
      xTitle="Статус"
      color={rows.map((row) => statusBarColor(row.status))}
    />
  );
}

export function ExecutiveObjectsChart({ rows }: { rows: CountRow[] }) {
  return <Chart data={rows} rows={rows} xTitle="Объект" color="#06A77D" />;
}

export function ExecutiveDynamicsChart({ rows }: { rows: CountRow[] }) {
  return <Chart data={rows} rows={rows} xTitle="Период" color="#60a5fa" />;
}
