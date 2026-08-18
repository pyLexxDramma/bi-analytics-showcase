"use client";

import { useCallback, useEffect, useState } from "react";
import { BarChart, Card, Grid, Metric, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import type { FinancePeriodPayload } from "@/lib/api";
import { formatMln } from "@/lib/format";
import {
  PLAN_FACT_DEVIATION_CATEGORIES,
  withRuPlanFactDeviation,
} from "@/lib/chart-ru";
import { FilterChipMulti, FilterChipSelect } from "@/components/dashboard-filters";
import {
  MobileCardStack,
  MobileEntityCard,
  MobileMetricGrid,
} from "@/components/mobile-entity-card";
import {
  DashboardTableTitle,
  MobileFilterChips,
  MobilePaneTabs,
} from "@/components/mobile-ux";

type Filters = {
  projects: string[];
  date_from: string;
  date_to: string;
  view: "monthly" | "cumulative";
};

function joinMulti(values: string[], allToken = "Все"): string | undefined {
  if (!values.length || (values.length === 1 && values[0] === allToken)) return undefined;
  return values.filter((v) => v !== allToken).join("|") || undefined;
}

const tableCell =
  "bi-num px-3 py-2 text-center tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong";

export function FinancePeriodView({
  title,
  subtitle,
  fetchPayload,
}: {
  title: string;
  subtitle: string;
  fetchPayload: (
    params: Record<string, string | undefined>,
  ) => Promise<FinancePeriodPayload>;
}) {
  const [filters, setFilters] = useState<Filters>({
    projects: [],
    date_from: "",
    date_to: "",
    view: "monthly",
  });
  const [data, setData] = useState<FinancePeriodPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mobilePane, setMobilePane] = useState<"chart" | "periods">("chart");

  const load = useCallback(
    async (nextFilters: Filters) => {
      setLoading(true);
      setError(null);
      try {
        setData(
          await fetchPayload({
            project: joinMulti(nextFilters.projects),
            date_from: nextFilters.date_from || undefined,
            date_to: nextFilters.date_to || undefined,
            view: nextFilters.view,
          }),
        );
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
    <AppShell title={title} subtitle={subtitle} loading={loading}>
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-4">
          <FilterChipMulti
            label="Проект"
            values={filters.projects}
            options={data?.filters.projects ?? []}
            onChange={(projects) => setFilters((state) => ({ ...state, projects }))}
          />
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
          <FilterChipSelect label="Вид" value={filters.view} options={[{ value: "monthly", label: "По месяцам" }, { value: "cumulative", label: "Накопительно" }]} onChange={(view) => setFilters((state) => ({ ...state, view: view as Filters["view"] }))} />
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

        <MobilePaneTabs
          value={mobilePane}
          onChange={setMobilePane}
          options={[
            { id: "chart", label: "График" },
            { id: "periods", label: "Периоды" },
          ]}
        />
        <div className="lg:hidden">
          <MobileFilterChips
            value={filters.view}
            onChange={(view) => setFilters((state) => ({ ...state, view }))}
            options={[
              { id: "monthly", label: "По месяцам" },
              { id: "cumulative", label: "Накопительно" },
            ]}
          />
        </div>

        <div className={mobilePane === "chart" ? "block" : "hidden lg:block"}>
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
              showTooltip={false}
            />
          </Card>
        </div>

        <div className={mobilePane === "periods" ? "block" : "hidden lg:block"}>
          <Grid numItemsLg={2} className="gap-6">
            <PeriodTable
              title="По периодам"
              rows={data?.period_rows ?? []}
              label="period"
              totals={kpis}
            />
            <PeriodTable
              title="По проектам"
              rows={data?.project_rows ?? []}
              label="project"
              totals={kpis}
            />
          </Grid>
        </div>
      </div>
    </AppShell>
  );
}

function PeriodTable({
  title,
  rows,
  label,
  totals,
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
  totals: { plan_mln: number; fact_mln: number; deviation_mln: number };
}) {
  return (
    <Card className="overflow-hidden rounded-xl p-0">
      <DashboardTableTitle>{title}</DashboardTableTitle>
      <MobileCardStack
        compact
        pinned={
          <MobileEntityCard className="bi-card-pinned" title="ИТОГО">
            <MobileMetricGrid
              columns={3}
              items={[
                { label: "План", value: formatMln(totals.plan_mln) },
                { label: "Факт", value: formatMln(totals.fact_mln) },
                {
                  label: "Откл.",
                  value: formatMln(totals.deviation_mln),
                  highlight: totals.deviation_mln < 0 ? "bad" : "ok",
                },
              ]}
            />
          </MobileEntityCard>
        }
      >
        {rows.map((row, index) => (
          <MobileEntityCard
            key={`m-${row[label]}-${index}`}
            title={row[label] ?? "—"}
            badge={formatMln(row.deviation / 1_000_000)}
            badgeTone={row.deviation < 0 ? "bad" : "ok"}
          >
            <MobileMetricGrid
              columns={3}
              items={[
                { label: "План", value: formatMln(row.plan / 1_000_000) },
                { label: "Факт", value: formatMln(row.fact / 1_000_000) },
                {
                  label: "Откл.",
                  value: formatMln(row.deviation / 1_000_000),
                  highlight: row.deviation < 0 ? "bad" : "ok",
                },
              ]}
            />
          </MobileEntityCard>
        ))}
      </MobileCardStack>
      <div className="bi-table-scroll hidden overflow-x-auto lg:block">
        <table className="bi-sticky-head bi-sticky-col min-w-full text-center text-tremor-default">
          <thead className="bg-tremor-background-subtle text-tremor-label uppercase text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
            <tr>
              <th className="bg-tremor-background-subtle px-3 py-2 dark:bg-dark-tremor-background-subtle">
                {label === "period" ? "Период" : "Проект"}
              </th>
              <th className="bg-tremor-background-subtle px-3 py-2 text-center dark:bg-dark-tremor-background-subtle">План</th>
              <th className="bg-tremor-background-subtle px-3 py-2 text-center dark:bg-dark-tremor-background-subtle">Факт</th>
              <th className="bg-tremor-background-subtle px-3 py-2 text-center dark:bg-dark-tremor-background-subtle">Отклонение</th>
            </tr>
          </thead>
          <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
            {rows.map((row, index) => (
              <tr
                key={`${row[label]}-${index}`}
                className="bi-row-alt border-t border-tremor-border dark:border-dark-tremor-border"
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
