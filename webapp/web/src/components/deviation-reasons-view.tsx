"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Metric, Text, Title } from "@tremor/react";
import {
  fetchDeviationReasons,
  type DeviationReasonsPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  MobileCardStack,
  MobileEntityCard,
  MobileMetricGrid,
} from "@/components/mobile-entity-card";
import {
  DeviationFacetChart,
  DeviationStackChart,
} from "@/components/deviation-reasons-dynamics-charts";
import {
  DeviationReasonsBarChart,
  DeviationReasonsPieChart,
} from "@/components/deviation-reasons-share-charts";
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
import {
  filterChip,
  formatDateChip,
  type ActiveFilter,
} from "@/lib/filters-summary";
import { useUrlFilterState } from "@/lib/use-url-filter-state";
import type { ExportCell, ExportTable } from "@/lib/table-export";

const INITIAL = {
  project: "Все",
  block: "Все",
  building: "Все",
  reason: "Все",
  dateFrom: "",
  dateTo: "",
  top5: false,
};

type SortKey =
  | "task_id"
  | "project"
  | "block"
  | "task"
  | "building"
  | "plan_end"
  | "base_end"
  | "end_diff_days"
  | "reason"
  | "notes";

type DynPmSortKey = "project" | "period" | "count";
type DynSumSortKey = "project" | "reason" | "count" | "days";
type SortState = { key: SortKey; asc: boolean } | null;
type DynSortState<K extends string> = { key: K; asc: boolean } | null;
type DetailRow = DeviationReasonsPayload["rows"][number] & { _index: number };
type DynPmRow = DeviationReasonsPayload["tremor"]["dynamics"]["project_month_rows"][number] & {
  _index: number;
};
type DynSumRow = DeviationReasonsPayload["tremor"]["dynamics"]["summary_rows"][number] & {
  _index: number;
};

const COL_SORT: Record<string, SortKey> = {
  "ID задачи": "task_id",
  Проект: "project",
  "Функциональный блок": "block",
  Название: "task",
  Строение: "building",
  Окончание: "plan_end",
  "Базовое окончание": "base_end",
  Отклонение: "end_diff_days",
  "Причина отклонения": "reason",
  Заметки: "notes",
};

const DATE_COLS = new Set(["Окончание", "Базовое окончание", "Отклонение"]);
const DATE_BG = "bg-[rgba(156,194,229,0.28)] dark:bg-[rgba(214,234,248,0.14)]";

const TH =
  "whitespace-nowrap border border-[#cbd5e1] bg-[#f3f4f6] px-2.5 py-2 text-center font-bold text-[#111827] dark:border-[#334155] dark:bg-[hsl(209,72%,6%)] dark:text-[#fafafa]";
const TD =
  "border border-[#cbd5e1] px-2.5 py-1.5 text-center align-middle dark:border-[#334155]";

function deviationClass(days: number | null | undefined): string {
  if (days == null) return "";
  if (days < 0) {
    return "font-bold text-[hsl(348,100%,45%)] dark:text-[#ff5454]";
  }
  if (days === 0) {
    return "font-bold text-[#6b7280] dark:text-[#8899aa]";
  }
  return "font-bold text-[#15803d] dark:text-[#46d68a]";
}

function compareRows(a: DetailRow, b: DetailRow, key: SortKey): number {
  const av = a[key];
  const bv = b[key];
  if (av == null && bv == null) return a._index - b._index;
  if (av == null) return 1;
  if (bv == null) return -1;
  if (typeof av === "number" && typeof bv === "number") return av - bv;
  const as = String(av);
  const bs = String(bv);
  if (key === "plan_end" || key === "base_end") {
    const am = Date.parse(as.split(".").reverse().join("-"));
    const bm = Date.parse(bs.split(".").reverse().join("-"));
    if (Number.isFinite(am) && Number.isFinite(bm)) return am - bm;
  }
  return as.localeCompare(bs, "ru", { numeric: true, sensitivity: "base" });
}

function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
  tint = false,
}: {
  label: string;
  sortKey: string;
  sort: { key: string; asc: boolean } | null;
  onSort: (key: string) => void;
  tint?: boolean;
}) {
  const active = sort?.key === sortKey;
  return (
    <th className={`${TH} ${tint ? DATE_BG : ""}`}>
      <button
        type="button"
        title="Сортировать по колонке"
        onClick={() => onSort(sortKey)}
        className="inline-flex w-full items-center justify-center gap-1"
      >
        <span>{label}</span>
        <span className={active ? "text-emerald-700 dark:text-emerald-300" : "opacity-60"}>
          {active ? (sort?.asc ? "↑" : "↓") : "⇅"}
        </span>
      </button>
    </th>
  );
}

function buildExport(rows: DeviationReasonsPayload["rows"]): ExportTable {
  const header = [
    "ID задачи",
    "Проект",
    "Функциональный блок",
    "Название",
    "Строение",
    "Окончание",
    "Базовое окончание",
    "Отклонение",
    "Причина отклонения",
    "Заметки",
  ];
  const body: ExportCell[][] = rows.map((row) => [
    row.task_id ?? "",
    row.project,
    row.block ?? "",
    row.task ?? "",
    row.building ?? "",
    row.plan_end ?? "",
    row.base_end ?? "",
    row.end_diff_days ?? "",
    row.reason,
    row.notes ?? "",
  ]);
  return { header: [header], rows: body, sheetName: "Детальные данные" };
}

function buildPmExport(
  rows: DeviationReasonsPayload["tremor"]["dynamics"]["project_month_rows"],
  total: number,
): ExportTable {
  return {
    header: [["Проект", "Период (месяц)", "Количество отклонений"]],
    rows: [
      ...rows.map((row) => [row.project, row.period, row.count] as ExportCell[]),
      ["Итого", "", total],
    ],
    sheetName: "По проекту и месяцу",
  };
}

function buildSummaryExport(
  rows: DeviationReasonsPayload["tremor"]["dynamics"]["summary_rows"],
  totals: { count: number; days: number },
): ExportTable {
  return {
    header: [
      ["Проект", "Причина отклонений", "Количество отклонений", "Всего дней отклонений"],
    ],
    rows: [
      ...rows.map(
        (row) => [row.project, row.reason, row.count, row.days] as ExportCell[],
      ),
      ["Итого", "Итого", totals.count, totals.days],
    ],
    sheetName: "Сводная",
  };
}

function emptyDynamics(): DeviationReasonsPayload["tremor"]["dynamics"] {
  return {
    by_project_charts: [],
    project_month_rows: [],
    project_month_total: 0,
    by_project_stack: [],
    stack_projects: [],
    stack_colors: {},
    summary_rows: [],
    summary_totals: { count: 0, days: 0 },
    period_label: "Период (месяц)",
  };
}

export function DeviationReasonsView() {
  const [filters, setFilters] = useState(INITIAL);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [periodReady, setPeriodReady] = useState(false);
  const [tab, setTab] = useState<"share" | "dynamics">("share");
  const [data, setData] = useState<DeviationReasonsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tableSort, setTableSort] = useState<SortState>(null);
  const [pmSort, setPmSort] = useState<DynSortState<DynPmSortKey>>(null);
  const [sumSort, setSumSort] = useState<DynSortState<DynSumSortKey>>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchDeviationReasons({
        project: filters.project,
        block: filters.block,
        building: filters.building,
        reason: filters.reason,
        date_from: filters.dateFrom || undefined,
        date_to: filters.dateTo || undefined,
        top5: filters.top5,
      });
      setData(payload);
      if (!periodReady) {
        setFilters((prev) => ({
          ...prev,
          dateFrom: payload.filters.applied.date_from ?? "",
          dateTo: payload.filters.applied.date_to ?? "",
        }));
        setPeriodReady(true);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [filters, periodReady]);

  useEffect(() => {
    void load();
  }, [load]);

  // Даты из адреса важнее автоподстановки периода из ответа API
  useUrlFilterState(
    filters,
    INITIAL,
    (patch) => setFilters((prev) => ({ ...prev, ...patch })),
    {
      onRestore: (restored) => {
        if (restored.dateFrom || restored.dateTo) setPeriodReady(true);
      },
    },
  );

  const dirty =
    filters.project !== INITIAL.project ||
    filters.block !== INITIAL.block ||
    filters.building !== INITIAL.building ||
    filters.reason !== INITIAL.reason ||
    filters.top5 !== INITIAL.top5 ||
    (periodReady &&
      (filters.dateFrom !== (data?.filters.period.min ?? "") ||
        filters.dateTo !== (data?.filters.period.max ?? "")));

  const selectClass = FILTER_SELECT_CLASS;

  const kpis = data?.kpis;
  const rows = useMemo(() => data?.rows ?? [], [data?.rows]);
  const columns = data?.columns ?? Object.keys(COL_SORT);
  const byReason = data?.tremor.by_reason ?? [];
  const reasonMix = data?.tremor.reason_mix ?? [];
  const dynamics = data?.tremor.dynamics ?? emptyDynamics();
  const facetCharts = dynamics.by_project_charts ?? [];
  const stackRows = dynamics.by_project_stack ?? [];
  const stackProjects = dynamics.stack_projects ?? [];
  const stackColors = dynamics.stack_colors ?? {};

  const sortedRows = useMemo(() => {
    const indexed = rows.map((row, index) => ({ ...row, _index: index }));
    if (!tableSort) return indexed;
    return [...indexed].sort((a, b) => {
      const diff = compareRows(a, b, tableSort.key);
      return tableSort.asc ? diff : -diff;
    });
  }, [rows, tableSort]);

  const sortedPmRows = useMemo(() => {
    const indexed: DynPmRow[] = (dynamics.project_month_rows ?? []).map((row, index) => ({
      ...row,
      _index: index,
    }));
    if (!pmSort) return indexed;
    return [...indexed].sort((a, b) => {
      const av = a[pmSort.key];
      const bv = b[pmSort.key];
      let diff = 0;
      if (typeof av === "number" && typeof bv === "number") diff = av - bv;
      else diff = String(av).localeCompare(String(bv), "ru", { numeric: true });
      return pmSort.asc ? diff : -diff;
    });
  }, [dynamics.project_month_rows, pmSort]);

  const sortedSumRows = useMemo(() => {
    const indexed: DynSumRow[] = (dynamics.summary_rows ?? []).map((row, index) => ({
      ...row,
      _index: index,
    }));
    if (!sumSort) return indexed;
    return [...indexed].sort((a, b) => {
      const av = a[sumSort.key];
      const bv = b[sumSort.key];
      let diff = 0;
      if (typeof av === "number" && typeof bv === "number") diff = av - bv;
      else diff = String(av).localeCompare(String(bv), "ru", { numeric: true });
      return sumSort.asc ? diff : -diff;
    });
  }, [dynamics.summary_rows, sumSort]);

  const toggleSort = useCallback((key: string) => {
    const k = key as SortKey;
    setTableSort((prev) => {
      if (!prev || prev.key !== k) return { key: k, asc: true };
      if (prev.asc) return { key: k, asc: false };
      return null;
    });
  }, []);

  const togglePmSort = useCallback((key: string) => {
    const k = key as DynPmSortKey;
    setPmSort((prev) => {
      if (!prev || prev.key !== k) return { key: k, asc: true };
      if (prev.asc) return { key: k, asc: false };
      return null;
    });
  }, []);

  const toggleSumSort = useCallback((key: string) => {
    const k = key as DynSumSortKey;
    setSumSort((prev) => {
      if (!prev || prev.key !== k) return { key: k, asc: true };
      if (prev.asc) return { key: k, asc: false };
      return null;
    });
  }, []);

  const exportTable = useMemo(() => buildExport(rows), [rows]);
  const pmExport = useMemo(
    () => buildPmExport(dynamics.project_month_rows ?? [], dynamics.project_month_total ?? 0),
    [dynamics.project_month_rows, dynamics.project_month_total],
  );
  const sumExport = useMemo(
    () =>
      buildSummaryExport(
        dynamics.summary_rows ?? [],
        dynamics.summary_totals ?? { count: 0, days: 0 },
      ),
    [dynamics.summary_rows, dynamics.summary_totals],
  );
  const metaError = data?.meta?.error as string | undefined;
  const hasDynamics =
    facetCharts.length > 0 ||
    (dynamics.project_month_rows?.length ?? 0) > 0 ||
    stackRows.length > 0 ||
    (dynamics.summary_rows?.length ?? 0) > 0;

  const resetFilters = () => {
    setPeriodReady(false);
    setFilters(INITIAL);
  };

  const periodMin = data?.filters.period.min ?? "";
  const periodMax = data?.filters.period.max ?? "";
  const activeFilters: ActiveFilter[] = [
    ...(filters.project !== "Все"
      ? [
          filterChip("project", "Проект", filters.project, () =>
            setFilters((prev) => ({
              ...prev,
              project: "Все",
              block: "Все",
              building: "Все",
            })),
          ),
        ]
      : []),
    ...(filters.block !== "Все"
      ? [
          filterChip("block", "Блок", filters.block, () =>
            setFilters((prev) => ({ ...prev, block: "Все", building: "Все" })),
          ),
        ]
      : []),
    ...(filters.building !== "Все"
      ? [
          filterChip("building", "Строение", filters.building, () =>
            setFilters((prev) => ({ ...prev, building: "Все" })),
          ),
        ]
      : []),
    ...(filters.reason !== "Все"
      ? [
          filterChip("reason", "Причина", filters.reason, () =>
            setFilters((prev) => ({ ...prev, reason: "Все" })),
          ),
        ]
      : []),
    ...(periodReady && filters.dateFrom && filters.dateFrom !== periodMin
      ? [
          filterChip("from", "С", formatDateChip(filters.dateFrom), () =>
            setFilters((prev) => ({ ...prev, dateFrom: periodMin })),
          ),
        ]
      : []),
    ...(periodReady && filters.dateTo && filters.dateTo !== periodMax
      ? [
          filterChip("to", "По", formatDateChip(filters.dateTo), () =>
            setFilters((prev) => ({ ...prev, dateTo: periodMax })),
          ),
        ]
      : []),
    ...(filters.top5
      ? [
          filterChip("top5", "ТОП 5 причин", "вкл", () =>
            setFilters((prev) => ({ ...prev, top5: false })),
          ),
        ]
      : []),
  ];

  return (
    <AppShell title="Причины отклонений" loading={loading}>
      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((value) => !value)}
        activeFilters={activeFilters}
        onReset={dirty ? resetFilters : undefined}
      >
        <FiltersReset disabled={!dirty} onClick={resetFilters} />
        <FilterFieldsRow cols={5}>
          <FilterChipSelect label="Проект" value={filters.project} options={data?.filters.projects ?? ["Все"]} onChange={(project) => setFilters((prev) => ({ ...prev, project, block: "Все", building: "Все" }))} />
          <FilterChipSelect label="Функциональный блок" value={filters.block} options={data?.filters.blocks ?? ["Все"]} onChange={(block) => setFilters((prev) => ({ ...prev, block, building: "Все" }))} />
          <FilterChipSelect label="Строение" value={filters.building} options={data?.filters.buildings ?? ["Все"]} onChange={(building) => setFilters((prev) => ({ ...prev, building }))} />
          <FilterField label="Период">
            <div className="flex flex-col gap-1 sm:flex-row sm:items-center">
              <input
                type="date"
                className={selectClass + " !mt-0"}
                value={filters.dateFrom}
                min={data?.filters.period.min ?? undefined}
                max={data?.filters.period.max ?? undefined}
                onChange={(event) =>
                  setFilters((prev) => ({ ...prev, dateFrom: event.target.value }))
                }
              />
              <span className="hidden text-tremor-content sm:inline dark:text-dark-tremor-content">
                —
              </span>
              <input
                type="date"
                className={selectClass + " !mt-0"}
                value={filters.dateTo}
                min={data?.filters.period.min ?? undefined}
                max={data?.filters.period.max ?? undefined}
                onChange={(event) =>
                  setFilters((prev) => ({ ...prev, dateTo: event.target.value }))
                }
              />
            </div>
          </FilterField>
          <FilterChipSelect label="Причина" value={filters.reason} options={data?.filters.reasons ?? ["Все"]} onChange={(reason) => setFilters((prev) => ({ ...prev, reason }))} />
        </FilterFieldsRow>
        <FilterChecksRow cols={5}>
          <FilterCheck
            label="ТОП 5 причин отклонений"
            checked={filters.top5}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, top5: event.target.checked }))
            }
          />
          <div />
          <div />
          <div />
          <div />
        </FilterChecksRow>
      </FiltersCard>

      {error || metaError ? (
        <Card className="mb-6 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            {error ? `API недоступен. ${error}` : metaError}
          </Text>
        </Card>
      ) : null}

      <div className="mb-4 flex flex-wrap gap-2 border-b border-tremor-border dark:border-dark-tremor-border">
        {(
          [
            ["share", "Доли причин отклонений по проекту"],
            ["dynamics", "Динамика причин отклонений по месяцам"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`border-b-2 px-3 py-2 text-sm font-medium ${
              tab === id
                ? "border-emerald-500 text-tremor-content-strong dark:text-dark-tremor-content-strong"
                : "border-transparent text-tremor-content dark:text-dark-tremor-content"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      {tab === "share" ? (
        <div className="space-y-6">
          <Text className="text-sm text-tremor-content dark:text-dark-tremor-content">
            Диаграммы и детальная таблица: {rows.length} задач (ур. 5, причина,
            отклонение окончания &lt; 0).
          </Text>

          <div className="grid gap-6 sm:grid-cols-2">
            <div>
              <Text>Основная причина отклонения</Text>
              <Metric className="mt-1 text-base text-tremor-content-strong dark:text-dark-tremor-content-strong sm:text-xl">
                {kpis?.main_reason
                  ? kpis.main_reason.length > 50
                    ? `${kpis.main_reason.slice(0, 50)}…`
                    : kpis.main_reason
                  : "—"}
              </Metric>
            </div>
            <div>
              <Text>Доля основной причины</Text>
              <Metric className="mt-1 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {kpis && kpis.main_reason_count > 0
                  ? `${Number(kpis.main_reason_share_pct).toFixed(1)}% (${kpis.main_reason_count})`
                  : "—"}
              </Metric>
            </div>
          </div>

          {filters.project !== "Все" ? (
            <p className="text-right text-lg font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong">
              {filters.project}
            </p>
          ) : null}

          <Card className="rounded-xl">
            <FullscreenPanel disabled={!byReason.length} fill>
              {(zoomed) => (
                <DeviationReasonsBarChart rows={byReason} fullscreen={zoomed} />
              )}
            </FullscreenPanel>
          </Card>

          <Card className="rounded-xl">
            <FullscreenPanel disabled={!reasonMix.length} fill>
              {(zoomed) => (
                <DeviationReasonsPieChart rows={reasonMix} fullscreen={zoomed} />
              )}
            </FullscreenPanel>
          </Card>
        </div>
      ) : (
        <div className="space-y-6">
          {!hasDynamics ? (
            <Card className="rounded-xl">
              <Text>
                {loading
                  ? "Загрузка…"
                  : "По макету нет строк: уровень 5, непустая причина, отклонение окончания < 0."}
              </Text>
            </Card>
          ) : null}

          {facetCharts.map((facet) => (
            <Card key={facet.project} className="rounded-xl">
              <FullscreenPanel disabled={!facet.rows.length} fill>
                {(zoomed) => (
                  <DeviationFacetChart
                    facet={facet}
                    periodLabel={dynamics.period_label || "Период (месяц)"}
                    fullscreen={zoomed}
                  />
                )}
              </FullscreenPanel>
            </Card>
          ))}

          <Card className="overflow-hidden rounded-xl p-0">
            <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Число отклонений по проекту и месяцу
              </Title>
            </div>
            <FullscreenPanel
              disabled={!sortedPmRows.length}
              className="!overflow-x-hidden"
            >
              {sortedPmRows.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  Нет данных по периодам.
                </div>
              ) : (
                <>
                  <MobileCardStack>
                    {sortedPmRows.map((row) => (
                      <MobileEntityCard
                        key={`${row.project}-${row.period_key}-${row._index}`}
                        title={row.project}
                        badge={row.count}
                        badgeTone="neutral"
                      >
                        <MobileMetricGrid
                          columns={2}
                          items={[
                            { label: "Период", value: row.period },
                            { label: "Отклонений", value: row.count },
                          ]}
                        />
                      </MobileEntityCard>
                    ))}
                    <MobileEntityCard
                      title="Итого"
                      badge={dynamics.project_month_total}
                      badgeTone="neutral"
                    >
                      <MobileMetricGrid
                        columns={2}
                        items={[
                          { label: "Период", value: "—" },
                          {
                            label: "Отклонений",
                            value: dynamics.project_month_total,
                          },
                        ]}
                      />
                    </MobileEntityCard>
                  </MobileCardStack>
                  <div className="hidden overflow-x-auto p-1 pt-10 lg:block">
                    <table className="min-w-full border-collapse text-xs">
                      <thead>
                        <tr>
                          <SortHeader
                            label="Проект"
                            sortKey="project"
                            sort={pmSort}
                            onSort={togglePmSort}
                          />
                          <SortHeader
                            label="Период (месяц)"
                            sortKey="period"
                            sort={pmSort}
                            onSort={togglePmSort}
                          />
                          <SortHeader
                            label="Количество отклонений"
                            sortKey="count"
                            sort={pmSort}
                            onSort={togglePmSort}
                          />
                        </tr>
                      </thead>
                      <tbody>
                        {sortedPmRows.map((row) => (
                          <tr
                            key={`${row.project}-${row.period_key}-${row._index}`}
                            className="odd:bg-slate-50/60 dark:odd:bg-slate-900/20"
                          >
                            <td className={`${TD} font-medium`}>{row.project}</td>
                            <td className={TD}>{row.period}</td>
                            <td className={`${TD} tabular-nums`}>{row.count}</td>
                          </tr>
                        ))}
                        <tr className="bg-slate-100 font-semibold dark:bg-slate-800/60">
                          <td className={TD}>Итого</td>
                          <td className={TD} />
                          <td className={`${TD} tabular-nums`}>
                            {dynamics.project_month_total}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </FullscreenPanel>
            <div className="border-t border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
              <DownloadTableButton
                getTable={() => pmExport}
                fileStem="deviation_reasons_project_month"
                disabled={!dynamics.project_month_rows?.length}
              />
            </div>
          </Card>

          <Card className="rounded-xl">
            <FullscreenPanel disabled={!stackRows.length} fill>
              {(zoomed) => (
                <DeviationStackChart
                  rows={stackRows}
                  projects={stackProjects}
                  colors={stackColors}
                  fullscreen={zoomed}
                />
              )}
            </FullscreenPanel>
          </Card>

          <Card className="overflow-hidden rounded-xl p-0">
            <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Сводная таблица (проект / причина)
              </Title>
            </div>
            <FullscreenPanel
              disabled={!sortedSumRows.length}
              className="!overflow-x-hidden"
            >
              {sortedSumRows.length === 0 ? (
                <div className="px-4 py-8 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  Нет сводных данных.
                </div>
              ) : (
                <>
                  <MobileCardStack>
                    {sortedSumRows.map((row) => (
                      <MobileEntityCard
                        key={`${row.project}-${row.reason}-${row._index}`}
                        title={`${row.project}: ${row.reason}`}
                        badge={row.count}
                        badgeTone="neutral"
                      >
                        <MobileMetricGrid
                          columns={2}
                          items={[
                            { label: "Отклонений", value: row.count },
                            { label: "Дней", value: row.days },
                          ]}
                        />
                      </MobileEntityCard>
                    ))}
                    <MobileEntityCard
                      title="Итого"
                      badge={dynamics.summary_totals?.count ?? 0}
                      badgeTone="neutral"
                    >
                      <MobileMetricGrid
                        columns={2}
                        items={[
                          {
                            label: "Отклонений",
                            value: dynamics.summary_totals?.count ?? 0,
                          },
                          {
                            label: "Дней",
                            value: dynamics.summary_totals?.days ?? 0,
                          },
                        ]}
                      />
                    </MobileEntityCard>
                  </MobileCardStack>
                  <div className="hidden overflow-x-auto p-1 pt-10 lg:block">
                    <table className="min-w-full border-collapse text-xs">
                      <thead>
                        <tr>
                          <SortHeader
                            label="Проект"
                            sortKey="project"
                            sort={sumSort}
                            onSort={toggleSumSort}
                          />
                          <SortHeader
                            label="Причина отклонений"
                            sortKey="reason"
                            sort={sumSort}
                            onSort={toggleSumSort}
                          />
                          <SortHeader
                            label="Количество отклонений"
                            sortKey="count"
                            sort={sumSort}
                            onSort={toggleSumSort}
                          />
                          <SortHeader
                            label="Всего дней отклонений"
                            sortKey="days"
                            sort={sumSort}
                            onSort={toggleSumSort}
                          />
                        </tr>
                      </thead>
                      <tbody>
                        {sortedSumRows.map((row) => (
                          <tr
                            key={`${row.project}-${row.reason}-${row._index}`}
                            className="odd:bg-slate-50/60 dark:odd:bg-slate-900/20"
                          >
                            <td className={`${TD} font-medium`}>{row.project}</td>
                            <td className={`${TD} max-w-md text-left`}>{row.reason}</td>
                            <td className={`${TD} tabular-nums`}>{row.count}</td>
                            <td className={`${TD} tabular-nums`}>{row.days}</td>
                          </tr>
                        ))}
                        <tr className="bg-slate-100 font-semibold dark:bg-slate-800/60">
                          <td className={TD}>Итого</td>
                          <td className={TD}>Итого</td>
                          <td className={`${TD} tabular-nums`}>
                            {dynamics.summary_totals?.count ?? 0}
                          </td>
                          <td className={`${TD} tabular-nums`}>
                            {dynamics.summary_totals?.days ?? 0}
                          </td>
                        </tr>
                      </tbody>
                    </table>
                  </div>
                </>
              )}
            </FullscreenPanel>
            <div className="border-t border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
              <DownloadTableButton
                getTable={() => sumExport}
                fileStem="deviation_reasons_summary"
                disabled={!dynamics.summary_rows?.length}
              />
            </div>
          </Card>
        </div>
      )}

      {tab === "share" ? (
        <Card className="mt-6 overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Детальные данные
            </Title>
            <Text className="mt-1 text-sm">
              Записей (по макету): {rows.length}
            </Text>
          </div>
          <FullscreenPanel
            disabled={!sortedRows.length}
            className="!overflow-x-hidden"
          >
            {loading && !data ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                Загрузка…
              </div>
            ) : sortedRows.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                По макету нет строк: уровень 5, непустая причина, отклонение окончания &lt; 0.
              </div>
            ) : (
              <>
                <MobileCardStack>
                  {sortedRows.map((row) => (
                    <div
                      key={`${row.project}-${row.task_id ?? row.task}-${row._index}`}
                      className="overflow-hidden rounded-xl border-l-4"
                      style={{ borderLeftColor: row.bucket_color }}
                    >
                      <MobileEntityCard
                        title={
                          row.project && row.task
                            ? `${row.project}: ${row.task}`
                            : (row.task ?? row.project ?? "—")
                        }
                        badge={
                          row.end_diff_days != null ? row.end_diff_days : undefined
                        }
                        badgeTone={
                          row.end_diff_days == null
                            ? "neutral"
                            : row.end_diff_days < 0
                              ? "bad"
                              : "ok"
                        }
                      >
                        <MobileMetricGrid
                          columns={2}
                          items={[
                            { label: "ID", value: row.task_id ?? "—" },
                            { label: "Блок", value: row.block ?? "—" },
                            { label: "Строение", value: row.building ?? "—" },
                            { label: "Окончание", value: row.plan_end ?? "—" },
                            {
                              label: "Базовое",
                              value: row.base_end ?? "—",
                            },
                            {
                              label: "Откл.",
                              value: row.end_diff_days ?? "—",
                              className: deviationClass(row.end_diff_days),
                            },
                            { label: "Причина", value: row.reason || "—" },
                            { label: "Заметки", value: row.notes || "—" },
                          ]}
                        />
                      </MobileEntityCard>
                    </div>
                  ))}
                </MobileCardStack>
                <div className="hidden overflow-x-auto p-1 pt-10 lg:block">
                  <table className="min-w-full border-collapse text-xs">
                    <thead>
                      <tr>
                        {columns.map((label) => {
                          const sortKey = COL_SORT[label];
                          if (!sortKey) {
                            return (
                              <th key={label} className={TH}>
                                {label}
                              </th>
                            );
                          }
                          return (
                            <SortHeader
                              key={label}
                              label={label}
                              sortKey={sortKey}
                              sort={tableSort}
                              onSort={toggleSort}
                              tint={DATE_COLS.has(label)}
                            />
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedRows.map((row) => (
                        <tr
                          key={`${row.project}-${row.task_id ?? row.task}-${row._index}`}
                          className="odd:bg-slate-50/60 dark:odd:bg-slate-900/20"
                        >
                          <td className={`${TD} tabular-nums`}>
                            {row.task_id ?? "—"}
                          </td>
                          <td className={`${TD} font-medium`}>{row.project}</td>
                          <td className={TD}>{row.block ?? "—"}</td>
                          <td className={`${TD} max-w-xs text-left`}>
                            {row.task ?? "—"}
                          </td>
                          <td className={TD}>{row.building ?? "—"}</td>
                          <td className={`${TD} ${DATE_BG} tabular-nums`}>
                            {row.plan_end ?? "—"}
                          </td>
                          <td className={`${TD} ${DATE_BG} tabular-nums`}>
                            {row.base_end ?? "—"}
                          </td>
                          <td
                            className={`${TD} ${DATE_BG} tabular-nums ${deviationClass(row.end_diff_days)}`}
                          >
                            {row.end_diff_days ?? "—"}
                          </td>
                          <td
                            className={`${TD} max-w-xs text-left font-semibold`}
                            style={{ borderLeft: `4px solid ${row.bucket_color}` }}
                          >
                            {row.reason}
                          </td>
                          <td className={`${TD} max-w-md whitespace-normal text-left`}>
                            {row.notes ?? "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              </>
            )}
          </FullscreenPanel>
          <div className="border-t border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <DownloadTableButton
              getTable={() => exportTable}
              fileStem="deviation_reasons_detail"
              disabled={!rows.length}
            />
          </div>
        </Card>
      ) : null}
    </AppShell>
  );
}
