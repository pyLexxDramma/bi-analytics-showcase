"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FinanceBarChart } from "@/components/finance-bar-chart";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  fetchBdds,
  type BddsQuery,
  type BddsGroup,
  type BddsPayload,
  type BddsTableRow,
  type BddsView,
} from "@/lib/api";
import {
  FilterCheck,
  FilterChipMulti,
  FilterChipSelect,
  FilterChecksRow,
  FilterField,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
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

const selectClass = FILTER_SELECT_CLASS;

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

type PeriodProjectBlock = { project: string; rows: PeriodRow[] };

/** Mobile: блоки по проекту — таблица Период|План|Факт|Откл без H-scroll. */
function groupPeriodByProject(rows: PeriodRow[]): PeriodProjectBlock[] {
  const blocks: PeriodProjectBlock[] = [];
  let current: PeriodProjectBlock | null = null;
  for (const row of rows) {
    if (row.kind === "project") {
      current = { project: row.project, rows: [] };
      blocks.push(current);
      continue;
    }
    const name: string = row.project || current?.project || "—";
    if (!current || current.project !== name) {
      current = { project: name, rows: [] };
      blocks.push(current);
    }
    current.rows.push(row);
  }
  return blocks.filter((b) => b.rows.length > 0);
}

function MobilePeriodBlocks({
  blocks,
  periodLabel,
  totals,
  totalPeriodLabel,
}: {
  blocks: PeriodProjectBlock[];
  periodLabel: string;
  totals: { plan: number; fact: number; deviation: number };
  totalPeriodLabel: string;
}) {
  return (
    <div className="flex flex-col gap-4 px-2 pb-2">
      {blocks.map((block) => (
        <section
          key={block.project}
          className="overflow-hidden rounded-xl border-[3px] border-[#94a3b8] dark:border-white"
        >
          <div className={`${BANNER} border-b border-[#94a3b8] dark:border-[#7a9ec4]`}>
            {block.project}
          </div>
          <table className="w-full table-fixed border-collapse text-left text-xs">
            <colgroup>
              <col className="w-[28%]" />
              <col className="w-[24%]" />
              <col className="w-[24%]" />
              <col className="w-[24%]" />
            </colgroup>
            <thead>
              <tr>
                <th className={`${HEAD_CELL} px-1.5 py-1.5 normal-case`}>{periodLabel}</th>
                <th className={`${HEAD_CELL} px-1.5 py-1.5 text-right normal-case`}>План</th>
                <th className={`${HEAD_CELL} px-1.5 py-1.5 text-right normal-case`}>Факт</th>
                <th className={`${HEAD_CELL} px-1.5 py-1.5 text-right normal-case`}>Откл.</th>
              </tr>
            </thead>
            <tbody>
              {block.rows.map((row, index) => (
                <tr key={`${block.project}-${row.period}-${index}`}>
                  <td className={`${CELL} ${BODY_CELL} px-1.5 py-1.5 text-[11px] leading-snug`}>
                    {row.period}
                  </td>
                  <td className={`${CELL} ${BODY_CELL} px-1 py-1.5 text-right text-[11px] tabular-nums`}>
                    {mlnNumber(row.plan).toFixed(1)}
                  </td>
                  <td className={`${CELL} ${BODY_CELL} px-1 py-1.5 text-right text-[11px] tabular-nums`}>
                    {mlnNumber(row.fact).toFixed(1)}
                  </td>
                  <td
                    className={`${CELL} px-1 py-1.5 text-right text-[11px] tabular-nums ${deviationClass(
                      row.deviation,
                    )}`}
                  >
                    {mlnNumber(row.deviation).toFixed(1)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </section>
      ))}
      <section className="overflow-hidden rounded-xl border-[3px] border-[#94a3b8] dark:border-white">
        <table className="w-full table-fixed border-collapse text-xs">
          <colgroup>
            <col className="w-[28%]" />
            <col className="w-[24%]" />
            <col className="w-[24%]" />
            <col className="w-[24%]" />
          </colgroup>
          <tbody>
            <tr className={TOTAL_ROW}>
              <td className={`${CELL} px-2 py-2`}>
                ИТОГО
                <div className="text-[10px] font-normal opacity-80">{totalPeriodLabel}</div>
              </td>
              <td className={`${CELL} px-1 py-2 text-right tabular-nums`}>
                {mlnNumber(totals.plan).toFixed(1)}
              </td>
              <td className={`${CELL} px-1 py-2 text-right tabular-nums`}>
                {mlnNumber(totals.fact).toFixed(1)}
              </td>
              <td
                className={`${CELL} px-1 py-2 text-right tabular-nums ${deviationClass(
                  totals.deviation,
                )}`}
              >
                {mlnNumber(totals.deviation).toFixed(1)}
              </td>
            </tr>
          </tbody>
        </table>
        <p className="px-2 py-1 text-[10px] text-tremor-content dark:text-dark-tremor-content">
          Значения — млн ₽
        </p>
      </section>
    </div>
  );
}

function MobileProjectBlocks({
  rows,
  totals,
}: {
  rows: ProjectRow[];
  totals: { plan: number; fact: number; deviation: number };
}) {
  return (
    <div className="flex flex-col gap-3 px-2 pb-2">
      {rows.map((row) => (
        <section
          key={row.project}
          className="overflow-hidden rounded-xl border-[3px] border-[#94a3b8] dark:border-white"
        >
          <div className={`${BANNER} border-b border-[#94a3b8] dark:border-[#7a9ec4]`}>
            {row.project}
          </div>
          <dl className="grid grid-cols-3 gap-0 text-center text-xs">
            <div className={`${CELL} px-1 py-2`}>
              <dt className="text-[10px] font-semibold uppercase text-[#64748b]">План</dt>
              <dd className="mt-0.5 tabular-nums font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {mlnNumber(row.plan).toFixed(1)}
              </dd>
            </div>
            <div className={`${CELL} px-1 py-2`}>
              <dt className="text-[10px] font-semibold uppercase text-[#64748b]">Факт</dt>
              <dd className="mt-0.5 tabular-nums font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {mlnNumber(row.fact).toFixed(1)}
              </dd>
            </div>
            <div className={`${CELL} px-1 py-2`}>
              <dt className="text-[10px] font-semibold uppercase text-[#64748b]">Откл.</dt>
              <dd className={`mt-0.5 tabular-nums ${deviationClass(row.deviation)}`}>
                {mlnNumber(row.deviation).toFixed(1)}
              </dd>
            </div>
          </dl>
        </section>
      ))}
      <section className="overflow-hidden rounded-xl border-[3px] border-[#94a3b8] dark:border-white">
        <div className={`${TOTAL_ROW} px-3 py-2`}>ИТОГО · млн ₽</div>
        <dl className="grid grid-cols-3 gap-0 text-center text-xs">
          <div className={`${CELL} px-1 py-2`}>
            <dt className="text-[10px] font-semibold uppercase">План</dt>
            <dd className="mt-0.5 font-bold tabular-nums">{mlnNumber(totals.plan).toFixed(1)}</dd>
          </div>
          <div className={`${CELL} px-1 py-2`}>
            <dt className="text-[10px] font-semibold uppercase">Факт</dt>
            <dd className="mt-0.5 font-bold tabular-nums">{mlnNumber(totals.fact).toFixed(1)}</dd>
          </div>
          <div className={`${CELL} px-1 py-2`}>
            <dt className="text-[10px] font-semibold uppercase">Откл.</dt>
            <dd className={`mt-0.5 font-bold tabular-nums ${deviationClass(totals.deviation)}`}>
              {mlnNumber(totals.deviation).toFixed(1)}
            </dd>
          </div>
        </dl>
      </section>
    </div>
  );
}

type FinanceViewConfig = {
  title: string;
  planSeries: string;
  factSeries: string;
  sheetName: string;
  fetchPayload: (query: BddsQuery) => Promise<BddsPayload>;
};

const BDDS_CONFIG: FinanceViewConfig = {
  title: "БДДС (расходы)",
  planSeries: "БДДС план",
  factSeries: "БДДС факт",
  sheetName: "БДДС",
  fetchPayload: fetchBdds,
};

export function BddsView({ config = BDDS_CONFIG }: { config?: FinanceViewConfig }) {
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
        await config.fetchPayload({
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
  }, [config]);

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

  const periodBlocks = useMemo(
    () => groupPeriodByProject(periodVisible),
    [periodVisible],
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
      sheetName: config.sheetName,
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
      sheetName: `${config.sheetName} по проектам`,
    };
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
    <AppShell title={config.title} loading={loading}>
      <FiltersCard open={filtersOpen} onToggle={() => setFiltersOpen((state) => !state)}>
        <FiltersReset disabled={!dirty} onClick={() => setFilters(INITIAL)} />
        <FilterChipMulti
          label="Проект"
          values={filters.projects}
          options={data?.filters.projects ?? []}
          onChange={(projects) => setFilters((state) => ({ ...state, projects }))}
        />
        <FilterFieldsRow cols={4}>
          <FilterField label="Период с">
            <input
              className={selectClass}
              type="date"
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_from || appliedFrom}
              onChange={(event) =>
                setFilters((state) => ({ ...state, date_from: event.target.value }))
              }
            />
          </FilterField>
          <FilterField label="Период по">
            <input
              className={selectClass}
              type="date"
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_to || appliedTo}
              onChange={(event) =>
                setFilters((state) => ({ ...state, date_to: event.target.value }))
              }
            />
          </FilterField>
          <FilterChipSelect
            label="Группировать по"
            value={filters.group}
            options={(data?.filters.groups ?? [{ id: "month", label: "Месяц" }]).map((item) => ({ value: item.id, label: item.label }))}
            onChange={(group) => setFilters((state) => ({ ...state, group: group as BddsGroup }))}
          />
          <FilterChipSelect
            label="Представление"
            value={filters.view}
            options={(data?.filters.views ?? [{ id: "monthly", label: "По месяцам" }]).map((item) => ({ value: item.id, label: item.label }))}
            onChange={(view) => setFilters((state) => ({ ...state, view: view as BddsView }))}
          />
        </FilterFieldsRow>
        <FilterChecksRow cols={4}>
          <FilterCheck
            label="Показать отклонение"
            checked={filters.show_deviation}
            onChange={(event) =>
              setFilters((state) => ({ ...state, show_deviation: event.target.checked }))
            }
          />
          <FilterCheck
            label="Скрывать месяцы, где план и факт равны 0"
            checked={zeroToggleEnabled ? hideZero : false}
            disabled={!zeroToggleEnabled}
            onChange={(event) =>
              setFilters((state) => ({ ...state, hide_zero: event.target.checked }))
            }
          />
          <div />
          <div />
        </FilterChecksRow>
      </FiltersCard>

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
                planName={config.planSeries}
                factName={config.factSeries}
                showDeviation={filters.show_deviation}
                xAxisTitle={data?.labels.chart_caption ?? `${config.sheetName} по месяцам`}
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
              {data?.labels.period_table_title ?? `Таблица ${config.sheetName} по месяцам`}
            </Title>
          </div>
          <FullscreenPanel disabled={!periodRows.length}>
            <div className="p-1 pt-10">
              {!periodRows.length ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "Загрузка…" : "Нет строк для сводной таблицы по выбранным фильтрам."}
                </div>
              ) : (
                <>
                  <div className="lg:hidden">
                    <MobilePeriodBlocks
                      blocks={periodBlocks}
                      periodLabel={periodLabel}
                      totals={totals}
                      totalPeriodLabel={data?.labels.total_period ?? ""}
                    />
                  </div>
                  <div className="hidden overflow-x-auto lg:block">
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
                  </div>
                </>
              )}
            </div>
          </FullscreenPanel>
        </Card>

        <div>
          <DownloadTableButton
            getTable={periodExport}
            fileStem={`${config.sheetName.toLowerCase()}_po_mesyacam`}
            disabled={!periodRows.length}
          />
        </div>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {data?.labels.project_table_title ?? `Таблица ${config.sheetName} по проектам`}
            </Title>
          </div>
          <FullscreenPanel disabled={!projectRows.length}>
            <div className="p-1 pt-10">
              {!projectRows.length ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "Загрузка…" : "Нет строк по выбранным фильтрам."}
                </div>
              ) : (
                <>
                  <div className="lg:hidden">
                    <MobileProjectBlocks rows={projectVisible} totals={totals} />
                  </div>
                  <div className="hidden overflow-x-auto lg:block">
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
                  </div>
                </>
              )}
            </div>
          </FullscreenPanel>
        </Card>

        <div>
          <DownloadTableButton
            getTable={projectExport}
            fileStem={`${config.sheetName.toLowerCase()}_po_proektam`}
            disabled={!projectRows.length}
          />
        </div>

        {hints.length ? (
          <Card className="hidden rounded-xl border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 lg:block">
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
