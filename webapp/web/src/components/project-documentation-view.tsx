"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Card,
  DonutChart,
  Grid,
  LineChart,
  Metric,
  Text,
  Title,
} from "@tremor/react";
import {
  fetchProjectDocumentation,
  type ProjectDocumentationPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { CHART_RU, withRuDocDynamics } from "@/lib/chart-ru";

function deviationClass(value: number | null | undefined): string {
  if (value == null || value === 0) {
    return "text-tremor-content-strong dark:text-dark-tremor-content-strong";
  }
  return value < 0
    ? "font-semibold text-rose-700 dark:text-rose-300"
    : "font-semibold text-emerald-700 dark:text-emerald-300";
}

export function ProjectDocumentationView() {
  const [project, setProject] = useState("Все");
  const [section, setSection] = useState("Все");
  const [granularity, setGranularity] = useState("week");
  const [data, setData] = useState<ProjectDocumentationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchProjectDocumentation({
          project,
          section,
          granularity,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [project, section, granularity]);

  useEffect(() => {
    void load();
  }, [load]);

  const kpis = data?.kpis;
  const selectClass =
    "mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background";

  return (
    <AppShell
      title="Проектная документация"
      subtitle="Разделы ПД по MSP: шифр, базовое/плановое окончание, исполнение"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-3">
          <label className="block text-sm">
            <Text>Проект</Text>
            <select
              className={selectClass}
              value={project}
              onChange={(event) => {
                setProject(event.target.value);
                setSection("Все");
              }}
            >
              {(data?.filters.projects ?? ["Все"]).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Раздел (шифр)</Text>
            <select
              className={selectClass}
              value={section}
              onChange={(event) => setSection(event.target.value)}
            >
              {(data?.filters.sections ?? ["Все"]).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Гранулярность динамики</Text>
            <select
              className={selectClass}
              value={granularity}
              onChange={(event) => setGranularity(event.target.value)}
            >
              {(data?.filters.granularities ?? []).map((item) => (
                <option key={item.id} value={item.id}>
                  {item.label}
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
            : `${data?.meta.files ?? 0} файлов · ${data?.meta.rows ?? 0} разделов`}
          {data?.filters.applied.report_date
            ? ` · отчётная дата ${data.filters.applied.report_date}`
            : null}
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
          <Card className="rounded-xl">
            <Text>План по проекту (БП)</Text>
            <Metric className="mt-2">{kpis?.plan_total ?? 0}</Metric>
          </Card>
          <Card className="rounded-xl">
            <Text>План на текущую дату (БП)</Text>
            <Metric className="mt-2">{kpis?.plan_to_date ?? 0}</Metric>
          </Card>
          <Card className="rounded-xl">
            <Text>Факт на текущую дату</Text>
            <Metric className="mt-2">{kpis?.fact_to_date ?? 0}</Metric>
          </Card>
          <Card className="rounded-xl">
            <Text>Отклонение на текущую дату</Text>
            <Metric className={`mt-2 ${deviationClass(kpis?.deviation_to_date)}`}>
              {kpis?.deviation_to_date ?? 0}
            </Metric>
          </Card>
        </Grid>

        <Grid numItemsSm={2} numItemsLg={2} className="gap-6">
          <Card className="rounded-xl">
            <Text>Текущая производительность</Text>
            <Metric className="mt-2">
              {Number(kpis?.current_productivity ?? 0).toFixed(1)}
            </Metric>
            <Text className="mt-1">разделов за окно гранулярности</Text>
          </Card>
          <Card className="rounded-xl">
            <Text>Необходимая производительность</Text>
            <Metric className="mt-2">
              {Number(kpis?.required_productivity ?? 0).toFixed(1)}
            </Metric>
            <Text className="mt-1">для закрытия остатка БП в срок</Text>
          </Card>
        </Grid>

        <Grid numItemsLg={3} className="gap-6">
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Исполнение ПД
            </Title>
            <Text className="mt-1">По статусу разделов</Text>
            <DonutChart
              className="mt-6 h-52"
              data={data?.tremor.status_mix ?? []}
              category="value"
              index="name"
              colors={["emerald", "amber", "slate"]}
              valueFormatter={(value) => `${value} шт.`}
            />
          </Card>
          <Card className="rounded-xl lg:col-span-2">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Динамика выдачи ПД
            </Title>
            <Text className="mt-1">Накопительно: БП vs прогноз (текущий план)</Text>
            <LineChart
              className="mt-6 h-72"
              data={withRuDocDynamics(data?.tremor.dynamics ?? [])}
              index="period_label"
              categories={[CHART_RU.planBp, CHART_RU.forecast]}
              colors={["teal", "orange"]}
              yAxisWidth={40}
              showLegend
              showAnimation
              showGridLines
            />
          </Card>
        </Grid>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Таблица по проектной документации
            </Title>
          </div>
          <div className="max-h-[28rem] overflow-auto">
            {(data?.rows.length ?? 0) === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                Нет разделов ПД по выбранным фильтрам.
              </div>
            ) : (
              <table className="min-w-full border-separate border-spacing-0 text-left text-xs">
                <thead className="sticky top-0 z-20 bg-tremor-background-subtle text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                  <tr>
                    {[
                      "№",
                      "Проект",
                      "Раздел",
                      "Название",
                      "Баз. окончание",
                      "Окончание",
                      "Откл.",
                      "%",
                      "Статус",
                    ].map((label) => (
                      <th
                        key={label}
                        className="whitespace-nowrap border-b border-tremor-border px-3 py-2 font-semibold dark:border-dark-tremor-border"
                      >
                        {label}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(data?.rows ?? []).map((row, index) => (
                    <tr
                      key={`${row.project}-${row.section}-${index}`}
                      className="border-b border-tremor-border dark:border-dark-tremor-border"
                    >
                      <td className="px-3 py-2 tabular-nums">{index + 1}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-medium">
                        {row.project}
                      </td>
                      <td className="px-3 py-2 font-semibold">{row.section}</td>
                      <td className="max-w-xs truncate px-3 py-2">{row.task}</td>
                      <td className="px-3 py-2 tabular-nums">{row.base_end ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.plan_end ?? "—"}</td>
                      <td className={`px-3 py-2 tabular-nums ${deviationClass(row.dev_end_days)}`}>
                        {row.dev_end}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {row.pct_complete == null ? "—" : `${row.pct_complete}%`}
                      </td>
                      <td className="px-3 py-2">{row.status}</td>
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
