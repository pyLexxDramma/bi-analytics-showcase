"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import {
  fetchBaselineDeviation,
  type BaselineDeviationPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { BaselineDeviationChart } from "@/components/baseline-deviation-chart";
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
  const selectClass =
    "mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background";

  const showReasons = data?.filters.applied.show_reasons ?? filters.showReasons;
  const showDur = data?.filters.applied.show_dur ?? filters.showDur;
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
  const metaError = data?.meta?.error as string | undefined;
  const plates = data?.kpis.plates ?? [];
  const tableTitle = showReasons
    ? "Причины отклонений (таблица)"
    : "Отклонение от базового плана (таблица)";

  return (
    <AppShell title="Отклонение от базового плана">
      <Card className="mb-6 rounded-xl">
        <button
          type="button"
          onClick={() => setFiltersOpen((value) => !value)}
          aria-expanded={filtersOpen}
          className="flex w-full items-center gap-2 text-left text-sm font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong"
        >
          <span className="text-xs">{filtersOpen ? "▾" : "▸"}</span>
          Фильтры
        </button>
        {filtersOpen ? (
          <div className="mt-3 space-y-4">
            <button
              type="button"
              disabled={!dirty}
              onClick={() => setFilters(INITIAL)}
              className="rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-1.5 text-sm disabled:opacity-40 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            >
              Сбросить
            </button>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-5">
              <label className="block text-sm">
                <Text>Проект</Text>
                <select
                  className={selectClass}
                  value={filters.project}
                  onChange={(event) =>
                    setFilters((prev) => ({
                      ...prev,
                      project: event.target.value,
                      building: "Все",
                    }))
                  }
                >
                  {(data?.filters.projects ?? ["Все"]).map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <Text>Функциональный блок</Text>
                <select
                  className={selectClass}
                  value={filters.block}
                  onChange={(event) =>
                    setFilters((prev) => ({
                      ...prev,
                      block: event.target.value,
                      building: "Все",
                    }))
                  }
                >
                  {(data?.filters.blocks ?? ["Все"]).map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <Text>Строение</Text>
                <select
                  className={selectClass}
                  value={filters.building}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, building: event.target.value }))
                  }
                >
                  {(data?.filters.buildings ?? ["Все"]).map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <Text>Детализация</Text>
                <select
                  className={selectClass}
                  value={filters.level}
                  disabled={
                    Boolean(data?.filters.applied.level_skipped) ||
                    filters.showReasons ||
                    filters.onlyCovenants
                  }
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, level: event.target.value }))
                  }
                >
                  {(data?.filters.levels ?? []).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <Text>Причина отклонения (категория)</Text>
                <select
                  className={selectClass}
                  value={filters.reason}
                  disabled={filters.onlyCovenants || (data?.filters.reasons.length ?? 1) <= 1}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, reason: event.target.value }))
                  }
                >
                  {(data?.filters.reasons ?? ["Все"]).map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={filters.showReasons}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, showReasons: event.target.checked }))
                  }
                />
                <Text>Показать причины отклонений</Text>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={filters.hideCompleted}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, hideCompleted: event.target.checked }))
                  }
                />
                <Text>Скрыть завершённые (100%)</Text>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={filters.onlyCovenants}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, onlyCovenants: event.target.checked }))
                  }
                />
                <Text>Только ковенанты</Text>
              </label>
              <label className="flex items-center gap-2 text-sm md:col-span-2">
                <input
                  type="checkbox"
                  checked={filters.onlyNegEnd}
                  disabled={filters.showReasons}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, onlyNegEnd: event.target.checked }))
                  }
                />
                <Text>Отображать только диаграммы, где отклонение окончания &lt; 0</Text>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={filters.showDur}
                  disabled={filters.showReasons}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, showDur: event.target.checked }))
                  }
                />
                <Text>Показать «Отклонение длительности» в таблице</Text>
              </label>
            </div>
            {(data?.filters.has_lot ?? false) ? (
              <fieldset className="text-sm">
                <Text>Подписи на графике и в таблице</Text>
                <div className="mt-2 flex flex-wrap gap-4">
                  {(data?.filters.label_modes ?? []).map((mode) => (
                    <label key={mode.id} className="inline-flex items-center gap-2">
                      <input
                        type="radio"
                        name="label-mode"
                        checked={filters.labelMode === mode.id}
                        onChange={() =>
                          setFilters((prev) => ({ ...prev, labelMode: mode.id }))
                        }
                      />
                      <span>{mode.label}</span>
                    </label>
                  ))}
                </div>
              </fieldset>
            ) : null}
          </div>
        ) : null}
      </Card>

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
                        { label: "План оконч.", value: plate.plan_end ?? "Н/Д" },
                        { label: "Факт оконч.", value: plate.fact_end ?? "Н/Д" },
                        {
                          label: "Отклонение",
                          value: plate.dev ?? "Н/Д",
                          className: plateDevClass(plate.dev_days),
                        },
                        {
                          label: "Макс. |откл.|",
                          value: plate.max_abs_dev_days ?? "Н/Д",
                          className:
                            (plate.max_abs_dev_days ?? 0) > 0
                              ? "text-rose-600 dark:text-rose-400"
                              : "",
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
                <div className="pt-8">
                  <BaselineDeviationChart data={data} fullscreen={zoomed} />
                </div>
              ) : (
                <div className="py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "загрузка…" : "Нет задач для графика."}
                </div>
              )
            }
          </FullscreenPanel>
        </Card>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="flex flex-wrap items-center justify-between gap-3 border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <div>
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                {tableTitle}
              </Title>
              <Text className="mt-1">
                {loading
                  ? "загрузка…"
                  : `Записей: ${rows.length}${
                      showReasons
                        ? " · ур.5 · причина · откл. окончания < 0"
                        : " · только откл. окончания < 0"
                    }`}
              </Text>
            </div>
          </div>
          <FullscreenPanel
            disabled={rows.length === 0}
            className="!overflow-x-hidden"
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
                                  },
                                  {
                                    label: "Базовое",
                                    value: row.base_end ?? "—",
                                  },
                                  {
                                    label: "Откл.",
                                    value:
                                      row.dev_end_days ?? row.dev_end ?? "—",
                                    className: deviationClass(row.dev_end_days),
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
                                  },
                                  {
                                    label: "Баз. нач.",
                                    value: row.base_start ?? "—",
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
                                  },
                                  {
                                    label: "Окончание",
                                    value: row.plan_end ?? "—",
                                  },
                                  {
                                    label: "Баз. оконч.",
                                    value: row.base_end ?? "—",
                                  },
                                  {
                                    label: "Откл. оконч.",
                                    value:
                                      row.dev_end_days ?? row.dev_end ?? "—",
                                    className: deviationClass(row.dev_end_days),
                                  },
                                  ...(showDur
                                    ? [
                                        {
                                          label: "Длит.",
                                          value: row.plan_dur_days ?? "—",
                                        },
                                        {
                                          label: "Баз. длит.",
                                          value: row.base_dur_days ?? "—",
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
                <div className="hidden max-h-[36rem] overflow-auto pt-8 lg:block">
                  <table className="min-w-full border-separate border-spacing-0 text-left text-xs">
                    <thead className="sticky top-0 z-20">
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
              </>
            )}
          </FullscreenPanel>
          <div className="border-t border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <DownloadTableButton getTable={() => exportTable} fileStem="baseline_deviation" />
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
