"use client";

import { useCallback, useEffect, useState } from "react";
import { BarChart, Card, Grid, Metric, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import {
  fetchApprovedBudget,
  type ApprovedBudgetPayload,
} from "@/lib/api";
import { formatMln } from "@/lib/format";
import {
  PLAN_FACT_DEVIATION_CATEGORIES,
  withRuPlanFactDeviation,
} from "@/lib/chart-ru";

const tableCell =
  "px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong";

export function ApprovedBudgetView() {
  const [project, setProject] = useState("Все");
  const [data, setData] = useState<ApprovedBudgetPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (nextProject: string) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchApprovedBudget({ project: nextProject }));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(project);
  }, [project, load]);

  const kpis = data?.kpis ?? {
    plan_mln: 0,
    fact_mln: 0,
    deviation_mln: 0,
    remainder_mln: 0,
  };

  return (
    <AppShell
      title="Утверждённый бюджет план/факт"
      subtitle="БДДС ∧ ПЛАН без (БДР) / БДДС ∧ ФАКТ · все статьи, без фильтра лотов"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="block text-sm">
            <Text>Проект</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={project}
              onChange={(event) => setProject(event.target.value)}
            >
              {(data?.filters.projects ?? ["Все"]).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
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
            ["Утверждённый бюджет (план)", formatMln(kpis.plan_mln)],
            ["Фактические расходы", formatMln(kpis.fact_mln)],
            ["Отклонение (факт−план)", formatMln(kpis.deviation_mln)],
            ["Остаток (план−факт)", formatMln(kpis.remainder_mln)],
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
            План и факт по проектам
          </Title>
          <Text className="mt-1">млн ₽</Text>
          <BarChart
            className="mt-6 h-80"
            data={withRuPlanFactDeviation(data?.tremor.by_project ?? [])}
            index="project"
            categories={[...PLAN_FACT_DEVIATION_CATEGORIES]}
            colors={["blue", "emerald", "amber"]}
            valueFormatter={(value) => formatMln(Number(value))}
            yAxisWidth={64}
            showLegend
            showAnimation
            showGridLines
          />
        </Card>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Сводка по проектам
            </Title>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-tremor-default">
              <thead className="bg-tremor-background-subtle text-tremor-label uppercase text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                <tr>
                  <th className="px-3 py-2">Проект</th>
                  <th className="px-3 py-2 text-right">План</th>
                  <th className="px-3 py-2 text-right">Факт</th>
                  <th className="px-3 py-2 text-right">Отклонение</th>
                  <th className="px-3 py-2 text-right">Остаток</th>
                </tr>
              </thead>
              <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
                {(data?.project_rows ?? []).map((row) => (
                  <tr
                    key={row.project}
                    className="border-t border-tremor-border dark:border-dark-tremor-border"
                  >
                    <td className="px-3 py-2 font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      {row.project}
                    </td>
                    <td className={tableCell}>{formatMln(row.plan / 1_000_000)}</td>
                    <td className={tableCell}>{formatMln(row.fact / 1_000_000)}</td>
                    <td className={tableCell}>
                      {formatMln(row.deviation / 1_000_000)}
                    </td>
                    <td className={tableCell}>
                      {formatMln(row.remainder / 1_000_000)}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
