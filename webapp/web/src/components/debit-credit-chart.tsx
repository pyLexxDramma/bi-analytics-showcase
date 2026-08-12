"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { PLOTLY_AXIS_LINE, PLOTLY_CONFIG, PLOTLY_ZEROLINE } from "@/lib/plotly-config";
import { useIsMobileViewport } from "@/lib/use-is-mobile";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => (
    <div className="flex h-72 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Загрузка диаграммы…
    </div>
  ),
});

export type DebitCreditContractorChartRow = {
  label: string;
  Аванс: number;
  "КС-2": number;
  "Отклонение ≥0": number;
  "Отклонение <0": number;
};

export type DebitCreditMetricChartRow = {
  label: string;
  value: number;
  color: string;
};

/** Как main `_DK_BAR_PX_SLOT` / `_DK_BAR_PX_SLOT_GROUP`. */
const SLOT_STACK_PX = 220;
const SLOT_GROUP_PX = 440;
const SCROLL_VP_PX = 1420;

const SERIES = {
  advance: { name: "Аванс", key: "Аванс", color: "#2E86AB" },
  ks2: { name: "КС-2", key: "КС-2", color: "#F1C40F" },
  positive: {
    name: "Отклонение, если больше или = 0",
    key: "Отклонение ≥0",
    color: "#95A5A6",
  },
  negative: {
    name: "Отклонение, если меньше 0",
    key: "Отклонение <0",
    color: "#F1948A",
  },
} as const;

const METRIC_LEGEND = [
  { name: "Договор стоимость", short: "Договор", color: "#2E86AB" },
  {
    name: "Всего выполненных обязательств по платежам",
    short: "Обязательства",
    color: "#95A5A6",
  },
  { name: "КС-2", short: "КС-2", color: "#B7950B" },
  { name: "Аванс", short: "Аванс", color: "#F7DC6F" },
  { name: "КС-2 − Аванс (≥ 0)", short: "КС−Ав ≥0", color: "#95A5A6" },
  { name: "КС-2 − Аванс (< 0)", short: "КС−Ав <0", color: "#F1948A" },
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
    axis: dark ? "#cbd5e1" : "#475569",
    label: dark ? "#e2e8f0" : "#111827",
    grid: dark ? "rgba(148,163,184,0.22)" : "#e2e8f0",
  };
}

/** Цифра + единица — как на замечании заказчика. */
function valueLabel(value: number): string {
  return Math.abs(value) >= 0.05 ? `${value.toFixed(1)} млн.руб` : "";
}

/** Как main `_dk_x_tick_labels`: wrap width 16, max 2 lines. */
function wrapTickLabel(raw: string): string {
  const s = raw.trim();
  if (!s) return "";
  const words = s.split(/\s+/);
  const lines: string[] = [];
  let cur = "";
  for (const w of words) {
    const next = cur ? `${cur} ${w}` : w;
    if (next.length <= 16) {
      cur = next;
    } else {
      if (cur) lines.push(cur);
      cur = w;
      if (lines.length >= 1) break;
    }
  }
  if (cur && lines.length < 2) lines.push(cur);
  return lines.join("<br>") || s;
}

function canvasWidth(n: number, grouped: boolean): { scroll: boolean; width: number } {
  const px = grouped ? SLOT_GROUP_PX : SLOT_STACK_PX;
  const content = n * px + 80;
  if (n >= 5) return { scroll: true, width: Math.min(18000, content) };
  if (content <= SCROLL_VP_PX) return { scroll: false, width: SCROLL_VP_PX };
  return { scroll: true, width: Math.min(18000, content) };
}

function isMetricRows(
  rows: Array<DebitCreditContractorChartRow | DebitCreditMetricChartRow>,
  aggregation: "by_contractor" | "by_metric",
): rows is DebitCreditMetricChartRow[] {
  return aggregation === "by_metric";
}

function niceDtick(peak: number, compact: boolean): number {
  const span = Math.max(peak, 0.01);
  const target = compact ? 5 : 8;
  const rough = span / target;
  const pow = 10 ** Math.floor(Math.log10(rough));
  const norm = rough / pow;
  const nice =
    norm <= 1 ? 1 : norm <= 2 ? 2 : norm <= 2.5 ? 2.5 : norm <= 5 ? 5 : 10;
  return nice * pow;
}

export function DebitCreditChart({
  rows,
  stacked,
  compact = false,
  aggregation = "by_contractor",
}: {
  rows: Array<DebitCreditContractorChartRow | DebitCreditMetricChartRow>;
  stacked: boolean;
  compact?: boolean;
  aggregation?: "by_contractor" | "by_metric";
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    if (isMetricRows(rows, aggregation)) {
      const labels = rows.map((row) => row.label);
      const values = rows.map((row) => row.value);
      const colors = rows.map((row) => row.color);
      const ticktext = labels.map(wrapTickLabel);
      const peak = Math.max(0.01, ...values.map((v) => Math.abs(v)));
      const negMin = Math.min(0, ...values);
      const yTop = peak * 1.14;
      const yBot =
        negMin < 0
          ? -(Math.abs(negMin) * 1.14 + Math.max(Math.abs(negMin) * 0.12, 0.8))
          : 0;
      const dtick = niceDtick(Math.max(yTop, Math.abs(yBot)), compact);
      const height = compact ? 360 : 720;
      // Для отрицательных столбцов «outside» уезжает вниз и пересекается с подписью оси X.
      const textPositions = values.map((v) => (v < 0 ? "inside" : "outside"));

      return {
        scroll: false,
        width: undefined as number | undefined,
        data: [
          {
            type: "bar" as const,
            x: labels,
            y: values,
            marker: { color: colors },
            width: 0.55,
            text: values.map(valueLabel),
            textposition: textPositions,
            textangle: 0,
            cliponaxis: false,
            constraintext: "none" as const,
            textfont: { size: compact ? 9 : 12, color: theme.label },
            hovertemplate: `<b>%{x}</b><br>%{y:.1f} млн руб.<extra></extra>`,
            showlegend: false,
          },
        ],
        layout: {
          height,
          autosize: true,
          barmode: "relative" as const,
          bargap: 0.28,
          showlegend: false,
          margin: compact
            ? { l: 56, r: 16, t: 28, b: 120 }
            : { l: 80, r: 40, t: 48, b: 140 },
          paper_bgcolor: "rgba(0,0,0,0)",
          plot_bgcolor: "rgba(0,0,0,0)",
          font: { family: "Inter, system-ui, sans-serif", color: theme.label },
          uniformtext: { minsize: 7, mode: "show" as const },
          xaxis: {
            type: "category" as const,
            categoryorder: "array" as const,
            categoryarray: labels,
            tickmode: "array" as const,
            tickvals: labels,
            ticktext,
            tickangle: 0,
            tickfont: { size: compact ? 11 : 12, color: theme.axis },
            automargin: true,
            ...PLOTLY_AXIS_LINE,
          },
          yaxis: {
            title: compact
              ? undefined
              : { text: "млн руб.", font: { size: 16, color: theme.axis } },
            range: [yBot, yTop],
            dtick,
            tick0: 0,
            nticks: compact ? 6 : 9,
            tickfont: { size: compact ? 11 : 14, color: theme.axis },
            gridcolor: theme.grid,
            automargin: true,
            separatethousands: true,
            ...PLOTLY_AXIS_LINE,
            ...PLOTLY_ZEROLINE,
          },
          modebar: {
            orientation: "v" as const,
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
    }

    const contractorRows = rows as DebitCreditContractorChartRow[];
    const n = Math.max(1, contractorRows.length);
    const labels = contractorRows.map((row) => row.label);
    const ticktext = labels.map(wrapTickLabel);
    const seriesOrder = stacked
      ? [SERIES.positive, SERIES.ks2, SERIES.advance]
      : [SERIES.advance, SERIES.ks2, SERIES.positive, SERIES.negative];

    const bargap = n >= 5 ? 0.1 : Math.max(0.05, Math.min(0.12, 1.6 / n));
    const bargroupgap = stacked ? 0.04 : seriesOrder.length > 1 ? 0.16 : 0.04;
    let barWidth: number;
    if (stacked) {
      barWidth = n === 1 ? 0.14 : 0.82;
    } else if (seriesOrder.length > 1) {
      barWidth = Math.min(
        0.82,
        Math.max(0.08, (0.82 * (1 - bargroupgap)) / seriesOrder.length),
      );
    } else {
      barWidth = n === 1 ? 0.14 : 0.82;
    }

    const traces: Array<Record<string, unknown>> = seriesOrder.map((series) => {
      const values = contractorRows.map((row) => row[series.key]);
      return {
        type: "bar" as const,
        x: labels,
        y: values,
        name: series.name,
        marker: { color: series.color },
        width: barWidth,
        text: values.map(valueLabel),
        textposition: stacked ? ("inside" as const) : ("outside" as const),
        insidetextanchor: stacked ? ("middle" as const) : undefined,
        textangle: 0,
        cliponaxis: false,
        constraintext: "none" as const,
        textfont: {
          size: compact ? 9 : stacked ? 11 : 11,
          color: stacked ? "#111827" : theme.label,
        },
        hovertemplate: `<b>%{x}</b><br>${series.name}: %{y:.1f} млн руб.<extra></extra>`,
        showlegend: true,
      };
    });

    const stackTops = contractorRows.map(
      (row) => row["Отклонение ≥0"] + row["КС-2"] + row.Аванс,
    );

    if (stacked) {
      traces.push({
        type: "scatter",
        mode: "text",
        x: labels,
        y: stackTops,
        text: stackTops.map((v) =>
          Math.abs(v) >= 0.05 ? valueLabel(v) : "",
        ),
        textposition: "top center",
        textfont: { size: compact ? 10 : 12, color: theme.label },
        hoverinfo: "skip",
        showlegend: false,
        cliponaxis: false,
      });
    }

    const groupPeaks = contractorRows.flatMap((row) => [
      row.Аванс,
      row["КС-2"],
      row["Отклонение ≥0"],
      Math.abs(row["Отклонение <0"]),
    ]);
    const peak = stacked
      ? Math.max(0.01, ...stackTops)
      : Math.max(0.01, ...groupPeaks);
    const negMin = stacked
      ? 0
      : Math.min(0, ...contractorRows.map((row) => row["Отклонение <0"]));
    const yTop = peak * (stacked ? 1.2 : 1.14);
    const yBot =
      negMin < 0 ? -(Math.abs(negMin) * 1.14 + Math.max(Math.abs(negMin) * 0.12, 0.8)) : 0;
    const dtick = niceDtick(Math.max(yTop, Math.abs(yBot)), compact);

    const { scroll, width } = compact
      ? { scroll: n > 6, width: Math.max(560, n * (stacked ? 140 : 220)) }
      : canvasWidth(n, !stacked);
    const height = compact
      ? 360
      : Math.max(720, Math.min(1120, 680 + n * 14));

    return {
      scroll,
      width: scroll ? width : undefined,
      data: traces,
      layout: {
        height,
        width: scroll ? width : undefined,
        autosize: !scroll,
        barmode: stacked ? ("stack" as const) : ("group" as const),
        bargap,
        bargroupgap,
        showlegend: false,
        margin: compact
          ? { l: 48, r: 16, t: stacked ? 36 : 28, b: 100 }
          : { l: 72, r: 40, t: 48, b: 120 },
        paper_bgcolor: "rgba(0,0,0,0)",
        plot_bgcolor: "rgba(0,0,0,0)",
        font: { family: "Inter, system-ui, sans-serif", color: theme.label },
        uniformtext: { minsize: 7, mode: "show" as const },
        xaxis: {
          type: "category" as const,
          categoryorder: "array" as const,
          categoryarray: labels,
          tickmode: "array" as const,
          tickvals: labels,
          ticktext,
          tickangle: 0,
          tickfont: { size: scroll || compact ? 11 : 12, color: theme.axis },
          automargin: true,
          ...PLOTLY_AXIS_LINE,
        },
        yaxis: {
          title: compact
            ? undefined
            : { text: "млн руб.", font: { size: 16, color: theme.axis } },
          range: [yBot, yTop],
          dtick,
          tick0: 0,
          tickfont: { size: compact ? 11 : 14, color: theme.axis },
          gridcolor: theme.grid,
          automargin: true,
          ...PLOTLY_AXIS_LINE,
          ...PLOTLY_ZEROLINE,
        },
        modebar: {
          orientation: "v" as const,
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
  }, [aggregation, compact, rows, stacked, theme]);

  if (!rows.length) {
    return (
      <div className="flex h-72 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет данных для диаграммы.
      </div>
    );
  }

  return (
    <div className={figure.scroll ? "overflow-x-auto" : undefined}>
      <PlotlyFigure
        data={figure.data}
        layout={figure.layout}
        config={figure.config}
        useResizeHandler={!figure.scroll}
        style={{
          width: figure.width ? `${figure.width}px` : "100%",
          height: `${figure.layout.height}px`,
          minWidth: figure.scroll ? `${figure.width}px` : undefined,
        }}
      />
    </div>
  );
}

/** Легенда под графиком. */
export function DebitCreditChartLegend({
  stacked,
  aggregation = "by_contractor",
}: {
  stacked: boolean;
  aggregation?: "by_contractor" | "by_metric";
}) {
  const mobile = useIsMobileViewport();
  const items =
    aggregation === "by_metric"
      ? METRIC_LEGEND.map((item) => ({
          name: item.name,
          short: item.short,
          color: item.color,
        }))
      : stacked
        ? [
            { name: "Отклонение, если больше или = 0", short: "Откл. ≥0", color: "#95A5A6" },
            { name: "КС-2", short: "КС-2", color: "#F1C40F" },
            { name: "Аванс", short: "Аванс", color: "#2E86AB" },
          ]
        : [
            { name: "Аванс", short: "Аванс", color: "#2E86AB" },
            { name: "КС-2", short: "КС-2", color: "#F1C40F" },
            { name: "Отклонение, если больше или = 0", short: "Откл. ≥0", color: "#95A5A6" },
            { name: "Отклонение, если меньше 0", short: "Откл. <0", color: "#F1948A" },
          ];
  return (
    <div
      className={
        mobile
          ? "mt-2 flex flex-wrap items-center justify-start gap-x-3 gap-y-1 px-0.5 text-[11px] leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong"
          : "mt-2 flex flex-wrap items-center justify-start gap-x-4 gap-y-1.5 px-1 text-xs text-tremor-content-strong dark:text-dark-tremor-content-strong"
      }
    >
      {items.map((item) => (
        <span key={item.name} className="inline-flex max-w-full items-center gap-1.5">
          <span
            className={
              mobile
                ? "inline-block h-2.5 w-2.5 shrink-0 rounded-sm"
                : "inline-block h-3.5 w-3.5 shrink-0 rounded-sm"
            }
            style={{ background: item.color }}
            aria-hidden
          />
          <span className="min-w-0 break-words">{mobile ? item.short : item.name}</span>
        </span>
      ))}
    </div>
  );
}
