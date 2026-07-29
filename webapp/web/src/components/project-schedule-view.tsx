"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Grid, Metric, Text, Title } from "@tremor/react";
import {
  fetchProjectSchedule,
  type ProjectSchedulePayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { CHART_RU } from "@/lib/chart-ru";

function toMs(iso: string | null | undefined): number | null {
  if (!iso) return null;
  const ms = Date.parse(iso);
  return Number.isFinite(ms) ? ms : null;
}

function barStyle(
  startIso: string | null | undefined,
  endIso: string | null | undefined,
  rangeStart: number,
  rangeSpan: number,
): { left: string; width: string } | null {
  const start = toMs(startIso);
  const end = toMs(endIso);
  if (start == null || end == null || rangeSpan <= 0) return null;
  const left = ((start - rangeStart) / rangeSpan) * 100;
  const width = Math.max(((end - start) / rangeSpan) * 100, 0.4);
  return {
    left: `${Math.max(0, Math.min(left, 100))}%`,
    width: `${Math.max(0.4, Math.min(width, 100 - Math.max(0, left)))}%`,
  };
}

function deviationClass(days: number | null | undefined): string {
  if (days == null) return "text-tremor-content dark:text-dark-tremor-content";
  if (days > 0) return "font-semibold text-rose-700 dark:text-rose-300";
  if (days < 0) return "font-semibold text-emerald-700 dark:text-emerald-300";
  return "font-semibold text-emerald-800 dark:text-emerald-200";
}

export function ProjectScheduleView() {
  const [project, setProject] = useState("Все");
  const [level, setLevel] = useState("4");
  const [block, setBlock] = useState("Все");
  const [hideCompleted, setHideCompleted] = useState(false);
  const [onlyDelay, setOnlyDelay] = useState(false);
  const [data, setData] = useState<ProjectSchedulePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchProjectSchedule({
          project,
          level,
          block,
          hide_completed: hideCompleted,
          only_delay: onlyDelay,
        }),
      );
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [project, level, block, hideCompleted, onlyDelay]);

  useEffect(() => {
    void load();
  }, [load]);

  const range = useMemo(() => {
    const start = toMs(data?.gantt.range_start);
    const end = toMs(data?.gantt.range_end);
    if (start == null || end == null || end <= start) {
      return null;
    }
    return { start, span: end - start };
  }, [data]);

  const kpis = data?.kpis;
  const kpiCards = [
    { title: "Задачи", metric: kpis?.tasks ?? 0 },
    {
      title: "Средний %",
      metric: `${Number(kpis?.avg_pct ?? 0).toFixed(1)}%`,
    },
    { title: "С отставанием", metric: kpis?.delayed ?? 0 },
    { title: "Завершено", metric: kpis?.completed ?? 0 },
  ];

  const selectClass =
    "mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background";

  return (
    <AppShell
      title="График проекта"
      subtitle="Гант MSP: план = базовые даты, факт = текущий план (Начало/Окончание)"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
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
            <Text>Уровень</Text>
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
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={hideCompleted}
              onChange={(event) => setHideCompleted(event.target.checked)}
            />
            <Text>Скрыть 100%</Text>
          </label>
          <label className="flex items-end gap-2 pb-2 text-sm">
            <input
              type="checkbox"
              checked={onlyDelay}
              onChange={(event) => setOnlyDelay(event.target.checked)}
            />
            <Text>Только отставание</Text>
          </label>
        </div>
        <Text className="mt-3">
          Режим данных: <b>{data?.meta.data_mode ?? "…"}</b>
          {" · "}
          {loading
            ? "загрузка…"
            : `${data?.meta.files ?? 0} файлов · ${data?.meta.rows ?? 0} задач`}
          {data?.gantt.capped ? " · гант ограничен 600 строками" : null}
          {data?.filters.applied.level_skipped
            ? " · для «Ковенанты» уровень не применяется (как в Streamlit)"
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
          {kpiCards.map((kpi) => (
            <Card key={kpi.title} className="rounded-xl">
              <Text>{kpi.title}</Text>
              <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {kpi.metric}
              </Metric>
            </Card>
          ))}
        </Grid>

        <Card className="rounded-xl">
          <div className="mb-4 flex flex-wrap items-end justify-between gap-3">
            <div>
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Диаграмма Ганта
              </Title>
              <Text className="mt-1">
                {CHART_RU.plan} = база · {CHART_RU.fact} = текущий план
              </Text>
            </div>
            <div className="flex gap-4 text-sm">
              <span className="inline-flex items-center gap-2">
                <span className="inline-block h-2.5 w-6 rounded bg-teal-500" />
                {CHART_RU.plan}
              </span>
              <span className="inline-flex items-center gap-2">
                <span className="inline-block h-2.5 w-6 rounded bg-orange-400" />
                {CHART_RU.fact}
              </span>
            </div>
          </div>

            {(data?.gantt.rows.length ?? 0) === 0 || !range ? (
            <div className="py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
              Нет задач для отображения на ганте.
              {block !== "Все"
                ? ` Смените блок «${block}» или уровень.`
                : null}
            </div>
          ) : (
            <div className="max-h-[34rem] overflow-auto rounded-lg border border-tremor-border dark:border-dark-tremor-border">
              <div className="min-w-[720px]">
                {(data?.gantt.rows ?? []).map((row) => {
                  const baseline = barStyle(
                    row.baseline.start,
                    row.baseline.end,
                    range.start,
                    range.span,
                  );
                  const current = barStyle(
                    row.current.start,
                    row.current.end,
                    range.start,
                    range.span,
                  );
                  return (
                    <div
                      key={`${row.project}-${row.task}`}
                      className="grid grid-cols-[minmax(14rem,22rem)_1fr] border-b border-tremor-border dark:border-dark-tremor-border"
                    >
                      <div className="sticky left-0 z-10 truncate border-r border-tremor-border bg-tremor-background px-3 py-2 text-xs font-medium text-tremor-content-strong dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong">
                        {row.label}
                      </div>
                      <div className="relative h-12 bg-slate-50 px-2 dark:bg-slate-900/40">
                        {baseline ? (
                          <div
                            className="absolute top-2 h-3 rounded bg-teal-500/90"
                            style={baseline}
                            title={`${CHART_RU.plan}: ${row.baseline.start} → ${row.baseline.end}`}
                          />
                        ) : null}
                        {current ? (
                          <div
                            className="absolute bottom-2 h-3 rounded bg-orange-400/90"
                            style={current}
                            title={`${CHART_RU.fact}: ${row.current.start} → ${row.current.end}`}
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
              Таблица задач
            </Title>
          </div>
          <div className="max-h-[28rem] overflow-auto">
            {(data?.rows.length ?? 0) === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                Нет строк по выбранным фильтрам.
              </div>
            ) : (
              <table className="min-w-full border-separate border-spacing-0 text-left text-xs">
                <thead className="sticky top-0 z-20 bg-tremor-background-subtle text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                  <tr>
                    {[
                      "Проект",
                      "ИД",
                      "Ур",
                      "Название задачи",
                      "%",
                      "Начало",
                      "Баз. начало",
                      "Откл. начала",
                      "Окончание",
                      "Баз. окончание",
                      "Откл. окончания",
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
                      <td className="whitespace-nowrap px-3 py-2 font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                        {row.project}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{row.task_id ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.level ?? "—"}</td>
                      <td className="max-w-xs truncate px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                        {row.task}
                      </td>
                      <td className="px-3 py-2 tabular-nums">
                        {row.pct_complete == null ? "—" : `${row.pct_complete}%`}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{row.plan_start ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.base_start ?? "—"}</td>
                      <td className={`px-3 py-2 tabular-nums ${deviationClass(row.dev_start_days)}`}>
                        {row.dev_start}
                      </td>
                      <td className="px-3 py-2 tabular-nums">{row.plan_end ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.base_end ?? "—"}</td>
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
      </div>
    </AppShell>
  );
}
