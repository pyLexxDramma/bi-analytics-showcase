"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import { ChartHtmlLegend } from "@/components/chart-html-legend";
import { DashboardEmptyState } from "@/components/dashboard-empty-state";
import { chartLegendHostFrom } from "@/lib/chart-legend-host";
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
  return <DashboardEmptyState message={message} className="h-64" />;
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
        width: contractors && !fullscreen ? chartWidth : undefined,
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

  const scrollEnabled = !!contractors;
  const pinRev = useMemo(
    () =>
      `${contractors}|${compact}|${fullscreen}|${rows.length}|${figure.layout.width ?? 0}|${figure.layout.height}`,
    [compact, contractors, figure.layout.height, figure.layout.width, fullscreen, rows.length],
  );
  const scrollWrapRef = usePinnedHScrollModebar(scrollEnabled && !compact, pinRev);

  if (!rows.length) return empty("Нет данных для графика.");
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
          style={{ width: contractors && !fullscreen ? "max-content" : "100%", height: "100%" }}
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
      ? 340
      : fullscreen
        ? Math.max(760, Math.min(window.innerHeight - 32, 980))
        : hasOutside
          ? 880
          : 780;
    // Вынесенные подписи мелких долей не должны обрезаться краем карточки.
    const pieMargin = compact
      ? hasOutside
        ? { l: 36, r: 36, t: 48, b: 48 }
        : { l: 8, r: 8, t: 8, b: 8 }
      : hasOutside
        ? { l: 56, r: 56, t: 72, b: 64 }
        : { l: 8, r: 8, t: 24, b: 24 };
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
          automargin: hasOutside,
          ...(hasOutside && !compact
            ? { domain: { x: [0.08, 0.92], y: [0.1, 0.9] } }
            : {}),
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
        margin: pieMargin,
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
                <button
                  type="button"
                  className="flex min-w-0 flex-1 items-start gap-2 text-left"
                  title="Скрыть/показать на графике"
                  onClick={(event) => {
                    chartLegendHostFrom(event.currentTarget)?.toggle(row.name);
                  }}
                >
                  <span
                    className="mt-1.5 h-2.5 w-2.5 shrink-0 rounded-full"
                    style={{ backgroundColor: PIE_COLORS[i % PIE_COLORS.length] }}
                    aria-hidden
                  />
                  <span className="min-w-0 flex-1 leading-snug">{row.name}</span>
                  <span className="shrink-0 tabular-nums text-tremor-content dark:text-dark-tremor-content">
                    {Math.round(value)} · {pct}%
                  </span>
                </button>
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
  tableSync = false,
  highlights = [],
}: {
  rows: Array<{ period: string; plan: number; fact: number }>;
  fullscreen?: boolean;
  /** Mobile: компактный холст, подписи на точках, горизонтальный скролл при «День». */
  compact?: boolean;
  tableSync?: boolean;
  /** Выбранные дни План/СКУД: вертикальная метка на графике-контексте. */
  highlights?: Array<{ period: string; label: string; color: string }>;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    // Сотни точек в 1150 px не влезают по-человечески: холст растёт в ширину,
    // а карточка получает горизонтальный скролл (как на мобиле при «День»).
    const scrollDense = rows.length > (compact ? 12 : 24);
    const pxPerPoint = compact ? 36 : 34;
    const baseWidth = compact ? 560 : 1150;
    const chartWidth = scrollDense
      ? Math.max(baseWidth, rows.length * pxPerPoint)
      : undefined;
    const layoutWidth = fullscreen ? undefined : chartWidth;
    const plotWidth =
      layoutWidth ??
      (fullscreen ? Math.max(900, window.innerWidth - 64) : baseWidth);
    // Подписи и даты прореживаем не «на глаз», а по фактической ширине холста.
    const labelPx = compact ? 26 : 30;
    const tickPx = compact ? 46 : 64;
    const maxLabels = Math.max(4, Math.floor(plotWidth / labelPx));
    const maxTicks = Math.max(3, Math.floor(plotWidth / tickPx));
    const labelStep = Math.max(1, Math.ceil(rows.length / maxLabels));
    const labelFont = compact ? 9 : 10;
    // Категории — всегда полный период: короткая подпись «11.08» повторяется в
    // 2026 и 2027, Plotly склеивает такие категории и линии превращаются в зигзаг.
    const x = rows.map((row) => row.period);
    const plan = rows.map((row) => row.plan);
    const fact = rows.map((row) => row.fact);
    const maximum = Math.max(1, ...plan, ...fact);
    // Выбранный день видно только при группировке «День»: иначе категории — недели/месяцы.
    const marks = highlights
      .map((h) => ({ ...h, at: h.period }))
      .filter((h) => h.at && x.includes(h.at));
    const markIdx = new Set(
      marks.map((m) => x.indexOf(m.at)).filter((i) => i >= 0),
    );
    const tickStep = Math.max(1, Math.ceil(rows.length / maxTicks));
    // Подписи оси сокращаем только визуально (ticktext), категории не трогаем.
    const tickIdx = x
      .map((_, i) => i)
      .filter(
        (i) => i % tickStep === 0 || i === x.length - 1 || markIdx.has(i),
      );
    const tickvals = tickIdx.map((i) => x[i]);
    const ticktext = tickIdx.map((i) =>
      compact ? shortPeriodLabel(x[i]) : x[i],
    );
    const height = compact
      ? 320
      : fullscreen
        ? Math.max(520, Math.min(window.innerHeight - 32, 760))
        : 440;
    // Нули не подписываем: на плотной оси они ложатся ровно на даты.
    const pointText = (values: number[]) =>
      values.map((value, i) =>
        (i % labelStep === 0 || i === values.length - 1 || markIdx.has(i)) &&
        Math.round(value) !== 0
          ? String(Math.round(value))
          : "",
      );
    // Plotly отбивает подпись от точки на радиус маркера — за счёт этого цифры
    // не ложатся на саму линию.
    const mode = "lines+markers+text" as const;
    const markerSize = scrollDense ? (compact ? 5 : 7) : compact ? 6 : 8;
    const markerColor = (color: string) => color;
    const lineWidth = compact ? 2 : 2.3;
    return {
      data: [
        {
          type: "scatter" as const,
          mode,
          name: "План",
          x,
          y: plan,
          text: pointText(plan),
          textposition: "top center" as const,
          textfont: { color: "#2563eb", size: labelFont },
          customdata: rows.map((row) => row.period),
          line: { color: "#2563eb", width: lineWidth },
          marker: {
            color: markerColor("#2563eb"),
            size: markerSize,
            line: { color: "#ffffff", width: 1 },
          },
          cliponaxis: false,
          hovertemplate: "<b>%{customdata}</b><br>План: %{y}<extra></extra>",
        },
        {
          type: "scatter" as const,
          mode,
          name: "Факт",
          x,
          y: fact,
          text: pointText(fact),
          textposition: "bottom center" as const,
          textfont: { color: "#ea580c", size: labelFont },
          customdata: rows.map((row) => row.period),
          line: { color: "#ea580c", width: lineWidth },
          marker: {
            color: markerColor("#ea580c"),
            size: markerSize,
            line: { color: "#ffffff", width: 1 },
          },
          cliponaxis: false,
          hovertemplate: "<b>%{customdata}</b><br>Факт: %{y}<extra></extra>",
        },
      ],
      layout: {
        width: layoutWidth,
        height,
        margin: compact
          ? { l: 40, r: 16, t: 28, b: 72 }
          : { l: 56, r: 36, t: 76, b: 72 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.paper,
        // Где подписи прорежены — значение читается наведением на дату.
        hovermode: labelStep > 1 ? ("x unified" as const) : (false as const),
        hoverlabel: {
          bgcolor: theme.dark ? "#0f172a" : "#ffffff",
          bordercolor: theme.grid,
          font: { size: compact ? 11 : 12, color: theme.label },
        },
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        showlegend: false,
        legend: plotlyLegendUnderLeft({
          fontSize: compact ? 11 : 12,
          y: -0.22,
        }),
        shapes: marks.map((m) => ({
          type: "line" as const,
          xref: "x" as const,
          yref: "paper" as const,
          x0: m.at,
          x1: m.at,
          y0: 0,
          y1: 1,
          line: { color: m.color, width: 2, dash: "dot" as const },
        })),
        annotations: marks.map((m, i) => ({
          x: m.at,
          xref: "x" as const,
          y: 1,
          yref: "paper" as const,
          yanchor: "bottom" as const,
          yshift: i * (compact ? 12 : 14),
          text: m.label,
          showarrow: false,
          font: { size: compact ? 9 : 10, color: m.color },
        })),
        xaxis: {
          title: compact ? undefined : "Период",
          // На широком холсте автозапас под подписи точек превращается в десятки
          // категорий пустоты слева — там фиксируем диапазон по данным.
          ...(scrollDense
            ? { range: [-0.5, Math.max(0.5, rows.length - 0.5)] }
            : {}),
          tickangle: -45,
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          gridcolor: theme.grid,
          ...(labelStep > 1
            ? {
                showspikes: true,
                spikemode: "across" as const,
                spikethickness: 1,
                spikedash: "dot" as const,
                spikecolor: theme.grid,
              }
            : {}),
          automargin: true,
          tickmode: "array" as const,
          tickvals,
          ticktext,
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
  }, [compact, fullscreen, highlights, rows, theme]);

  // Скролл — там, где холст шире контейнера (мобила и плотная динамика на desktop).
  const scrollEnabled = !fullscreen && rows.length > (compact ? 12 : 24);
  const pinRev = useMemo(
    () =>
      `${compact}|${fullscreen}|${rows.length}|${figure.layout.width ?? 0}|${figure.layout.height}`,
    [compact, figure.layout.height, figure.layout.width, fullscreen, rows.length],
  );
  const scrollWrapRef = usePinnedHScrollModebar(scrollEnabled, pinRev);

  // План уходит в будущее, факт кончается сегодня: открываем скролл на последнем
  // дне с фактом, иначе пользователь видит пустой «хвост» графика.
  const factEndIdx = useMemo(() => {
    let last = -1;
    rows.forEach((row, i) => {
      if (row.fact > 0) last = i;
    });
    return last;
  }, [rows]);

  useEffect(() => {
    if (!scrollEnabled) return;
    // При смене группировки Plotly перестраивает холст не мгновенно: ждём, пока
    // ширина совпадёт с расчётной, иначе позиция считается по старым точкам.
    const expected =
      typeof figure.layout.width === "number" ? figure.layout.width : null;
    const focus = (): boolean => {
      const el = scrollWrapRef.current;
      if (!el || el.scrollWidth <= el.clientWidth + 8) return false;
      if (expected !== null && Math.abs(el.scrollWidth - expected) > 2)
        return false;
      const idx = factEndIdx >= 0 ? factEndIdx + 1 : rows.length;
      const target =
        (el.scrollWidth * idx) / Math.max(1, rows.length) - el.clientWidth * 0.85;
      el.scrollLeft = Math.max(0, target);
      return true;
    };
    if (focus()) return;
    const timer = window.setInterval(() => {
      if (focus()) window.clearInterval(timer);
    }, 250);
    const stop = window.setTimeout(() => window.clearInterval(timer), 8000);
    return () => {
      window.clearInterval(timer);
      window.clearTimeout(stop);
    };
  }, [
    factEndIdx,
    figure.layout.width,
    pinRev,
    rows.length,
    scrollEnabled,
    scrollWrapRef,
  ]);

  if (!rows.length) return empty("Нет точек динамики.");
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
          tableSync={tableSync}
          useResizeHandler={!scrollEnabled}
          style={{
            width: scrollEnabled ? "max-content" : "100%",
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
