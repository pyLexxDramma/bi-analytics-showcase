"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FinanceBarChart } from "@/components/finance-bar-chart";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  fetchBddsPlanFact,
  type BddsPlanFactPayload,
  type BddsPlanFactQuery,
} from "@/lib/api";
import { BddsPlanFactEditor } from "@/components/bdds-plan-fact-editor";
import type { ExportTable } from "@/lib/table-export";

type Filters = {
  project: string;
  date_from: string;
  date_to: string;
  group: "month" | "quarter" | "year";
  view: "monthly" | "cumulative";
  dev_base: "plan" | "fact";
  hide_deviation: boolean;
  hide_zero: boolean | null;
};

const INITIAL: Filters = {
  project: "Все",
  date_from: "",
  date_to: "",
  group: "month",
  view: "monthly",
  dev_base: "plan",
  hide_deviation: false,
  hide_zero: null,
};

const inputClass =
  "mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background";
const CELL = "border border-[#cbd5e1] dark:border-[#7a9ec4]";
const HEAD =
  "border border-[#cbd5e1] bg-[#e8f0fe] px-3 py-2 text-xs font-semibold uppercase text-[#111827] dark:border-[#7a9ec4] dark:bg-[#16283a] dark:text-[#f0f4f8]";
const TABLE =
  "min-w-full border-collapse border-2 border-[#94a3b8] text-left text-tremor-default dark:border-[#7a9ec4]";
const BODY =
  "px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong";
const TOTAL =
  "border-t-[3px] border-t-[#94a3b8] bg-[#f1f5f9] font-bold dark:border-t-white dark:bg-[#16283a]";
const BANNER =
  "rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-950 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100";

function mlnCell(value: number): string {
  return `${(Number(value || 0) / 1_000_000).toFixed(1)} млн. руб.`;
}

function mlnPlain(value: number): string {
  return (Number(value || 0) / 1_000_000).toFixed(1);
}

function deviationClass(value: number): string {
  if (Math.abs(value) < 10_000) return "";
  return value < 0
    ? "font-semibold text-[#b91c1c] dark:text-rose-300"
    : "font-semibold text-[#15803d] dark:text-emerald-300";
}

function statusClass(status: string): string {
  const s = status.toLowerCase();
  if (s.includes("перерасход")) return "text-[#15803d] dark:text-emerald-300";
  if (s.includes("отставание")) return "text-[#b91c1c] dark:text-rose-300";
  return "";
}

export function BddsPlanFactView() {
  const [filters, setFilters] = useState<Filters>(INITIAL);
  const [data, setData] = useState<BddsPlanFactPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const [previewError, setPreviewError] = useState<string | null>(null);

  const singleProject = filters.project !== "Все";

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      const query: BddsPlanFactQuery = {
        project: next.project,
        group: next.group,
        view: next.view,
        dev_base: next.dev_base,
        hide_deviation: next.hide_deviation,
      };
      if (next.date_from) query.date_from = next.date_from;
      if (next.date_to) query.date_to = next.date_to;
      if (next.hide_zero !== null) query.hide_zero = next.hide_zero;
      setData(await fetchBddsPlanFact(query));
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    if (singleProject) return;
    void load(filters);
  }, [filters, load, singleProject]);

  useEffect(() => {
    if (!data?.filters) return;
    setFilters((state) => {
      const applied = data.filters.applied;
      const nextFrom = applied.date_from ?? "";
      const nextTo = applied.date_to ?? "";
      if (state.date_from === nextFrom && state.date_to === nextTo) return state;
      return { ...state, date_from: nextFrom, date_to: nextTo };
    });
  }, [data?.filters.applied.date_from, data?.filters.applied.date_to]);

  const zeroToggleEnabled = filters.group === "month";
  const hideZero = filters.hide_zero ?? true;
  const showEditBanner = !singleProject;
  const metaError = data?.meta.error;
  const displayError = error || previewError || metaError;

  const chartRows = useMemo(
    () =>
      (data?.tremor.by_period ?? []).map((row) => ({
        period: row.period,
        plan: row.plan,
        fact: row.fact,
        forecast: row.forecast,
        deviation: row.deviation,
      })),
    [data?.tremor.by_period],
  );

  const periodRows = data?.period_rows ?? [];
  const dataRows = periodRows.filter((row) => row.kind !== "total");
  const totalRow = periodRows.find((row) => row.kind === "total");
  const deviationColumn =
    data?.labels.deviation_column ?? "Откл. (план − прогноз), млн";
  const periodLabel = data?.labels.period_column ?? "Месяц";

  const periodExport: ExportTable = useMemo(
    () => ({
      filename: "forecast_bddcs_summary",
      columns: [
        { key: "period", header: periodLabel },
        { key: "plan", header: "БДДС план" },
        { key: "fact", header: "БДДС факт" },
        { key: "forecast", header: "БДДС прогноз" },
        ...(filters.hide_deviation
          ? []
          : [{ key: "deviation", header: deviationColumn }]),
      ],
      rows: periodRows.map((row) => ({
        period: row.period,
        plan: mlnPlain(row.plan),
        fact: mlnPlain(row.fact),
        forecast: mlnPlain(row.forecast),
        deviation: mlnPlain(row.deviation),
      })),
    }),
    [periodRows, periodLabel, deviationColumn, filters.hide_deviation],
  );

  const statusExport: ExportTable = useMemo(
    () => ({
      filename: "forecast_bddcs_financier_status",
      columns: [
        { key: "month", header: "Месяц" },
        { key: "project", header: "Проект" },
        { key: "plan_mln", header: "БДДС (план), млн" },
        { key: "fact_mln", header: "БДДС (факт), млн" },
        { key: "forecast_mln", header: "БДДС (прогноз), млн" },
        { key: "deviation_mln", header: "Отклонение по сумме, млн" },
        { key: "status", header: "Статус" },
      ],
      rows: (data?.status_rows ?? []).map((row) => ({
        month: row.month,
        project: row.project,
        plan_mln: row.plan_mln.toFixed(2),
        fact_mln: row.fact_mln.toFixed(2),
        forecast_mln: row.forecast_mln.toFixed(2),
        deviation_mln: row.deviation_mln.toFixed(2),
        status: row.status,
      })),
    }),
    [data?.status_rows],
  );

  return (
    <AppShell
      title="БДДС расходы (план, факт, уточненный план)"
      subtitle="Прогнозный бюджет: план, факт и БДДС прогноз по лотам MSP"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
          <label className="block text-sm sm:col-span-2 lg:col-span-1">
            <Text>Проект</Text>
            <select
              className={inputClass}
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
            <Text>Группировать по</Text>
            <select
              className={inputClass}
              value={filters.group}
              onChange={(e) =>
                setFilters((s) => ({
                  ...s,
                  group: e.target.value as Filters["group"],
                }))
              }
            >
              {(data?.filters.groups ?? [{ id: "month", label: "Месяц" }]).map(
                (g) => (
                  <option key={g.id} value={g.id}>
                    {g.label}
                  </option>
                ),
              )}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Представление</Text>
            <select
              className={inputClass}
              value={filters.view}
              onChange={(e) =>
                setFilters((s) => ({
                  ...s,
                  view: e.target.value as Filters["view"],
                }))
              }
            >
              {(data?.filters.views ?? []).map((v) => (
                <option key={v.id} value={v.id}>
                  {v.label}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Дата с</Text>
            <input
              type="date"
              className={inputClass}
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
              className={inputClass}
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_to}
              onChange={(e) =>
                setFilters((s) => ({ ...s, date_to: e.target.value }))
              }
            />
          </label>
        </div>

        <div className="mt-4 space-y-3">
          <fieldset>
            <Text className="mb-2 block">
              Отклонение от БДДС прогноз считать к
            </Text>
            <div className="flex flex-wrap gap-4 text-sm">
              {(data?.filters.dev_bases ?? []).map((item) => (
                <label key={item.id} className="flex items-center gap-2">
                  <input
                    type="radio"
                    name="dev_base"
                    checked={filters.dev_base === item.id}
                    onChange={() =>
                      setFilters((s) => ({
                        ...s,
                        dev_base: item.id as Filters["dev_base"],
                      }))
                    }
                  />
                  {item.label}
                </label>
              ))}
            </div>
          </fieldset>
          <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                checked={filters.hide_deviation}
                onChange={(e) =>
                  setFilters((s) => ({
                    ...s,
                    hide_deviation: e.target.checked,
                  }))
                }
              />
              Скрыть отклонение
            </label>
            <label className="flex items-center gap-2">
              <input
                type="checkbox"
                disabled={!zeroToggleEnabled}
                checked={zeroToggleEnabled ? hideZero : false}
                onChange={(e) =>
                  setFilters((s) => ({
                    ...s,
                    hide_zero: e.target.checked,
                  }))
                }
              />
              <span className={zeroToggleEnabled ? "" : "opacity-50"}>
                Скрывать месяцы, где план, факт и прогноз равны 0
              </span>
            </label>
          </div>
        </div>

        <Text className="mt-3">
          Режим данных: <b>{data?.meta.data_mode ?? "…"}</b>
          {loading ? " · загрузка…" : ` · ${data?.meta.rows ?? 0} периодов`}
        </Text>
      </Card>

      {singleProject ? (
        <BddsPlanFactEditor
          project={filters.project}
          filters={{
            project: filters.project,
            date_from: filters.date_from || undefined,
            date_to: filters.date_to || undefined,
            group: filters.group,
            view: filters.view,
            dev_base: filters.dev_base,
            hide_deviation: filters.hide_deviation,
            hide_zero: filters.hide_zero,
          }}
          onDataChange={(payload) => {
            setData(payload);
            setLoading(false);
            setError(null);
          }}
          onPreviewError={setPreviewError}
        />
      ) : null}

      {showEditBanner ? (
        <div className={`${BANNER} mb-4`}>{data?.labels.edit_banner}</div>
      ) : null}

      {displayError ? (
        <Card className="mb-4 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            {displayError}
          </Text>
        </Card>
      ) : null}

      <div className="space-y-6">
        <Card className="rounded-xl">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {data?.labels.chart_title ?? "График Прогнозный бюджет"}
            </Title>
          </div>
          <FullscreenPanel disabled={!chartRows.length} fill>
            {(zoomed) => (
              <FinanceBarChart
                rows={chartRows}
                planName="БДДС план"
                factName="БДДС факт"
                forecastName="БДДС прогноз"
                showForecast
                showDeviation={!filters.hide_deviation}
                deviationLabel={
                  filters.dev_base === "fact"
                    ? "Откл. (факт − прогноз)"
                    : "Откл. (план − прогноз)"
                }
                xAxisTitle={periodLabel}
                fullscreen={zoomed}
                emptyText={
                  loading
                    ? "Загрузка…"
                    : "Нет периодов для графика. Снимите «Скрывать месяцы…» или измените фильтры."
                }
              />
            )}
          </FullscreenPanel>
        </Card>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {data?.labels.period_table_title ?? "Таблица Прогнозный бюджет"}
            </Title>
            <DownloadTableButton table={periodExport} disabled={!periodRows.length} />
          </div>
          <FullscreenPanel disabled={!periodRows.length}>
            <div className="p-1 pt-10">
              {!periodRows.length ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "Загрузка…" : "Нет строк для таблицы по выбранным фильтрам."}
                </div>
              ) : (
                <>
                  <div className="lg:hidden">
                    <div className="flex flex-col gap-3 px-2 pb-2">
                      {dataRows.map((row) => (
                        <div
                          key={row.period}
                          className="rounded-lg border-2 border-[#94a3b8] p-3 text-xs dark:border-[#7a9ec4]"
                        >
                          <div className="mb-2 font-semibold">{row.period}</div>
                          <dl className="grid grid-cols-2 gap-1">
                            <dt>План</dt>
                            <dd className="text-right tabular-nums">{mlnCell(row.plan)}</dd>
                            <dt>Факт</dt>
                            <dd className="text-right tabular-nums">{mlnCell(row.fact)}</dd>
                            <dt>Прогноз</dt>
                            <dd className="text-right tabular-nums">{mlnCell(row.forecast)}</dd>
                            {!filters.hide_deviation ? (
                              <>
                                <dt>Откл.</dt>
                                <dd
                                  className={`text-right tabular-nums ${deviationClass(row.deviation)}`}
                                >
                                  {mlnCell(row.deviation)}
                                </dd>
                              </>
                            ) : null}
                          </dl>
                        </div>
                      ))}
                      {totalRow ? (
                        <div className={`rounded-lg border-2 border-[#94a3b8] p-3 text-xs font-bold ${TOTAL}`}>
                          <div className="mb-2">ИТОГО</div>
                          <dl className="grid grid-cols-2 gap-1">
                            <dt>План</dt>
                            <dd className="text-right tabular-nums">{mlnCell(totalRow.plan)}</dd>
                            <dt>Факт</dt>
                            <dd className="text-right tabular-nums">{mlnCell(totalRow.fact)}</dd>
                            <dt>Прогноз</dt>
                            <dd className="text-right tabular-nums">{mlnCell(totalRow.forecast)}</dd>
                            {!filters.hide_deviation ? (
                              <>
                                <dt>Откл.</dt>
                                <dd
                                  className={`text-right tabular-nums ${deviationClass(totalRow.deviation)}`}
                                >
                                  {mlnCell(totalRow.deviation)}
                                </dd>
                              </>
                            ) : null}
                          </dl>
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <div className="hidden overflow-x-auto lg:block">
                    <table className={TABLE}>
                      <thead>
                        <tr>
                          <th className={HEAD}>{periodLabel}</th>
                          <th className={`${HEAD} text-right`}>БДДС план</th>
                          <th className={`${HEAD} text-right`}>БДДС факт</th>
                          <th className={`${HEAD} text-right`}>БДДС прогноз</th>
                          {!filters.hide_deviation ? (
                            <th className={`${HEAD} text-right`}>{deviationColumn}</th>
                          ) : null}
                        </tr>
                      </thead>
                      <tbody>
                        {dataRows.map((row) => (
                          <tr key={row.period}>
                            <td className={`${CELL} ${BODY}`}>{row.period}</td>
                            <td className={`${CELL} ${BODY} text-right tabular-nums`}>
                              {mlnCell(row.plan)}
                            </td>
                            <td className={`${CELL} ${BODY} text-right tabular-nums`}>
                              {mlnCell(row.fact)}
                            </td>
                            <td className={`${CELL} ${BODY} text-right tabular-nums`}>
                              {mlnCell(row.forecast)}
                            </td>
                            {!filters.hide_deviation ? (
                              <td
                                className={`${CELL} ${BODY} text-right tabular-nums ${deviationClass(row.deviation)}`}
                              >
                                {mlnCell(row.deviation)}
                              </td>
                            ) : null}
                          </tr>
                        ))}
                        {totalRow ? (
                          <tr className={TOTAL}>
                            <td className={`${CELL} ${BODY}`}>ИТОГО</td>
                            <td className={`${CELL} ${BODY} text-right tabular-nums`}>
                              {mlnCell(totalRow.plan)}
                            </td>
                            <td className={`${CELL} ${BODY} text-right tabular-nums`}>
                              {mlnCell(totalRow.fact)}
                            </td>
                            <td className={`${CELL} ${BODY} text-right tabular-nums`}>
                              {mlnCell(totalRow.forecast)}
                            </td>
                            {!filters.hide_deviation ? (
                              <td
                                className={`${CELL} ${BODY} text-right tabular-nums ${deviationClass(totalRow.deviation)}`}
                              >
                                {mlnCell(totalRow.deviation)}
                              </td>
                            ) : null}
                          </tr>
                        ) : null}
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </div>
          </FullscreenPanel>
        </Card>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {data?.labels.status_table_title ?? "Статус"}
            </Title>
            <DownloadTableButton
              table={statusExport}
              disabled={!(data?.status_rows.length ?? 0)}
            />
          </div>
          <div className="p-1">
            {!(data?.status_rows.length ?? 0) ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                {loading ? "Загрузка…" : "Нет данных для статуса."}
              </div>
            ) : (
              <>
                <div className="lg:hidden">
                  <div className="flex flex-col gap-3 px-2 pb-2">
                    {(data?.status_rows ?? []).map((row, index) => (
                      <div
                        key={`${row.month}-${row.project}-${index}`}
                        className="rounded-lg border-2 border-[#94a3b8] p-3 text-xs dark:border-[#7a9ec4]"
                      >
                        <div className="mb-1 font-semibold">
                          {row.month} · {row.project}
                        </div>
                        <dl className="grid grid-cols-2 gap-1">
                          <dt>План</dt>
                          <dd className="text-right">{row.plan_mln.toFixed(2)}</dd>
                          <dt>Факт</dt>
                          <dd className="text-right">{row.fact_mln.toFixed(2)}</dd>
                          <dt>Прогноз</dt>
                          <dd className="text-right">{row.forecast_mln.toFixed(2)}</dd>
                          <dt>Откл.</dt>
                          <dd className={`text-right ${deviationClass(row.deviation_mln * 1e6)}`}>
                            {row.deviation_mln.toFixed(2)}
                          </dd>
                          <dt className="col-span-2 mt-1">Статус</dt>
                          <dd className={`col-span-2 ${statusClass(row.status)}`}>
                            {row.status}
                          </dd>
                        </dl>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="hidden overflow-x-auto lg:block">
                <table className={TABLE}>
                  <thead>
                    <tr>
                      <th className={HEAD}>Месяц</th>
                      <th className={HEAD}>Проект</th>
                      <th className={`${HEAD} text-right`}>БДДС (план), млн</th>
                      <th className={`${HEAD} text-right`}>БДДС (факт), млн</th>
                      <th className={`${HEAD} text-right`}>БДДС (прогноз), млн</th>
                      <th className={`${HEAD} text-right`}>Отклонение по сумме, млн</th>
                      <th className={HEAD}>Статус</th>
                    </tr>
                  </thead>
                  <tbody>
                    {(data?.status_rows ?? []).map((row, index) => (
                      <tr key={`${row.month}-${row.project}-${index}`}>
                        <td className={`${CELL} ${BODY}`}>{row.month}</td>
                        <td className={`${CELL} ${BODY}`}>{row.project}</td>
                        <td className={`${CELL} ${BODY} text-right tabular-nums`}>
                          {row.plan_mln.toFixed(2)}
                        </td>
                        <td className={`${CELL} ${BODY} text-right tabular-nums`}>
                          {row.fact_mln.toFixed(2)}
                        </td>
                        <td className={`${CELL} ${BODY} text-right tabular-nums`}>
                          {row.forecast_mln.toFixed(2)}
                        </td>
                        <td
                          className={`${CELL} ${BODY} text-right tabular-nums ${deviationClass(row.deviation_mln * 1e6)}`}
                        >
                          {row.deviation_mln.toFixed(2)}
                        </td>
                        <td className={`${CELL} ${BODY} ${statusClass(row.status)}`}>
                          {row.status}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                </div>
              </>
            )}
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
