"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { ChartHtmlLegend } from "@/components/chart-html-legend";
import { DashboardEmptyState } from "@/components/dashboard-empty-state";
import { PLOTLY_CONFIG, plotlyLegendUnderLeft } from "@/lib/plotly-config";
import { usePinnedHScrollModebar } from "@/lib/use-pinned-hscroll-modebar";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Загрузка диаграммы…
    </div>
  ),
});

type ByContractor = {
  contractor: string;
  total: number;
  overdue: number;
  /** Неустранённые — ключ сортировки диаграммы сверху вниз. */
  unresolved?: number;
};
type ByStatus = { status: string; value: number; share_pct: number };
type ByObject = { object: string; total: number } & Record<string, number | string>;

export const PRED_PIE_STATUS_COLOR: Record<string, string> = {
  "Остановка работ": "#722F37",
  Критические: "#e74c3c",
  "Не устранено": "#e67e22",
  "Сдано в срок": "#2ecc71",
  "Устранено с просрочкой": "#f1c40f",
};

export const PRED_OBJECT_STATUS_COLOR: Record<string, string> = {
  "Остановка работ": "#922b3e",
  Критические: "#e74c3c",
  "Не устранено": "#e67e22",
  "Сдано в срок": "#2ecc71",
  "Устранено с просрочкой": "#f1c40f",
};

/** Контраст цифры внутри сегмента: на жёлтом белый не читается. */
function predSegmentLabelColor(status: string): string {
  return status === "Устранено с просрочкой" ? "#1e293b" : "#ffffff";
}

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

function empty(message: string) {
  return <DashboardEmptyState message={message} className="h-64" />;
}

function axisUpperBound(xmax: number): number {
  if (!Number.isFinite(xmax) || xmax <= 0) return 5;
  if (xmax <= 5) return 5;
  if (xmax <= 10) return 10;
  if (xmax <= 25) return Math.ceil(xmax / 5) * 5;
  if (xmax <= 100) return Math.ceil(xmax / 10) * 10;
  return Math.ceil(xmax / 25) * 25;
}

function sparseBargap(n: number): { bargap: number; bargroupgap: number } | Record<string, never> {
  if (n <= 2) return { bargap: 0.84, bargroupgap: 0.24 };
  if (n <= 4) return { bargap: 0.66, bargroupgap: 0.17 };
  return {};
}

/**
 * Высота сегментов для отрисовки: мелкие не тоньше ~9% столбца (цифры влезают
 * и центрируются), сумма по столбцу = исходный total.
 */
function stackDisplayHeights(raw: number[]): number[] {
  const total = raw.reduce((sum, value) => sum + value, 0);
  if (total <= 0) return raw.map(() => 0);
  const nPos = raw.filter((value) => value > 0).length;
  if (nPos <= 1) return raw.slice();
  const minShare = Math.min(0.09, 0.36 / nPos);
  const minHeight = total * minShare;
  const floors = raw.map((value) => (value > 0 ? Math.max(value, minHeight) : 0));
  const floorSum = floors.reduce((sum, value) => sum + value, 0);
  return floors.map((value) => (value * total) / floorSum);
}

/** Горизонтальный бар «Предписания по подрядчикам» — фон=всего/неустранено, оранжевый сегмент=просроченные, синий пузырёк=итог. 1:1 с main `dashboard_predpisania`. */
export function PrescriptionsContractorChart({
  rows,
  hideResolved,
  fullscreen = false,
  compact = false,
}: {
  rows: ByContractor[];
  hideResolved: boolean;
  fullscreen?: boolean;
  compact?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    // Сверху вниз: больше неустранённых → меньше. Plotly h-bar: первая категория внизу → reverse.
    const ordered = [...rows]
      .sort((a, b) => {
        const aKey = a.unresolved ?? a.total ?? 0;
        const bKey = b.unresolved ?? b.total ?? 0;
        if (bKey !== aKey) return bKey - aKey;
        const byTotal = (b.total ?? 0) - (a.total ?? 0);
        if (byTotal !== 0) return byTotal;
        const byOverdue = (b.overdue ?? 0) - (a.overdue ?? 0);
        if (byOverdue !== 0) return byOverdue;
        return String(a.contractor).localeCompare(String(b.contractor), "ru");
      })
      .reverse();
    const y = ordered.map((row) => row.contractor);
    const totals = ordered.map((row) => row.total);
    const overdues = ordered.map((row) => row.overdue);
    const xmax = Math.max(...totals, 1);
    const axisUpper = axisUpperBound(xmax);
    const bubbleShift = Math.max(axisUpper * 0.06, 0.5);
    const height = compact
      ? Math.max(240, ordered.length * 44 + 80)
      : fullscreen
        ? Math.max(420, Math.min(window.innerHeight - 32, ordered.length * 64 + 200))
        : Math.max(280, ordered.length * 64 + 200);
    const title = hideResolved
      ? "Неустранённые предписания по подрядчикам"
      : "Все предписания по подрядчикам";
    const cntWord = hideResolved ? "Неустранённых" : "Всего";

    return {
      data: [
        {
          type: "bar" as const,
          orientation: "h" as const,
          y,
          x: totals,
          marker: {
            color: "rgba(230,126,34,0.22)",
            line: { color: "rgba(230,126,34,0.55)", width: 1 },
          },
          customdata: ordered.map((row) => row.overdue),
          hovertemplate:
            `<b>%{y}</b><br>${cntWord}: %{x}<br>Просроченных: %{customdata}<extra></extra>`,
          showlegend: false,
        },
        {
          type: "bar" as const,
          orientation: "h" as const,
          y,
          x: overdues,
          marker: {
            color: "#E67E22",
            line: { color: "rgba(255,255,255,0.18)", width: 1 },
          },
          text: overdues.map((v) => (v > 0 ? String(v) : "")),
          textposition: "inside" as const,
          insidetextanchor: "middle" as const,
          textangle: 0,
          textfont: { color: "#ffffff", size: compact ? 11 : 14 },
          hovertemplate: "<b>%{y}</b><br>Просроченных: %{x}<extra></extra>",
          showlegend: false,
        },
        {
          type: "scatter" as const,
          mode: "markers+text" as const,
          y,
          x: totals.map((v) => v + bubbleShift),
          marker: {
            size: compact ? 22 : 34,
            color: "#3498db",
            line: { color: "rgba(255,255,255,0.45)", width: 2 },
            symbol: "circle" as const,
          },
          text: totals.map((v) => String(v)),
          textfont: { color: "#ffffff", size: compact ? 10 : 13 },
          textposition: "middle center" as const,
          hovertemplate: `<b>%{y}</b><br>${cntWord}: %{text}<extra></extra>`,
          showlegend: false,
        },
      ],
      layout: {
        height,
        bargap: 0.3,
        barmode: "overlay" as const,
        showlegend: false,
        margin: compact
          ? { l: 8, r: 44, t: 40, b: 40 }
          : { l: 12, r: 80, t: 64, b: 72 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        font: { family: "Inter, system-ui, sans-serif", color: theme.label },
        title: compact
          ? undefined
          : {
              text: title,
              font: { size: 16, color: theme.label },
              x: 0.5,
              xanchor: "center" as const,
            },
        xaxis: {
          range: [0, axisUpper + bubbleShift * 2],
          title: compact
            ? undefined
            : {
                text: "Количество (столбец — всего, оранжевый сегмент — просроченные)",
                standoff: 18,
                font: { size: 12, color: theme.axis },
              },
          automargin: true,
          fixedrange: false,
          tickfont: { color: theme.axis },
        },
        yaxis: {
          categoryorder: "array" as const,
          categoryarray: y,
          automargin: true,
          tickfont: { size: compact ? 11 : 14, color: theme.label },
          fixedrange: false,
        },
        uniformtext: { minsize: 11, mode: "show" as const },
        modebar: { bgcolor: "rgba(0,0,0,0)", color: theme.axis, activecolor: "#0f766e" },
      },
      config: {
        ...PLOTLY_CONFIG,
        ...(compact ? { displayModeBar: false } : {}),
      },
    };
  }, [compact, fullscreen, hideResolved, rows, theme]);

  if (!rows.length) return empty("Нет данных для диаграммы.");
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

/** Круговая диаграмма по статусам (5 взаимоисключающих бакетов) — 1:1 с main `_pred_build_status_pie_df`. */
export function PrescriptionsStatusPieChart({
  rows,
  fullscreen = false,
  compact = false,
}: {
  rows: ByStatus[];
  fullscreen?: boolean;
  compact?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const n = rows.length;
    const labels = rows.map((row) => `${row.status} (${row.share_pct.toFixed(1)}%)`);
    const values = rows.map((row) => row.value);
    const colors = rows.map((row) => PRED_PIE_STATUS_COLOR[row.status] ?? "#94a3b8");
    const pctFontSize = compact ? 13 : n <= 6 ? 26 : 22;
    const height = compact
      ? Math.max(260, 220 + n * 20)
      : fullscreen
        ? Math.max(560, Math.min(window.innerHeight - 32, 900))
        : Math.max(560, 480 + n * 28);
    return {
      data: [
        {
          type: "pie" as const,
          labels,
          values,
          hole: 0,
          sort: false,
          direction: "clockwise" as const,
          marker: { colors, line: { color: "rgba(0,0,0,0)", width: 0 } },
          textinfo: "percent" as const,
          texttemplate: "%{percent:.0%}",
          textposition: "inside" as const,
          insidetextorientation: "horizontal" as const,
          textfont: { color: "#ffffff", size: pctFontSize },
          customdata: rows.map((row) => [row.status, row.share_pct]),
          hovertemplate:
            "<b>%{customdata[0]}</b><br>Количество: %{value}<br>Доля: %{customdata[1]:.1f}%<extra></extra>",
        },
      ],
      layout: {
        height,
        margin: compact ? { l: 8, r: 8, t: 8, b: 24 } : { l: 44, r: 44, t: 44, b: 40 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        font: { family: "Inter, system-ui, sans-serif", color: theme.label },
        showlegend: false,
        legend: plotlyLegendUnderLeft({
          fontSize: compact ? 11 : 12,
          labelColor: theme.label,
          y: -0.1,
        }),
        uniformtext: { minsize: 10, mode: "show" as const },
        modebar: { bgcolor: "rgba(0,0,0,0)", color: theme.axis, activecolor: "#0f766e" },
      },
      config: {
        ...PLOTLY_CONFIG,
        ...(compact ? { displayModeBar: false } : {}),
      },
    };
  }, [compact, fullscreen, rows, theme]);

  if (!rows.length) return empty("Нет данных для круговой диаграммы по статусам.");
  return (
    <div>
      <PlotlyFigure
        data={figure.data}
        layout={figure.layout}
        config={figure.config}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
      <ChartHtmlLegend
        compact={compact}
        items={rows.map((row) => ({
          name: row.status,
          color: PRED_PIE_STATUS_COLOR[row.status] ?? "#94a3b8",
        }))}
      />
    </div>
  );
}

/** Стек-бар «Предписания по объектам» с подписью суммы над столбцом — 1:1 с main `_pred_objects_by_status_figure`. */
export function PrescriptionsObjectsChart({
  rows,
  statusKeys,
  fullscreen = false,
  compact = false,
}: {
  rows: ByObject[];
  statusKeys: string[];
  fullscreen?: boolean;
  compact?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const x = rows.map((row) => String(row.object));
    const n = x.length;
    const chartWidth = compact && n > 6 ? Math.max(560, n * 96) : undefined;
    // Выше график — сегменты выше в пикселях, цифры чаще помещаются внутрь.
    const height = compact
      ? 380
      : fullscreen
        ? Math.max(560, Math.min(window.innerHeight - 32, 820))
        : 640;
    const ymax = Math.max(...rows.map((row) => Number(row.total) || 0), 0);
    const axisUpper = ymax > 0 ? axisUpperBound(ymax) : 5;

    const rawByRow = rows.map((row) =>
      statusKeys.map((status) => Number(row[status] ?? 0) || 0),
    );
    const displayByRow = rawByRow.map(stackDisplayHeights);

    const data = statusKeys.map((status, statusIdx) => {
      const realVals = rawByRow.map((raw) => raw[statusIdx] ?? 0);
      const displayVals = displayByRow.map((display) => display[statusIdx] ?? 0);
      return {
        type: "bar" as const,
        x,
        y: displayVals,
        name: status,
        marker: { color: PRED_OBJECT_STATUS_COLOR[status] ?? "#94a3b8" },
        customdata: realVals,
        text: realVals.map((value) => (value > 0 ? String(value) : "")),
        texttemplate: "%{text}",
        textposition: "inside" as const,
        insidetextanchor: "middle" as const,
        constraintext: "none" as const,
        cliponaxis: false,
        textangle: 0,
        textfont: {
          color: predSegmentLabelColor(status),
          size: compact ? 11 : 14,
        },
        hovertemplate: `<b>%{x}</b><br>${status}: %{customdata}<extra></extra>`,
      };
    });

    const totalAnnotations = rows
      .filter((row) => Number(row.total) > 0)
      .map((row) => ({
        x: String(row.object),
        y: Number(row.total),
        text: `<b>${row.total}</b>`,
        showarrow: false,
        xref: "x" as const,
        yref: "y" as const,
        xanchor: "center" as const,
        yanchor: "bottom" as const,
        yshift: 14,
        font: { color: theme.label, size: compact ? 12 : 16 },
      }));

    const annotations = totalAnnotations;

    return {
      data,
      layout: {
        width: chartWidth,
        height,
        barmode: "stack" as const,
        xaxis: {
          title: "",
          categoryorder: "array" as const,
          categoryarray: x,
          tickangle: 0,
          tickfont: { size: compact ? 11 : 16, color: theme.label },
          fixedrange: false,
        },
        yaxis: {
          title: compact ? undefined : { text: "Количество", font: { color: theme.axis } },
          range: [0, axisUpper * 1.1],
          fixedrange: false,
          tickfont: { color: theme.axis },
        },
        showlegend: false,
        legend: plotlyLegendUnderLeft({
          fontSize: compact ? 10 : 12,
          labelColor: theme.label,
          y: -0.14,
        }),
        annotations,
        margin: compact
          ? { l: 48, r: 48, t: 44, b: 64 }
          : { l: 64, r: 72, t: 56, b: 88 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        font: { family: "Inter, system-ui, sans-serif", color: theme.label },
        uniformtext: { minsize: 10, mode: "show" as const },
        modebar: { bgcolor: "rgba(0,0,0,0)", color: theme.axis, activecolor: "#0f766e" },
        ...sparseBargap(n),
      },
      config: {
        ...PLOTLY_CONFIG,
        ...(compact ? { displayModeBar: false } : {}),
      },
    };
  }, [compact, fullscreen, rows, statusKeys, theme]);

  const scrollEnabled = !!(compact && rows.length > 6);
  const pinRev = useMemo(
    () =>
      `${compact}|${fullscreen}|${rows.length}|${statusKeys.join(",")}|${figure.layout.height}`,
    [compact, figure.layout.height, fullscreen, rows.length, statusKeys],
  );
  const scrollWrapRef = usePinnedHScrollModebar(scrollEnabled, pinRev);

  if (!rows.length) return empty("Нет данных для диаграммы по объектам.");
  return (
    <div>
      <div
        ref={scrollWrapRef}
        className={scrollEnabled ? "relative overflow-x-auto" : undefined}
      >
        <PlotlyFigure
          data={figure.data}
          layout={figure.layout}
          config={figure.config}
          useResizeHandler={!scrollEnabled}
          style={{ width: scrollEnabled ? "max-content" : "100%", height: "100%" }}
        />
      </div>
      <ChartHtmlLegend
        compact={compact}
        items={statusKeys.map((status) => ({
          name: status,
          color: PRED_OBJECT_STATUS_COLOR[status] ?? "#94a3b8",
        }))}
      />
    </div>
  );
}
