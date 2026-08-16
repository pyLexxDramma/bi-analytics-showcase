"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { Card, Grid, Metric, Text, Title } from "@tremor/react";
import {
  fetchWorkingDocumentation,
  type WorkingDocumentationPayload,
  type WorkingDocumentationQuery,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
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
import { buildFilterChips } from "@/lib/filters-summary";
import { isSingleProjectSelection } from "@/lib/chart-labels";
import { useUrlFilterState } from "@/lib/use-url-filter-state";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  MobileCardStack,
  MobileEntityCard,
  MobileMetricGrid,
} from "@/components/mobile-entity-card";
import {
  RdDelayGanttChart,
  RdDynamicsLineChart,
  RdExecutionPieChart,
  RdMonthlyCumulativeChart,
} from "@/components/working-documentation-charts";
import type { ExportCell, ExportTable } from "@/lib/table-export";
import {
  deviationCellStyle,
  isDeviationCol,
  isIdentityCol,
  parseSortableNumber,
} from "@/lib/deviation-cell-style";
import { useIsMobileViewport } from "@/lib/use-is-mobile";
import { DashboardEmptyState } from "@/components/dashboard-empty-state";
import { DashboardInsight } from "@/components/dashboard-insight";

const TH =
  "whitespace-nowrap px-2.5 py-2 text-center text-[13px] font-bold leading-tight text-[#111827] dark:text-[#fafafa]";
const TD =
  "whitespace-nowrap px-2.5 py-1.5 text-center align-middle text-[13px] text-[#111827] dark:text-[#e8eef5]";

type TabId = "main" | "delay";
type SortState = { key: string; asc: boolean } | null;

const INITIAL = {
  projects: [] as string[],
  sections: [] as string[],
  statuses: [] as string[],
  periodMode: "Весь период (за всё время)",
  dateFrom: "",
  dateTo: "",
  metricMode: "Количество разделов",
  showForecast: true,
  viewMode: "project",
};

function joinMulti(values: string[], allToken = "Все"): string | undefined {
  if (!values.length || (values.length === 1 && values[0] === allToken)) return undefined;
  if (values.includes(allToken) && values.length === 1) return undefined;
  return values.filter((v) => v !== allToken).join("|") || undefined;
}

function deviationClass(value: number | null | undefined): string {
  if (value == null || value === 0) {
    return "font-semibold text-[#15803d] dark:text-[#46d68a]";
  }
  return value < 0
    ? "font-semibold text-[hsl(348,100%,45%)] dark:text-[#ff5454]"
    : "font-semibold text-[#15803d] dark:text-[#46d68a]";
}

function compareVal(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null || a === "" || a === "—") return 1;
  if (b == null || b === "" || b === "—") return -1;
  const na = parseSortableNumber(a);
  const nb = parseSortableNumber(b);
  if (na != null && nb != null) return na - nb;
  return String(a).localeCompare(String(b), "ru", {
    numeric: true,
    sensitivity: "base",
  });
}

function highlightFromDays(
  value: number | null | undefined,
): "none" | "date" | "bad" | "ok" {
  if (value == null || Number.isNaN(value)) return "none";
  if (value < 0) return "bad";
  return "ok";
}

function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
  dark,
}: {
  label: string;
  sortKey: string;
  sort: SortState;
  onSort: (key: string) => void;
  dark: boolean;
}) {
  const active = sort?.key === sortKey;
  return (
    <th
      className={TH}
      style={{
        border: dark ? "1px solid #334155" : "1px solid #d1d5db",
        backgroundColor: dark ? "hsl(209,72%,6%)" : "#f3f4f6",
      }}
    >
      <button
        type="button"
        title="Сортировать по колонке"
        onClick={() => onSort(sortKey)}
        className="inline-flex w-full items-center justify-center gap-1"
      >
        <span>{label}</span>
        <span
          className={
            active
              ? "font-bold text-emerald-700 dark:text-emerald-300"
              : "opacity-70"
          }
          aria-hidden
        >
          {active ? (sort?.asc ? "↑" : "↓") : "⇅"}
        </span>
      </button>
    </th>
  );
}

function fmtNum(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("ru-RU", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function fmtSigned(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value > 0) return `+${fmtNum(value)}`;
  return fmtNum(value);
}

function cellDisplay(
  row: Record<string, string | number | null>,
  col: string,
): string {
  const label = row[`${col}__label`];
  if (label != null && label !== "") return String(label);
  const v = row[col];
  if (v == null || v === "") return "—";
  if (typeof v === "number" && col.toLowerCase().includes("отклонен")) {
    return v > 0 ? `+${v}` : String(v);
  }
  return String(v);
}

function DetailTable({
  columns,
  rows,
  fileStem,
  onReset,
}: {
  columns: string[];
  rows: Array<Record<string, string | number | null>>;
  fileStem: string;
  onReset?: () => void;
}) {
  const [sort, setSort] = useState<SortState>(null);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const el = document.documentElement;
    const sync = () => setDark(el.classList.contains("dark"));
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  const onSort = useCallback((key: string) => {
    setSort((prev) => {
      if (prev?.key === key) {
        return prev.asc ? { key, asc: false } : null;
      }
      return { key, asc: true };
    });
  }, []);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const cmp = compareVal(a[sort.key], b[sort.key]);
      return sort.asc ? cmp : -cmp;
    });
    return copy;
  }, [rows, sort]);

  const vmaxByCol = useMemo(() => {
    const map: Record<string, number> = {};
    for (const c of columns) {
      if (!isDeviationCol(c)) continue;
      let vmax = 1;
      for (const row of rows) {
        const n = parseSortableNumber(row[c] ?? row[`${c}__label`]);
        if (n != null) vmax = Math.max(vmax, Math.abs(n));
      }
      map[c] = vmax;
    }
    return map;
  }, [columns, rows]);

  const titleCol = useMemo(() => {
    const prefer = ["Проект", "Раздел", "Наименование разделов работ", "Шифр"];
    for (const p of prefer) {
      if (columns.includes(p)) return p;
    }
    return columns[0] ?? "";
  }, [columns]);

  const badgeCol = useMemo(
    () => columns.find((c) => isDeviationCol(c)) ?? "",
    [columns],
  );

  const exportTable = useCallback((): ExportTable | null => {
    if (!sortedRows.length || !columns.length) return null;
    const header: ExportCell[][] = [columns];
    const body: ExportCell[][] = sortedRows.map((row) =>
      columns.map((c) => cellDisplay(row, c)),
    );
    return { header, rows: body, sheetName: "РД" };
  }, [sortedRows, columns]);

  return (
    <FullscreenPanel disabled={!sortedRows.length}>
      <Card className="min-w-0 max-w-full rounded-xl p-0">
        {!sortedRows.length || !columns.length ? (
          <DashboardEmptyState
            message="Нет строк по фильтрам."
            onReset={onReset}
          />
        ) : (
          <>
            <MobileCardStack>
              {sortedRows.map((row, i) => {
                const badgeVal = badgeCol ? parseSortableNumber(row[badgeCol]) : null;
                const badgeText = badgeCol ? cellDisplay(row, badgeCol) : undefined;
                const metricCols = columns.filter((c) => c !== titleCol).slice(0, 8);
                return (
                  <MobileEntityCard
                    key={`rd-m-${i}`}
                    title={titleCol ? cellDisplay(row, titleCol) : `Строка ${i + 1}`}
                    badge={badgeText && badgeText !== "—" ? badgeText : undefined}
                    badgeTone={
                      badgeVal == null ? "neutral" : badgeVal < 0 ? "bad" : "ok"
                    }
                  >
                    <MobileMetricGrid
                      columns={2}
                      items={metricCols.map((c) => {
                        const isDev = isDeviationCol(c);
                        const num = isDev
                          ? parseSortableNumber(row[c] ?? row[`${c}__label`])
                          : null;
                        return {
                          label: c.length > 28 ? `${c.slice(0, 26)}…` : c,
                          value: cellDisplay(row, c),
                          className: isDev ? deviationClass(num) : undefined,
                          highlight: isDev ? highlightFromDays(num) : "none",
                        };
                      })}
                    />
                  </MobileEntityCard>
                );
              })}
            </MobileCardStack>
            <div className="hidden max-h-[32rem] w-full min-w-0 max-w-full overflow-x-auto overflow-y-auto lg:block">
              <table
                className="bi-sticky-head bi-sticky-col w-max min-w-full border-separate border-spacing-0 text-sm"
                style={{
                  width: "100%",
                  border: dark ? "1px solid #334155" : "1px solid #d1d5db",
                }}
              >
                <thead>
                  <tr>
                    {columns.map((c) => (
                      <SortHeader
                        key={c}
                        label={c}
                        sortKey={c}
                        sort={sort}
                        onSort={onSort}
                        dark={dark}
                      />
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {sortedRows.map((row, i) => (
                    <tr key={i} className="bi-row-alt">
                      {columns.map((c, colIdx) => {
                        const isDev = isDeviationCol(c);
                        const isId = isIdentityCol(c);
                        const stickyCol = colIdx === 0;
                        const num = isDev
                          ? parseSortableNumber(row[c] ?? row[`${c}__label`])
                          : isId && badgeCol
                            ? parseSortableNumber(row[badgeCol] ?? row[`${badgeCol}__label`])
                            : null;
                        const label = cellDisplay(row, c);
                        const tint =
                          isDev || isId
                            ? deviationCellStyle(
                                num,
                                vmaxByCol[isDev ? c : badgeCol] ?? 1,
                                dark,
                                stickyCol || isId ? { opaque: true } : undefined,
                              )
                            : { className: "", style: undefined as CSSProperties | undefined };
                        const stickyTone =
                          stickyCol && num != null && !Number.isNaN(num)
                            ? num > 0
                              ? "bi-row-ahead"
                              : num < 0
                                ? "bi-row-overdue"
                                : ""
                            : "";
                        const cellBorder = dark
                          ? "1px solid #334155"
                          : "1px solid #e5e7eb";
                        const zebra =
                          !tint.style &&
                          (i % 2 === 0
                            ? dark
                              ? "#111827"
                              : "#ffffff"
                            : dark
                              ? "#0f172a"
                              : "#fafafa");
                        const solidBg =
                          (tint.style?.backgroundColor as string | undefined) ||
                          zebra ||
                          (dark ? "#111827" : "#ffffff");
                        return (
                          <td
                            key={c}
                            className={`${TD} ${tint.className} ${stickyTone} ${
                              isDev || (isId && badgeCol) ? "bi-num" : ""
                            } ${
                              isDev && !tint.style ? deviationClass(num) : ""
                            }`}
                            style={
                              stickyCol
                                ? {
                                    border: cellBorder,
                                    backgroundColor: solidBg,
                                    color: tint.style?.color,
                                    position: "sticky",
                                    left: 0,
                                    zIndex: 2,
                                    backgroundClip: "padding-box",
                                    boxShadow: dark
                                      ? "6px 0 8px -6px rgba(0,0,0,0.55)"
                                      : "6px 0 8px -6px rgba(15,23,42,0.28)",
                                  }
                                : {
                                    border: cellBorder,
                                    backgroundColor: zebra || undefined,
                                    ...(tint.style ?? {}),
                                  }
                            }
                          >
                            {label}
                          </td>
                        );
                      })}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </>
        )}
        <div className="border-t border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
          <DownloadTableButton
            getTable={exportTable}
            fileStem={fileStem}
            disabled={!sortedRows.length}
          />
        </div>
      </Card>
    </FullscreenPanel>
  );
}

export function WorkingDocumentationView() {
  const [tab, setTab] = useState<TabId>("main");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState(INITIAL);
  const [data, setData] = useState<WorkingDocumentationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const allStatuses = data?.filters.statuses ?? [];
    const statusParam =
      filters.statuses.length &&
      allStatuses.length &&
      filters.statuses.length !== allStatuses.length
        ? filters.statuses.join("|")
        : undefined;
    const q: WorkingDocumentationQuery = {
      projects: filters.projects,
      section: joinMulti(filters.sections),
      status: statusParam,
      period_mode: filters.periodMode,
      date_from: filters.dateFrom || undefined,
      date_to: filters.dateTo || undefined,
      metric_mode: filters.metricMode,
      show_forecast: filters.showForecast,
      view_mode: filters.viewMode,
      tab,
    };
    setLoading(true);
    fetchWorkingDocumentation(q)
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setError(payload.meta.error || null);
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    tab,
    filters.projects,
    filters.sections,
    filters.statuses,
    filters.periodMode,
    filters.dateFrom,
    filters.dateTo,
    filters.metricMode,
    filters.showForecast,
    filters.viewMode,
  ]);

  const kpis = data?.kpis;
  const statusMix = data?.tremor.status_mix ?? [];
  const dynamics = data?.tremor.dynamics ?? [];
  const monthly = data?.tremor.monthly ?? [];
  const mobile = useIsMobileViewport();
  const issuedProduction =
    kpis?.issued_production ??
    statusMix.find((s) => /производств/i.test(s.name))?.value ??
    null;
  const notIssued =
    kpis?.not_issued ??
    (kpis?.total_sections != null && issuedProduction != null
      ? Math.max(0, Number(kpis.total_sections) - Number(issuedProduction))
      : null);

  const resetFilters = () => {
    setFilters({
      ...INITIAL,
    });
  };

  useUrlFilterState(
    filters, INITIAL,
    (patch) => setFilters((f) => ({ ...f, ...patch })),
    { navId: "working-documentation" },
  );

  const viewModeLabel = (id: string) =>
    (data?.filters.view_modes ?? []).find((m) => m.id === id)?.label ?? id;
  const activeFilters = buildFilterChips(
    filters,
    INITIAL,
    [
      { key: "projects", name: "Проект" },
      { key: "sections", name: "Раздел" },
      { key: "statuses", name: "Статус" },
      { key: "periodMode", name: "Период" },
      { key: "dateFrom", name: "С", kind: "date" },
      { key: "dateTo", name: "По", kind: "date" },
      { key: "metricMode", name: "Метрика" },
      { key: "showForecast", name: "Прогноз", kind: "flag" },
      { key: "viewMode", name: "Отображение", label: viewModeLabel },
    ],
    (patch) => setFilters((f) => ({ ...f, ...patch })),
  );

  return (
    <AppShell title="Рабочая документация" loading={loading}>
      <div className="mb-4 flex gap-4 border-b border-tremor-border dark:border-dark-tremor-border">
        {(
          [
            ["main", "Рабочая документация"],
            ["delay", "Просрочка выдачи РД"],
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

      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((v) => !v)}
        title={tab === "main" ? "План выдачи РД — фильтры" : "Фильтры"}
        activeFilters={activeFilters}
        onReset={activeFilters.length ? resetFilters : undefined}
      >
        <FiltersReset onClick={resetFilters} />
        <FilterChipMulti label="Проект" values={filters.projects} options={data?.filters.projects ?? []} onChange={(projects) => setFilters((f) => ({ ...f, projects }))} />
        <FilterFieldsRow cols={3}>
          <FilterChipMulti label="Раздел" options={data?.filters.sections ?? []} values={filters.sections} onChange={(sections) => setFilters((f) => ({ ...f, sections }))} />
          <FilterChipSelect label="Период" value={filters.periodMode} options={data?.filters.period_modes ?? [INITIAL.periodMode]} onChange={(periodMode) => setFilters((f) => ({ ...f, periodMode }))} />
          <FilterChipMulti label="Статус" options={data?.filters.statuses ?? []} values={filters.statuses} onChange={(statuses) => setFilters((f) => ({ ...f, statuses }))} />
        </FilterFieldsRow>
        {filters.periodMode !== "Весь период (за всё время)" ? (
          <FilterFieldsRow cols={3}>
            <FilterField label="С">
              <input
                type="date"
                className={FILTER_SELECT_CLASS}
                value={filters.dateFrom}
                min={data?.filters.plan_date_min ?? undefined}
                max={data?.filters.plan_date_max ?? undefined}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, dateFrom: e.target.value }))
                }
              />
            </FilterField>
            <FilterField label="По">
              <input
                type="date"
                className={FILTER_SELECT_CLASS}
                value={filters.dateTo}
                min={data?.filters.plan_date_min ?? undefined}
                max={data?.filters.plan_date_max ?? undefined}
                onChange={(e) =>
                  setFilters((f) => ({ ...f, dateTo: e.target.value }))
                }
              />
            </FilterField>
            <div />
          </FilterFieldsRow>
        ) : null}
        {tab === "delay" ? (
          <FilterFieldsRow cols={3}>
            <FilterChipSelect label="Отображение" value={filters.viewMode} options={(data?.filters.view_modes ?? []).map((item) => ({ value: item.id, label: item.label }))} onChange={(viewMode) => setFilters((f) => ({ ...f, viewMode }))} />
            <div />
            <div />
          </FilterFieldsRow>
        ) : null}
        <FilterChipSelect label="Метрика" value={filters.metricMode} options={data?.filters.metric_modes ?? ["Количество разделов", "% от общего объёма"]} onChange={(metricMode) => setFilters((f) => ({ ...f, metricMode }))} />
        <FilterChecksRow cols={3}>
          <FilterCheck
            label="Показать прогнозную дату выдачи разделов"
            checked={filters.showForecast}
            onChange={(e) =>
              setFilters((f) => ({ ...f, showForecast: e.target.checked }))
            }
          />
          <div />
          <div />
        </FilterChecksRow>
      </FiltersCard>

      {error ? (
        <Card className="mb-4 border-rose-300 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
          {error}
        </Card>
      ) : null}
      {loading && !data ? (
        <Text>Загрузка…</Text>
      ) : (
        <>
          <DashboardInsight
            text={
              kpis?.total_sections != null
                ? `Всего разделов ${fmtNum(kpis.total_sections)} · выдано ${fmtNum(issuedProduction)} · не выдано ${fmtNum(notIssued)}${
                    kpis.overdue != null ? ` · просрочено ${fmtNum(kpis.overdue)}` : ""
                  }${
                    kpis.deviation_to_date != null
                      ? ` · отклонение на дату ${fmtSigned(kpis.deviation_to_date)}`
                      : ""
                  }`
                : null
            }
          />
          <Grid numItemsSm={1} numItemsMd={3} className="mb-6 gap-4">
            <Card className="rounded-xl">
              <Text className="leading-snug">Всего разделов</Text>
              <Metric className="mt-1">{fmtNum(kpis?.total_sections)}</Metric>
            </Card>
            <Card className="rounded-xl">
              <Text className="leading-snug">
                {mobile ? "Выдано в пр-во" : "Выдано в производство работ"}
              </Text>
              <Metric className="mt-1">{fmtNum(issuedProduction)}</Metric>
            </Card>
            <Card className="rounded-xl">
              <Text className="leading-snug">
                {mobile ? "Не выдано (всего − выдано)" : "Не выдано (всего − выдано в пр-во)"}
              </Text>
              <Metric className="mt-1">{fmtNum(notIssued)}</Metric>
            </Card>
          </Grid>

          {tab === "main" ? (
            <>
              <FullscreenPanel fill className="mb-6" disabled={!statusMix.length}>
                {(zoomed) => (
                  <Card className="rounded-xl">
                    <Title>Исполнение РД</Title>
                    <div className="mt-4">
                      <RdExecutionPieChart rows={statusMix} fullscreen={zoomed} />
                    </div>
                    {statusMix.length ? (
                      <div className="mt-3 flex flex-wrap gap-3 text-xs text-tremor-content dark:text-dark-tremor-content">
                        {statusMix.map((s) => (
                          <span key={s.name} className="inline-flex items-center gap-1.5">
                            <span
                              className="inline-block h-2.5 w-2.5 rounded-sm"
                              style={{ backgroundColor: s.color || "#7F8C8D" }}
                            />
                            {s.name}: {fmtNum(s.value)}
                          </span>
                        ))}
                      </div>
                    ) : null}
                  </Card>
                )}
              </FullscreenPanel>

              <FullscreenPanel fill className="mb-6" disabled={!monthly.length}>
                {(zoomed) => (
                  <Card className="rounded-xl">
                    <Title>Динамика по месяцам</Title>
                    <Text className="mt-1 text-xs text-tremor-content dark:text-dark-tremor-content">
                      Накопительно: жёлтый — план на дату месяца, зелёный — факт.
                      Справа «+N» — разделы, выданные в производство за этот месяц.
                    </Text>
                    <div className="mt-3">
                      <RdMonthlyCumulativeChart rows={monthly} fullscreen={zoomed} />
                    </div>
                  </Card>
                )}
              </FullscreenPanel>

              <Card className="mb-6 rounded-xl">
                <Title className="mb-4">Динамика выдачи РД</Title>
                <Grid numItemsSm={2} numItemsMd={4} className="mb-4 gap-3">
                  <div>
                    <Text>План по проекту</Text>
                    <Metric className="text-2xl">{fmtNum(kpis?.plan_total)}</Metric>
                  </div>
                  <div>
                    <Text>План на текущую дату</Text>
                    <Metric className="text-2xl">{fmtNum(kpis?.plan_to_date)}</Metric>
                  </div>
                  <div>
                    <Text>Факт на текущую дату</Text>
                    <Metric className="text-2xl">{fmtNum(kpis?.fact_to_date)}</Metric>
                  </div>
                  <div>
                    <Text>Отклонение на текущую дату</Text>
                    <Metric
                      className={`text-2xl ${
                        (kpis?.deviation_to_date ?? 0) < 0
                          ? "font-semibold text-[hsl(348,100%,45%)] dark:text-[#ff5454]"
                          : "font-semibold text-[#15803d] dark:text-[#46d68a]"
                      }`}
                    >
                      {fmtSigned(kpis?.deviation_to_date)}
                    </Metric>
                  </div>
                </Grid>
                <Grid numItemsSm={1} numItemsMd={3} className="mb-4 gap-3">
                  <div>
                    <Text>Плановая производительность / нед.</Text>
                    <p className="text-lg font-semibold">
                      {kpis?.planned_weekly != null ? fmtNum(kpis.planned_weekly, 1) : "—"}
                    </p>
                  </div>
                  <div>
                    <Text>Фактическая производительность / нед.</Text>
                    <p className="text-lg font-semibold">
                      {kpis?.fact_weekly != null ? fmtNum(kpis.fact_weekly, 1) : "—"}
                    </p>
                  </div>
                  <div>
                    <Text>Необходимая производительность / нед.</Text>
                    <p className="text-lg font-semibold">
                      {kpis?.nec_weekly != null ? fmtNum(kpis.nec_weekly, 1) : "—"}
                    </p>
                  </div>
                </Grid>
                <FullscreenPanel fill disabled={!dynamics.length}>
                  {(zoomed) => (
                    <div className="mt-2">
                      <RdDynamicsLineChart
                        rows={dynamics}
                        fullscreen={zoomed}
                        showForecast={filters.showForecast}
                      />
                    </div>
                  )}
                </FullscreenPanel>
              </Card>

              <Title className="mb-3">Детальная таблица</Title>
              <DetailTable
                columns={data?.detail_columns ?? []}
                rows={data?.detail_rows ?? []}
                fileStem="rd_detail"
                onReset={activeFilters.length ? resetFilters : undefined}
              />
            </>
          ) : (
            <>
              <FullscreenPanel
                fill
                className="mb-6"
                disabled={!(data?.delay.gantt.rows.length ?? 0)}
              >
                {(zoomed) => (
                  <Card className="rounded-xl">
                    <Title>График Просрочка выдачи РД</Title>
                    <div className="mt-4">
                      <RdDelayGanttChart
                        rows={data?.delay.gantt.rows ?? []}
                        rangeStart={data?.delay.gantt.range_start ?? null}
                        rangeEnd={data?.delay.gantt.range_end ?? null}
                        fullscreen={zoomed}
                        hideProjectPrefix={isSingleProjectSelection(filters.projects)}
                      />
                    </div>
                  </Card>
                )}
              </FullscreenPanel>

              <FullscreenPanel fill className="mb-6" disabled={!monthly.length}>
                {(zoomed) => (
                  <Card className="rounded-xl">
                    <Title>Динамика по месяцам</Title>
                    <Text className="mt-1 text-xs text-tremor-content dark:text-dark-tremor-content">
                      Накопительно: жёлтый — план на дату месяца, зелёный — факт.
                      Справа «+N» — разделы, выданные в производство за этот месяц.
                    </Text>
                    <div className="mt-3">
                      <RdMonthlyCumulativeChart rows={monthly} fullscreen={zoomed} />
                    </div>
                  </Card>
                )}
              </FullscreenPanel>

              <Title className="mb-3">Детальная таблица</Title>
              <DetailTable
                columns={data?.delay.detail_columns ?? data?.detail_columns ?? []}
                rows={data?.delay.detail_rows ?? data?.detail_rows ?? []}
                fileStem="rd_delay_detail"
                onReset={activeFilters.length ? resetFilters : undefined}
              />
            </>
          )}
        </>
      )}
    </AppShell>
  );
}
