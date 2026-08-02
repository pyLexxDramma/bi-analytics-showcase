"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  LabelList,
  Legend,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import { Text } from "@tremor/react";
import { formatMln } from "@/lib/format";

export type FinanceBarPoint = {
  period: string;
  plan: number;
  fact: number;
  deviation: number;
  forecast?: number;
};

const DEFAULT_PLAN = "#3b82f6";
const DEFAULT_FACT = "#f43f5e";
const DEFAULT_FORECAST = "#f59e0b";
const DEFAULT_DEV = "#f59e0b";

const FORECAST_PLAN = "#2E86AB";
const FORECAST_FACT = "#A23B72";
const FORECAST_SERIES = "#F18F01";

function useIsNarrow(): boolean {
  const [narrow, setNarrow] = useState(false);
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

function formatBarLabel(value: unknown, compact: boolean): string {
  const n = Number(value);
  if (!Number.isFinite(n) || Math.abs(n) < 1e-9) return "";
  if (compact) {
    return n.toLocaleString("ru-RU", {
      maximumFractionDigits: Math.abs(n) >= 100 ? 0 : 1,
      minimumFractionDigits: 0,
    });
  }
  return n.toLocaleString("ru-RU", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function deviationBarColor(value: number, forecastMode: boolean): string {
  if (!forecastMode) return DEFAULT_DEV;
  if (Math.abs(value) < 0.005) return "rgba(148,163,184,0.75)";
  return value > 0 ? "#22c55e" : "#ef4444";
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
  const forecastMode = showForecast;
  const seriesCount =
    (showForecast ? 1 : 0) + 2 + (showDeviation ? 1 : 0);
  const slotPx = compact ? (showForecast ? 36 : 44) : fullscreen ? 110 : 72;
  const chartWidth = Math.max(
    fullscreen ? viewport.width - 48 : 0,
    rows.length * slotPx * Math.min(seriesCount, 3) + (compact ? 48 : 80),
  );
  const height = fullscreen
    ? Math.max(520, viewport.height - 96)
    : compact
      ? 280
      : 360;

  const planColor =
    colors?.plan ?? (forecastMode ? FORECAST_PLAN : DEFAULT_PLAN);
  const factColor =
    colors?.fact ?? (forecastMode ? FORECAST_FACT : DEFAULT_FACT);
  const forecastColor =
    colors?.forecast ?? (forecastMode ? FORECAST_SERIES : DEFAULT_FORECAST);

  const chartData = useMemo(
    () =>
      rows.map((row) => ({
        period: row.period,
        [planName]: row.plan,
        [factName]: row.fact,
        ...(showForecast ? { [forecastName]: row.forecast ?? 0 } : {}),
        ...(showDeviation ? { [deviationLabel]: row.deviation } : {}),
      })),
    [rows, planName, factName, forecastName, showForecast, showDeviation, deviationLabel],
  );

  const labelFont = compact ? 9 : 10;
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

  const renderValueLabel = (props: Record<string, unknown>) => {
    const text = formatBarLabel(props.value, compact);
    if (!text) return null;
    const x = Number(props.x) + Number(props.width) / 2;
    const y = Number(props.y) - 4;
    if (!Number.isFinite(x) || !Number.isFinite(y)) return null;
    return (
      <text
        x={x}
        y={y}
        fill={dark ? "#e2e8f0" : "#334155"}
        fontSize={labelFont}
        textAnchor="middle"
        dominantBaseline="auto"
      >
        {text}
      </text>
    );
  };

  return (
    <div
      className={
        fullscreen
          ? "h-full w-full min-w-0 max-w-full overflow-x-auto p-4 text-slate-700 dark:text-slate-200"
          : "w-full min-w-0 max-w-full overflow-x-auto text-slate-700 dark:text-slate-200"
      }
    >
      <Text className="mb-2 text-tremor-content dark:text-dark-tremor-content">
        {xAxisTitle}
      </Text>
      <div
        className="min-w-0"
        style={{ width: chartWidth, minWidth: "100%", height }}
      >
        <ResponsiveContainer width="100%" height="100%">
          <BarChart
            data={chartData}
            margin={{
              top: compact ? 28 : 32,
              right: 8,
              left: 0,
              bottom: compact ? 48 : 8,
            }}
            barCategoryGap={compact ? "12%" : "18%"}
            barGap={2}
          >
            <CartesianGrid strokeDasharray="3 3" vertical={false} />
            <XAxis
              dataKey="period"
              tick={{ fontSize: compact ? 10 : 12 }}
              interval={0}
              angle={compact || rows.length > 8 ? -35 : 0}
              textAnchor={compact || rows.length > 8 ? "end" : "middle"}
              height={compact || rows.length > 8 ? 70 : 40}
            />
            <YAxis
              width={compact ? 44 : 64}
              tick={{ fontSize: compact ? 10 : 12 }}
              tickFormatter={(v) =>
                Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 0 })
              }
            />
            <Tooltip
              formatter={(value) => formatMln(Number(value))}
              labelStyle={{ fontWeight: 600 }}
              contentStyle={{
                borderRadius: 8,
                border: "1px solid #e2e8f0",
              }}
            />
            <Legend wrapperStyle={{ fontSize: compact ? 11 : 13 }} />
            <Bar
              dataKey={planName}
              fill={planColor}
              radius={[3, 3, 0, 0]}
              isAnimationActive
            >
              <LabelList dataKey={planName} content={renderValueLabel as never} />
            </Bar>
            <Bar
              dataKey={factName}
              fill={factColor}
              radius={[3, 3, 0, 0]}
              isAnimationActive
            >
              <LabelList dataKey={factName} content={renderValueLabel as never} />
            </Bar>
            {showForecast ? (
              <Bar
                dataKey={forecastName}
                fill={forecastColor}
                radius={[3, 3, 0, 0]}
                isAnimationActive
              >
                <LabelList
                  dataKey={forecastName}
                  content={renderValueLabel as never}
                />
              </Bar>
            ) : null}
            {showDeviation ? (
              <Bar
                dataKey={deviationLabel}
                radius={[3, 3, 0, 0]}
                isAnimationActive
              >
                {chartData.map((entry, index) => (
                  <Cell
                    key={`dev-${index}`}
                    fill={deviationBarColor(
                      Number(entry[deviationLabel as keyof typeof entry] ?? 0),
                      forecastMode,
                    )}
                  />
                ))}
                <LabelList
                  dataKey={deviationLabel}
                  content={renderValueLabel as never}
                />
              </Bar>
            ) : null}
          </BarChart>
        </ResponsiveContainer>
      </div>
      <p className="mt-1 text-[11px] text-tremor-content dark:text-dark-tremor-content">
        {compact
          ? "Подписи на столбцах — млн ₽ (кратко). Прокрутите график вправо при длинном периоде."
          : "Подписи на столбцах — млн ₽."}
      </p>
    </div>
  );
}
