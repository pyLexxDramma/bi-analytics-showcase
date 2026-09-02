"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { ProjectDocumentationPayload } from "@/lib/api";
import { ChartHtmlLegend } from "@/components/chart-html-legend";
import { DashboardEmptyState } from "@/components/dashboard-empty-state";
import { stripProjectPrefixIfSingle, uniquePlotCategories, wrapAxisLabel, monthlyPlanFactDeltaAnnotations } from "@/lib/chart-labels";
import { CHART_RU } from "@/lib/chart-ru";
import { PLOTLY_CONFIG, plotlyLegendUnderLeft } from "@/lib/plotly-config";
import { useIsMobileViewport } from "@/lib/use-is-mobile";

const PlotlyFigure = dynamic(() => import("@/components/plotly-figure"), {
  ssr: false,
  loading: () => (
    <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Загрузка диаграммы…
    </div>
  ),
});

/** Цвета линий как main (`GDRS_THEME_DARK` + `_PD_FACT_LINE_COLOR`). */
const PD_PLAN = "#29b6f6";
const PD_FCST = "#ff8c2d";
const PD_FACT = "#27AE60";
const PD_MONTH_PLAN = "#F39C12";
const PD_MONTH_FACT = "#27AE60";
const PD_MONTH_OVERDUE = "#C0392B";

type StatusMix = ProjectDocumentationPayload["tremor"]["status_mix"][number];
type DynamicsRow = ProjectDocumentationPayload["tremor"]["dynamics"][number];
type MonthlyRow = ProjectDocumentationPayload["tremor"]["monthly"][number];
type GanttRow = ProjectDocumentationPayload["delay"]["gantt"]["rows"][number];

const DAY_MS = 86_400_000;
const PD_GANTT_YELLOW = "#F1C40F";
const PD_GANTT_GREEN = "#27AE60";
const PD_GANTT_RED = "#C0392B";

function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function barLenMs(startIso: string | null | undefined, endIso: string | null | undefined): number | null {
  const s = toMs(startIso);
  const e = toMs(endIso);
  if (s == null || e == null || e < s) return null;
  const ms = e - s;
  return ms > 0 ? ms : DAY_MS;
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
    label: dark ? "#e8eef5" : "#111827",
    paper: "rgba(0,0,0,0)",
    plot: "rgba(0,0,0,0)",
    grid: dark ? "rgba(148,163,184,0.22)" : "rgba(148,163,184,0.35)",
  };
}

function pointLabel(v: number | null | undefined): string {
  if (v == null || !Number.isFinite(v) || v === 0) return "";
  return String(Math.round(v));
}

/** Pie «Исполнение ПД» как main Plotly (%, легенда слева через внешний UI). */
export function PdExecutionPieChart({
  rows,
  fullscreen = false,
}: {
  rows: StatusMix[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const figure = useMemo(() => {
    const height = fullscreen
      ? Math.max(520, Math.min(window.innerHeight * 0.6, 720))
      : 420;
    const labels = rows.map((r) => r.name);
    const values = rows.map((r) => r.value);
    const colors = rows.map((r, i) => {
      if (r.color) return r.color;
      if (r.name.includes("Заверш")) return "#2E86AB";
      if (r.name.includes("работ")) return "#F59E0B";
      return ["#E74C3C", "#94a3b8", "#8bc34a"][i % 3];
    });
    return {
      data: [
        {
          type: "pie" as const,
          labels,
          values,
          sort: false,
          direction: "clockwise" as const,
          hole: 0,
          marker: { colors, line: { color: "#fff", width: 1 } },
          textinfo: "percent" as const,
          textposition: "inside" as const,
          insidetextorientation: "horizontal" as const,
          textfont: { size: fullscreen ? 18 : 15, color: "#ffffff" },
          hovertemplate:
            "<b>%{label}</b><br>Количество: %{value}<br>Доля: %{percent}<extra></extra>",
          showlegend: false,
        },
      ],
      layout: {
        height,
        margin: { l: 8, r: 8, t: 8, b: 8 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        showlegend: false,
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG, scrollZoom: false },
    };
  }, [rows, fullscreen, theme]);

  if (!rows.length) {
    return <DashboardEmptyState message="Нет данных по исполнению." className="h-64" />;
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

/** Line «Динамика выдачи ПД»: lines+markers+text как main. */
export function PdDynamicsLineChart({
  rows,
  fullscreen = false,
}: {
  rows: DynamicsRow[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const mobile = useIsMobileViewport();
  const compact = mobile && !fullscreen;
  const figure = useMemo(() => {
    const height = fullscreen
      ? Math.max(520, Math.min(window.innerHeight * 0.62, 760))
      : compact
        ? 360
        : 420;
    const x = rows.map((r) => r.period_label || r.period);
    const plan = rows.map((r) =>
      r.plan_bp == null || Number.isNaN(Number(r.plan_bp))
        ? null
        : Number(r.plan_bp),
    );
    const forecast = rows.map((r) =>
      r.forecast == null || Number.isNaN(Number(r.forecast))
        ? null
        : Number(r.forecast),
    );
    const fact = rows.map((r) =>
      r.fact == null || Number.isNaN(Number(r.fact)) ? null : Number(r.fact),
    );
    const yMax = Math.max(
      1,
      ...plan.map((v) => Number(v) || 0),
      ...forecast.map((v) => (v == null ? 0 : v)),
      ...fact.map((v) => Number(v) || 0),
    );
    const yHead = Math.max(yMax * (compact ? 0.08 : 0.1), 4);
    const tickStep = Math.max(1, Math.ceil(x.length / (compact ? 8 : 12)));
    const tickvals: string[] = [];
    const ticktext: string[] = [];
    for (let i = 0; i < x.length; i += tickStep) {
      tickvals.push(x[i]);
      ticktext.push(x[i]);
    }
    if (x.length && tickvals[tickvals.length - 1] !== x[x.length - 1]) {
      tickvals.push(x[x.length - 1]);
      ticktext.push(x[x.length - 1]);
    }
    const mk = (
      y: Array<number | null>,
      name: string,
      color: string,
      width: number,
      markerSize: number,
      opts?: { dash?: string },
    ): Record<string, unknown> => ({
      type: "scatter",
      mode: compact ? "lines+markers" : "lines+markers+text",
      name,
      x,
      y,
      connectgaps: false,
      ...(compact
        ? {}
        : {
            text: y.map((v) => (v == null ? "" : pointLabel(v))),
            textposition: "top center",
            textfont: { color, size: 10 },
          }),
      line: {
        color,
        width,
        ...(opts?.dash ? { dash: opts.dash } : {}),
      },
      marker: { size: markerSize, color, line: { width: 1, color: "#fff" } },
      cliponaxis: false,
      hovertemplate: `<b>%{x}</b><br>${name}: %{y}<extra></extra>`,
    });
    return {
      data: [
        mk(plan, CHART_RU.planBp, PD_PLAN, 2.5, compact ? 7 : 8),
        mk(forecast, CHART_RU.forecast, PD_FCST, 3, compact ? 8 : 9, {
          dash: "dash",
        }),
        mk(fact, CHART_RU.factLine, PD_FACT, 2.5, compact ? 7 : 8),
      ],
      layout: {
        height,
        margin: compact
          ? { l: 44, r: 16, t: 24, b: 72 }
          : { l: 56, r: 28, t: 40, b: 80 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        hovermode: false as const,
        showlegend: false,
        xaxis: {
          title: {
            text: compact ? "" : "Период",
            standoff: 14,
            font: { size: 12, color: theme.axis },
          },
          tickmode: "array" as const,
          tickvals,
          ticktext,
          tickangle: -35,
          tickfont: { size: compact ? 10 : 12, color: theme.axis },
          gridcolor: theme.grid,
          automargin: true,
        },
        yaxis: {
          title: {
            text: compact ? "Разделы ПД" : "Количество разделов ПД",
            font: { size: compact ? 11 : 12, color: theme.axis },
          },
          tickfont: { size: 10, color: theme.axis },
          gridcolor: theme.grid,
          zeroline: false,
          range: [0, yMax + yHead],
        },
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG },
      legendItems: [
        { name: CHART_RU.planBp, color: PD_PLAN, short: "План (БП)" },
        { name: CHART_RU.forecast, color: PD_FCST, short: "Прогноз" },
        { name: CHART_RU.factLine, color: PD_FACT },
      ],
    };
  }, [rows, fullscreen, theme, compact]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет точек динамики.
      </div>
    );
  }

  return (
    <div className="min-w-0">
      <PlotlyFigure
        data={figure.data}
        layout={figure.layout}
        config={figure.config}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
      <ChartHtmlLegend items={figure.legendItems} compact={compact} />
    </div>
  );
}

/** Накопительный overlay «Динамика по месяцам» / просрочка (паритет с РД):
 * жёлтый план и зелёный факт одной ширины; на конце: план · факт · Δ. */
export function PdMonthlyCumulativeChart({
  rows,
  fullscreen = false,
}: {
  rows: MonthlyRow[];
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const mobile = useIsMobileViewport();
  const compact = mobile && !fullscreen;
  const figure = useMemo(() => {
    const chronological = [...rows].sort((a, b) => a.month.localeCompare(b.month));
    const labels = chronological.map((r) => r.month_label);
    const plan = chronological.map((r) => Math.max(0, Number(r.plan) || 0));
    const fact = chronological.map((r) => {
      if (r.fact != null) return Math.max(0, Number(r.fact) || 0);
      return Math.max(0, Number(r.done) || 0);
    });
    const delta = chronological.map((_, i) => fact[i] - plan[i]);
    const yIdx = chronological.map((_, i) => i);
    const xMax = Math.max(1, ...plan, ...fact);
    const tipSize = compact ? 11 : 13;
    const tipFamily = "Inter, system-ui, sans-serif";
    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.55, 680))
      : Math.max(compact ? 360 : 320, (compact ? 72 : 56) + chronological.length * (compact ? 52 : 48));

    const barW = 0.55;
    const barBase = {
      type: "bar" as const,
      orientation: "h" as const,
      y: yIdx,
      cliponaxis: false,
      constraintext: "none" as const,
      width: barW,
      hovertemplate:
        "<b>%{customdata}</b><br>%{fullData.name} (накопительно): %{x}<extra></extra>",
    };

    const uirevision = chronological
      .map((r) => `${r.month}:${r.plan}:${r.fact ?? r.done}`)
      .join("|");

    return {
      data: [
        {
          ...barBase,
          name: CHART_RU.plan,
          x: plan,
          marker: { color: PD_MONTH_PLAN, opacity: 0.92 },
          customdata: labels,
        },
        {
          ...barBase,
          name: CHART_RU.fact,
          x: fact,
          marker: { color: PD_MONTH_FACT, opacity: 0.96 },
          customdata: labels,
        },
      ],
      layout: {
        height,
        uirevision,
        barmode: "overlay" as const,
        bargap: 0.28,
        margin: compact
          ? { l: 8, r: 128, t: 12, b: 96 }
          : { l: 16, r: 140, t: 48, b: 96 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        legend: plotlyLegendUnderLeft({
          fontSize: compact ? 11 : 12,
          labelColor: theme.axis,
          y: compact ? -0.28 : -0.12,
        }),
        xaxis: {
          title: {
            text: compact ? "" : "Количество разделов (накопительно)",
            font: { size: 12, color: theme.axis },
          },
          range: [0, xMax * (compact ? 1.18 : 1.12)],
          autorange: false,
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          gridcolor: theme.grid,
          zeroline: false,
          nticks: compact ? 5 : undefined,
        },
        yaxis: {
          title: {
            text: compact ? "" : "Месяц",
            font: { size: 12, color: theme.axis },
          },
          tickmode: "array" as const,
          tickvals: yIdx,
          ticktext: labels,
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          automargin: true,
        },
        annotations: monthlyPlanFactDeltaAnnotations({
          yIdx,
          plan,
          fact,
          delta,
          planColor: PD_MONTH_PLAN,
          factColor: PD_MONTH_FACT,
          negColor: PD_MONTH_OVERDUE,
          fontSize: tipSize,
          fontFamily: tipFamily,
          compact,
        }),
        font: { family: tipFamily, color: theme.axis },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG },
    };
  }, [rows, fullscreen, theme, compact]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет помесячных данных.
      </div>
    );
  }

  return (
    <div className="min-w-0 overflow-x-hidden">
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

/** Gantt «Просрочка выдачи ПД» — Plotly overlay bars + даты как main. */
export function PdDelayGanttChart({
  rows,
  rangeStart,
  rangeEnd,
  fullscreen = false,
  hideProjectPrefix = false,
}: {
  rows: GanttRow[];
  rangeStart: string | null;
  rangeEnd: string | null;
  fullscreen?: boolean;
  /** Один проект в фильтре — без префикса «Проект | ». */
  hideProjectPrefix?: boolean;
}) {
  const theme = useChartTheme();
  const mobile = useIsMobileViewport();
  const compact = mobile && !fullscreen;
  const figure = useMemo(() => {
    const sorted = [...rows].sort((a, b) => (b.delay_dur || 0) - (a.delay_dur || 0));
    const displayLabels = sorted.map((r) =>
      stripProjectPrefixIfSingle(r.label, hideProjectPrefix),
    );
    const { keys: yLabels, texts: yTickTexts } = uniquePlotCategories(displayLabels);
    const categoryOrder = [...yLabels].reverse();

    const yellowY: string[] = [];
    const yellowBase: number[] = [];
    const yellowLen: number[] = [];
    const yellowCd: string[] = [];
    const greenY: string[] = [];
    const greenBase: number[] = [];
    const greenLen: number[] = [];
    const greenCd: string[] = [];
    const redY: string[] = [];
    const redBase: number[] = [];
    const redLen: number[] = [];
    const redCd: string[] = [];
    const annotations: Array<Record<string, unknown>> = [];
    /** На узком экране две даты рядом нечитаемы — оставляем одну с min gap. */
    const minLabelGapDays = compact ? 55 : 12;
    const labelFont = compact ? 9 : 10;
    /** Даты на конце полос — ×1.5 к базовому (ТЗ / скрин). */
    const dateLabelFont = Math.max(11, Math.round(labelFont * 1.5));

    const arrowY: string[] = [];
    const arrowStartX: number[] = [];
    const arrowX: number[] = [];
    const arrowCd: string[] = [];

    for (let i = 0; i < sorted.length; i++) {
      const row = sorted[i];
      const y = yLabels[i];
      const startMs = toMs(row.start);
      const bfMs = toMs(row.base_finish);
      const finMs = toMs(row.finish);
      const delayEndMs = toMs(row.delay_end);
      // Сдано с опозданием: finish совпадает с концом красной полосы (или флаг API).
      const lateComplete =
        Boolean(row.late_complete) ||
        (Boolean(row.finish) &&
          Boolean(row.delay_end) &&
          row.finish === row.delay_end &&
          (row.fact_dur || 0) <= 0 &&
          (row.delay_dur || 0) > 0);
      const hasRed = (row.delay_dur || 0) > 0 && delayEndMs != null && bfMs != null;
      const hasGreen =
        (row.fact_dur || 0) > 0 && Boolean(row.finish) && !row.delay_end && startMs != null;

      const yLen = barLenMs(row.start, row.base_finish);
      if (yLen != null && startMs != null) {
        yellowY.push(y);
        yellowBase.push(startMs);
        yellowLen.push(yLen);
        yellowCd.push(row.base_label || "");
      }

      if (hasGreen) {
        const gLen = barLenMs(row.start, row.finish);
        if (gLen != null && startMs != null) {
          greenY.push(y);
          greenBase.push(startMs);
          greenLen.push(gLen);
          greenCd.push(row.finish_label || "");
        }
      }

      if (hasRed && bfMs != null) {
        const rLen = barLenMs(row.base_finish, row.delay_end);
        if (rLen != null) {
          redY.push(y);
          redBase.push(bfMs);
          redLen.push(rLen);
          redCd.push(row.finish_label || "");
        }
      }

      const arrowMs = lateComplete ? finMs ?? delayEndMs : null;
      const arrowFrom = startMs ?? bfMs;
      if (arrowMs != null && arrowFrom != null) {
        arrowY.push(y);
        arrowStartX.push(arrowFrom);
        arrowX.push(arrowMs);
        arrowCd.push(
          row.finish_label
            ? `Сдано с опозданием: ${row.finish_label}`
            : "Сдано с опозданием",
        );
      }

      const labelColor = theme.dark ? "#e2e8f0" : "#1a1a1a";
      const annBase = {
        y,
        showarrow: false,
        yanchor: "middle" as const,
        font: { size: dateLabelFont, color: labelColor },
      };

      const placedXs: number[] = [];
      const farEnough = (ms: number) =>
        placedXs.every((p) => Math.abs(ms - p) / DAY_MS >= minLabelGapDays);
      const place = (ms: number, text: string, xanchor: "left" | "right", xshift: number) => {
        if (!text || !farEnough(ms)) return;
        placedXs.push(ms);
        annotations.push({
          ...annBase,
          x: ms,
          text,
          xanchor,
          xshift,
        });
      };

      // Даты у правого края сегментов — без склейки у названий слева.
      const tipMs = delayEndMs ?? (hasGreen ? finMs : null) ?? bfMs;
      const tipText = hasRed
        ? row.finish_label || row.base_label || ""
        : hasGreen
          ? row.finish_label || row.base_label || ""
          : row.base_label || "";

      if (compact) {
        if (tipMs != null && tipText) {
          place(tipMs, tipText, "left", lateComplete ? 18 : 6);
        }
      } else {
        if (tipMs != null && tipText) {
          place(tipMs, tipText, "left", lateComplete ? 20 : 8);
        }
        if (hasRed && row.base_label && bfMs != null && tipMs != null) {
          if ((tipMs - bfMs) / DAY_MS >= minLabelGapDays * 2.5) {
            place(bfMs, row.base_label, "right", -6);
          }
        } else if (
          hasGreen &&
          !hasRed &&
          row.finish_label &&
          finMs != null &&
          bfMs != null &&
          tipMs === bfMs &&
          finMs < bfMs - DAY_MS &&
          (bfMs - finMs) / DAY_MS >= minLabelGapDays * 2
        ) {
          place(finMs, row.finish_label, "right", -4);
        }
      }
    }

    const data: Array<Record<string, unknown>> = [];
    if (yellowY.length) {
      data.push({
        type: "bar",
        orientation: "h",
        name: "Базовое окончание",
        y: yellowY,
        x: yellowLen,
        base: yellowBase,
        marker: { color: PD_GANTT_YELLOW },
        width: 0.48,
        customdata: yellowCd,
        hovertemplate: "%{y}<br>Базовое окончание: %{customdata}<extra></extra>",
      });
    }
    if (greenY.length) {
      data.push({
        type: "bar",
        orientation: "h",
        name: "Окончание",
        y: greenY,
        x: greenLen,
        base: greenBase,
        marker: { color: PD_GANTT_GREEN },
        width: 0.48,
        customdata: greenCd,
        hovertemplate: "%{y}<br>Окончание: %{customdata}<extra></extra>",
      });
    }
    if (redY.length) {
      data.push({
        type: "bar",
        orientation: "h",
        name: "Просрочка",
        y: redY,
        x: redLen,
        base: redBase,
        marker: { color: PD_GANTT_RED },
        width: 0.48,
        customdata: redCd,
        hovertemplate: "%{y}<br>Просрочка до %{customdata}<extra></extra>",
      });
    }
    if (arrowY.length) {
      for (let i = 0; i < arrowY.length; i++) {
        const tip = Number(arrowX[i]);
        const stemStart = Number(arrowStartX[i]);
        data.push({
          type: "scatter",
          mode: "lines+markers",
          name: i === 0 ? "Сдано с опозданием" : "Сдано с опозданием ",
          showlegend: i === 0,
          y: [arrowY[i], arrowY[i]],
          x: [stemStart, tip],
          line: { color: PD_GANTT_GREEN, width: compact ? 7 : 9 },
          marker: {
            symbol: ["circle", "triangle-right"],
            size: [7, compact ? 16 : 20],
            color: PD_GANTT_GREEN,
            line: { width: 1, color: "#145a32" },
          },
          customdata: [arrowCd[i], arrowCd[i]],
          hovertemplate: "%{y}<br>%{customdata}<extra></extra>",
          cliponaxis: false,
        });
      }
    }

    const xs: number[] = [];
    for (const row of sorted) {
      for (const v of [row.start, row.base_finish, row.finish, row.delay_end]) {
        const ms = toMs(v);
        if (ms != null) xs.push(ms);
      }
    }
    const rangeLo = rangeStart ? toMs(rangeStart) : xs.length ? Math.min(...xs) : null;
    const rangeHi = rangeEnd ? toMs(rangeEnd) : xs.length ? Math.max(...xs) : null;
    let xRange: [number, number] | undefined;
    if (rangeLo != null && rangeHi != null) {
      const pad = Math.max((rangeHi - rangeLo) * (compact ? 0.12 : 0.1), 6 * DAY_MS);
      xRange = [rangeLo - pad, rangeHi + pad];
    }

    const dense = sorted.length >= 8;
    const perLine = dense ? 26 : 30;
    const wrapped = yTickTexts.map((t) => wrapAxisLabel(t, perLine, 3));
    const tickTextsDisplay = wrapped.map((w) => w.text);
    const maxWrapLines = Math.max(1, ...wrapped.map((w) => w.lines));
    const rowH =
      (dense ? (compact ? 42 : 44) : compact ? 40 : 44) +
      (maxWrapLines - 1) * (compact ? 14 : 16);
    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.72, 900))
      : Math.max(compact ? 300 : 280, (compact ? 100 : 72) + sorted.length * rowH);

    const maxTick = Math.max(8, ...tickTextsDisplay.map((t) =>
      Math.max(...t.split("<br>").map((line) => line.length)),
    ));
    const leftMargin = compact ? 8 : Math.min(dense ? 280 : 200, Math.max(100, maxTick * 7.2));

    const legendItems = [
      { name: "Базовое окончание", color: PD_GANTT_YELLOW },
      ...(greenY.length ? [{ name: "Окончание", color: PD_GANTT_GREEN }] : []),
      ...(redY.length ? [{ name: "Просрочка", color: PD_GANTT_RED }] : []),
      ...(arrowY.length
        ? [{ name: "Сдано с опозданием", color: PD_GANTT_GREEN, short: "С опозданием" }]
        : []),
    ];

    return {
      data,
      legendItems,
      layout: {
        height,
        barmode: "overlay" as const,
        bargap: dense ? 0.35 : 0.44,
        margin: compact
          ? { l: 8, r: 88, t: 12, b: 56 }
          : { l: leftMargin, r: 120, t: 28, b: 52 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        showlegend: false,
        annotations,
        xaxis: {
          type: "date" as const,
          title: { text: "" },
          tickformat: compact ? "%d.%m.%y" : "%d.%m.%Y",
          tickangle: compact ? -35 : 0,
          nticks: compact ? 5 : undefined,
          tickfont: { size: compact ? 9 : 11, color: theme.axis },
          gridcolor: theme.grid,
          automargin: true,
          ...(xRange ? { range: xRange } : {}),
        },
        yaxis: {
          categoryorder: "array" as const,
          categoryarray: categoryOrder,
          tickmode: "array" as const,
          tickvals: yLabels,
          ticktext: tickTextsDisplay,
          tickfont: { size: compact ? 10 : dense ? 10 : 11, color: theme.axis },
          automargin: compact,
        },
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
        modebar: {
          bgcolor: "rgba(0,0,0,0)",
          color: theme.axis,
          activecolor: "#0f766e",
        },
      },
      config: { ...PLOTLY_CONFIG },
    };
  }, [rows, rangeStart, rangeEnd, fullscreen, theme, compact, hideProjectPrefix]);

  if (!rows.length) {
    return <DashboardEmptyState message="Нет данных для графика просрочки." className="h-64" />;
  }

  return (
    <div className="min-w-0 overflow-x-hidden">
      <PlotlyFigure
        data={figure.data}
        layout={figure.layout}
        config={figure.config}
        useResizeHandler
        style={{ width: "100%", height: "100%" }}
      />
      <ChartHtmlLegend items={figure.legendItems} compact={compact} />
    </div>
  );
}
