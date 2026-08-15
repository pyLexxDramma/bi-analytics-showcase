"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  LabelList,
  ReferenceLine,
  ResponsiveContainer,
  XAxis,
  YAxis,
} from "recharts";
import { Text } from "@tremor/react";
import { ChartHtmlLegend } from "@/components/chart-html-legend";

export type FinanceBarPoint = {
  period: string;
  plan: number;
  fact: number;
  deviation: number;
  forecast?: number;
};

const DEFAULT_PLAN = "#3b82f6";
/** Факт не красный: красный зарезервирован под отклонение (как цифры в таблице). */
const DEFAULT_FACT = "#0d9488";
const DEFAULT_FORECAST = "#f59e0b";

const FORECAST_PLAN = "#2E86AB";
const FORECAST_FACT = "#0f766e";
const FORECAST_SERIES = "#F18F01";

const DEV_NEG_NAME = "Отклонение (факт < план)";
const DEV_POS_NAME = "Отклонение (факт > план)";
const DEV_THR = 0.01;

function useIsNarrow(): boolean {
  const [narrow, setNarrow] = useState(() => {
    if (typeof window === "undefined") return true;
    return window.matchMedia("(max-width: 1023px)").matches;
  });
  useEffect(() => {
    const mq = window.matchMedia("(max-width: 1023px)");
    const sync = () => setNarrow(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);
  return narrow;
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

/** Как main `_finance_bar_text_mln_rub`: число + « млн. руб.» (compact — без суффикса). */
function formatBarLabel(
  value: unknown,
  compact: boolean,
  signed = false,
): { line1: string; line2: string } | null {
  const n = Number(value);
  if (!Number.isFinite(n) || Math.abs(n) < 1e-9) return null;
  const abs = Math.abs(n).toLocaleString("ru-RU", {
    minimumFractionDigits: compact && Math.abs(n) >= 100 ? 0 : 1,
    maximumFractionDigits: compact && Math.abs(n) >= 100 ? 0 : 1,
  });
  let num = abs;
  if (signed) {
    if (n > 0) num = `+${abs}`;
    else if (n < 0) num = `-${abs}`;
  } else if (n < 0) {
    num = `-${abs}`;
  }
  if (compact) return { line1: num, line2: "" };
  return { line1: num, line2: "млн. руб." };
}

/** Отклонение как в таблице: <0 красный, >0 зелёный. Факт — бирюзовый. */
const DEV_BAR_NEG = "#dc2626";
const DEV_BAR_POS = "#16a34a";
/** Подписи отклонения: на светлой теме тёмнее, на тёмной — ярче (контраст к фону). */
const DEV_LABEL_NEG_LIGHT = "#b91c1c";
const DEV_LABEL_NEG_DARK = "#fb7185";
const DEV_LABEL_POS_LIGHT = "#166534";
const DEV_LABEL_POS_DARK = "#4ade80";

/** Как таблица: <0 красный (ниже оси), >0 зелёный (выше оси). */
function deviationLabelColor(value: number, dark: boolean): string {
  if (Math.abs(value) < 0.005) return dark ? "#e2e8f0" : "#111827";
  if (value > 0) return dark ? DEV_LABEL_POS_DARK : DEV_LABEL_POS_LIGHT;
  return dark ? DEV_LABEL_NEG_DARK : DEV_LABEL_NEG_LIGHT;
}

export function FinanceBarChart({
  rows,
  planName,
  factName,
  forecastName = "БДДС прогноз",
  showForecast = false,
  showDeviation = false,
  deviationLabel = "Отклонение",
  xAxisTitle,
  yAxisTitle = "млн. руб.",
  categoryKey = "period",
  emptyText = "Нет периодов для графика",
  fullscreen = false,
  colors,
}: {
  rows: FinanceBarPoint[];
  planName: string;
  factName: string;
  forecastName?: string;
  showForecast?: boolean;
  showDeviation?: boolean;
  deviationLabel?: string;
  xAxisTitle: string;
  yAxisTitle?: string;
  /** Поле категории на оси X: период или проект. */
  categoryKey?: "period" | "project";
  emptyText?: string;
  fullscreen?: boolean;
  colors?: {
    plan?: string;
    fact?: string;
    forecast?: string;
    deviation?: string;
  };
}) {
  const narrow = useIsNarrow();
  const viewport = useViewportSize(fullscreen);
  const compact = narrow && !fullscreen;
  /** Desktop / fullscreen — «млн. руб.» под цифрой; mobile — только число. */
  const showUnitOnBars = !compact;
  const forecastMode = showForecast;
  const hasNegDev =
    showDeviation && rows.some((r) => Number(r.deviation) < -DEV_THR);
  const hasPosDev =
    showDeviation && rows.some((r) => Number(r.deviation) > DEV_THR);
  const seriesCount =
    (showForecast ? 1 : 0) +
    2 +
    (hasNegDev ? 1 : 0) +
    (hasPosDev ? 1 : 0);
  const slotPx = compact
    ? showForecast
      ? 40
      : 48
    : fullscreen
      ? 130
      : categoryKey === "project"
        ? 100
        : 88;
  const chartWidth = Math.max(
    fullscreen ? viewport.width - 48 : 0,
    rows.length * slotPx * Math.min(seriesCount, 3) + (compact ? 56 : 96),
  );
  // При отклонении ось уходит в минус — выше блок, иначе мелкие суммы
  // (десятки млн при шкале до тысяч) сливаются с линией нуля.
  const height = fullscreen
    ? Math.max(showDeviation ? 640 : 560, viewport.height - 72)
    : compact
      ? showDeviation
        ? 420
        : 340
      : showDeviation
        ? 640
        : 520;

  const planColor =
    colors?.plan ?? (forecastMode ? FORECAST_PLAN : DEFAULT_PLAN);
  const factColor =
    colors?.fact ?? (forecastMode ? FORECAST_FACT : DEFAULT_FACT);
  const forecastColor =
    colors?.forecast ?? (forecastMode ? FORECAST_SERIES : DEFAULT_FORECAST);

  const chartData = useMemo(
    () =>
      rows.map((row) => {
        const dev = Number(row.deviation) || 0;
        return {
          category: row.period,
          [planName]: row.plan,
          [factName]: row.fact,
          ...(showForecast ? { [forecastName]: row.forecast ?? 0 } : {}),
          ...(showDeviation
            ? {
                [DEV_NEG_NAME]:
                  dev < -DEV_THR ? dev : null,
                [DEV_POS_NAME]:
                  dev > DEV_THR ? dev : null,
                [deviationLabel]: dev,
              }
            : {}),
        };
      }),
    [
      rows,
      planName,
      factName,
      forecastName,
      showForecast,
      showDeviation,
      deviationLabel,
    ],
  );

  const labelFont = compact ? 9 : fullscreen ? 12 : 10;
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const root = document.documentElement;
    const sync = () => setDark(root.classList.contains("dark"));
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(root, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  if (!rows.length) {
    return (
      <div className="flex h-80 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        {emptyText}
      </div>
    );
  }

  const renderValueLabel = (
    props: Record<string, unknown>,
    opts?: { signed?: boolean; colorBySign?: boolean },
  ) => {
    const parts = formatBarLabel(props.value, !showUnitOnBars, opts?.signed);
    if (!parts) return null;
    const x = Number(props.x) + Number(props.width) / 2;
    const rawY = Number(props.y);
    const rawH = Number(props.height);
    const value = Number(props.value);
    const lineGap = Math.round(labelFont * 1.25);
    const gap = opts?.colorBySign ? (compact ? 10 : 14) : compact ? 6 : 10;
    // height у Recharts для отрицательных иногда < 0 — берём края прямоугольника.
    const h = Number.isFinite(rawH) ? rawH : 0;
    const rectTop = Math.min(rawY, rawY + h);
    const rectBottom = Math.max(rawY, rawY + h);
    const below = Number.isFinite(value) && value < 0;
    const yNum = below ? rectBottom + gap : rectTop - gap - (parts.line2 ? lineGap : 0);
    const yUnit = below ? yNum + lineGap : rectTop - gap;
    if (!Number.isFinite(x) || !Number.isFinite(yNum)) return null;
    const fill = opts?.colorBySign
      ? deviationLabelColor(value, dark)
      : dark
        ? "#e2e8f0"
        : "#111827";
    const stroke = dark ? "rgba(15,23,42,0.85)" : "rgba(255,255,255,0.92)";
    const textProps = {
      x,
      fill,
      stroke,
      strokeWidth: 3,
      paintOrder: "stroke" as const,
      fontSize: labelFont,
      textAnchor: "middle" as const,
      style: { fontWeight: opts?.colorBySign ? 700 : 600 },
    };
    if (!showUnitOnBars || !parts.line2) {
      return (
        <text
          {...textProps}
          y={yNum}
          dominantBaseline={below ? "hanging" : "auto"}
        >
          {parts.line1}
        </text>
      );
    }
    return (
      <g>
        <text
          {...textProps}
          y={yNum}
          dominantBaseline={below ? "hanging" : "auto"}
        >
          {parts.line1}
        </text>
        <text
          {...textProps}
          y={yUnit}
          fontSize={Math.max(8, labelFont - 1)}
          dominantBaseline={below ? "hanging" : "auto"}
        >
          {parts.line2}
        </text>
      </g>
    );
  };

  const angled = compact || rows.length > 6 || categoryKey === "project";

  const legendItems = [
    { name: planName, color: planColor, short: "План" },
    { name: factName, color: factColor, short: "Факт" },
    ...(showForecast
      ? [{ name: forecastName, color: forecastColor, short: "Прогноз" }]
      : []),
    ...(hasNegDev
      ? [{ name: DEV_NEG_NAME, color: DEV_BAR_NEG, short: "Факт < план" }]
      : []),
    ...(hasPosDev
      ? [{ name: DEV_POS_NAME, color: DEV_BAR_POS, short: "Факт > план" }]
      : []),
  ];

  return (
    <div
      className={
        fullscreen
          ? "flex h-full w-full min-w-0 max-w-full flex-col p-4 text-slate-700 dark:text-slate-200"
          : "flex w-full min-w-0 max-w-full flex-col text-slate-700 dark:text-slate-200"
      }
    >
      <Text className="mb-2 text-tremor-content dark:text-dark-tremor-content">
        {xAxisTitle}
      </Text>
      <div className="min-w-0 max-w-full overflow-x-auto">
        <div
          className="min-w-0"
          style={{ width: chartWidth, minWidth: "100%", height }}
        >
          <ResponsiveContainer width="100%" height="100%">
            <BarChart
              data={chartData}
              margin={{
                top: compact ? 28 : 72,
                right: 12,
                left: 8,
                bottom:
                  (angled ? 64 : 28) +
                  (hasNegDev ? (showUnitOnBars ? 52 : 28) : 0),
              }}
              barCategoryGap={compact ? "12%" : "18%"}
              barGap={showDeviation ? 6 : 2}
            >
              <CartesianGrid strokeDasharray="3 3" vertical={false} />
              <XAxis
                dataKey="category"
                tick={{ fontSize: compact ? 10 : 12 }}
                interval={0}
                angle={angled ? -35 : 0}
                textAnchor={angled ? "end" : "middle"}
                height={angled ? (hasNegDev ? 96 : 80) : hasNegDev ? 56 : 40}
                dy={hasNegDev ? 8 : 0}
              />
              <YAxis
                width={compact ? 48 : 72}
                tick={{ fontSize: compact ? 10 : 12 }}
                label={
                  yAxisTitle && showUnitOnBars
                    ? {
                        value: yAxisTitle,
                        angle: -90,
                        position: "insideLeft",
                        style: {
                          textAnchor: "middle",
                          fontSize: 12,
                          fill: dark ? "#94a3b8" : "#64748b",
                        },
                      }
                    : undefined
                }
                tickFormatter={(v) =>
                  Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 0 })
                }
                domain={
                  showDeviation
                    ? [
                        (dataMin: number) =>
                          dataMin < 0
                            ? Math.floor(dataMin * (showUnitOnBars ? 1.28 : 1.18))
                            : 0,
                        (dataMax: number) => Math.ceil(dataMax * 1.32),
                      ]
                    : [0, (dataMax: number) => Math.ceil(dataMax * 1.32)]
                }
              />
              {showDeviation ? (
                <ReferenceLine
                  y={0}
                  stroke={dark ? "#e2e8f0" : "#0f172a"}
                  strokeWidth={2}
                  strokeOpacity={0.9}
                  ifOverflow="extendDomain"
                  label={{
                    value: "0",
                    position: "insideTopRight",
                    fill: dark ? "#e2e8f0" : "#0f172a",
                    fontSize: 11,
                    fontWeight: 700,
                  }}
                />
              ) : null}
              <Bar
                dataKey={planName}
                fill={planColor}
                radius={[3, 3, 0, 0]}
                minPointSize={showDeviation ? 5 : 2}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey={planName}
                  content={(props) => renderValueLabel(props as never) as never}
                />
              </Bar>
              <Bar
                dataKey={factName}
                fill={factColor}
                radius={[3, 3, 0, 0]}
                minPointSize={showDeviation ? 5 : 2}
                isAnimationActive={false}
              >
                <LabelList
                  dataKey={factName}
                  content={(props) => renderValueLabel(props as never) as never}
                />
              </Bar>
              {showForecast ? (
                <Bar
                  dataKey={forecastName}
                  fill={forecastColor}
                  radius={[3, 3, 0, 0]}
                  isAnimationActive={false}
                >
                  <LabelList
                    dataKey={forecastName}
                    content={(props) => renderValueLabel(props as never) as never}
                  />
                </Bar>
              ) : null}
              {hasNegDev ? (
                <Bar
                  dataKey={DEV_NEG_NAME}
                  name={DEV_NEG_NAME}
                  fill={DEV_BAR_NEG}
                  radius={[3, 3, 3, 3]}
                  isAnimationActive={false}
                >
                  <LabelList
                    dataKey={DEV_NEG_NAME}
                    content={
                      ((props: Record<string, unknown>) =>
                        renderValueLabel(props, {
                          signed: true,
                          colorBySign: true,
                        })) as never
                    }
                  />
                </Bar>
              ) : null}
              {hasPosDev ? (
                <Bar
                  dataKey={DEV_POS_NAME}
                  name={DEV_POS_NAME}
                  fill={DEV_BAR_POS}
                  radius={[3, 3, 0, 0]}
                  isAnimationActive={false}
                >
                  <LabelList
                    dataKey={DEV_POS_NAME}
                    content={
                      ((props: Record<string, unknown>) =>
                        renderValueLabel(props, {
                          signed: true,
                          colorBySign: true,
                        })) as never
                    }
                  />
                </Bar>
              ) : null}
            </BarChart>
          </ResponsiveContainer>
        </div>
      </div>
      <ChartHtmlLegend items={legendItems} compact={compact} />
    </div>
  );
}
