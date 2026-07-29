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
  fetchDeviationReasons,
  type DeviationReasonsPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { CHART_RU, withRuReasonCount } from "@/lib/chart-ru";

export function DeviationReasonsView() {
  const [project, setProject] = useState("Все");
  const [block, setBlock] = useState("Все");
  const [reason, setReason] = useState("Все");
  const [dateFrom, setDateFrom] = useState("");
  const [dateTo, setDateTo] = useState("");
  const [periodReady, setPeriodReady] = useState(false);
  const [data, setData] = useState<DeviationReasonsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchDeviationReasons({
        project,
        block,
        reason,
        date_from: dateFrom || undefined,
        date_to: dateTo || undefined,
      });
      setData(payload);
      if (!periodReady) {
        setDateFrom(payload.filters.applied.date_from ?? "");
        setDateTo(payload.filters.applied.date_to ?? "");
        setPeriodReady(true);
      }
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [project, block, reason, dateFrom, dateTo, periodReady]);

  useEffect(() => {
    void load();
  }, [load]);

  const kpis = data?.kpis;
  const selectClass =
    "mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background";

  return (
    <AppShell
      title="Причины отклонений"
      subtitle="Доли причин по задачам ур. 5 с отставанием окончания (база − план < 0)"
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
            <Text>Причина</Text>
            <select
              className={selectClass}
              value={reason}
              onChange={(event) => setReason(event.target.value)}
            >
              {(data?.filters.reasons ?? ["Все"]).map((item) => (
                <option key={item} value={item}>
                  {item}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Период с</Text>
            <input
              type="date"
              className={selectClass}
              value={dateFrom}
              min={data?.filters.period.min ?? undefined}
              max={data?.filters.period.max ?? undefined}
              onChange={(event) => setDateFrom(event.target.value)}
            />
          </label>
          <label className="block text-sm">
            <Text>Период по</Text>
            <input
              type="date"
              className={selectClass}
              value={dateTo}
              min={data?.filters.period.min ?? undefined}
              max={data?.filters.period.max ?? undefined}
              onChange={(event) => setDateTo(event.target.value)}
            />
          </label>
        </div>
        <Text className="mt-3">
          Режим данных: <b>{data?.meta.data_mode ?? "…"}</b>
          {" · "}
          {loading
            ? "загрузка…"
            : `${data?.meta.files ?? 0} файлов · ${data?.meta.rows ?? 0} задач`}
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
            <Text>Основная причина отклонения</Text>
            <Metric className="mt-2 text-base text-tremor-content-strong dark:text-dark-tremor-content-strong sm:text-xl">
              {kpis?.main_reason ?? "—"}
            </Metric>
          </Card>
          <Card className="rounded-xl">
            <Text>Доля основной причины</Text>
            <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
              {`${Number(kpis?.main_reason_share_pct ?? 0).toFixed(1)}% (${kpis?.main_reason_count ?? 0})`}
            </Metric>
            <Text className="mt-2">Всего задач: {kpis?.tasks ?? 0}</Text>
          </Card>
        </Grid>

        <Grid numItemsLg={3} className="gap-6">
          <Card className="rounded-xl lg:col-span-2">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Причины отклонений (за отчётный период)
            </Title>
            <Text className="mt-1">Количество задач по причине</Text>
            <BarChart
              className="mt-6 h-80"
              data={withRuReasonCount(data?.tremor.by_reason ?? [])}
              index="reason"
              categories={[CHART_RU.reasonCount]}
              colors={["rose"]}
              valueFormatter={(value) => `${value}`}
              yAxisWidth={48}
              showLegend
              showAnimation
              showGridLines
            />
          </Card>
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Доли причин
            </Title>
            <Text className="mt-1">Распределение</Text>
            <DonutChart
              className="mt-6 h-52"
              data={data?.tremor.reason_mix ?? []}
              category="value"
              index="name"
              colors={["rose", "amber", "cyan", "emerald", "slate", "violet"]}
              valueFormatter={(value) => `${value} шт.`}
            />
          </Card>
        </Grid>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Детальные данные
            </Title>
            <Text className="mt-1">
              Записей (по макету): {data?.meta.rows ?? 0}
            </Text>
          </div>
          <div className="max-h-[28rem] overflow-auto">
            {(data?.rows.length ?? 0) === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                Нет задач с причиной и отставанием по выбранным фильтрам.
              </div>
            ) : (
              <table className="min-w-full border-separate border-spacing-0 text-left text-xs">
                <thead className="sticky top-0 z-20 bg-tremor-background-subtle text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                  <tr>
                    {[
                      "ID",
                      "Проект",
                      "Блок",
                      "Строение",
                      "Баз. окончание",
                      "Окончание",
                      "Отклонение",
                      "Причина",
                      "Заметки",
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
                      key={`${row.project}-${row.task_id ?? row.reason}-${index}`}
                      className="border-b border-tremor-border dark:border-dark-tremor-border"
                    >
                      <td className="px-3 py-2 tabular-nums">{row.task_id ?? "—"}</td>
                      <td className="whitespace-nowrap px-3 py-2 font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                        {row.project}
                      </td>
                      <td className="px-3 py-2">{row.block ?? "—"}</td>
                      <td className="px-3 py-2">{row.building ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.base_end ?? "—"}</td>
                      <td className="px-3 py-2 tabular-nums">{row.plan_end ?? "—"}</td>
                      <td className="px-3 py-2 font-semibold tabular-nums text-rose-700 dark:text-rose-300">
                        {row.end_diff_days}
                      </td>
                      <td
                        className="max-w-xs px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong"
                        style={{ borderLeft: `4px solid ${row.bucket_color}` }}
                        title={row.bucket}
                      >
                        {row.reason}
                      </td>
                      <td className="max-w-xs truncate px-3 py-2">
                        {row.notes ?? "—"}
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
