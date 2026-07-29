"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Grid, Metric, Text, Title } from "@tremor/react";
import {
  fetchBaselineDeviation,
  type BaselineDeviationPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { CHART_RU } from "@/lib/chart-ru";

function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function endBarStyle(
  endIso: string | null | undefined,
  rangeStart: number,
  rangeSpan: number,
): { left: string; width: string } | null {
  const end = toMs(endIso);
  if (end == null || rangeSpan <= 0) return null;
  const width = Math.max(((end - rangeStart) / rangeSpan) * 100, 0.4);
  return {
    left: "0%",
    width: `${Math.max(0.4, Math.min(width, 100))}%`,
  };
}

function deviationClass(days: number | null | undefined): string {
  if (days == null) return "text-tremor-content dark:text-dark-tremor-content";
  if (days < 0) return "font-semibold text-rose-700 dark:text-rose-300";
  if (days === 0) return "font-semibold text-emerald-700 dark:text-emerald-300";
  return "text-tremor-content-strong dark:text-dark-tremor-content-strong";
}

export function BaselineDeviationView() {
  const [project, setProject] = useState("Все");
  const [block, setBlock] = useState("Все");
  const [building, setBuilding] = useState("Все");
  const [level, setLevel] = useState("4");
  const [data, setData] = useState<BaselineDeviationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchBaselineDeviation({
          project,
          block,
          building,
          level,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [project, block, building, level]);

  useEffect(() => {
    void load();
  }, [load]);

  const range = useMemo(() => {
    const start = toMs(data?.chart.range_start);
    const end = toMs(data?.chart.range_end);
    if (start == null || end == null || end <= start) return null;
    return { start, span: end - start };
  }, [data]);

  const selectClass =
    "mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background";

  return (
    <AppShell
      title="Отклонение от базового плана"
      subtitle="Сравнение базовых дат и текущего плана MSP (откл. = база − план)"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-2 lg:grid-cols-4">
          <label className="block text-sm">
            <Text>Проект</Text>
            <select
              className={selectClass}
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
          <label className="block text-sm">
            <Text>Блок</Text>
            <select
              className={selectClass}
              value={block}
              onChange={(event) => setBlock(event.target.value)}
            >
              {(data?.filters.blocks ?? ["Все"]).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Строение</Text>
            <select
              className={selectClass}
              value={building}
              onChange={(event) => setBuilding(event.target.value)}
            >
              {(data?.filters.buildings ?? ["Все"]).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Детализация</Text>
            <select
              className={selectClass}
              value={level}
              disabled={Boolean(data?.filters.applied.level_skipped)}
              onChange={(event) => setLevel(event.target.value)}
            >
              {(data?.filters.levels ?? []).map((item) => (
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
            : `${data?.meta.files ?? 0} файлов · таблица ${data?.meta.rows ?? 0} · гант ${data?.meta.chart_rows ?? 0}`}
          {data?.chart.capped ? " · график ограничен 400 строками" : null}
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
        <Grid numItemsSm={1} numItemsLg={2} className="gap-6">
          <Card className="rounded-xl">
            <Text>Максимальное отклонение (дней)</Text>
            <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
              {data?.kpis.max_abs_dev_days ?? 0}
            </Metric>
          </Card>
          <Card className="rounded-xl">
            <Text>Задач с отставанием окончания</Text>
            <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
              {data?.meta.rows ?? 0}
            </Metric>
          </Card>
        </Grid>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              ЗОС по проектам
            </Title>
            <Text className="mt-1">
              Базовое окончание / текущее окончание / отклонение
            </Text>
          </div>
          <div className="overflow-x-auto">
            {(data?.kpis.zos_rows.length ?? 0) === 0 ? (
              <div className="px-4 py-8 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                Задачи ЗОС не найдены в выбранном срезе.
              </div>
            ) : (
              <table className="min-w-full text-left text-xs">
                <thead className="bg-tremor-background-subtle text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                  <tr>
                    {["Проект", "Задача", "Баз. окончание", "Окончание", "Откл."].map(
                      (label) => (
                        <th key={label} className="px-3 py-2 font-semibold">
                          {label}
                        </th>
                      ),
                    )}
                  </tr>
                </thead>
                <tbody>
                  {(data?.kpis.zos_rows ?? []).map((row) => (
                    <tr
                      key={row.project}
                      className="border-t border-tremor-border dark:border-dark-tremor-border"
                    >
                      <td className="px-3 py-2 font-medium">{row.project}</td>
                      <td className="max-w-sm truncate px-3 py-2">{row.task}</td>
                      <td className="px-3 py-2 tabular-nums">{row.base_end ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.plan_end ?? "—"}</td>
                      <td className={`px-3 py-2 tabular-nums ${deviationClass(row.dev_end_days)}`}>
                        {row.dev_end}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
        </Card>

        <Card className="rounded-xl">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Базовое окончание vs окончание
              </Title>
              <Text className="mt-1">
                Столбцы от начала шкалы до даты окончания
              </Text>
            </div>
            <div className="flex gap-4 text-sm">
              <span className="inline-flex items-center gap-2">
                <span className="inline-block h-2.5 w-6 rounded bg-teal-500" />
                {CHART_RU.baseEnd}
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="inline-block h-2.5 w-6 rounded bg-orange-400" />
                {CHART_RU.planEnd}
              </span>
            </div>
          </div>

          {(data?.chart.rows.length ?? 0) === 0 || !range ? (
            <div className="py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
              Нет задач для графика.
            </div>
          ) : (
            <div className="max-h-[34rem] overflow-auto rounded-lg border border-tremor-border dark:border-dark-tremor-border">
              <div className="min-w-[720px]">
                {(data?.chart.rows ?? []).map((row) => {
                  const base = endBarStyle(row.base_end, range.start, range.span);
                  const plan = endBarStyle(row.plan_end, range.start, range.span);
                  return (
                    <div
                      key={`${row.project}-${row.task}`}
                      className="grid grid-cols-[minmax(14rem,22rem)_1fr] border-b border-tremor-border dark:border-dark-tremor-border"
                    >
                      <div className="sticky left-0 z-10 truncate border-r border-tremor-border bg-tremor-background px-3 py-2 text-xs font-medium dark:border-dark-tremor-border dark:bg-dark-tremor-background">
                        {row.label}
                      </div>
                      <div className="relative h-12 bg-slate-50 px-2 dark:bg-slate-900/40">
                        {base ? (
                          <div
                            className="absolute top-2 h-3 rounded bg-teal-500/90"
                            style={base}
                            title={`${CHART_RU.baseEnd}: ${row.base_end}`}
                          />
                        ) : null}
                        {plan ? (
                          <div
                            className="absolute bottom-2 h-3 rounded bg-orange-400/90"
                            style={plan}
                            title={`${CHART_RU.planEnd}: ${row.plan_end}`}
                          />
                        ) : null}
                      </div>
                    </div>
                  );
                })}
              </div>
            </div>
          )}
        </Card>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Отклонение от базового плана (таблица)
            </Title>
            <Text className="mt-1">Только задачи с отставанием окончания</Text>
          </div>
          <div className="max-h-[28rem] overflow-auto">
            {(data?.rows.length ?? 0) === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                Нет строк с отставанием по выбранным фильтрам.
              </div>
            ) : (
              <table className="min-w-full border-separate border-spacing-0 text-left text-xs">
                <thead className="sticky top-0 z-20 bg-tremor-background-subtle text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                  <tr>
                    {[
                      "Проект",
                      "ID",
                      "Задача",
                      "Блок",
                      "Баз. начало",
                      "Начало",
                      "Откл. нач.",
                      "Баз. оконч.",
                      "Окончание",
                      "Откл. оконч.",
                      "Баз. длит.",
                      "Длит.",
                      "Откл. длит.",
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
                      key={`${row.project}-${row.task_id ?? row.task}-${index}`}
                      className="border-b border-tremor-border dark:border-dark-tremor-border"
                    >
                      <td className="whitespace-nowrap px-3 py-2 font-medium">
                        {row.project}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{row.task_id ?? "—"}</td>
                      <td className="max-w-xs truncate px-3 py-2">{row.task}</td>
                      <td className="px-3 py-2">{row.block ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.base_start ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.plan_start ?? "—"}</td>
                      <td className={`px-3 py-2 tabular-nums ${deviationClass(row.dev_start_days)}`}>
                        {row.dev_start}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{row.base_end ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.plan_end ?? "—"}</td>
                      <td className={`px-3 py-2 tabular-nums ${deviationClass(row.dev_end_days)}`}>
                        {row.dev_end}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {row.base_dur_days ?? "—"}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {row.plan_dur_days ?? "—"}
                      </td>
                      <td className={`px-3 py-2 tabular-nums ${deviationClass(row.dev_dur_days)}`}>
                        {row.dev_dur}
                      </td>
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
