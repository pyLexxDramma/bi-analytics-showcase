"use client";

import { useCallback, useEffect, useState } from "react";
import {
  BarChart,
  Card,
  DonutChart,
  Grid,
  Metric,
  Text,
  Title,
} from "@tremor/react";
import {
  fetchControlPoints,
  type ControlPointsPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { CHART_RU, withRuPctComplete } from "@/lib/chart-ru";

export function ControlPointsView() {
  const [project, setProject] = useState("Все");
  const [data, setData] = useState<ControlPointsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (nextProject: string) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchControlPoints(nextProject));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(project);
  }, [project, load]);

  const kpis = data?.kpis;
  const kpiCards = [
    { title: "Проекты", metric: kpis?.projects ?? 0 },
    { title: "Контрольные точки", metric: kpis?.milestones_found ?? 0 },
    {
      title: "Выполнено",
      metric: `${Number(kpis?.completed_pct ?? 0).toFixed(1)}%`,
    },
    { title: "Просрочено", metric: kpis?.overdue ?? 0 },
  ];

  return (
    <AppShell
      title="Контрольные точки"
      subtitle="Ковенанты MSP: план = базовое окончание, факт = плановое окончание"
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
          Режим данных: <b>{data?.meta.data_mode ?? "…"}</b>
          {" · "}
          {loading
            ? "загрузка…"
            : `${data?.meta.files ?? 0} файлов · ${data?.meta.rows ?? 0} строк`}
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
          {kpiCards.map((kpi) => (
            <Card key={kpi.title} className="rounded-xl">
              <Text>{kpi.title}</Text>
              <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {kpi.metric}
              </Metric>
            </Card>
          ))}
        </Grid>

        <Grid numItemsLg={3} className="gap-6">
          <Card className="rounded-xl lg:col-span-2">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Выполнение контрольных точек
            </Title>
            <Text className="mt-1">Доля завершённых точек по проектам</Text>
            <BarChart
              className="mt-6 h-80"
              data={withRuPctComplete(data?.tremor.completion_by_project ?? [])}
              index="project"
              categories={[CHART_RU.pctComplete]}
              colors={["emerald"]}
              valueFormatter={(value) => `${Number(value).toFixed(1)}%`}
              yAxisWidth={52}
              showLegend
              showAnimation
              showGridLines
            />
          </Card>
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Статусы точек
            </Title>
            <Text className="mt-1">По выбранным проектам</Text>
            <DonutChart
              className="mt-6 h-52"
              data={data?.tremor.status_mix ?? []}
              category="value"
              index="name"
              colors={["emerald", "rose", "slate", "blue"]}
              valueFormatter={(value) => `${value} шт.`}
            />
            <Text className="mt-4">
              Без факта: <b>{kpis?.missing_fact ?? 0}</b>
            </Text>
          </Card>
        </Grid>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Матрица контрольных точек (ковенанты)
            </Title>
            <Text className="mt-1">
              План / факт / отклонение по 13 вехам
            </Text>
          </div>
          <div className="overflow-x-auto">
            {(data?.matrix.projects.length ?? 0) === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                Нет данных по контрольным точкам.
              </div>
            ) : (
              <table className="min-w-max border-separate border-spacing-0 text-center text-xs text-tremor-content-strong dark:text-dark-tremor-content-strong">
                <thead>
                  <tr className="bg-tremor-background-subtle text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                    <th
                      rowSpan={2}
                      className="sticky left-0 z-30 min-w-52 border-b-2 border-r-2 border-white bg-slate-100 px-4 py-3 text-left font-bold dark:border-slate-700 dark:bg-slate-800"
                    >
                      Проект
                    </th>
                    {(data?.matrix.milestones ?? []).map((milestone) => (
                      <th
                        key={milestone.slug}
                        colSpan={3}
                        className="border-b border-r-2 border-white px-2 py-2 font-semibold dark:border-slate-700"
                      >
                        {milestone.title}
                      </th>
                    ))}
                  </tr>
                  <tr className="bg-tremor-background-subtle text-[10px] uppercase text-tremor-label dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                    {(data?.matrix.milestones ?? []).flatMap((milestone) =>
                      ["План", "Факт", "Откл."].map((label, index) => (
                        <th
                          key={`${milestone.slug}-${label}`}
                          className={`border-b px-2 py-2 ${index === 2 ? "border-r-2 border-white dark:border-r-slate-700" : "border-r border-tremor-border dark:border-dark-tremor-border"}`}
                        >
                          {label}
                        </th>
                      )),
                    )}
                  </tr>
                </thead>
                <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
                  {(data?.matrix.projects ?? []).map((matrixProject) => (
                    <tr
                      key={matrixProject.project}
                      className="border-b border-tremor-border dark:border-dark-tremor-border"
                    >
                      <td className="sticky left-0 z-10 border-b border-r-2 border-white bg-slate-100 px-4 py-3 text-left font-bold dark:border-slate-700 dark:bg-slate-800">
                        {matrixProject.project}
                      </td>
                      {(data?.matrix.milestones ?? []).flatMap((milestone) => {
                        const cell = matrixProject.cells[milestone.slug];
                        const deviationClass =
                          cell?.otkl_days === null || cell?.otkl_days === undefined
                            ? "text-tremor-content dark:text-dark-tremor-content"
                            : cell.otkl_days >= 0
                              ? "font-semibold text-emerald-700 dark:text-emerald-300"
                              : "font-semibold text-rose-800 dark:text-rose-300";
                        return [
                          <td
                            key={`${milestone.slug}-plan`}
                            className="border-b border-r border-tremor-border px-2 py-3 font-bold tabular-nums dark:border-dark-tremor-border"
                          >
                            {cell?.plan ?? "—"}
                          </td>,
                          <td
                            key={`${milestone.slug}-fact`}
                            className="border-b border-r border-tremor-border px-2 py-3 font-bold tabular-nums dark:border-dark-tremor-border"
                          >
                            {cell?.fact ?? "—"}
                          </td>,
                          <td
                            key={`${milestone.slug}-otkl`}
                            className={`border-b border-r-2 border-white px-2 py-3 tabular-nums dark:border-r-slate-700 ${deviationClass}`}
                          >
                            {cell?.otkl ?? "Н/Д"}
                          </td>,
                        ];
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
