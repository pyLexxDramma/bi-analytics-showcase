"use client";

import dynamic from "next/dynamic";
import { useEffect, useMemo, useState } from "react";
import type { ProjectDocumentationPayload } from "@/lib/api";
import { CHART_RU } from "@/lib/chart-ru";
import { PLOTLY_CONFIG } from "@/lib/plotly-config";
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
  const figure = useMemo(() => {
    const height = fullscreen
      ? Math.max(520, Math.min(window.innerHeight * 0.62, 760))
      : 420;
    const x = rows.map((r) => r.period_label || r.period);
    const ys = [
      rows.map((r) => r.plan_bp),
      rows.map((r) => r.forecast),
      rows.map((r) => r.fact ?? 0),
    ];
    const yMax = Math.max(1, ...ys.flat().map((v) => Number(v) || 0));
    const yHead = Math.max(yMax * 0.1, 4);
    const mk = (
      y: number[],
      name: string,
      color: string,
      width: number,
      markerSize: number,
    ): Record<string, unknown> => ({
      type: "scatter",
      mode: "lines+markers+text",
      name,
      x,
      y,
      text: y.map(pointLabel),
      textposition: "top center",
      textfont: { color, size: 10 },
      line: { color, width },
      marker: { size: markerSize, color, line: { width: 1, color: "#fff" } },
      cliponaxis: false,
      hovertemplate: `<b>%{x}</b><br>${name}: %{y}<extra></extra>`,
    });
    return {
      data: [
        mk(ys[0], CHART_RU.planBp, PD_PLAN, 2.5, 8),
        mk(ys[1], CHART_RU.forecast, PD_FCST, 3, 9),
        mk(ys[2], CHART_RU.factLine, PD_FACT, 2.5, 8),
      ],
      layout: {
        height,
        margin: { l: 56, r: 36, t: 72, b: 88 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        hovermode: false as const,
        legend: {
          orientation: "h" as const,
          y: 1.14,
          x: 0.5,
          xanchor: "center" as const,
          font: { size: 13, color: theme.axis },
        },
        xaxis: {
          title: {
            text: "Период",
            standoff: 18,
            font: { size: 12, color: theme.axis },
          },
          tickangle: -35,
          tickfont: { size: 12, color: theme.axis },
          gridcolor: theme.grid,
          automargin: true,
        },
        yaxis: {
          title: {
            text: "Количество разделов ПД",
            font: { size: 12, color: theme.axis },
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
    };
  }, [rows, fullscreen, theme]);

  if (!rows.length) {
    return (
      <div className="flex h-64 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет точек динамики.
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
    const chronological = [...rows].sort((a, b) => a.month.localeCompare(b.month));
    const labels = chronological.map((r) => r.month_label);
    const plan = chronological.map((r) => r.plan);
    const fact = chronological.map((r) => r.fact);
    const factInc = chronological.map((r, i) =>
      i === 0 ? r.fact : Math.max(0, r.fact - chronological[i - 1].fact),
    );
    const yIdx = chronological.map((_, i) => i);
    const xMax = Math.max(1, ...plan, ...fact);
    const height = fullscreen
      ? Math.max(420, Math.min(window.innerHeight * 0.55, 680))
      : Math.max(compact ? 360 : 320, (compact ? 72 : 56) + chronological.length * (compact ? 52 : 48));

    const incTxt = factInc.map((v) => (v > 0 ? `+${Math.round(v)}` : ""));
    const planLonger = plan.map((p, i) => p >= fact[i]);
    const planText = incTxt.map((t, i) => (planLonger[i] ? t : ""));
    const factText = incTxt.map((t, i) => (planLonger[i] ? "" : t));

    const barBase = {
      type: "bar" as const,
      orientation: "h" as const,
      y: yIdx,
      textposition: "outside" as const,
      textfont: { size: compact ? 12 : 15, color: theme.label },
      cliponaxis: false,
      constraintext: "none" as const,
      hovertemplate: "<b>%{customdata}</b><br>%{fullData.name}: %{x}<extra></extra>",
    };

    return {
      data: [
        {
          ...barBase,
          name: CHART_RU.plan,
          x: plan,
          text: planText,
          texttemplate: "%{text}",
          marker: { color: PD_MONTH_PLAN, opacity: 0.92 },
          customdata: labels,
        },
        {
          ...barBase,
          name: CHART_RU.fact,
          x: fact,
          text: factText,
          texttemplate: "%{text}",
          marker: { color: PD_MONTH_FACT, opacity: 0.95 },
          customdata: labels,
        },
      ],
      layout: {
        height,
        barmode: "overlay" as const,
        bargap: 0.28,
        // Mobile: легенда снизу — иначе наезжает на верхний бар (Март 2026).
        margin: compact
          ? { l: 8, r: 56, t: 12, b: 96 }
          : { l: 16, r: 72, t: 48, b: 56 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        legend: compact
          ? {
              orientation: "h" as const,
              y: -0.28,
              yanchor: "top" as const,
              x: 0,
              xanchor: "left" as const,
              font: { size: 11, color: theme.axis },
              bgcolor: "rgba(0,0,0,0)",
            }
          : {
              orientation: "h" as const,
              y: 1.12,
              x: 0,
              font: { size: 12, color: theme.axis },
            },
        xaxis: {
          title: {
            text: compact ? "" : "Количество разделов (накопительно)",
            font: { size: 12, color: theme.axis },
          },
          range: [0, xMax * (compact ? 1.22 : 1.12)],
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
}: {
  rows: GanttRow[];
  rangeStart: string | null;
  rangeEnd: string | null;
  fullscreen?: boolean;
}) {
  const theme = useChartTheme();
  const mobile = useIsMobileViewport();
  const compact = mobile && !fullscreen;
  const figure = useMemo(() => {
    const sorted = [...rows].sort((a, b) => (b.delay_dur || 0) - (a.delay_dur || 0));
    const yLabels = sorted.map((r) => r.label);
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

    for (const row of sorted) {
      const y = row.label;
      const startMs = toMs(row.start);
      const bfMs = toMs(row.base_finish);
      const finMs = toMs(row.finish);
      const delayEndMs = toMs(row.delay_end);
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

      const labelColor = theme.dark ? "#e2e8f0" : "#1a1a1a";
      const annBase = {
        y,
        showarrow: false,
        yanchor: "middle" as const,
        font: { size: labelFont, color: labelColor },
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
          place(delayEndMs, row.finish_label, "left", 6);
        } else if (hasGreen && row.finish_label && finMs != null) {
          place(finMs, row.finish_label, "left", 6);
        } else if (row.base_label && bfMs != null) {
          place(bfMs, row.base_label, "left", 6);
        }
      } else {
        if (row.base_label && bfMs != null && !hasRed && (finMs == null || finMs <= bfMs)) {
          place(bfMs, row.base_label, "left", 6);
        } else if (row.base_label && bfMs != null && hasRed) {
          place(bfMs, row.base_label, "right", -6);
        }

        if (hasGreen && row.finish_label && finMs != null && !hasRed) {
          const gapDays =
            bfMs != null && finMs != null ? Math.abs((bfMs - finMs) / DAY_MS) : 99;
          if (gapDays > minLabelGapDays) {
            place(finMs, row.finish_label, "left", 6);
          }
        }

        if (hasRed && row.finish_label && delayEndMs != null) {
          place(delayEndMs, row.finish_label, "left", 6);
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
          ? { l: 8, r: 64, t: 16, b: 168 }
          : { l: 16, r: 140, t: 56, b: 56 },
        paper_bgcolor: theme.paper,
        plot_bgcolor: theme.plot,
        showlegend: true,
        legend: compact
          ? {
              orientation: "h" as const,
              y: -0.42,
              yanchor: "top" as const,
              x: 0,
              xanchor: "left" as const,
              font: { size: 10, color: theme.axis },
              bgcolor: "rgba(0,0,0,0)",
            }
          : {
              orientation: "h" as const,
              y: 1.12,
              x: 0,
              font: { size: 12, color: theme.axis },
            },
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
          ticktext: yLabels,
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
  }, [rows, rangeStart, rangeEnd, fullscreen, theme, compact]);

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
