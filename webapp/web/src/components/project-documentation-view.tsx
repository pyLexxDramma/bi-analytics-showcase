"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart,
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
  type ProjectDocumentationQuery,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import {
  FilterField,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import { CHART_RU, withRuDocDynamics } from "@/lib/chart-ru";
import type { ExportCell, ExportTable } from "@/lib/table-export";

const TH =
  "whitespace-nowrap border border-[#cbd5e1] bg-[#f3f4f6] px-2.5 py-2 text-center font-bold text-[#111827] dark:border-[#334155] dark:bg-[hsl(209,72%,6%)] dark:text-[#fafafa]";
const TD =
  "border border-[#cbd5e1] px-2.5 py-1.5 text-center align-middle dark:border-[#334155]";
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

function PdDelayGantt({
  rows,
  rangeStart,
  rangeEnd,
}: {
  rows: ProjectDocumentationPayload["delay"]["gantt"]["rows"];
  rangeStart: string | null;
  rangeEnd: string | null;
}) {
  if (!rows.length) {
    return (
      <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет данных для графика просрочки.
      </div>
    );
  }
  const lo = rangeStart ? Date.parse(rangeStart) : Math.min(...rows.map((r) => Date.parse(r.start)));
  const hiCandidates = rows.flatMap((r) =>
    [r.delay_end, r.finish, r.base_finish].filter(Boolean).map((d) => Date.parse(String(d))),
  );
  const hi = rangeEnd ? Date.parse(rangeEnd) : Math.max(...hiCandidates);
  const span = Math.max(hi - lo, 1);
  const pct = (iso: string | null | undefined) => {
    if (!iso) return 0;
    return ((Date.parse(iso) - lo) / span) * 100;
  };
  const width = (from: string, to: string | null | undefined) => {
    if (!to) return 0;
    return Math.max(((Date.parse(to) - Date.parse(from)) / span) * 100, 0.4);
  };

  return (
    <div className="space-y-3 px-2 py-2">
      <div className="flex flex-wrap gap-4 text-xs text-tremor-content dark:text-dark-tremor-content">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#F1C40F]" /> Базовое окончание
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#27AE60]" /> Окончание
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#C0392B]" /> Просрочка
        </span>
      </div>
      {rows.map((row) => {
        const baseLeft = pct(row.start);
        const baseW = width(row.start, row.base_finish);
        const green = row.fact_dur > 0 && row.finish && !row.delay_end;
        const red = row.delay_dur > 0 && row.delay_end;
        return (
          <div key={row.label} className="grid grid-cols-[9rem_1fr] items-center gap-2">
            <div className="truncate text-right text-xs font-medium">{row.label}</div>
            <div className="relative h-7 rounded bg-tremor-background-muted dark:bg-dark-tremor-background-muted">
              <div
                className="absolute top-1 h-5 rounded-sm bg-[#F1C40F]"
                style={{ left: `${baseLeft}%`, width: `${baseW}%` }}
                title={`Базовое окончание ${row.base_label}`}
              />
              {green ? (
                <div
                  className="absolute top-1 h-5 rounded-sm bg-[#27AE60]"
                  style={{
                    left: `${baseLeft}%`,
                    width: `${width(row.start, row.finish)}%`,
                  }}
                  title={`Окончание ${row.finish_label}`}
                />
              ) : null}
              {red ? (
                <div
                  className="absolute top-1 h-5 rounded-sm bg-[#C0392B]"
                  style={{
                    left: `${pct(row.base_finish)}%`,
                    width: `${width(row.base_finish, row.delay_end)}%`,
                  }}
                  title={`Просрочка до ${row.finish_label}`}
                />
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
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

  const kpis = data?.kpis;
  const dynamics = useMemo(
    () => withRuDocDynamics(data?.tremor.dynamics ?? []),
    [data?.tremor.dynamics],
  );
  const monthly = useMemo(
    () =>
      (data?.tremor.monthly ?? []).map((row) => ({
        ...row,
        [CHART_RU.plan]: row.plan,
        [CHART_RU.fact]: row.fact,
      })),
    [data?.tremor.monthly],
  );

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

  const donutColors = (data?.tremor.status_mix ?? []).map((item) => {
    if (item.name.includes("Заверш")) return "blue";
    if (item.name.includes("работ")) return "amber";
    return "rose";
  }) as ("blue" | "amber" | "rose")[];

  return (
    <AppShell title={title}>
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

      <FiltersCard open={filtersOpen} onToggle={() => setFiltersOpen((v) => !v)}>
        <FiltersReset
          onClick={() =>
            setFilters({
              ...INITIAL,
              reportDate: data?.filters.applied.report_date || INITIAL.reportDate,
            })
          }
        />
        {tab === "main" ? (
          <FilterFieldsRow cols={3}>
            <FilterField label="Проект">
              <select
                className={selectClass}
                value={filters.project}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, project: e.target.value, section: "Все" }))
                }
              >
                {(data?.filters.projects ?? ["Все"]).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Период">
              <select
                className={selectClass}
                value={filters.period}
                onChange={(e) => setFilters((f) => ({ ...f, period: e.target.value }))}
              >
                <option value="Все месяцы">Все месяцы</option>
                {(data?.filters.periods ?? []).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Вид раздела">
              <select
                className={selectClass}
                value={filters.section}
                onChange={(e) => setFilters((f) => ({ ...f, section: e.target.value }))}
              >
                {(data?.filters.sections ?? ["Все"]).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </FilterField>
          </FilterFieldsRow>
        ) : (
          <FilterFieldsRow cols={5}>
            <FilterField label="Проект">
              <select
                className={selectClass}
                value={filters.project}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, project: e.target.value, section: "Все" }))
                }
              >
                {(data?.filters.projects ?? ["Все"]).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Отображение">
              <select
                className={selectClass}
                value={filters.viewMode}
                onChange={(e) => setFilters((f) => ({ ...f, viewMode: e.target.value }))}
              >
                {(data?.filters.view_modes ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Вид раздела">
              <select
                className={selectClass}
                value={filters.section}
                onChange={(e) => setFilters((f) => ({ ...f, section: e.target.value }))}
              >
                {(data?.filters.sections ?? ["Все"]).map((item) => (
                  <option key={item} value={item}>
                    {item}
                  </option>
                ))}
              </select>
            </FilterField>
            <FilterField label="Статус">
              <span className="mt-1 inline-flex rounded-full bg-rose-100 px-2.5 py-1 text-xs font-medium text-rose-700 dark:bg-rose-950/40 dark:text-rose-300">
                Просрочка по утверждению
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
            <FilterField label="Гранулярность">
              <select
                className={selectClass}
                value={filters.granularity}
                onChange={(e) => setFilters((f) => ({ ...f, granularity: e.target.value }))}
              >
                {(data?.filters.granularities ?? []).map((item) => (
                  <option key={item.id} value={item.id}>
                    {item.label}
                  </option>
                ))}
              </select>
            </FilterField>
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
                      <span>{item.name}</span>
                    </div>
                  ))}
                </div>
                <DonutChart
                  className="h-64"
                  data={data?.tremor.status_mix ?? []}
                  category="value"
                  index="name"
                  colors={donutColors.length ? donutColors : ["blue", "rose"]}
                  showLabel
                  valueFormatter={(v) => `${v}`}
                />
              </div>
              <Text className="mt-2 text-center text-xs text-tremor-content dark:text-dark-tremor-content">
                График Исполнение ПД
              </Text>
            </Card>
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
            <Card className="rounded-xl">
              <Title>График Динамика выдачи ПД</Title>
              <LineChart
                className="mt-6 h-80"
                data={dynamics}
                index="period_label"
                categories={[CHART_RU.planBp, CHART_RU.forecast, CHART_RU.factLine]}
                colors={["blue", "orange", "emerald"]}
                yAxisWidth={48}
                showLegend
                showAnimation
                showGridLines
                valueFormatter={(v) => `${Math.round(v)}`}
              />
              <Text className="mt-2 text-center text-xs">Количество разделов ПД · Период</Text>
            </Card>
          </FullscreenPanel>

          <FullscreenPanel disabled={!mainRows.length}>
            <Card className="overflow-hidden rounded-xl p-0">
              <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
                <Title>Таблица Выдача проектной документации по проектам</Title>
              </div>
              <div className="max-h-[28rem] overflow-auto">
                {!mainRows.length ? (
                  <div className="px-4 py-10 text-center text-sm">Нет строк по фильтрам.</div>
                ) : (
                  <table className="min-w-full border-separate border-spacing-0 text-sm">
                    <thead className="sticky top-0 z-10">
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
                )}
              </div>
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
            <Card className="rounded-xl">
              <Title>График Просрочка выдачи ПД</Title>
              <div className="mt-4 max-h-[28rem] overflow-auto">
                <PdDelayGantt
                  rows={data?.delay.gantt.rows ?? []}
                  rangeStart={data?.delay.gantt.range_start ?? null}
                  rangeEnd={data?.delay.gantt.range_end ?? null}
                />
              </div>
            </Card>
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
            <Card className="rounded-xl">
              <Title>Динамика выдачи ПД по месяцам</Title>
              <BarChart
                className="mt-6 h-80"
                data={monthly}
                index="month_label"
                categories={[CHART_RU.plan, CHART_RU.fact]}
                colors={["blue", "emerald"]}
                layout="vertical"
                yAxisWidth={110}
                showLegend
                showAnimation
                valueFormatter={(v) => `${Math.round(v)}`}
              />
              <Text className="mt-2 text-center text-xs">
                График Выдача проектной документации по месяцам
              </Text>
            </Card>
          </FullscreenPanel>

          <FullscreenPanel disabled={!detailRows.length}>
            <Card className="overflow-hidden rounded-xl p-0">
              <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
                <Title>Детальная таблица</Title>
              </div>
              <div className="max-h-[28rem] overflow-auto">
                {!detailRows.length ? (
                  <div className="px-4 py-10 text-center text-sm">Нет данных.</div>
                ) : (
                  <table className="min-w-full border-separate border-spacing-0 text-xs">
                    <thead className="sticky top-0 z-10">
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
                )}
              </div>
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
            <Card className="overflow-hidden rounded-xl p-0">
              <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
                <Title>Таблица Сводка по просрочке выдачи документации</Title>
              </div>
              <div className="overflow-auto">
                <table className="min-w-full border-separate border-spacing-0 text-sm">
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
              <div className="px-4 py-3">
                <DownloadTableButton
                  getTable={summaryExport}
                  fileStem="rd_delay_summary"
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
