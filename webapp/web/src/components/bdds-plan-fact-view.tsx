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
import {
  FilterCheck,
  FilterChipSelect,
  FilterChecksRow,
  FilterField,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import { buildFilterChips } from "@/lib/filters-summary";
import { useUrlFilterState } from "@/lib/use-url-filter-state";
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

const selectClass = FILTER_SELECT_CLASS;
const CELL = "border border-[#cbd5e1] dark:border-[#7a9ec4]";
const HEAD =
  "border border-[#cbd5e1] bg-[#e8f0fe] px-3 py-2 text-xs font-semibold uppercase text-[#111827] dark:border-[#7a9ec4] dark:bg-[#16283a] dark:text-[#f0f4f8]";
const TABLE =
  "min-w-full border-collapse border-2 border-[#94a3b8] text-left text-tremor-default dark:border-[#7a9ec4]";
const BODY =
  "px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong";
const TOTAL =
  "border-t-[3px] border-t-[#94a3b8] !bg-[#f1f5f9] font-bold dark:border-t-white dark:!bg-[#16283a]";
const BANNER =
  "break-words rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-950 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100";

function mlnCell(value: number, compact = false): string {
  const n = (Number(value || 0) / 1_000_000).toFixed(1);
  return compact ? n : `${n} млн. руб.`;
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

  const [filtersOpen, setFiltersOpen] = useState(false);
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

  const periodExport = useCallback((): ExportTable | null => {
    if (!periodRows.length) return null;
    const headers = [
      periodLabel,
      "БДДС план",
      "БДДС факт",
      "БДДС прогноз",
      ...(filters.hide_deviation ? [] : [deviationColumn]),
    ];
    return {
      header: [headers],
      rows: periodRows.map((row) => [
        row.period,
        mlnPlain(row.plan),
        mlnPlain(row.fact),
        mlnPlain(row.forecast),
        ...(filters.hide_deviation ? [] : [mlnPlain(row.deviation)]),
      ]),
      sheetName: "Прогнозный бюджет",
    };
  }, [periodRows, periodLabel, deviationColumn, filters.hide_deviation]);

  const statusExport = useCallback((): ExportTable | null => {
    const statusRows = data?.status_rows ?? [];
    if (!statusRows.length) return null;
    return {
      header: [
        [
          "Месяц",
          "Проект",
          "БДДС (план), млн",
          "БДДС (факт), млн",
          "БДДС (прогноз), млн",
          "Отклонение по сумме, млн",
          "Статус",
        ],
      ],
      rows: statusRows.map((row) => [
        row.month,
        row.project,
        row.plan_mln.toFixed(2),
        row.fact_mln.toFixed(2),
        row.forecast_mln.toFixed(2),
        row.deviation_mln.toFixed(2),
        row.status,
      ]),
      sheetName: "Статус",
    };
  }, [data?.status_rows]);

  useUrlFilterState(filters, INITIAL, (patch) =>
    setFilters((s) => ({ ...s, ...patch })),
  );

  const optionLabel = (
    items: Array<{ id: string; label: string }> | undefined,
    id: string,
  ) => items?.find((i) => i.id === id)?.label ?? id;

  const activeFilters = buildFilterChips(
    filters,
    INITIAL,
    [
      { key: "project", name: "Проект" },
      {
        key: "group",
        name: "Группировка",
        label: (v) => optionLabel(data?.filters.groups, v),
      },
      {
        key: "view",
        name: "Представление",
        label: (v) => optionLabel(data?.filters.views, v),
      },
      { key: "date_from", name: "С", kind: "date" },
      { key: "date_to", name: "По", kind: "date" },
      {
        key: "dev_base",
        name: "База отклонения",
        label: (v) => optionLabel(data?.filters.dev_bases, v),
      },
      { key: "hide_deviation", name: "Отклонение скрыто", kind: "flag" },
      { key: "hide_zero", name: "Нулевые месяцы", kind: "flag" },
    ],
    (patch) => setFilters((s) => ({ ...s, ...patch })),
  );

  return (
    <AppShell
      title="БДДС расходы (план, факт, уточненный план)"
      subtitle="Прогнозный бюджет: план, факт и БДДС прогноз по лотам MSP"
     loading={loading}>
      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((v) => !v)}
        activeFilters={activeFilters}
        onReset={activeFilters.length ? () => setFilters(INITIAL) : undefined}
      >
        <FiltersReset onClick={() => setFilters(INITIAL)} />
        <FilterFieldsRow cols={5}>
          <FilterChipSelect label="Проект" value={filters.project} options={data?.filters.projects ?? ["Все"]} onChange={(project) => setFilters((s) => ({ ...s, project }))} />
          <FilterChipSelect label="Группировать по" value={filters.group} options={(data?.filters.groups ?? [{ id: "month", label: "Месяц" }]).map((item) => ({ value: item.id, label: item.label }))} onChange={(group) => setFilters((s) => ({ ...s, group: group as Filters["group"] }))} />
          <FilterChipSelect label="Представление" value={filters.view} options={(data?.filters.views ?? []).map((item) => ({ value: item.id, label: item.label }))} onChange={(view) => setFilters((s) => ({ ...s, view: view as Filters["view"] }))} />
          <FilterField label="Дата с">
            <input
              type="date"
              className={selectClass}
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_from}
              onChange={(e) =>
                setFilters((s) => ({ ...s, date_from: e.target.value }))
              }
            />
          </FilterField>
          <FilterField label="Дата по">
            <input
              type="date"
              className={selectClass}
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_to}
              onChange={(e) =>
                setFilters((s) => ({ ...s, date_to: e.target.value }))
              }
            />
          </FilterField>
        </FilterFieldsRow>
        <FilterChipSelect
          label="Отклонение от БДДС прогноз считать к"
          value={filters.dev_base}
          options={(data?.filters.dev_bases ?? []).map((item) => ({ value: item.id, label: item.label }))}
          onChange={(dev_base) => setFilters((s) => ({ ...s, dev_base: dev_base as Filters["dev_base"] }))}
        />
        <FilterChecksRow cols={2}>
          <FilterCheck
            label="Скрыть отклонение"
            checked={filters.hide_deviation}
            onChange={(e) =>
              setFilters((s) => ({
                ...s,
                hide_deviation: e.target.checked,
              }))
            }
          />
          <FilterCheck
            label="Скрывать месяцы, где план, факт и прогноз равны 0"
            checked={zeroToggleEnabled ? hideZero : false}
            disabled={!zeroToggleEnabled}
            onChange={(e) =>
              setFilters((s) => ({
                ...s,
                hide_zero: e.target.checked,
              }))
            }
          />
        </FilterChecksRow>
        <Text className="mt-3">
          Режим данных: <b>{data?.meta.data_mode ?? "…"}</b>
          {loading ? " · загрузка…" : ` · ${data?.meta.rows ?? 0} периодов`}
        </Text>
      </FiltersCard>

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

      <div className="min-w-0 max-w-full space-y-6">
        <Card className="min-w-0 max-w-full overflow-hidden rounded-xl">
          <div className="border-b border-tremor-border px-3 py-3 dark:border-dark-tremor-border sm:px-4">
            <Title className="!break-words !text-base !text-tremor-content-strong sm:!text-tremor-title dark:!text-dark-tremor-content-strong">
              {data?.labels.chart_title ?? "График Прогнозный бюджет"}
            </Title>
          </div>
          <FullscreenPanel disabled={!chartRows.length} fill className="min-w-0">
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

        <Card className="min-w-0 max-w-full overflow-hidden rounded-xl p-0">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-tremor-border px-3 py-3 dark:border-dark-tremor-border sm:px-4">
            <Title className="min-w-0 flex-1 !break-words !text-base !text-tremor-content-strong sm:!text-tremor-title dark:!text-dark-tremor-content-strong">
              {data?.labels.period_table_title ?? "Таблица Прогнозный бюджет"}
            </Title>
            <DownloadTableButton
              getTable={periodExport}
              fileStem="forecast_bddcs_summary"
              disabled={!periodRows.length}
            />
          </div>
          <FullscreenPanel disabled={!periodRows.length} className="min-w-0">
            <div className="min-w-0 p-1 pt-3 lg:pt-1">
              {!periodRows.length ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "Загрузка…" : "Нет строк для таблицы по выбранным фильтрам."}
                </div>
              ) : (
                <>
                  <div className="lg:hidden">
                    <div className="flex flex-col gap-3 px-2 pb-2">
                      <p className="px-1 text-[10px] text-tremor-content dark:text-dark-tremor-content">
                        Значения — млн ₽
                      </p>
                      {dataRows.map((row) => (
                        <div
                          key={row.period}
                          className="min-w-0 rounded-xl border-[3px] border-[#94a3b8] p-3 text-xs dark:border-white"
                        >
                          <div className="mb-2 break-words font-semibold">{row.period}</div>
                          <dl className="grid grid-cols-2 gap-1">
                            <dt>План</dt>
                            <dd className="text-right tabular-nums">{mlnCell(row.plan, true)}</dd>
                            <dt>Факт</dt>
                            <dd className="text-right tabular-nums">{mlnCell(row.fact, true)}</dd>
                            <dt>Прогноз</dt>
                            <dd className="text-right tabular-nums">{mlnCell(row.forecast, true)}</dd>
                            {!filters.hide_deviation ? (
                              <>
                                <dt>Откл.</dt>
                                <dd
                                  className={`text-right tabular-nums ${deviationClass(row.deviation)}`}
                                >
                                  {mlnCell(row.deviation, true)}
                                </dd>
                              </>
                            ) : null}
                          </dl>
                        </div>
                      ))}
                      {totalRow ? (
                        <div className={`min-w-0 rounded-xl border-[3px] border-[#94a3b8] p-3 text-xs font-bold dark:border-white ${TOTAL}`}>
                          <div className="mb-2">ИТОГО</div>
                          <dl className="grid grid-cols-2 gap-1">
                            <dt>План</dt>
                            <dd className="text-right tabular-nums">{mlnCell(totalRow.plan, true)}</dd>
                            <dt>Факт</dt>
                            <dd className="text-right tabular-nums">{mlnCell(totalRow.fact, true)}</dd>
                            <dt>Прогноз</dt>
                            <dd className="text-right tabular-nums">{mlnCell(totalRow.forecast, true)}</dd>
                            {!filters.hide_deviation ? (
                              <>
                                <dt>Откл.</dt>
                                <dd
                                  className={`text-right tabular-nums ${deviationClass(totalRow.deviation)}`}
                                >
                                  {mlnCell(totalRow.deviation, true)}
                                </dd>
                              </>
                            ) : null}
                          </dl>
                        </div>
                      ) : null}
                    </div>
                  </div>
                  <div className="bi-table-scroll hidden overflow-x-auto lg:block">
                    <table className={`${TABLE} bi-sticky-head bi-sticky-col`}>
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

        <Card className="min-w-0 max-w-full overflow-hidden rounded-xl p-0">
          <div className="flex flex-wrap items-center justify-between gap-2 border-b border-tremor-border px-3 py-3 dark:border-dark-tremor-border sm:px-4">
            <Title className="min-w-0 flex-1 !break-words !text-base !text-tremor-content-strong sm:!text-tremor-title dark:!text-dark-tremor-content-strong">
              {data?.labels.status_table_title ?? "Статус"}
            </Title>
            <DownloadTableButton
              getTable={statusExport}
              fileStem="forecast_bddcs_financier_status"
              disabled={!(data?.status_rows.length ?? 0)}
            />
          </div>
          <div className="min-w-0 p-1">
            {!(data?.status_rows.length ?? 0) ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                {loading ? "Загрузка…" : "Нет данных для статуса."}
              </div>
            ) : (
              <>
                <div className="lg:hidden">
                  <div className="flex flex-col gap-3 px-2 pb-2">
                    <p className="px-1 text-[10px] text-tremor-content dark:text-dark-tremor-content">
                      Значения — млн ₽
                    </p>
                    {(data?.status_rows ?? []).map((row, index) => (
                      <div
                        key={`${row.month}-${row.project}-${index}`}
                        className="min-w-0 rounded-xl border-[3px] border-[#94a3b8] p-3 text-xs dark:border-white"
                      >
                        <div className="mb-1 break-words font-semibold">
                          {row.month} · {row.project}
                        </div>
                        <dl className="grid grid-cols-2 gap-1">
                          <dt>План</dt>
                          <dd className="text-right tabular-nums">{row.plan_mln.toFixed(1)}</dd>
                          <dt>Факт</dt>
                          <dd className="text-right tabular-nums">{row.fact_mln.toFixed(1)}</dd>
                          <dt>Прогноз</dt>
                          <dd className="text-right tabular-nums">{row.forecast_mln.toFixed(1)}</dd>
                          <dt>Откл.</dt>
                          <dd className={`text-right tabular-nums ${deviationClass(row.deviation_mln * 1e6)}`}>
                            {row.deviation_mln.toFixed(1)}
                          </dd>
                          <dt className="col-span-2 mt-1">Статус</dt>
                          <dd className={`col-span-2 break-words ${statusClass(row.status)}`}>
                            {row.status}
                          </dd>
                        </dl>
                      </div>
                    ))}
                  </div>
                </div>
                <div className="bi-table-scroll hidden overflow-x-auto lg:block">
                <table className={`${TABLE} bi-sticky-head bi-sticky-col`}>
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
