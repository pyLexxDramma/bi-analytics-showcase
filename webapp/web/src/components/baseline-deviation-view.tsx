"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import {
  fetchBaselineDeviation,
  type BaselineDeviationPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { BaselineDeviationChart } from "@/components/baseline-deviation-chart";
import {
  FilterCheck,
  FilterChipSelect,
  FilterChecksRow,
  FilterFieldsRow,
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
import type { ExportCell, ExportTable } from "@/lib/table-export";

const INITIAL = {
  project: "Все",
  block: "Все",
  building: "Все",
  level: "4",
  reason: "Все",
  showReasons: true,
  hideCompleted: false,
  onlyCovenants: false,
  onlyNegEnd: false,
  showDur: true,
  labelMode: "name",
};

const TH =
  "whitespace-nowrap border border-[#cbd5e1] bg-[#f3f4f6] px-2.5 py-2 text-center font-bold text-[#111827] dark:border-[#334155] dark:bg-[hsl(209,72%,6%)] dark:text-[#fafafa]";
const TD =
  "border border-[#cbd5e1] px-2.5 py-1.5 text-center align-middle dark:border-[#334155]";
const DATE_BG = "bg-[rgba(156,194,229,0.28)] dark:bg-[rgba(214,234,248,0.14)]";
// Липкая шапка не должна просвечивать: тон кладём слоем поверх непрозрачного фона TH.
const DATE_BG_HEAD =
  "bg-[linear-gradient(rgba(156,194,229,0.28),rgba(156,194,229,0.28))] dark:bg-[linear-gradient(rgba(214,234,248,0.14),rgba(214,234,248,0.14))]";
const DATE_COLS = new Set([
  "Окончание",
  "Базовое окончание",
  "Отклонение",
  "Базовое начало",
  "Начало",
  "Откл. начала",
  "Откл. окончания",
  "Длительность",
  "Баз. длит.",
  "Откл. длит.",
]);

type Row = BaselineDeviationPayload["rows"][number] & { _index: number };
type SortState = { key: string; asc: boolean } | null;

function deviationClass(days: number | null | undefined): string {
  if (days == null) return "";
  if (days < 0) return "font-bold text-[hsl(348,100%,45%)] dark:text-[#ff5454]";
  if (days === 0) return "font-bold text-[#6b7280] dark:text-[#8899aa]";
  return "font-bold text-[#15803d] dark:text-[#46d68a]";
}

function plateDevClass(days: number | null | undefined): string {
  if (days == null) return "";
  if (days < 0) return "text-rose-600 dark:text-rose-400";
  if (days === 0) return "text-emerald-600 dark:text-emerald-400";
  return "";
}

function highlightFromDays(
  days: number | null | undefined,
): "none" | "bad" | "ok" {
  if (days == null) return "none";
  if (days < 0) return "bad";
  return "ok";
}

function cellValue(row: Row, col: string): string | number {
  switch (col) {
    case "ID задачи":
      return row.task_id ?? "";
    case "Проект":
      return row.project ?? "";
    case "Функциональный блок":
    case "Функц. блок":
      return row.block ?? "";
    case "Название":
    case "Задача":
      return row.task ?? "";
    case "Строение":
      return row.building ?? "";
    case "Окончание":
      return row.plan_end ?? "";
    case "Базовое окончание":
      return row.base_end ?? "";
    case "Отклонение":
    case "Откл. окончания":
      return row.dev_end_days ?? row.dev_end ?? "";
    case "Причина отклонения":
      return row.reason ?? "";
    case "Заметки":
      return row.notes ?? "";
    case "Базовое начало":
      return row.base_start ?? "";
    case "Начало":
      return row.plan_start ?? "";
    case "Откл. начала":
      return row.dev_start_days ?? row.dev_start ?? "";
    case "Длительность":
      return row.plan_dur_days ?? "";
    case "Баз. длит.":
      return row.base_dur_days ?? "";
    case "Откл. длит.":
      return row.dev_dur_days ?? row.dev_dur ?? "";
    default:
      return "";
  }
}

function sortKeyForCol(col: string): string {
  const map: Record<string, string> = {
    "ID задачи": "task_id",
    Проект: "project",
    "Функциональный блок": "block",
    "Функц. блок": "block",
    Название: "task",
    Задача: "task",
    Строение: "building",
    Окончание: "plan_end",
    "Базовое окончание": "base_end",
    Отклонение: "dev_end_days",
    "Откл. окончания": "dev_end_days",
    "Причина отклонения": "reason",
    Заметки: "notes",
    "Базовое начало": "base_start",
    Начало: "plan_start",
    "Откл. начала": "dev_start_days",
    Длительность: "plan_dur_days",
    "Баз. длит.": "base_dur_days",
    "Откл. длит.": "dev_dur_days",
  };
  return map[col] ?? col;
}

function compareRows(a: Row, b: Row, key: string): number {
  const av = (a as Record<string, unknown>)[key];
  const bv = (b as Record<string, unknown>)[key];
  if (av == null && bv == null) return a._index - b._index;
  if (av == null) return 1;
  if (bv == null) return -1;
  if (typeof av === "number" && typeof bv === "number") return av - bv;
  const as = String(av);
  const bs = String(bv);
  if (key.includes("end") || key.includes("start") || key.includes("plan") || key.includes("base")) {
    if (as.includes(".") && bs.includes(".")) {
      const am = Date.parse(as.split(".").reverse().join("-"));
      const bm = Date.parse(bs.split(".").reverse().join("-"));
      if (Number.isFinite(am) && Number.isFinite(bm)) return am - bm;
    }
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
  sort: SortState;
  onSort: (key: string) => void;
  tint?: boolean;
}) {
  const active = sort?.key === sortKey;
  return (
    <th className={`${TH} ${tint ? DATE_BG_HEAD : ""}`}>
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

function displayDev(row: Row, col: string): string {
  const raw = cellValue(row, col);
  if (raw === "" || raw == null) return "—";
  if (typeof raw === "number") {
    if (col.includes("Откл") || col === "Отклонение") {
      return raw > 0 ? `+${raw}` : String(raw);
    }
    return String(raw);
  }
  return String(raw) || "—";
}

function buildExport(
  columns: string[],
  rows: BaselineDeviationPayload["rows"],
): ExportTable {
  const body: ExportCell[][] = rows.map((row) =>
    columns.map((col) => {
      const indexed = { ...row, _index: 0 };
      const v = cellValue(indexed, col);
      return v === "" || v == null ? "" : v;
    }),
  );
  return { header: [columns], rows: body, sheetName: "Отклонение от БП" };
}

export function BaselineDeviationView() {
  const [filters, setFilters] = useState(INITIAL);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [data, setData] = useState<BaselineDeviationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tableSort, setTableSort] = useState<SortState>(null);
  const [fullTableOpen, setFullTableOpen] = useState(true);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchBaselineDeviation({
          project: filters.project,
          block: filters.block,
          building: filters.building,
          level: filters.level,
          reason: filters.reason,
          show_reasons: filters.showReasons,
          hide_completed: filters.hideCompleted,
          only_covenants: filters.onlyCovenants,
          only_neg_end: filters.onlyNegEnd,
          show_dur: filters.showDur,
          label_mode: filters.labelMode,
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, [filters]);

  useEffect(() => {
    void load();
  }, [load]);

  const dirty = JSON.stringify(filters) !== JSON.stringify(INITIAL);
  const showReasons = data?.filters.applied.show_reasons ?? filters.showReasons;
  const showDur = data?.filters.applied.show_dur ?? filters.showDur;
  const covenantMode =
    Boolean(data?.filters.applied.only_covenants) || data?.meta?.mode === "covenant";
  const covenantTable = data?.covenant_table;
  const covenantRows = covenantTable?.rows ?? [];
  const covenantColumns = covenantTable?.columns ?? [];
  const columns = useMemo(() => {
    if (data?.columns?.length) return data.columns;
    if (showReasons) {
      return [
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
    }
    return [
      "Проект",
      "Задача",
      "ID задачи",
      "Функц. блок",
      "Строение",
      "Базовое начало",
      "Начало",
      "Откл. начала",
      "Базовое окончание",
      "Окончание",
      "Откл. окончания",
      "Длительность",
      "Баз. длит.",
      ...(showDur ? ["Откл. длит."] : []),
    ];
  }, [data?.columns, showReasons, showDur]);

  const rows = useMemo(() => data?.rows ?? [], [data?.rows]);
  const sortedRows = useMemo(() => {
    const indexed: Row[] = rows.map((row, index) => ({ ...row, _index: index }));
    if (!tableSort) return indexed;
    return [...indexed].sort((a, b) => {
      const diff = compareRows(a, b, tableSort.key);
      return tableSort.asc ? diff : -diff;
    });
  }, [rows, tableSort]);

  const toggleSort = useCallback((key: string) => {
    setTableSort((prev) => {
      if (!prev || prev.key !== key) return { key, asc: true };
      if (prev.asc) return { key, asc: false };
      return null;
    });
  }, []);

  const exportTable = useMemo(() => buildExport(columns, rows), [columns, rows]);
  const covenantExport = useMemo((): ExportTable => {
    const cols = covenantColumns.length
      ? covenantColumns
      : ["Проект", "Задача", "ID задачи", "Базовое окончание", "Окончание", "Отклонение окончания (дней)"];
    const body: ExportCell[][] = covenantRows.map((row) =>
      cols.map((col) => {
        if (col === "Проект") return row.project ?? "";
        if (col === "Задача") return row.task ?? "";
        if (col === "ID задачи") return row.task_id ?? "";
        if (col === "Базовое окончание") return row.base_end ?? "";
        if (col === "Окончание") return row.plan_end ?? "";
        if (col === "Отклонение окончания (дней)") {
          return row.dev_end_days ?? row.dev_end ?? "";
        }
        return "";
      }),
    );
    return { header: [cols], rows: body, sheetName: "Ковенанты" };
  }, [covenantColumns, covenantRows]);
  const metaError = data?.meta?.error as string | undefined;
  const plates = data?.kpis.plates ?? [];
  const tableTitle = covenantMode
    ? "Полная таблица отклонений по всем задачам фильтра"
    : showReasons
      ? "Причины отклонений (таблица)"
      : "Отклонение от базового плана (таблица)";

  useUrlFilterState(filters, INITIAL, (patch) =>
    setFilters((prev) => ({ ...prev, ...patch })),
  );

  const levelLabel = (id: string) =>
    (data?.filters.levels ?? []).find((l) => l.id === id)?.label ?? id;
  const activeFilters = buildFilterChips(
    filters,
    INITIAL,
    [
      {
        key: "project",
        name: "Проект",
        clear: { project: "Все", building: "Все" },
      },
      { key: "block", name: "Блок", clear: { block: "Все", building: "Все" } },
      { key: "building", name: "Строение" },
      { key: "level", name: "Детализация", label: levelLabel },
      { key: "reason", name: "Причина" },
      { key: "showReasons", name: "Причины отклонений", kind: "flag" },
      { key: "hideCompleted", name: "Завершённые скрыты", kind: "flag" },
      { key: "onlyCovenants", name: "Только ковенанты", kind: "flag" },
      { key: "onlyNegEnd", name: "Только отрицательные", kind: "flag" },
      { key: "showDur", name: "Длительность", kind: "flag" },
      { key: "labelMode", name: "Подписи" },
    ],
    (patch) => setFilters((prev) => ({ ...prev, ...patch })),
  );

  return (
    <AppShell title="Отклонение от базового плана" loading={loading}>
      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((v) => !v)}
        activeFilters={activeFilters}
        onReset={dirty ? () => setFilters(INITIAL) : undefined}
      >
        <FiltersReset disabled={!dirty} onClick={() => setFilters(INITIAL)} />
        <FilterFieldsRow cols={5}>
          <FilterChipSelect label="Проект" value={filters.project} options={data?.filters.projects ?? ["Все"]} onChange={(project) => setFilters((prev) => ({ ...prev, project, building: "Все" }))} />
          <FilterChipSelect label="Функциональный блок" value={filters.block} options={data?.filters.blocks ?? ["Все"]} onChange={(block) => setFilters((prev) => ({ ...prev, block, building: "Все" }))} />
          <FilterChipSelect label="Строение" value={filters.building} options={data?.filters.buildings ?? ["Все"]} onChange={(building) => setFilters((prev) => ({ ...prev, building }))} />
          <FilterChipSelect label="Детализация" value={filters.level} options={(data?.filters.levels ?? []).map((item) => ({ value: item.id, label: item.label }))} disabled={Boolean(data?.filters.applied.level_skipped) || filters.showReasons || filters.onlyCovenants} onChange={(level) => setFilters((prev) => ({ ...prev, level }))} />
          <FilterChipSelect label="Причина отклонения (категория)" value={filters.reason} options={data?.filters.reasons ?? ["Все"]} disabled={filters.onlyCovenants || (data?.filters.reasons.length ?? 1) <= 1} onChange={(reason) => setFilters((prev) => ({ ...prev, reason }))} />
        </FilterFieldsRow>
        <FilterChecksRow cols={5}>
          <FilterCheck
            label="Показать причины отклонений"
            checked={filters.showReasons}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, showReasons: event.target.checked }))
            }
          />
          <FilterCheck
            label="Скрыть завершённые (100%)"
            checked={filters.hideCompleted}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, hideCompleted: event.target.checked }))
            }
          />
          <FilterCheck
            label="Только ковенанты"
            checked={filters.onlyCovenants}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, onlyCovenants: event.target.checked }))
            }
          />
          <FilterCheck
            label="Отображать только диаграммы, где отклонение окончания < 0"
            checked={filters.onlyNegEnd}
            disabled={filters.showReasons}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, onlyNegEnd: event.target.checked }))
            }
          />
          <FilterCheck
            label="Показать «Отклонение длительности» в таблице"
            checked={filters.showDur}
            disabled={filters.showReasons}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, showDur: event.target.checked }))
            }
          />
        </FilterChecksRow>
        {(data?.filters.has_lot ?? false) ? (
          <FilterChipSelect label="Подписи на графике и в таблице" value={filters.labelMode} options={(data?.filters.label_modes ?? []).map((item) => ({ value: item.id, label: item.label }))} onChange={(labelMode) => setFilters((prev) => ({ ...prev, labelMode }))} />
        ) : null}
      </FiltersCard>

      {error || metaError ? (
        <Card className="mb-6 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            {error ?? metaError}
          </Text>
        </Card>
      ) : null}

      <div className="space-y-6">
        <div>
          <Title className="mb-3 !text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            {data?.kpis.metric_task ?? "ЗОС"}
          </Title>
          {loading && !data ? (
            <Text>загрузка…</Text>
          ) : plates.length === 0 ? (
            <Text>Нет данных для плашек KPI.</Text>
          ) : (
            <>
              <MobileCardStack>
                {plates.map((plate, index) => (
                  <MobileEntityCard
                    key={`m-${plate.project ?? "one"}-${index}`}
                    title={plate.project || data?.kpis.metric_task || "ЗОС"}
                    badge={plate.dev ?? undefined}
                    badgeTone={
                      plate.dev_days == null
                        ? "neutral"
                        : plate.dev_days < 0
                          ? "bad"
                          : "ok"
                    }
                  >
                    <MobileMetricGrid
                      columns={2}
                      items={[
                        {
                          label: "План оконч.",
                          value: plate.plan_end ?? "Н/Д",
                          highlight: "date",
                        },
                        {
                          label: "Факт оконч.",
                          value: plate.fact_end ?? "Н/Д",
                          highlight: "date",
                        },
                        {
                          label: "Отклонение",
                          value: plate.dev ?? "Н/Д",
                          className: plateDevClass(plate.dev_days),
                          highlight: highlightFromDays(plate.dev_days),
                        },
                        {
                          label: "Макс. |откл.|",
                          value: plate.max_abs_dev_days ?? "Н/Д",
                          className:
                            (plate.max_abs_dev_days ?? 0) > 0
                              ? "text-rose-600 dark:text-rose-400"
                              : "",
                          highlight:
                            (plate.max_abs_dev_days ?? 0) > 0 ? "bad" : "none",
                        },
                      ]}
                    />
                  </MobileEntityCard>
                ))}
              </MobileCardStack>
              <div className="hidden space-y-2 lg:block">
                {plates.map((plate, index) => (
                  <div
                    key={`${plate.project ?? "one"}-${index}`}
                    className="grid gap-2 rounded-lg border border-tremor-border bg-tremor-background px-3 py-2.5 dark:border-dark-tremor-border dark:bg-dark-tremor-background md:grid-cols-2 xl:grid-cols-5"
                  >
                    {plate.project ? (
                      <div>
                        <Text className="!text-xs">Проект</Text>
                        <p className="mt-0.5 text-base font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong">
                          {plate.project}
                        </p>
                      </div>
                    ) : null}
                    <div>
                      <Text className="!text-xs">План окончания проекта</Text>
                      <p className="mt-0.5 text-xl font-bold tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                        {plate.plan_end ?? "Н/Д"}
                      </p>
                    </div>
                    <div>
                      <Text className="!text-xs">Факт окончания проекта</Text>
                      <p className="mt-0.5 text-xl font-bold tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                        {plate.fact_end ?? "Н/Д"}
                      </p>
                    </div>
                    <div>
                      <Text className="!text-xs">Отклонение</Text>
                      <p
                        className={`mt-0.5 text-xl font-bold tabular-nums ${plateDevClass(plate.dev_days)}`}
                      >
                        {plate.dev ?? "Н/Д"}
                      </p>
                    </div>
                    <div>
                      <Text className="!text-xs">Максимальное отклонение (дней)</Text>
                      <p
                        className={`mt-0.5 text-xl font-bold tabular-nums ${
                          (plate.max_abs_dev_days ?? 0) > 0
                            ? "text-rose-600 dark:text-rose-400"
                            : ""
                        }`}
                      >
                        {plate.max_abs_dev_days ?? "Н/Д"}
                      </p>
                    </div>
                  </div>
                ))}
              </div>
            </>
          )}
        </div>

        <Card className="rounded-xl">
          <FullscreenPanel fill disabled={(data?.chart.rows.length ?? 0) === 0}>
            {(zoomed) =>
              data && (data.chart.rows.length ?? 0) > 0 ? (
                <BaselineDeviationChart data={data} fullscreen={zoomed} />
              ) : (
                <div className="py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "загрузка…" : "Нет задач для графика."}
                </div>
              )
            }
          </FullscreenPanel>
        </Card>

        {covenantMode ? (
          <Card className="overflow-hidden rounded-xl p-0">
            <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Ковенанты (таблица)
              </Title>
              <Text className="mt-1">
                {loading ? "загрузка…" : `Записей: ${covenantRows.length}`}
              </Text>
            </div>
            <FullscreenPanel disabled={!covenantRows.length} scroll={false}>
              {covenantRows.length === 0 ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  Нет строк для таблицы ковенантов.
                </div>
              ) : (
                <>
                  <MobileCardStack>
                    {covenantRows.map((row, index) => (
                      <MobileEntityCard
                        key={`cov-m-${row.project ?? ""}-${row.task_id ?? row.task}-${index}`}
                        title={
                          row.project ? `${row.project}: ${row.task}` : row.task
                        }
                        badge={row.dev_end_days ?? row.dev_end ?? undefined}
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
                            ...(row.project
                              ? [{ label: "Проект", value: row.project }]
                              : []),
                            { label: "ID", value: row.task_id ?? "—" },
                            {
                              label: "Базовое оконч.",
                              value: row.base_end ?? "—",
                              highlight: "date" as const,
                            },
                            {
                              label: "Окончание",
                              value: row.plan_end ?? "—",
                              highlight: "date" as const,
                            },
                            {
                              label: "Откл. оконч.",
                              value: row.dev_end_days ?? row.dev_end ?? "—",
                              className: deviationClass(row.dev_end_days),
                              highlight: highlightFromDays(row.dev_end_days),
                            },
                          ]}
                        />
                      </MobileEntityCard>
                    ))}
                  </MobileCardStack>
                  <div className="hidden lg:block">
                    <div className="bi-table-scroll">
                    <table className="bi-sticky-head bi-sticky-col min-w-full border-separate border-spacing-0 text-left text-xs">
                      <thead>
                        <tr>
                          {covenantColumns.map((label) => (
                            <th
                              key={label}
                              className={`${TH} ${
                                label.includes("окончание") ||
                                label.includes("Отклонение") ||
                                label === "Окончание" ||
                                label === "Базовое окончание"
                                  ? DATE_BG_HEAD
                                  : ""
                              }`}
                            >
                              {label}
                            </th>
                          ))}
                        </tr>
                      </thead>
                      <tbody>
                        {covenantRows.map((row, index) => (
                          <tr
                            key={`cov-${row.project ?? ""}-${row.task_id ?? row.task}-${index}`}
                          >
                            {covenantColumns.map((col) => {
                              const tint =
                                col === "Базовое окончание" ||
                                col === "Окончание" ||
                                col === "Отклонение окончания (дней)";
                              const isDev = col === "Отклонение окончания (дней)";
                              const value =
                                col === "Проект"
                                  ? (row.project ?? "")
                                  : col === "Задача"
                                    ? row.task
                                    : col === "ID задачи"
                                      ? (row.task_id ?? "")
                                      : col === "Базовое окончание"
                                        ? (row.base_end ?? "")
                                        : col === "Окончание"
                                          ? (row.plan_end ?? "")
                                          : (row.dev_end_days ??
                                            row.dev_end ??
                                            "");
                              return (
                                <td
                                  key={col}
                                  className={`${TD} ${tint ? DATE_BG : ""} ${
                                    isDev ? deviationClass(row.dev_end_days) : ""
                                  } tabular-nums`}
                                >
                                  {value === "" || value == null ? "" : value}
                                </td>
                              );
                            })}
                          </tr>
                        ))}
                      </tbody>
                    </table>
                    </div>
                  </div>
                </>
              )}
            </FullscreenPanel>
            <div className="border-t border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
              <DownloadTableButton
                getTable={() => covenantExport}
                fileStem="covenants_baseline_deviation"
              />
            </div>
          </Card>
        ) : null}

        <Card className="overflow-hidden rounded-xl p-0">
          <button
            type="button"
            onClick={() => {
              if (covenantMode) setFullTableOpen((v) => !v);
            }}
            className={`flex w-full flex-wrap items-center justify-between gap-3 border-b border-tremor-border px-4 py-3 text-left dark:border-dark-tremor-border ${
              covenantMode ? "cursor-pointer" : "cursor-default"
            }`}
            aria-expanded={covenantMode ? fullTableOpen : true}
          >
            <div>
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                {covenantMode ? (
                  <span className="inline-flex items-center gap-2">
                    <span className="text-xs">{fullTableOpen ? "▾" : "▸"}</span>
                    {tableTitle}
                  </span>
                ) : (
                  tableTitle
                )}
              </Title>
              <Text className="mt-1">
                {loading
                  ? "загрузка…"
                  : `Записей: ${rows.length}${
                      covenantMode
                        ? ""
                        : showReasons
                          ? " · ур.5 · причина · откл. окончания < 0"
                          : " · только откл. окончания < 0"
                    }`}
              </Text>
            </div>
          </button>
          {(!covenantMode || fullTableOpen) ? (
            <>
          <FullscreenPanel
            disabled={rows.length === 0}
            scroll={false}
          >
            {rows.length === 0 ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                Нет строк по выбранным фильтрам.
              </div>
            ) : (
              <>
                <MobileCardStack>
                  {sortedRows.map((row) => {
                    const title =
                      row.project && row.task
                        ? `${row.project}: ${row.task}`
                        : (row.task ?? row.project ?? "—");
                    const badge =
                      row.dev_end_days != null
                        ? row.dev_end_days
                        : row.dev_end || undefined;
                    return (
                      <MobileEntityCard
                        key={`m-${row.project}-${row.task_id ?? row.task}-${row._index}`}
                        title={title}
                        badge={badge}
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
                          items={
                            showReasons
                              ? [
                                  { label: "ID", value: row.task_id ?? "—" },
                                  { label: "Блок", value: row.block ?? "—" },
                                  {
                                    label: "Строение",
                                    value: row.building ?? "—",
                                  },
                                  {
                                    label: "Окончание",
                                    value: row.plan_end ?? "—",
                                    highlight: "date",
                                  },
                                  {
                                    label: "Базовое",
                                    value: row.base_end ?? "—",
                                    highlight: "date",
                                  },
                                  {
                                    label: "Откл.",
                                    value:
                                      row.dev_end_days ?? row.dev_end ?? "—",
                                    className: deviationClass(row.dev_end_days),
                                    highlight: highlightFromDays(
                                      row.dev_end_days,
                                    ),
                                  },
                                  {
                                    label: "Причина",
                                    value: row.reason || "—",
                                  },
                                  {
                                    label: "Заметки",
                                    value: row.notes || "—",
                                  },
                                ]
                              : [
                                  { label: "ID", value: row.task_id ?? "—" },
                                  {
                                    label: "Начало",
                                    value: row.plan_start ?? "—",
                                    highlight: "date",
                                  },
                                  {
                                    label: "Баз. нач.",
                                    value: row.base_start ?? "—",
                                    highlight: "date",
                                  },
                                  {
                                    label: "Откл. нач.",
                                    value:
                                      row.dev_start_days ??
                                      row.dev_start ??
                                      "—",
                                    className: deviationClass(
                                      row.dev_start_days,
                                    ),
                                    highlight: highlightFromDays(
                                      row.dev_start_days,
                                    ),
                                  },
                                  {
                                    label: "Окончание",
                                    value: row.plan_end ?? "—",
                                    highlight: "date",
                                  },
                                  {
                                    label: "Баз. оконч.",
                                    value: row.base_end ?? "—",
                                    highlight: "date",
                                  },
                                  {
                                    label: "Откл. оконч.",
                                    value:
                                      row.dev_end_days ?? row.dev_end ?? "—",
                                    className: deviationClass(row.dev_end_days),
                                    highlight: highlightFromDays(
                                      row.dev_end_days,
                                    ),
                                  },
                                  ...(showDur
                                    ? [
                                        {
                                          label: "Длит.",
                                          value: row.plan_dur_days ?? "—",
                                          highlight: "date" as const,
                                        },
                                        {
                                          label: "Баз. длит.",
                                          value: row.base_dur_days ?? "—",
                                          highlight: "date" as const,
                                        },
                                        {
                                          label: "Откл. длит.",
                                          value:
                                            row.dev_dur_days ??
                                            row.dev_dur ??
                                            "—",
                                          className: deviationClass(
                                            row.dev_dur_days,
                                          ),
                                          highlight: highlightFromDays(
                                            row.dev_dur_days,
                                          ),
                                        },
                                      ]
                                    : []),
                                ]
                          }
                        />
                      </MobileEntityCard>
                    );
                  })}
                </MobileCardStack>
                <div className="hidden lg:block">
                  <div className="max-h-[36rem] overflow-auto">
                  <table className="bi-sticky-head bi-sticky-col min-w-full border-separate border-spacing-0 text-left text-xs">
                    <thead>
                      <tr>
                        {columns.map((label) => (
                          <SortHeader
                            key={label}
                            label={label}
                            sortKey={sortKeyForCol(label)}
                            sort={tableSort}
                            onSort={toggleSort}
                            tint={DATE_COLS.has(label)}
                          />
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedRows.map((row) => (
                        <tr
                          key={`${row.project}-${row.task_id ?? row.task}-${row._index}`}
                        >
                          {columns.map((col) => {
                            const tint = DATE_COLS.has(col);
                            const isDev =
                              col === "Отклонение" ||
                              col === "Откл. окончания" ||
                              col === "Откл. начала" ||
                              col === "Откл. длит.";
                            const days =
                              col === "Откл. начала"
                                ? row.dev_start_days
                                : col === "Откл. длит."
                                  ? row.dev_dur_days
                                  : row.dev_end_days;
                            return (
                              <td
                                key={col}
                                className={`${TD} ${tint ? DATE_BG : ""} ${
                                  isDev ? deviationClass(days) : ""
                                } tabular-nums`}
                              >
                                {displayDev(row, col)}
                              </td>
                            );
                          })}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                  </div>
                </div>
              </>
            )}
          </FullscreenPanel>
          <div className="border-t border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <DownloadTableButton getTable={() => exportTable} fileStem="baseline_deviation" />
          </div>
            </>
          ) : null}
        </Card>
      </div>
    </AppShell>
  );
}
