"use client";

import { useCallback, useEffect, useState } from "react";
import { BarChart, Card, Grid, Metric, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import {
  fetchBddsPlanFact,
  type BddsPlanFactPayload,
} from "@/lib/api";
import { formatMln } from "@/lib/format";
import {
  PLAN_FACT_REVISED_CATEGORIES,
  withRuPlanFactRevised,
} from "@/lib/chart-ru";

type Filters = {
  project: string;
  date_from: string;
  date_to: string;
  view: "monthly" | "cumulative";
};

const tableCell =
  "px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong";

export function BddsPlanFactView() {
  const [filters, setFilters] = useState<Filters>({
    project: "Все",
    date_from: "",
    date_to: "",
    view: "monthly",
  });
  const [data, setData] = useState<BddsPlanFactPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchBddsPlanFact(next));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(filters);
  }, [filters, load]);

  const kpis = data?.kpis ?? {
    plan_mln: 0,
    fact_mln: 0,
    revised_mln: 0,
    deviation_mln: 0,
  };

  return (
    <AppShell
      title="БДДС расходы (план, факт, уточненный план)"
      subtitle="План и факт из 1С; уточнённый план — факт за прошлые месяцы, план за текущие/будущие"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-4">
          <label className="block text-sm">
            <Text>Проект</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.project}
              onChange={(e) =>
                setFilters((s) => ({ ...s, project: e.target.value }))
              }
            >
              {(data?.filters.projects ?? ["Все"]).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Дата с</Text>
            <input
              type="date"
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_from}
              onChange={(e) =>
                setFilters((s) => ({ ...s, date_from: e.target.value }))
              }
            />
          </label>
          <label className="block text-sm">
            <Text>Дата по</Text>
            <input
              type="date"
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_to}
              onChange={(e) =>
                setFilters((s) => ({ ...s, date_to: e.target.value }))
              }
            />
          </label>
          <label className="block text-sm">
            <Text>Вид</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.view}
              onChange={(e) =>
                setFilters((s) => ({
                  ...s,
                  view: e.target.value as Filters["view"],
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
          {[
            ["План", formatMln(kpis.plan_mln)],
            ["Факт", formatMln(kpis.fact_mln)],
            ["Уточнённый план", formatMln(kpis.revised_mln)],
            ["Отклонение", formatMln(kpis.deviation_mln)],
          ].map(([title, metric]) => (
            <Card key={title} className="rounded-xl">
              <Text>{title}</Text>
              <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {metric}
              </Metric>
            </Card>
          ))}
        </Grid>

        <Card className="rounded-xl">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            План, факт и уточнённый план
          </Title>
          <Text className="mt-1">По периодам, млн ₽</Text>
          <BarChart
            className="mt-6 h-80"
            data={withRuPlanFactRevised(data?.tremor.by_period ?? [])}
            index="period"
            categories={[...PLAN_FACT_REVISED_CATEGORIES]}
            colors={["blue", "emerald", "amber"]}
            valueFormatter={(v) => formatMln(Number(v))}
            yAxisWidth={64}
            showLegend
            showAnimation
            showGridLines
          />
        </Card>

        <Grid numItemsLg={2} className="gap-6">
          <RowsTable
            title="По периодам"
            label="period"
            rows={data?.period_rows ?? []}
          />
          <RowsTable
            title="По проектам"
            label="project"
            rows={data?.project_rows ?? []}
          />
        </Grid>
      </div>
    </AppShell>
  );
}

function RowsTable({
  title,
  label,
  rows,
}: {
  title: string;
  label: "period" | "project";
  rows: Array<{
    period?: string;
    project?: string;
    plan: number;
    fact: number;
    revised: number;
    deviation: number;
  }>;
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
              <th className="px-3 py-2 text-right">Уточнённый</th>
              <th className="px-3 py-2 text-right">Откл.</th>
            </tr>
          </thead>
          <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
            {rows.map((row, i) => (
              <tr
                key={`${row[label]}-${i}`}
                className="border-t border-tremor-border dark:border-dark-tremor-border"
              >
                <td className="px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                  {row[label]}
                </td>
                <td className={tableCell}>{formatMln(row.plan / 1_000_000)}</td>
                <td className={tableCell}>{formatMln(row.fact / 1_000_000)}</td>
                <td className={tableCell}>
                  {formatMln(row.revised / 1_000_000)}
                </td>
                <td className={tableCell}>
                  {formatMln(row.deviation / 1_000_000)}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
    </Card>
  );
}
