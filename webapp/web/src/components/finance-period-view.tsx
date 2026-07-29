"use client";

import { useCallback, useEffect, useState } from "react";
import { BarChart, Card, Grid, Metric, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import type { BddsPayload } from "@/lib/api";
import { formatMln } from "@/lib/format";
import {
  PLAN_FACT_DEVIATION_CATEGORIES,
  withRuPlanFactDeviation,
} from "@/lib/chart-ru";

type Filters = {
  project: string;
  date_from: string;
  date_to: string;
  view: "monthly" | "cumulative";
};

const tableCell =
  "px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong";

export function FinancePeriodView({
  title,
  subtitle,
  fetchPayload,
}: {
  title: string;
  subtitle: string;
  fetchPayload: (params: Record<string, string | undefined>) => Promise<BddsPayload>;
}) {
  const [filters, setFilters] = useState<Filters>({
    project: "Все",
    date_from: "",
    date_to: "",
    view: "monthly",
  });
  const [data, setData] = useState<BddsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(
    async (nextFilters: Filters) => {
      setLoading(true);
      setError(null);
      try {
        setData(await fetchPayload(nextFilters));
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [fetchPayload],
  );

  useEffect(() => {
    void load(filters);
  }, [filters, load]);

  const kpis = data?.kpis ?? { plan_mln: 0, fact_mln: 0, deviation_mln: 0 };
  const kpiCards = [
    ["План", formatMln(kpis.plan_mln)],
    ["Факт", formatMln(kpis.fact_mln)],
    ["Отклонение", formatMln(kpis.deviation_mln)],
    ["Периодов", String(data?.period_rows.length ?? 0)],
  ];

  return (
    <AppShell title={title} subtitle={subtitle}>
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="block text-sm">
            <Text>Проект</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.project}
              onChange={(event) =>
                setFilters((state) => ({ ...state, project: event.target.value }))
              }
            >
              {(data?.filters.projects ?? ["Все"]).map((project) => (
                <option key={project} value={project}>
                  {project}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Дата с</Text>
            <input
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              type="date"
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_from}
              onChange={(event) =>
                setFilters((state) => ({ ...state, date_from: event.target.value }))
              }
            />
          </label>
          <label className="block text-sm">
            <Text>Дата по</Text>
            <input
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              type="date"
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_to}
              onChange={(event) =>
                setFilters((state) => ({ ...state, date_to: event.target.value }))
              }
            />
          </label>
          <label className="block text-sm">
            <Text>Вид</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.view}
              onChange={(event) =>
                setFilters((state) => ({
                  ...state,
                  view: event.target.value as Filters["view"],
                }))
              }
            >
              <option value="monthly">По месяцам</option>
              <option value="cumulative">Накопительно</option>
            </select>
          </label>
        </div>
        <Text className="mt-3">
          Режим данных: <b>{data?.meta.data_mode ?? "…"}</b> ·{" "}
          {loading ? "загрузка…" : `${data?.meta.rows ?? 0} строк`}
        </Text>
      </Card>

      {error ? (
        <Card className="mb-6 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            API недоступен. {error}
          </Text>
        </Card>
      ) : null}

      <div className="space-y-6">
        <Grid numItemsSm={2} numItemsLg={4} className="gap-6">
          {kpiCards.map(([cardTitle, metric]) => (
            <Card key={cardTitle} className="rounded-xl">
              <Text>{cardTitle}</Text>
              <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {metric}
              </Metric>
            </Card>
          ))}
        </Grid>

        <Card className="rounded-xl">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            План и факт расходов
          </Title>
          <Text className="mt-1">По периодам, млн ₽</Text>
          <BarChart
            className="mt-6 h-80"
            data={withRuPlanFactDeviation(data?.tremor.by_period ?? [])}
            index="period"
            categories={[...PLAN_FACT_DEVIATION_CATEGORIES]}
            colors={["blue", "emerald", "amber"]}
            valueFormatter={(value) => formatMln(Number(value))}
            yAxisWidth={64}
            showLegend
            showAnimation
            showGridLines
          />
        </Card>

        <Grid numItemsLg={2} className="gap-6">
          <PeriodTable title="По периодам" rows={data?.period_rows ?? []} label="period" />
          <PeriodTable title="По проектам" rows={data?.project_rows ?? []} label="project" />
        </Grid>
      </div>
    </AppShell>
  );
}

function PeriodTable({
  title,
  rows,
  label,
}: {
  title: string;
  rows: Array<{
    period?: string;
    project?: string;
    plan: number;
    fact: number;
    deviation: number;
  }>;
  label: "period" | "project";
}) {
  return (
    <Card className="overflow-hidden rounded-xl p-0">
      <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
        <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
          {title}
        </Title>
      </div>
      <div className="overflow-x-auto">
        <table className="min-w-full text-left text-tremor-default">
          <thead className="bg-tremor-background-subtle text-tremor-label uppercase text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
            <tr>
              <th className="px-3 py-2">
                {label === "period" ? "Период" : "Проект"}
              </th>
              <th className="px-3 py-2 text-right">План</th>
              <th className="px-3 py-2 text-right">Факт</th>
              <th className="px-3 py-2 text-right">Отклонение</th>
            </tr>
          </thead>
          <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
            {rows.map((row, index) => (
              <tr
                key={`${row[label]}-${index}`}
                className="border-t border-tremor-border dark:border-dark-tremor-border"
              >
                <td className="px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                  {row[label]}
                </td>
                <td className={tableCell}>{formatMln(row.plan / 1_000_000)}</td>
                <td className={tableCell}>{formatMln(row.fact / 1_000_000)}</td>
                <td className={tableCell}>{formatMln(row.deviation / 1_000_000)}</td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
