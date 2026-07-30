"use client";

import { useEffect, useMemo, useState } from "react";
import { BarChart, Text } from "@tremor/react";
import { formatMln } from "@/lib/format";

export type FinanceBarPoint = {
  period: string;
  plan: number;
  fact: number;
  deviation: number;
};

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

/**
 * Столбчатый график план/факт(/отклонение) на Tremor — как «БДДС план/факт»:
 * `showAnimation` плавно перерисовывает столбцы при смене фильтров.
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
  const viewport = useViewportSize(fullscreen);
  const height = fullscreen ? Math.max(520, viewport.height - 96) : 360;
  const width = fullscreen
    ? Math.max(viewport.width - 32, rows.length * 110 + 120)
    : undefined;

  const deviationName = "Отклонение";
  const categories = useMemo(
    () =>
      showDeviation
        ? [planName, factName, deviationName]
        : [planName, factName],
    [planName, factName, showDeviation],
  );
  const colors = showDeviation
    ? (["blue", "rose", "amber"] as const)
    : (["blue", "rose"] as const);

  const chartData = useMemo(
    () =>
      rows.map((row) => ({
        period: row.period,
        [planName]: row.plan,
        [factName]: row.fact,
        ...(showDeviation ? { [deviationName]: row.deviation } : {}),
      })),
    [rows, planName, factName, showDeviation],
  );

  if (!rows.length) {
    return (
      <div className="flex h-80 items-center justify-center text-sm text-tremor-content dark:text-dark-tremor-content">
        {emptyText}
      </div>
    );
  }

  return (
    <div className={fullscreen ? "h-full w-full overflow-x-auto p-4" : "w-full"}>
      <div style={{ width: width ?? "100%", minHeight: height }}>
        <Text className="mb-2 text-tremor-content dark:text-dark-tremor-content">
          {xAxisTitle}
        </Text>
        <BarChart
          key={`${categories.join("|")}-${rows.map((r) => r.period).join(",")}`}
          className={fullscreen ? "mt-2 h-[calc(100vh-8rem)]" : "mt-2 h-80"}
          data={chartData}
          index="period"
          categories={[...categories]}
          colors={[...colors]}
          valueFormatter={(value) => formatMln(Number(value))}
          yAxisWidth={fullscreen ? 80 : 64}
          showLegend
          showAnimation
          showGridLines
          autoMinValue
        />
      </div>
    </div>
  );
}
