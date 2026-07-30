"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FinanceBarChart } from "@/components/finance-bar-chart";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  fetchBdds,
  type BddsGroup,
  type BddsPayload,
  type BddsTableRow,
  type BddsView,
} from "@/lib/api";
import type { ExportTable } from "@/lib/table-export";

type Filters = {
  projects: string[];
  date_from: string;
  date_to: string;
  group: BddsGroup;
  view: BddsView;
  hide_zero: boolean | null;
  show_deviation: boolean;
};

const INITIAL: Filters = {
  projects: [],
  date_from: "",
  date_to: "",
  group: "month",
  view: "monthly",
  hide_zero: null,
  show_deviation: false,
};

const PLAN_SERIES = "БДДС план";
const FACT_SERIES = "БДДС факт";

const inputClass =
  "mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background";
const chipClass =
  "rounded-md border px-2.5 py-1 text-xs border-tremor-border bg-white text-tremor-content-strong dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong";
const chipOnClass =
  "rounded-md border px-2.5 py-1 text-xs border-emerald-600 bg-emerald-50 text-emerald-900 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-200";

/** Сетка и рамки как в CSS финансовых таблиц [main] (1px #cbd5e1 / #7a9ec4). */
const CELL = "border border-[#cbd5e1] dark:border-[#7a9ec4]";
const HEAD_CELL =
  "border border-[#cbd5e1] bg-[#e8f0fe] px-3 py-2 text-xs font-semibold uppercase text-[#111827] dark:border-[#7a9ec4] dark:bg-[#16283a] dark:text-[#f0f4f8]";
const TABLE =
  "min-w-full border-collapse border-2 border-[#94a3b8] text-left text-tremor-default dark:border-[#7a9ec4]";
const BANNER =
  "bg-[#e2e8f0] px-3 py-2 font-bold text-[#111827] dark:bg-slate-600/50 dark:text-[#f0f4f8]";
const TOTAL_ROW =
  "border-t-[3px] border-t-[#94a3b8] bg-[#f1f5f9] font-bold dark:border-t-white dark:bg-[#16283a]";
const BODY_CELL =
  "px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong";

type SortKey = "project" | "period" | "plan" | "fact" | "deviation";
type SortState = { key: SortKey; asc: boolean } | null;
type PeriodRow = BddsTableRow & { _index: number };
type ProjectRow = BddsPayload["project_rows"][number] & { _index: number };

/** «445.6 млн. руб.» — `utils.format_million_rub(value, decimals=1)` в [main]. */
function mlnCell(value: number): string {
  return `${(Number(value || 0) / 1_000_000).toFixed(1)} млн. руб.`;
}

function mlnNumber(value: number): number {
  return Number((Number(value || 0) / 1_000_000).toFixed(1));
}

function deviationClass(value: number): string {
  if (Math.abs(value) < 10_000) {
    return "text-tremor-content-strong dark:text-dark-tremor-content-strong";
  }
  return value < 0
    ? "font-semibold text-[#b91c1c] dark:text-rose-300"
    : "font-semibold text-[#15803d] dark:text-emerald-300";
}

function SortableHeader({
  label,
  sortKey,
  sort,
  onSort,
  align = "left",
}: {
  label: string;
  sortKey: SortKey;
  sort: SortState;
  onSort: (key: SortKey) => void;
  align?: "left" | "right";
}) {
  const active = sort?.key === sortKey;
  return (
    <th className={`${HEAD_CELL} ${align === "right" ? "text-right" : "text-left"}`}>
      <button
        type="button"
        onClick={() => onSort(sortKey)}
        title="Сортировать по колонке"
        className={`flex w-full items-center gap-1 ${
          align === "right" ? "justify-end" : "justify-start"
        }`}
      >
        <span>{label}</span>
        <span className={active ? "text-emerald-700 dark:text-emerald-300" : "opacity-60"}>
          {active ? (sort?.asc ? "↑" : "↓") : "⇅"}
        </span>
      </button>
    </th>
  );
}

/** Период сортируется хронологически (порядок строк API), остальные колонки — по значению. */
function compareRows(
  a: PeriodRow | ProjectRow,
  b: PeriodRow | ProjectRow,
  key: SortKey,
): number {
  if (key === "period") return a._index - b._index;
  if (key === "project") {
    return String(a.project ?? "").localeCompare(String(b.project ?? ""), "ru");
  }
  return Number(a[key] ?? 0) - Number(b[key] ?? 0);
}

function sorted<T extends PeriodRow | ProjectRow>(rows: T[], sort: SortState): T[] {
  if (!sort) return rows;
  return [...rows].sort((a, b) => {
    const diff = compareRows(a, b, sort.key);
    return sort.asc ? diff : -diff;
  });
}

export function BddsView() {
  const [filters, setFilters] = useState<Filters>(INITIAL);
  const [data, setData] = useState<BddsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [periodSort, setPeriodSort] = useState<SortState>(null);
  const [projectSort, setProjectSort] = useState<SortState>(null);

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchBdds({
          projects: next.projects,
          date_from: next.date_from || undefined,
          date_to: next.date_to || undefined,
          group: next.group,
          view: next.view,
          hide_zero: next.hide_zero ?? undefined,
          show_deviation: next.show_deviation,
        }),
      );
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

  const periodLabel = data?.labels.period ?? "Месяц";
  const zeroToggleEnabled = filters.group === "month" && filters.view === "monthly";
  // как в main: чекбокс включён по умолчанию, пока не выбран конкретный проект
  const hideZero = filters.hide_zero ?? filters.projects.length === 0;
  const periodRows = useMemo(() => data?.period_rows ?? [], [data]);
  const projectRows = useMemo(() => data?.project_rows ?? [], [data]);
  const totals = data?.totals ?? { plan: 0, fact: 0, deviation: 0 };
  const metaError = data?.meta.error ?? null;
  const hints = data?.hints ?? [];
  const appliedFrom = data?.filters.applied.date_from ?? "";
  const appliedTo = data?.filters.applied.date_to ?? "";

  const chartRows = useMemo(
    () => (data?.tremor.by_period ?? []).map((row) => ({ ...row })),
    [data],
  );

  /**
   * Без сортировки — блоки с баннерами проектов, как в [main].
   * При сортировке блоки разворачиваются в плоский список (иначе баннеры
   * оказались бы посреди чужих строк), а имя проекта переносится в строку.
   */
  const periodVisible = useMemo<PeriodRow[]>(() => {
    const indexed: PeriodRow[] = [];
    let banner = "";
    periodRows.forEach((row, index) => {
      if (row.kind === "project") banner = row.project;
      indexed.push({
        ...row,
        project: row.kind === "data" && !row.project ? banner : row.project,
        _index: index,
      });
    });
    if (!periodSort) return indexed;
    return sorted(
      indexed.filter((row) => row.kind === "data"),
      periodSort,
    );
  }, [periodRows, periodSort]);

  const projectVisible = useMemo<ProjectRow[]>(
    () => sorted(projectRows.map((row, index) => ({ ...row, _index: index })), projectSort),
    [projectRows, projectSort],
  );

  const togglePeriodSort = (key: SortKey) =>
    setPeriodSort((state) =>
      state && state.key === key ? (state.asc ? { key, asc: false } : null) : { key, asc: true },
    );
  const toggleProjectSort = (key: SortKey) =>
    setProjectSort((state) =>
      state && state.key === key ? (state.asc ? { key, asc: false } : null) : { key, asc: true },
    );

  const periodExport = (): ExportTable | null => {
    if (!periodRows.length) return null;
    const rows = periodRows.map((row) => [
      row.project,
      row.period,
      row.kind === "project" ? "" : mlnNumber(row.plan),
      row.kind === "project" ? "" : mlnNumber(row.fact),
      row.kind === "project" ? "" : mlnNumber(row.deviation),
    ]);
    rows.push([
      "ИТОГО",
      data?.labels.total_period ?? "",
      mlnNumber(totals.plan),
      mlnNumber(totals.fact),
      mlnNumber(totals.deviation),
    ]);
    return {
      header: [
        ["Проект", periodLabel, "План, млн. руб.", "Факт, млн. руб.", "Отклонение, млн. руб."],
      ],
      rows,
      sheetName: "БДДС",
    };
  };

  const projectExport = (): ExportTable | null => {
    if (!projectRows.length) return null;
    const rows = projectRows.map((row) => [
      row.project,
      mlnNumber(row.plan),
      mlnNumber(row.fact),
      mlnNumber(row.deviation),
    ]);
    rows.push([
      "ИТОГО",
      mlnNumber(totals.plan),
      mlnNumber(totals.fact),
      mlnNumber(totals.deviation),
    ]);
    return {
      header: [["Проект", "План, млн. руб.", "Факт, млн. руб.", "Отклонение, млн. руб."]],
      rows,
      sheetName: "БДДС по проектам",
    };
  };

  const toggleProject = (name: string) => {
    setFilters((state) => ({
      ...state,
      projects: state.projects.includes(name)
        ? state.projects.filter((p) => p !== name)
        : [...state.projects, name],
    }));
  };

  const dirty =
    filters.projects.length > 0 ||
    filters.date_from !== "" ||
    filters.date_to !== "" ||
    filters.group !== "month" ||
    filters.view !== "monthly" ||
    filters.hide_zero !== null ||
    filters.show_deviation;

  return (
    <AppShell title="БДДС (расходы)">
      <Card className="mb-6 rounded-xl">
        <button
          type="button"
          onClick={() => setFiltersOpen((state) => !state)}
          aria-expanded={filtersOpen}
          className="flex w-full items-center gap-2 text-left text-sm font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong"
        >
          <span className="text-xs">{filtersOpen ? "▾" : "▸"}</span>
          Фильтры
        </button>

        {filtersOpen ? (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setFilters(INITIAL)}
              disabled={!dirty}
              className="rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-1.5 text-sm disabled:opacity-40 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            >
              Сбросить
            </button>

            <Text className="mt-3">Проект</Text>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setFilters((state) => ({ ...state, projects: [] }))}
                className={filters.projects.length === 0 ? chipOnClass : chipClass}
              >
                Все
              </button>
              {(data?.filters.projects ?? []).map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => toggleProject(name)}
                  className={filters.projects.includes(name) ? chipOnClass : chipClass}
                >
                  {name}
                </button>
              ))}
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <label className="block text-sm">
                <Text>Период с</Text>
                <input
                  className={inputClass}
                  type="date"
                  min={data?.filters.date_min ?? undefined}
                  max={data?.filters.date_max ?? undefined}
                  value={filters.date_from || appliedFrom}
                  onChange={(event) =>
                    setFilters((state) => ({ ...state, date_from: event.target.value }))
                  }
                />
              </label>
              <label className="block text-sm">
                <Text>Период по</Text>
                <input
                  className={inputClass}
                  type="date"
                  min={data?.filters.date_min ?? undefined}
                  max={data?.filters.date_max ?? undefined}
                  value={filters.date_to || appliedTo}
                  onChange={(event) =>
                    setFilters((state) => ({ ...state, date_to: event.target.value }))
                  }
                />
              </label>
              <label className="block text-sm">
                <Text>Группировать по</Text>
                <select
                  className={inputClass}
                  value={filters.group}
                  onChange={(event) =>
                    setFilters((state) => ({ ...state, group: event.target.value as BddsGroup }))
                  }
                >
                  {(data?.filters.groups ?? [{ id: "month", label: "Месяц" }]).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <Text>Представление</Text>
                <select
                  className={inputClass}
                  value={filters.view}
                  onChange={(event) =>
                    setFilters((state) => ({ ...state, view: event.target.value as BddsView }))
                  }
                >
                  {(data?.filters.views ?? [{ id: "monthly", label: "По месяцам" }]).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={filters.show_deviation}
                  onChange={(event) =>
                    setFilters((state) => ({ ...state, show_deviation: event.target.checked }))
                  }
                />
                Показать отклонение
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  disabled={!zeroToggleEnabled}
                  checked={zeroToggleEnabled ? hideZero : false}
                  onChange={(event) =>
                    setFilters((state) => ({ ...state, hide_zero: event.target.checked }))
                  }
                />
                <span className={zeroToggleEnabled ? "" : "opacity-50"}>
                  Скрывать месяцы, где план и факт равны 0
                </span>
              </label>
            </div>
          </div>
        ) : null}
      </Card>

      {error || metaError ? (
        <Card className="mb-4 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">{error || metaError}</Text>
        </Card>
      ) : null}

      <div className="space-y-6">
        <Card className="rounded-xl">
          <FullscreenPanel disabled={!chartRows.length} fill>
            {(zoomed) => (
              <FinanceBarChart
                rows={chartRows}
                planName={PLAN_SERIES}
                factName={FACT_SERIES}
                showDeviation={filters.show_deviation}
                xAxisTitle={data?.labels.chart_caption ?? "БДДС по месяцам"}
                fullscreen={zoomed}
                emptyText={
                  loading
                    ? "Загрузка…"
                    : "Нет периодов для графика. Снимите «Скрывать месяцы, где план и факт равны 0» или расширьте период/фильтры."
                }
              />
            )}
          </FullscreenPanel>
        </Card>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {data?.labels.period_table_title ?? "Таблица БДДС по месяцам"}
            </Title>
          </div>
          <FullscreenPanel disabled={!periodRows.length}>
            <div className="overflow-x-auto p-1 pt-10">
              {!periodRows.length ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "Загрузка…" : "Нет строк для сводной таблицы по выбранным фильтрам."}
                </div>
              ) : (
                <table className={TABLE}>
                  <thead>
                    <tr>
                      <SortableHeader
                        label="Проект"
                        sortKey="project"
                        sort={periodSort}
                        onSort={togglePeriodSort}
                      />
                      <SortableHeader
                        label={periodLabel}
                        sortKey="period"
                        sort={periodSort}
                        onSort={togglePeriodSort}
                      />
                      <SortableHeader
                        label="План, млн. руб."
                        sortKey="plan"
                        sort={periodSort}
                        onSort={togglePeriodSort}
                        align="right"
                      />
                      <SortableHeader
                        label="Факт, млн. руб."
                        sortKey="fact"
                        sort={periodSort}
                        onSort={togglePeriodSort}
                        align="right"
                      />
                      <SortableHeader
                        label="Отклонение, млн. руб."
                        sortKey="deviation"
                        sort={periodSort}
                        onSort={togglePeriodSort}
                        align="right"
                      />
                    </tr>
                  </thead>
                  <tbody>
                    {periodVisible.map((row, index) =>
                      row.kind === "project" ? (
                        <tr key={`banner-${row.project}-${index}`}>
                          <td colSpan={5} className={`${CELL} ${BANNER}`}>
                            {row.project}
                          </td>
                        </tr>
                      ) : (
                        <tr key={`${row.project}-${row.period}-${index}`}>
                          <td className={`${CELL} ${BODY_CELL}`}>{row.project}</td>
                          <td className={`${CELL} ${BODY_CELL}`}>{row.period}</td>
                          <td className={`${CELL} ${BODY_CELL} text-right tabular-nums`}>
                            {mlnCell(row.plan)}
                          </td>
                          <td className={`${CELL} ${BODY_CELL} text-right tabular-nums`}>
                            {mlnCell(row.fact)}
                          </td>
                          <td
                            className={`${CELL} px-3 py-2 text-right tabular-nums ${deviationClass(
                              row.deviation,
                            )}`}
                          >
                            {mlnCell(row.deviation)}
                          </td>
                        </tr>
                      ),
                    )}
                    <tr className={TOTAL_ROW}>
                      <td className={`${CELL} px-3 py-2`}>ИТОГО</td>
                      <td className={`${CELL} px-3 py-2`}>{data?.labels.total_period}</td>
                      <td className={`${CELL} px-3 py-2 text-right tabular-nums`}>
                        {mlnCell(totals.plan)}
                      </td>
                      <td className={`${CELL} px-3 py-2 text-right tabular-nums`}>
                        {mlnCell(totals.fact)}
                      </td>
                      <td
                        className={`${CELL} px-3 py-2 text-right tabular-nums ${deviationClass(
                          totals.deviation,
                        )}`}
                      >
                        {mlnCell(totals.deviation)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
          </FullscreenPanel>
        </Card>

        <div>
          <DownloadTableButton
            getTable={periodExport}
            fileStem="bdds_po_mesyacam"
            disabled={!periodRows.length}
          />
        </div>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {data?.labels.project_table_title ?? "Таблица БДДС по проектам"}
            </Title>
          </div>
          <FullscreenPanel disabled={!projectRows.length}>
            <div className="overflow-x-auto p-1 pt-10">
              {!projectRows.length ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "Загрузка…" : "Нет строк по выбранным фильтрам."}
                </div>
              ) : (
                <table className={TABLE}>
                  <thead>
                    <tr>
                      <SortableHeader
                        label="Проект"
                        sortKey="project"
                        sort={projectSort}
                        onSort={toggleProjectSort}
                      />
                      <SortableHeader
                        label="План, млн. руб."
                        sortKey="plan"
                        sort={projectSort}
                        onSort={toggleProjectSort}
                        align="right"
                      />
                      <SortableHeader
                        label="Факт, млн. руб."
                        sortKey="fact"
                        sort={projectSort}
                        onSort={toggleProjectSort}
                        align="right"
                      />
                      <SortableHeader
                        label="Отклонение, млн. руб."
                        sortKey="deviation"
                        sort={projectSort}
                        onSort={toggleProjectSort}
                        align="right"
                      />
                    </tr>
                  </thead>
                  <tbody>
                    {projectVisible.map((row) => (
                      <tr key={row.project}>
                        <td className={`${CELL} ${BODY_CELL}`}>{row.project}</td>
                        <td className={`${CELL} ${BODY_CELL} text-right tabular-nums`}>
                          {mlnCell(row.plan)}
                        </td>
                        <td className={`${CELL} ${BODY_CELL} text-right tabular-nums`}>
                          {mlnCell(row.fact)}
                        </td>
                        <td
                          className={`${CELL} px-3 py-2 text-right tabular-nums ${deviationClass(
                            row.deviation,
                          )}`}
                        >
                          {mlnCell(row.deviation)}
                        </td>
                      </tr>
                    ))}
                    <tr className={TOTAL_ROW}>
                      <td className={`${CELL} px-3 py-2`}>ИТОГО</td>
                      <td className={`${CELL} px-3 py-2 text-right tabular-nums`}>
                        {mlnCell(totals.plan)}
                      </td>
                      <td className={`${CELL} px-3 py-2 text-right tabular-nums`}>
                        {mlnCell(totals.fact)}
                      </td>
                      <td
                        className={`${CELL} px-3 py-2 text-right tabular-nums ${deviationClass(
                          totals.deviation,
                        )}`}
                      >
                        {mlnCell(totals.deviation)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
          </FullscreenPanel>
        </Card>

        <div>
          <DownloadTableButton
            getTable={projectExport}
            fileStem="bdds_po_proektam"
            disabled={!projectRows.length}
          />
        </div>

        {hints.length ? (
          <Card className="rounded-xl border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30">
            <Text className="font-medium text-amber-900 dark:text-amber-200">
              О данных для план-факта месяцами — возможны пропуски/приближения:
            </Text>
            <ul className="mt-2 list-disc pl-5 text-sm text-amber-900 dark:text-amber-200">
              {hints.map((hint) => (
                <li key={hint}>{hint}</li>
              ))}
            </ul>
          </Card>
        ) : null}
      </div>
    </AppShell>
  );
}
