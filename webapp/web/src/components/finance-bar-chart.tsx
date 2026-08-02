"use client";

import { useEffect, useMemo, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
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
};

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

/** Короткая подпись на столбце: «144.3», нули не рисуем. */
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

const PLAN_COLOR = "#3b82f6";
const FACT_COLOR = "#f43f5e";
const DEV_COLOR = "#f59e0b";

/**
 * Столбчатый график план/факт(/отклонение).
 * Подписи значений всегда на столбцах (без hover); на mobile — короткий формат + scroll-x.
 */
export function FinanceBarChart({
  rows,
  planName,
  factName,
  showDeviation = false,
  xAxisTitle,
  emptyText = "Нет периодов для графика",
  fullscreen = false,
}: {
  rows: FinanceBarPoint[];
  planName: string;
  factName: string;
  showDeviation?: boolean;
  xAxisTitle: string;
  yAxisTitle?: string;
  emptyText?: string;
  /** Зум: график занимает весь экран, столбцы шире. */
  fullscreen?: boolean;
}) {
  const narrow = useIsNarrow();
  const viewport = useViewportSize(fullscreen);
  const compact = narrow && !fullscreen;
  const seriesCount = showDeviation ? 3 : 2;
  const slotPx = compact ? 52 : fullscreen ? 110 : 72;
  const chartWidth = Math.max(
    fullscreen ? viewport.width - 48 : 0,
    rows.length * slotPx * seriesCount + (compact ? 56 : 80),
  );
  const height = fullscreen
    ? Math.max(520, viewport.height - 96)
    : compact
      ? 280
      : 360;

  const chartData = useMemo(
    () =>
      rows.map((row) => ({
        period: row.period,
        [planName]: row.plan,
        [factName]: row.fact,
        ...(showDeviation ? { Отклонение: row.deviation } : {}),
      })),
    [rows, planName, factName, showDeviation],
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

  const renderValueLabel = (props: {
    x?: number | string;
    y?: number | string;
    width?: number | string;
    value?: number | string;
  }) => {
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
          ? "h-full w-full overflow-x-auto p-4 text-slate-700 dark:text-slate-200"
          : "w-full overflow-x-auto text-slate-700 dark:text-slate-200"
      }
    >
      <Text className="mb-2 text-tremor-content dark:text-dark-tremor-content">
        {xAxisTitle}
      </Text>
      <div style={{ width: chartWidth, minWidth: "100%", height }}>
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
              fill={PLAN_COLOR}
              radius={[3, 3, 0, 0]}
              isAnimationActive
            >
              <LabelList dataKey={planName} content={renderValueLabel} />
            </Bar>
            <Bar
              dataKey={factName}
              fill={FACT_COLOR}
              radius={[3, 3, 0, 0]}
              isAnimationActive
            >
              <LabelList dataKey={factName} content={renderValueLabel} />
            </Bar>
            {showDeviation ? (
              <Bar
                dataKey="Отклонение"
                fill={DEV_COLOR}
                radius={[3, 3, 0, 0]}
                isAnimationActive
              >
                <LabelList dataKey="Отклонение" content={renderValueLabel} />
              </Bar>
            ) : null}
          </BarChart>
        </ResponsiveContainer>
      </div>
      {compact ? (
        <p className="mt-1 text-[11px] text-tremor-content dark:text-dark-tremor-content">
          Подписи — млн ₽ (кратко). Прокрутите график вправо при длинном периоде.
        </p>
      ) : null}
    </div>
  );
}
