"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  Card,
  Grid,
  Metric,
  Text,
  Title,
} from "@tremor/react";
import {
  fetchProjectDocumentation,
  type ProjectDocumentationPayload,
  type ProjectDocumentationQuery,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import {
  FilterChipSelect,
  FilterField,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import { buildFilterChips } from "@/lib/filters-summary";
import { useUrlFilterState } from "@/lib/use-url-filter-state";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  MobileCardStack,
  MobileEntityCard,
  MobileMetricGrid,
} from "@/components/mobile-entity-card";
import {
  PdDelayGanttChart,
  PdDynamicsLineChart,
  PdExecutionPieChart,
  PdMonthlyCumulativeChart,
} from "@/components/project-documentation-charts";
import type { ExportCell, ExportTable } from "@/lib/table-export";

const TH =
  "whitespace-nowrap border border-[#cbd5e1] bg-[#f3f4f6] px-2.5 py-2 text-center font-bold text-[#111827] dark:border-[#334155] dark:bg-[hsl(209,72%,6%)] dark:text-[#fafafa]";
const TD =
  "whitespace-nowrap border border-[#cbd5e1] px-2.5 py-1.5 text-center align-middle dark:border-[#334155]";
const AHEAD_BG = "bg-[rgba(46,204,113,0.22)] dark:bg-[rgba(70,214,138,0.18)]";
const OVERDUE_BG = "bg-[rgba(231,76,60,0.22)] dark:bg-[rgba(255,84,84,0.18)]";
const OK_BG = "bg-[rgba(46,204,113,0.22)] dark:bg-[rgba(70,214,138,0.18)]";

type TabId = "main" | "delay";
type SortState = { key: string; asc: boolean } | null;

const INITIAL = {
  project: "Все",
  section: "Все",
  period: "Все месяцы",
  granularity: "week",
  viewMode: "project",
  reportDate: "",
};

function deviationClass(value: number | null | undefined): string {
  if (value == null || value === 0) {
    return "font-semibold text-[#15803d] dark:text-[#46d68a]";
  }
  return value < 0
    ? "font-semibold text-[hsl(348,100%,45%)] dark:text-[#ff5454]"
    : "font-semibold text-[#15803d] dark:text-[#46d68a]";
}

function highlightFromDays(
  days: number | null | undefined,
): "none" | "bad" | "ok" {
  if (days == null || days === 0) return "ok";
  if (days < 0) return "bad";
  return "ok";
}

function fmtDev(value: number | null | undefined): string {
  if (value == null) return "0";
  if (value > 0) return `+${value}`;
  return String(value);
}

function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: string;
  sort: SortState;
  onSort: (key: string) => void;
}) {
  const active = sort?.key === sortKey;
  return (
    <th className={TH}>
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

function compareVal(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null) return 1;
  if (b == null) return -1;
  if (typeof a === "number" && typeof b === "number") return a - b;
  return String(a).localeCompare(String(b), "ru", { numeric: true, sensitivity: "base" });
}

function ProjectDocumentationScreen({
  title,
  fetchPayload,
  showDelayTab,
}: {
  title: string;
  fetchPayload: (query?: ProjectDocumentationQuery) => Promise<ProjectDocumentationPayload>;
  showDelayTab: boolean;
}) {
  const [tab, setTab] = useState<TabId>("main");
  const [filters, setFilters] = useState(INITIAL);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [dateReady, setDateReady] = useState(false);
  const [data, setData] = useState<ProjectDocumentationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [mainSort, setMainSort] = useState<SortState>(null);
  const [detailSort, setDetailSort] = useState<SortState>(null);
  const [sumSort, setSumSort] = useState<SortState>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchPayload({
        project: filters.project,
        section: filters.section,
        period: filters.period === "Все месяцы" ? undefined : filters.period,
        granularity: filters.granularity,
        report_date: filters.reportDate || undefined,
        view_mode: filters.viewMode,
        tab,
      });
      setData(payload);
      if (!dateReady && payload.filters.applied.report_date) {
        setFilters((prev) => ({
          ...prev,
          reportDate: payload.filters.applied.report_date,
        }));
        setDateReady(true);
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [fetchPayload, filters, tab, dateReady]);

  useEffect(() => {
    void load();
  }, [load]);

  const selectClass = FILTER_SELECT_CLASS;

  // Дата из адреса приоритетнее подстановки из ответа API
  useUrlFilterState(
    filters,
    INITIAL,
    (patch) => setFilters((f) => ({ ...f, ...patch })),
    {
      onRestore: (restored) => {
        if (restored.reportDate) setDateReady(true);
      },
      navId: "project-documentation",
    },
  );

  const appliedReportDate = data?.filters.applied.report_date || INITIAL.reportDate;
  const resetFilters = () =>
    setFilters({ ...INITIAL, reportDate: appliedReportDate });
  const viewModeLabel = (id: string) =>
    (data?.filters.view_modes ?? []).find((m) => m.id === id)?.label ?? id;
  const activeFilters = buildFilterChips(
    filters,
    { ...INITIAL, reportDate: appliedReportDate },
    [
      { key: "project", name: "Проект", clear: { project: "Все", section: "Все" } },
      { key: "period", name: "Период" },
      { key: "section", name: "Вид раздела" },
      { key: "viewMode", name: "Отображение", label: viewModeLabel },
      { key: "reportDate", name: "Дата", kind: "date" },
    ],
    (patch) => setFilters((f) => ({ ...f, ...patch })),
  );

  const kpis = data?.kpis;
  const dynamics = data?.tremor.dynamics ?? [];
  const monthly = data?.tremor.monthly ?? [];

  const mainRows = useMemo(() => {
    const rows = [...(data?.rows ?? [])];
    if (!mainSort) return rows;
    return rows.sort((a, b) => {
      const key = mainSort.key as keyof (typeof rows)[number];
      const cmp = compareVal(a[key], b[key]);
      return mainSort.asc ? cmp : -cmp;
    });
  }, [data?.rows, mainSort]);

  const detailRows = useMemo(() => {
    const rows = [...(data?.delay.detail_rows ?? [])];
    if (!detailSort) return rows;
    return rows.sort((a, b) => {
      const key = detailSort.key as keyof (typeof rows)[number];
      const cmp = compareVal(a[key], b[key]);
      return detailSort.asc ? cmp : -cmp;
    });
  }, [data?.delay.detail_rows, detailSort]);

  const summaryRows = useMemo(() => {
    const rows = [...(data?.delay.summary_rows ?? [])];
    if (!sumSort) return rows;
    return rows.sort((a, b) => {
      const key = sumSort.key as keyof (typeof rows)[number];
      const cmp = compareVal(a[key], b[key]);
      return sumSort.asc ? cmp : -cmp;
    });
  }, [data?.delay.summary_rows, sumSort]);

  const toggleSort = (current: SortState, key: string, set: (s: SortState) => void) => {
    if (!current || current.key !== key) set({ key, asc: true });
    else if (current.asc) set({ key, asc: false });
    else set(null);
  };

  const mainExport = useCallback((): ExportTable | null => {
    if (!mainRows.length) return null;
    const headers = [
      "№ п/п",
      "Проект",
      "Раздел ПД",
      "Базовое окончание",
      "Окончание",
      "Отклонение (дней)",
    ];
    const body: ExportCell[][] = mainRows.map((row, i) => [
      row.n ?? i + 1,
      row.project,
      row.section,
      row.base_end ?? "",
      row.plan_end ?? "",
      row.dev_end,
    ]);
    return { header: [headers], rows: body, sheetName: "Выдача ПД" };
  }, [mainRows]);

  const detailExport = useCallback((): ExportTable | null => {
    if (!detailRows.length) return null;
    const headers = data?.delay.detail_columns ?? [];
    const body: ExportCell[][] = detailRows.map((row) => [
      row.project,
      row.work_name,
      row.section,
      row.status,
      row.start,
      row.base_start,
      row.finish,
      row.base_finish,
      row.dev_start,
      row.dev_end,
    ]);
    return { header: [headers], rows: body, sheetName: "Детальная ПД" };
  }, [detailRows, data?.delay.detail_columns]);

  const summaryExport = useCallback((): ExportTable | null => {
    if (!summaryRows.length) return null;
    return {
      header: [
        data?.delay.summary_columns ?? ["Проект", "План ПД", "Факт ПД", "Просрочка ПД"],
      ],
      rows: summaryRows.map((row) => [
        row.project,
        row.plan,
        row.fact,
        row.overdue_label,
      ]),
      sheetName: "Сводка просрочки ПД",
    };
  }, [summaryRows, data?.delay.summary_columns]);

  return (
    <AppShell title={title} loading={loading}>
      {showDelayTab ? (
        <div className="mb-4 flex gap-4 border-b border-tremor-border dark:border-dark-tremor-border">
          {(
            [
              ["main", "Проектная документация"],
              ["delay", "Просрочка выдачи ПД"],
            ] as const
          ).map(([id, label]) => (
            <button
              key={id}
              type="button"
              onClick={() => setTab(id)}
              className={`border-b-2 px-1 pb-2 text-sm font-medium ${
                tab === id
                  ? "border-emerald-600 text-emerald-700 dark:border-emerald-400 dark:text-emerald-300"
                  : "border-transparent text-tremor-content dark:text-dark-tremor-content"
              }`}
            >
              {label}
            </button>
          ))}
        </div>
      ) : null}

      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((v) => !v)}
        activeFilters={activeFilters}
        onReset={activeFilters.length ? resetFilters : undefined}
      >
        <FiltersReset onClick={resetFilters} />
        {tab === "main" ? (
          <FilterFieldsRow cols={3}>
            <FilterChipSelect label="Проект" value={filters.project} options={data?.filters.projects ?? ["Все"]} onChange={(project) => setFilters((f) => ({ ...f, project, section: "Все" }))} />
            <FilterChipSelect label="Период" value={filters.period} options={["Все месяцы", ...(data?.filters.periods ?? [])]} onChange={(period) => setFilters((f) => ({ ...f, period }))} />
            <FilterChipSelect label="Вид раздела" value={filters.section} options={data?.filters.sections ?? ["Все"]} onChange={(section) => setFilters((f) => ({ ...f, section }))} />
          </FilterFieldsRow>
        ) : (
          <FilterFieldsRow cols={5}>
            <FilterChipSelect label="Проект" value={filters.project} options={data?.filters.projects ?? ["Все"]} onChange={(project) => setFilters((f) => ({ ...f, project, section: "Все" }))} />
            <FilterChipSelect label="Отображение" value={filters.viewMode} options={(data?.filters.view_modes ?? []).map((item) => ({ value: item.id, label: item.label }))} onChange={(viewMode) => setFilters((f) => ({ ...f, viewMode }))} />
            <FilterChipSelect label="Вид раздела" value={filters.section} options={data?.filters.sections ?? ["Все"]} onChange={(section) => setFilters((f) => ({ ...f, section }))} />
            <FilterField label="Статус">
              <span className="mt-1 inline-flex rounded-full bg-rose-100 px-2.5 py-1 text-xs font-medium text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
                Просрочено подрядчиком
              </span>
            </FilterField>
            <FilterField label="Дата">
              <input
                type="date"
                className={selectClass}
                value={filters.reportDate}
                onChange={(e) => setFilters((f) => ({ ...f, reportDate: e.target.value }))}
              />
            </FilterField>
          </FilterFieldsRow>
        )}
        {tab === "main" ? (
          <div className="flex flex-wrap gap-2 pt-1">
            {(data?.filters.status_legend ?? []).map((item) => (
              <span
                key={item.id}
                className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
                  item.tone === "ok"
                    ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-300"
                    : "bg-rose-100 text-rose-700 dark:bg-rose-950/40 dark:text-rose-300"
                }`}
              >
                {item.label}
              </span>
            ))}
          </div>
        ) : null}
        {tab === "main" ? (
          <FilterFieldsRow cols={3}>
            <FilterChipSelect label="Гранулярность" value={filters.granularity} options={(data?.filters.granularities ?? []).map((item) => ({ value: item.id, label: item.label }))} onChange={(granularity) => setFilters((f) => ({ ...f, granularity }))} />
            <div />
            <div />
          </FilterFieldsRow>
        ) : null}
      </FiltersCard>

      {error ? (
        <Card className="mb-6 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">API недоступен. {error}</Text>
        </Card>
      ) : null}

      {loading && !data ? (
        <Text className="mb-4 text-sm text-tremor-content dark:text-dark-tremor-content">
          загрузка…
        </Text>
      ) : null}

      {data?.meta.error ? (
        <Card className="mb-6 rounded-xl border-amber-300 bg-amber-50 dark:bg-amber-950/30">
          <Text className="text-amber-800 dark:text-amber-200">{data.meta.error}</Text>
        </Card>
      ) : null}

      {tab === "main" ? (
        <div className="space-y-6">
          <FullscreenPanel fill disabled={!data?.tremor.status_mix.length}>
            {(zoomed) => (
              <Card className="rounded-xl">
                <Title>Исполнение ПД</Title>
                <div className="mt-4 grid gap-4 md:grid-cols-[12rem_1fr]">
                  <div className="flex flex-col justify-center gap-3 text-sm">
                    {(data?.tremor.status_mix ?? []).map((item) => (
                      <div key={item.name} className="flex items-center gap-2">
                        <span
                          className="inline-block h-3 w-3 rounded-sm"
                          style={{ background: item.color || "#2E86AB" }}
                        />
                        <span>
                          {item.name}: {item.value}
                        </span>
                      </div>
                    ))}
                  </div>
                  <div className="min-h-[16rem]">
                    <PdExecutionPieChart
                      rows={data?.tremor.status_mix ?? []}
                      fullscreen={zoomed}
                    />
                  </div>
                </div>
                <Text className="mt-2 text-center text-xs text-tremor-content dark:text-dark-tremor-content">
                  График Исполнение ПД
                </Text>
              </Card>
            )}
          </FullscreenPanel>

          <Grid numItemsSm={2} numItemsLg={6} className="gap-4">
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
                {fmtDev(kpis?.deviation_to_date)}
              </Metric>
            </Card>
            <Card className="rounded-xl">
              <Text>Текущая производительность {kpis?.productivity_label ?? "за неделю"}</Text>
              <Metric className="mt-2">{kpis?.current_productivity ?? 0}</Metric>
            </Card>
            <Card className="rounded-xl">
              <Text>Необходимая производительность ({kpis?.required_label ?? "в неделю"})</Text>
              <Metric className="mt-2">
                {Number(kpis?.required_productivity ?? 0).toLocaleString("ru-RU", {
                  maximumFractionDigits: 1,
                })}
              </Metric>
            </Card>
          </Grid>

          <FullscreenPanel fill disabled={!dynamics.length}>
            {(zoomed) => (
              <Card className="rounded-xl">
                <Title>График Динамика выдачи ПД</Title>
                <div className="mt-4">
                  <PdDynamicsLineChart rows={dynamics} fullscreen={zoomed} />
                </div>
                <Text className="mt-2 text-center text-xs">
                  Количество разделов ПД · Период
                </Text>
              </Card>
            )}
          </FullscreenPanel>

          <FullscreenPanel disabled={!mainRows.length}>
            <Card className="min-w-0 max-w-full rounded-xl p-0">
              <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
                <Title>Таблица Выдача проектной документации по проектам</Title>
              </div>
              {!mainRows.length ? (
                <div className="px-4 py-10 text-center text-sm">Нет строк по фильтрам.</div>
              ) : (
                <>
                  <MobileCardStack>
                    {mainRows.map((row, index) => {
                      const ahead = (row.dev_end_days ?? 0) > 0;
                      return (
                        <MobileEntityCard
                          key={`m-pd-${row.project}-${row.section}-${index}`}
                          title={`${row.project}: ${row.section}`}
                          badge={row.dev_end || undefined}
                          badgeTone={
                            row.dev_end_days == null
                              ? "neutral"
                              : row.dev_end_days < 0
                                ? "bad"
                                : "ok"
                          }
                        >
                          <MobileMetricGrid
                            columns={2}
                            items={[
                              { label: "№", value: row.n ?? index + 1 },
                              { label: "Раздел", value: row.section },
                              {
                                label: "Базовое",
                                value: row.base_end ?? "—",
                                highlight: ahead ? "ok" : "date",
                              },
                              {
                                label: "Окончание",
                                value: row.plan_end ?? "—",
                                highlight: ahead ? "ok" : "date",
                              },
                              {
                                label: "Откл.",
                                value: row.dev_end || "—",
                                className: deviationClass(row.dev_end_days),
                                highlight: highlightFromDays(row.dev_end_days),
                              },
                            ]}
                          />
                        </MobileEntityCard>
                      );
                    })}
                  </MobileCardStack>
                  <div className="hidden lg:block">
                  <div className="max-h-[28rem] w-full min-w-0 max-w-full overflow-x-auto overflow-y-auto">
                  <table className="bi-sticky-head bi-sticky-col w-max min-w-full border-separate border-spacing-0 text-sm">
                    <thead>
                      <tr>
                        <SortHeader
                          label="№ п/п"
                          sortKey="n"
                          sort={mainSort}
                          onSort={(k) => toggleSort(mainSort, k, setMainSort)}
                        />
                        <SortHeader
                          label="Проект"
                          sortKey="project"
                          sort={mainSort}
                          onSort={(k) => toggleSort(mainSort, k, setMainSort)}
                        />
                        <SortHeader
                          label="Раздел ПД"
                          sortKey="section"
                          sort={mainSort}
                          onSort={(k) => toggleSort(mainSort, k, setMainSort)}
                        />
                        <SortHeader
                          label="Базовое окончание"
                          sortKey="base_end"
                          sort={mainSort}
                          onSort={(k) => toggleSort(mainSort, k, setMainSort)}
                        />
                        <SortHeader
                          label="Окончание"
                          sortKey="plan_end"
                          sort={mainSort}
                          onSort={(k) => toggleSort(mainSort, k, setMainSort)}
                        />
                        <SortHeader
                          label="Отклонение (дней)"
                          sortKey="dev_end_days"
                          sort={mainSort}
                          onSort={(k) => toggleSort(mainSort, k, setMainSort)}
                        />
                      </tr>
                    </thead>
                    <tbody>
                      {mainRows.map((row, index) => {
                        const ahead = (row.dev_end_days ?? 0) > 0;
                        return (
                          <tr key={`${row.project}-${row.section}-${index}`}>
                            <td className={`${TD} tabular-nums`}>{row.n ?? index + 1}</td>
                            <td className={TD}>{row.project}</td>
                            <td className={`${TD} ${ahead ? AHEAD_BG : ""}`}>{row.section}</td>
                            <td className={`${TD} tabular-nums ${ahead ? AHEAD_BG : ""}`}>
                              {row.base_end ?? "—"}
                            </td>
                            <td className={`${TD} tabular-nums ${ahead ? AHEAD_BG : ""}`}>
                              {row.plan_end ?? "—"}
                            </td>
                            <td
                              className={`${TD} tabular-nums ${ahead ? AHEAD_BG : ""} ${deviationClass(row.dev_end_days)}`}
                            >
                              {row.dev_end || "—"}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                  </div>
                  </div>
                </>
              )}
              <div className="px-4 py-3">
                <DownloadTableButton
                  getTable={mainExport}
                  fileStem="pd_dynamics_table"
                  disabled={!mainRows.length}
                />
              </div>
            </Card>
          </FullscreenPanel>
        </div>
      ) : (
        <div className="space-y-6">
          <Title className="!text-xl">Просрочка выдачи ПД</Title>

          <FullscreenPanel fill disabled={!data?.delay.gantt.rows.length}>
            {(zoomed) => (
              <Card className="rounded-xl">
                <Title>График Просрочка выдачи ПД</Title>
                <div className="mt-4">
                  <PdDelayGanttChart
                    rows={data?.delay.gantt.rows ?? []}
                    rangeStart={data?.delay.gantt.range_start ?? null}
                    rangeEnd={data?.delay.gantt.range_end ?? null}
                    fullscreen={zoomed}
                  />
                </div>
              </Card>
            )}
          </FullscreenPanel>

          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-5">
            {(data?.delay.cards ?? []).map((card) => (
              <Card
                key={card.project}
                className={`rounded-xl border-0 text-white ${
                  card.tone === "bad" ? "bg-[#C0392B]" : "bg-[#1E8449]"
                }`}
              >
                <Text className="!text-white/90">{card.project}</Text>
                <Metric className="mt-1 !text-white !text-lg">{card.label}</Metric>
              </Card>
            ))}
          </div>

          <FullscreenPanel fill disabled={!monthly.length}>
            {(zoomed) => (
              <Card className="rounded-xl">
                <Title>Динамика выдачи ПД по месяцам</Title>
                <div className="mt-4">
                  <PdMonthlyCumulativeChart rows={monthly} fullscreen={zoomed} />
                </div>
                <Text className="mt-2 text-center text-xs">
                  График Выдача проектной документации по месяцам
                </Text>
              </Card>
            )}
          </FullscreenPanel>

          <FullscreenPanel disabled={!detailRows.length}>
            <Card className="min-w-0 max-w-full rounded-xl p-0">
              <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
                <Title>Детальная таблица</Title>
              </div>
              {!detailRows.length ? (
                <div className="px-4 py-10 text-center text-sm">Нет данных.</div>
              ) : (
                <>
                  <MobileCardStack>
                    {detailRows.map((row, i) => (
                      <MobileEntityCard
                        key={`m-det-${row.project}-${row.section}-${i}`}
                        title={`${row.project}: ${row.work_name || row.section}`}
                        badge={row.dev_end || undefined}
                        badgeTone={
                          row.dev_end_days == null
                            ? "neutral"
                            : row.dev_end_days < 0
                              ? "bad"
                              : "ok"
                        }
                      >
                        <MobileMetricGrid
                          columns={2}
                          items={[
                            { label: "Раздел", value: row.section },
                            { label: "Статус", value: row.status || "—" },
                            {
                              label: "Начало",
                              value: row.start || "—",
                              highlight: "date",
                            },
                            {
                              label: "Баз. нач.",
                              value: row.base_start || "—",
                              highlight: "date",
                            },
                            {
                              label: "Окончание",
                              value: row.finish || "—",
                              highlight: "date",
                            },
                            {
                              label: "Баз. оконч.",
                              value: row.base_finish || "—",
                              highlight: "date",
                            },
                            {
                              label: "Откл. нач.",
                              value: row.dev_start || "—",
                              className: deviationClass(row.dev_start_days),
                              highlight: highlightFromDays(row.dev_start_days),
                            },
                            {
                              label: "Откл. оконч.",
                              value: row.dev_end || "—",
                              className: deviationClass(row.dev_end_days),
                              highlight: highlightFromDays(row.dev_end_days),
                            },
                          ]}
                        />
                      </MobileEntityCard>
                    ))}
                  </MobileCardStack>
                  <div className="hidden lg:block">
                  <div className="max-h-[28rem] w-full min-w-0 max-w-full overflow-x-auto overflow-y-auto">
                  <table className="bi-sticky-head bi-sticky-col w-max min-w-full border-separate border-spacing-0 text-xs">
                    <thead>
                      <tr>
                        {(
                          [
                            ["project", "Проект"],
                            ["work_name", "Наименование раздела работ"],
                            ["section", "Раздел"],
                            ["status", "Статус"],
                            ["start", "Начало"],
                            ["base_start", "Базовое начало"],
                            ["finish", "Окончание"],
                            ["base_finish", "Базовое окончание"],
                            ["dev_start_days", "Отклонение начала, дн"],
                            ["dev_end_days", "Отклонение окончания, дн"],
                          ] as const
                        ).map(([key, label]) => (
                          <SortHeader
                            key={key}
                            label={label}
                            sortKey={key}
                            sort={detailSort}
                            onSort={(k) => toggleSort(detailSort, k, setDetailSort)}
                          />
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {detailRows.map((row, i) => (
                        <tr key={`${row.project}-${row.section}-${i}`}>
                          <td className={TD}>{row.project}</td>
                          <td className={`${TD} max-w-xs truncate text-left`}>{row.work_name}</td>
                          <td className={TD}>{row.section}</td>
                          <td className={TD}>{row.status}</td>
                          <td className={`${TD} tabular-nums`}>{row.start}</td>
                          <td className={`${TD} tabular-nums`}>{row.base_start}</td>
                          <td className={`${TD} tabular-nums`}>{row.finish}</td>
                          <td className={`${TD} tabular-nums`}>{row.base_finish}</td>
                          <td className={`${TD} tabular-nums ${deviationClass(row.dev_start_days)}`}>
                            {row.dev_start || "—"}
                          </td>
                          <td
                            className={`${TD} tabular-nums ${
                              (row.dev_end_days ?? 0) > 0
                                ? AHEAD_BG
                                : (row.dev_end_days ?? 0) < 0
                                  ? OVERDUE_BG
                                  : ""
                            } ${deviationClass(row.dev_end_days)}`}
                          >
                            {row.dev_end || "—"}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                  </div>
                </>
              )}
              <div className="px-4 py-3">
                <DownloadTableButton
                  getTable={detailExport}
                  fileStem="pd_delay_detail"
                  disabled={!detailRows.length}
                />
              </div>
            </Card>
          </FullscreenPanel>

          <FullscreenPanel disabled={!summaryRows.length}>
            <Card className="min-w-0 max-w-full rounded-xl p-0">
              <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
                <Title>Таблица Сводка по просрочке выдачи документации</Title>
              </div>
              {!summaryRows.length ? (
                <div className="px-4 py-10 text-center text-sm">Нет данных.</div>
              ) : (
                <>
                  <MobileCardStack>
                    {summaryRows.map((row) => (
                      <MobileEntityCard
                        key={`m-sum-${row.project}`}
                        title={row.project}
                        badge={row.overdue_label}
                        badgeTone={row.overdue < 0 ? "bad" : "ok"}
                      >
                        <MobileMetricGrid
                          columns={2}
                          items={[
                            { label: "План ПД", value: row.plan },
                            { label: "Факт ПД", value: row.fact },
                            {
                              label: "Просрочка",
                              value: row.overdue_label,
                              className: deviationClass(row.overdue),
                              highlight: row.overdue < 0 ? "bad" : "ok",
                            },
                          ]}
                        />
                      </MobileEntityCard>
                    ))}
                  </MobileCardStack>
                  <div className="hidden lg:block">
                  <div className="bi-table-scroll w-full min-w-0 max-w-full overflow-x-auto overflow-y-auto">
                <table className="bi-sticky-head bi-sticky-col w-max min-w-full border-separate border-spacing-0 text-sm">
                  <thead>
                    <tr>
                      {(
                        [
                          ["project", "Проект"],
                          ["plan", "План ПД"],
                          ["fact", "Факт ПД"],
                          ["overdue", "Просрочка ПД"],
                        ] as const
                      ).map(([key, label]) => (
                        <SortHeader
                          key={key}
                          label={label}
                          sortKey={key}
                          sort={sumSort}
                          onSort={(k) => toggleSort(sumSort, k, setSumSort)}
                        />
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {summaryRows.map((row) => (
                      <tr key={row.project}>
                        <td className={TD}>{row.project}</td>
                        <td className={`${TD} tabular-nums`}>{row.plan}</td>
                        <td className={`${TD} tabular-nums`}>{row.fact}</td>
                        <td
                          className={`${TD} tabular-nums ${
                            row.overdue < 0 ? OVERDUE_BG : OK_BG
                          } ${deviationClass(row.overdue)}`}
                        >
                          {row.overdue_label}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
                  </div>
                  </div>
                </>
              )}
              <div className="px-4 py-3">
                <DownloadTableButton
                  getTable={summaryExport}
                  fileStem="pd_delay_summary"
                  disabled={!summaryRows.length}
                />
              </div>
            </Card>
          </FullscreenPanel>
        </div>
      )}
    </AppShell>
  );
}

export function ProjectDocumentationView() {
  return (
    <ProjectDocumentationScreen
      title="Проектная документация"
      fetchPayload={fetchProjectDocumentation}
      showDelayTab
    />
  );
}
