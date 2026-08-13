"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { ProjectDocumentationPayload } from "@/lib/api";
import { ChartHtmlLegend } from "@/components/chart-html-legend";
import { stripProjectPrefixIfSingle, uniquePlotCategories } from "@/lib/chart-labels";
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
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет данных по исполнению.
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
    const plan = rows.map((r) => r.plan_bp);
    const forecast = rows.map((r) =>
      r.forecast == null || Number.isNaN(Number(r.forecast))
        ? null
        : Number(r.forecast),
    );
    const fact = rows.map((r) => r.fact ?? 0);
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

/** Горизонтальные overlay-бары «Динамика по месяцам» как main (жёлтый план / зелёный факт, «+N»). */
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
    // Ascending months: Plotly y=0 at bottom → newest month on top.
    const chronological = [...rows].sort((a, b) => a.month.localeCompare(b.month));
    const labels = chronological.map((r) => r.month_label);
    const plan = chronological.map((r) => Number(r.plan) || 0);
    const overdue = chronological.map((r) => Math.max(0, Number(r.overdue) || 0));
    const done = chronological.map((r, i) => {
      if (r.done != null) return Math.max(0, Number(r.done) || 0);
      const fact = Math.max(0, Number(r.fact) || 0);
      return Math.max(0, fact - overdue[i]);
    });
    const rest = chronological.map((r, i) => {
      if (r.rest != null) return Math.max(0, Number(r.rest) || 0);
      return Math.max(0, plan[i] - done[i] - overdue[i]);
    });
    const factInc = chronological.map((r, i) => {
      if (r.fact_inc != null) return Math.max(0, Number(r.fact_inc) || 0);
      if (i === 0) return done[i] + overdue[i];
      return Math.max(0, done[i] + overdue[i] - (done[i - 1] + overdue[i - 1]));
    });
    const yIdx = chronological.map((_, i) => i);
    const xMax = Math.max(1, ...plan, ...done.map((d, i) => d + overdue[i] + rest[i]));
    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.55, 680))
      : Math.max(compact ? 360 : 320, (compact ? 72 : 56) + chronological.length * (compact ? 52 : 48));

    const incTxt = factInc.map((v) => (v > 0 ? `+${Math.round(v)}` : ""));
    const tipText = chronological.map((_, i) => {
      const total = done[i] + overdue[i] + rest[i];
      return total > 0 ? incTxt[i] : "";
    });
    const tipFont = compact ? 13 : 15;

    const barBase = {
      type: "bar" as const,
      orientation: "h" as const,
      y: yIdx,
      cliponaxis: false,
      constraintext: "none" as const,
      hovertemplate:
        "<b>%{customdata}</b><br>%{fullData.name} (накопительно): %{x}<extra></extra>",
    };

    return {
      data: [
        {
          ...barBase,
          name: "Выполнено",
          x: done,
          marker: { color: PD_MONTH_FACT, opacity: 0.95 },
          customdata: labels,
          text: tipText.map((t, i) => (rest[i] <= 0 && overdue[i] <= 0 ? t : "")),
          textposition: "outside" as const,
          texttemplate: "%{text}",
          textfont: { size: tipFont, color: theme.label },
        },
        {
          ...barBase,
          name: CHART_RU.overdue,
          x: overdue,
          marker: { color: PD_MONTH_OVERDUE, opacity: 0.95 },
          customdata: labels,
          text: tipText.map((t, i) => (rest[i] <= 0 && overdue[i] > 0 ? t : "")),
          textposition: "outside" as const,
          texttemplate: "%{text}",
          textfont: { size: tipFont, color: theme.label },
        },
        {
          ...barBase,
          name: CHART_RU.plan,
          x: rest,
          marker: { color: PD_MONTH_PLAN, opacity: 0.92 },
          customdata: labels,
          text: tipText.map((t, i) => (rest[i] > 0 ? t : "")),
          textposition: "outside" as const,
          texttemplate: "%{text}",
          textfont: { size: tipFont, color: theme.label },
        },
      ],
      layout: {
        height,
        barmode: "stack" as const,
        bargap: 0.28,
        margin: compact
          ? { l: 8, r: 72, t: 12, b: 96 }
          : { l: 16, r: 80, t: 48, b: 96 },
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
          range: [0, xMax * (compact ? 1.32 : 1.14)],
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
        font: { family: "Inter, system-ui, sans-serif", color: theme.axis },
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
      if (arrowMs != null) {
        arrowY.push(y);
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

      // Mobile: одна подпись на ряд (конец факта/просрочки), без пары дат на полосе.
      if (compact) {
        if (hasRed && row.finish_label && delayEndMs != null) {
          place(delayEndMs, row.finish_label, "left", lateComplete ? 18 : 6);
        } else if (hasGreen && row.finish_label && finMs != null) {
          place(finMs, row.finish_label, "left", 6);
        } else if (row.base_label && bfMs != null) {
          place(bfMs, row.base_label, "left", 6);
        }
      } else if (hasRed) {
        if (row.base_label && bfMs != null) {
          place(bfMs, row.base_label, "right", -6);
        }
        if (row.finish_label && delayEndMs != null) {
          place(delayEndMs, row.finish_label, "left", lateComplete ? 20 : 6);
        }
      } else if (hasGreen && finMs != null) {
        // Опережение: факт левее базы — даты по разные стороны стыка (без «29.01.202531.03»).
        const ahead = bfMs != null && finMs < bfMs - DAY_MS;
        if (ahead) {
          if (row.finish_label) place(finMs, row.finish_label, "right", -4);
          if (row.base_label && bfMs != null) place(bfMs, row.base_label, "left", 6);
        } else {
          const tip = row.finish_label || row.base_label || "";
          place(finMs, tip, "left", 6);
        }
      } else if (row.base_label && bfMs != null) {
        place(bfMs, row.base_label, "left", 6);
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
      data.push({
        type: "scatter",
        mode: "markers",
        name: "Сдано с опозданием",
        y: arrowY,
        x: arrowX,
        marker: {
          symbol: "triangle-right",
          size: compact ? 14 : 16,
          color: PD_GANTT_GREEN,
          line: { width: 1, color: "#1e8449" },
        },
        customdata: arrowCd,
        hovertemplate: "%{y}<br>%{customdata}<extra></extra>",
        cliponaxis: false,
      });
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
      const pad = Math.max((rangeHi - rangeLo) * (compact ? 0.12 : 0.08), 6 * DAY_MS);
      xRange = [rangeLo - pad, rangeHi + pad];
    }

    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.62, 780))
      : Math.max(compact ? 300 : 280, (compact ? 140 : 120) + sorted.length * (compact ? 48 : 52));

    return {
      data,
      layout: {
        height,
        barmode: "overlay" as const,
        bargap: 0.44,
        // Mobile: легенда снизу — иначе наезжает на первую полосу
        margin: compact
          ? { l: 8, r: 80, t: 16, b: 168 }
          : { l: 16, r: 168, t: 40, b: 88 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        showlegend: true,
        legend: plotlyLegendUnderLeft({
          fontSize: compact ? 10 : 12,
          labelColor: theme.axis,
          y: compact ? -0.42 : -0.14,
        }),
        annotations,
        xaxis: {
          type: "date" as const,
          title: {
            text: compact ? "" : "Период",
            font: { size: compact ? 11 : 12, color: theme.axis },
            standoff: compact ? 8 : 4,
          },
          tickformat: compact ? "%d.%m.%y" : "%d.%m.%Y",
          tickangle: compact ? -45 : 0,
          nticks: compact ? 5 : undefined,
          tickfont: { size: compact ? 9 : 11, color: theme.axis },
          gridcolor: theme.grid,
          automargin: !compact,
          ...(xRange ? { range: xRange } : {}),
        },
        yaxis: {
          categoryorder: "array" as const,
          categoryarray: categoryOrder,
          tickmode: "array" as const,
          tickvals: yLabels,
          ticktext: yTickTexts,
          tickfont: { size: compact ? 10 : 11, color: theme.axis },
          automargin: true,
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
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет данных для графика просрочки.
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
