"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
import { Card, Text, Title } from "@tremor/react";
import {
  fetchProjectSchedule,
  type ProjectSchedulePayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  MobileCardStack,
  MobileEntityCard,
  MobileMetricGrid,
} from "@/components/mobile-entity-card";
import { ProjectScheduleGantt } from "@/components/project-schedule-gantt";
import type { ExportCell, ExportTable } from "@/lib/table-export";

const INITIAL = {
  project: "Все",
  block: "Все",
  building: "Все",
  level: "Верхний уровень",
  showReasons: false,
  showLots: false,
  labelPct: false,
  hideCompleted: false,
  onlyDelay: false,
};

type SortKey =
  | "project"
  | "task_id"
  | "level"
  | "task"
  | "pct_complete"
  | "plan_start"
  | "base_start"
  | "dev_start_days"
  | "plan_end"
  | "base_end"
  | "dev_end_days"
  | "reason"
  | "notes";

type SortState = { key: SortKey; asc: boolean } | null;
type ScheduleRow = ProjectSchedulePayload["rows"][number] & { _index: number };

const COL_SORT: Record<string, SortKey> = {
  Проект: "project",
  Лот: "task",
  ИД: "task_id",
  Ур: "level",
  "Название задачи": "task",
  "% завершения": "pct_complete",
  Начало: "plan_start",
  "Базовое начало": "base_start",
  "Отклонение начала": "dev_start_days",
  Окончание: "plan_end",
  "Базовое окончание": "base_end",
  "Отклонение окончания": "dev_end_days",
  "Причины отклонений": "reason",
  Заметки: "notes",
};

/** Как main `_plan_fact_deviation_span`: <0 красный, ≥0 зелёный. */
function deviationClass(days: number | null | undefined): string {
  if (days == null) return "";
  if (days < 0) {
    return "font-bold text-[hsl(348,100%,45%)] dark:text-[#ff6b6b]";
  }
  return "font-bold text-[#166534] dark:text-[#00e676]";
}

/** Фон ячеек дат/откл. — `_plan_fact_deviation_bg_style` (светлая). */
function tintStyle(days: number | null | undefined): CSSProperties | undefined {
  if (days == null || Number.isNaN(Number(days))) return undefined;
  const n = Number(days);
  if (n < 0) {
    const t = Math.min(Math.max(-n, 0), 365) / 365;
    return {
      backgroundColor: `rgba(248,113,113,${(0.16 + 0.24 * t).toFixed(3)})`,
    };
  }
  if (n === 0) {
    return { backgroundColor: "rgba(34,197,94,0.14)" };
  }
  const t = Math.min(Math.max(n, 0), 365) / 365;
  return {
    backgroundColor: `rgba(34,197,94,${(0.12 + 0.2 * t).toFixed(3)})`,
  };
}

const TH =
  "whitespace-nowrap border border-[#cbd5e1] bg-[#f3f4f6] px-2.5 py-2 text-center font-bold text-[#111827] dark:border-[#334155] dark:bg-[hsl(209,72%,6%)] dark:text-[#fafafa]";
const TD =
  "border border-[#cbd5e1] px-2.5 py-1.5 text-center align-middle dark:border-[#334155]";

function compareSchedule(a: ScheduleRow, b: ScheduleRow, key: SortKey): number {
  const av = a[key];
  const bv = b[key];
  if (av == null && bv == null) return a._index - b._index;
  if (av == null) return 1;
  if (bv == null) return -1;
  if (typeof av === "number" && typeof bv === "number") return av - bv;
  const as = String(av);
  const bs = String(bv);
  if (
    key === "plan_start" ||
    key === "base_start" ||
    key === "plan_end" ||
    key === "base_end"
  ) {
    const am = Date.parse(as);
    const bm = Date.parse(bs);
    if (Number.isFinite(am) && Number.isFinite(bm)) return am - bm;
  }
  return as.localeCompare(bs, "ru", { numeric: true, sensitivity: "base" });
}

function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
}: {
  label: string;
  sortKey: SortKey;
  sort: SortState;
  onSort: (key: SortKey) => void;
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

function buildExport(data: ProjectSchedulePayload): ExportTable {
  const showLots = data.filters.applied.show_lots;
  const showReasons = data.filters.applied.show_reasons;
  const header = [
    "Проект",
    ...(showLots ? ["Лот"] : ["ИД", "Ур", "Название задачи"]),
    "% завершения",
    "Начало",
    "Базовое начало",
    "Отклонение начала",
    "Окончание",
    "Базовое окончание",
    "Отклонение окончания",
    ...(showReasons ? ["Причины отклонений", "Заметки"] : []),
  ];
  const rows: ExportCell[][] = data.rows.map((row) => [
    row.project,
    ...(showLots
      ? [row.task]
      : [row.task_id ?? "", row.level ?? "", row.task]),
    row.pct_complete == null ? "" : `${row.pct_complete}%`,
    row.plan_start ?? "",
    row.base_start ?? "",
    row.dev_start,
    row.plan_end ?? "",
    row.base_end ?? "",
    row.dev_end,
    ...(showReasons ? [row.reason ?? "", row.notes ?? ""] : []),
  ]);
  return { header: [header], rows, sheetName: "Таблица задач" };
}

export function ProjectScheduleView() {
  const [filters, setFilters] = useState(INITIAL);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [data, setData] = useState<ProjectSchedulePayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [tableSort, setTableSort] = useState<SortState>(null);

  const load = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchProjectSchedule({
          project: filters.project,
          level: filters.level,
          block: filters.block,
          building: filters.building,
          hide_completed: filters.hideCompleted,
          only_delay: filters.onlyDelay,
          show_reasons: filters.showReasons,
          show_lots: filters.showLots,
          label_pct: filters.labelPct,
        }),
      );
    } catch (cause) {
      setData(null);
      setError(cause instanceof Error ? cause.message : String(cause));
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
  const metaError = data?.meta?.error as string | undefined;
  const rows = useMemo(() => data?.rows ?? [], [data?.rows]);
  const showLots = data?.filters.applied.show_lots ?? filters.showLots;
  const showReasons = data?.filters.applied.show_reasons ?? filters.showReasons;
  const multiProject = Boolean(
    data?.filters.applied.multi_project ?? filters.project === "Все",
  );

  const columnLabels = useMemo(() => {
    if (data?.columns?.length) return data.columns;
    return [
      "Проект",
      ...(showLots ? ["Лот"] : ["ИД", "Ур", "Название задачи"]),
      "% завершения",
      "Начало",
      "Базовое начало",
      "Отклонение начала",
      "Окончание",
      "Базовое окончание",
      "Отклонение окончания",
      ...(showReasons ? ["Причины отклонений", "Заметки"] : []),
    ];
  }, [data?.columns, showLots, showReasons]);

  const sortedRows = useMemo(() => {
    const indexed = rows.map((row, index) => ({ ...row, _index: index }));
    if (!tableSort) return indexed;
    return [...indexed].sort((a, b) => {
      const diff = compareSchedule(a, b, tableSort.key);
      return tableSort.asc ? diff : -diff;
    });
  }, [rows, tableSort]);

  const toggleSort = useCallback((key: SortKey) => {
    setTableSort((prev) => {
      if (!prev || prev.key !== key) return { key, asc: true };
      if (prev.asc) return { key, asc: false };
      return null;
    });
  }, []);

  return (
    <AppShell title="График проекта">
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
            <div className="grid gap-3 md:grid-cols-2 xl:grid-cols-4">
              <label className="block text-sm">
                <Text>Проект</Text>
                <select
                  className={selectClass}
                  value={filters.project}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, project: event.target.value, building: "Все" }))
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
                    setFilters((prev) => ({ ...prev, block: event.target.value, building: "Все" }))
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
                <Text>Уровень отображения задач</Text>
                <select
                  className={selectClass}
                  value={filters.level}
                  disabled={Boolean(data?.filters.applied.level_skipped) || filters.showReasons || filters.showLots}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, level: event.target.value }))
                  }
                >
                  {(data?.filters.levels ?? [
                    { id: "Верхний уровень", label: "Верхний уровень" },
                    { id: "Детальный уровень", label: "Детальный уровень" },
                  ]).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
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
                  checked={filters.showLots}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, showLots: event.target.checked }))
                  }
                />
                <Text>Отображать в лотах</Text>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={filters.labelPct}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, labelPct: event.target.checked }))
                  }
                />
                <Text>Показать %</Text>
              </label>
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={filters.hideCompleted}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, hideCompleted: event.target.checked }))
                  }
                />
                <Text>Скрыть задачи с 100% выполнения</Text>
              </label>
              <label className="flex items-center gap-2 text-sm md:col-span-2">
                <input
                  type="checkbox"
                  checked={filters.onlyDelay}
                  onChange={(event) =>
                    setFilters((prev) => ({ ...prev, onlyDelay: event.target.checked }))
                  }
                />
                <Text>Отображать только диаграммы, где отклонение окончания &lt; 0</Text>
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

      {data?.meta.banner ? (
        <Card className="mb-4 rounded-xl border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30">
          <Text className="text-amber-900 dark:text-amber-200">{data.meta.banner}</Text>
        </Card>
      ) : null}

      {loading && !data ? (
        <Card className="rounded-xl">
          <Text>Загрузка…</Text>
        </Card>
      ) : (
        <div className="space-y-6">
          <Card className="rounded-xl">
            <FullscreenPanel disabled={!data?.gantt.rows.length} fill>
              {(zoomed) =>
                data ? <ProjectScheduleGantt data={data} fullscreen={zoomed} /> : null
              }
            </FullscreenPanel>
          </Card>

          <Card className="overflow-hidden rounded-xl p-0">
            <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Таблица задач
              </Title>
            </div>
            <FullscreenPanel disabled={!rows.length} className="!overflow-x-hidden">
              <MobileCardStack>
                {sortedRows.map((row, index) => {
                  const title = showLots
                    ? row.task
                    : multiProject
                      ? `${row.project}: ${row.task}`
                      : row.task;
                  const badge =
                    row.dev_end != null && row.dev_end !== ""
                      ? row.dev_end
                      : row.pct_complete != null
                        ? `${row.pct_complete}%`
                        : undefined;
                  const badgeTone =
                    row.dev_end_days == null
                      ? "neutral"
                      : row.dev_end_days < 0
                        ? "bad"
                        : "ok";
                  return (
                    <MobileEntityCard
                      key={`${row.project}-${row.task_id ?? row.task}-${index}`}
                      title={title}
                      badge={badge}
                      badgeTone={badgeTone}
                    >
                      <MobileMetricGrid
                        columns={2}
                        items={[
                          ...(showLots
                            ? []
                            : [
                                { label: "ИД", value: row.task_id ?? "—" },
                                { label: "Ур", value: row.level ?? "—" },
                              ]),
                          {
                            label: "%",
                            value: row.pct_complete == null ? "—" : `${row.pct_complete}%`,
                          },
                          { label: "Начало", value: row.plan_start ?? "—" },
                          { label: "Баз. нач.", value: row.base_start ?? "—" },
                          {
                            label: "Откл. нач.",
                            value: row.dev_start || "—",
                            className: deviationClass(row.dev_start_days),
                          },
                          { label: "Окончание", value: row.plan_end ?? "—" },
                          { label: "Баз. оконч.", value: row.base_end ?? "—" },
                          {
                            label: "Откл. оконч.",
                            value: row.dev_end || "—",
                            className: deviationClass(row.dev_end_days),
                          },
                          ...(showReasons
                            ? [
                                { label: "Причина", value: row.reason || "—" },
                                { label: "Заметки", value: row.notes || "—" },
                              ]
                            : []),
                        ]}
                      />
                    </MobileEntityCard>
                  );
                })}
              </MobileCardStack>
              <div className="hidden max-h-[32rem] overflow-auto p-1 pt-10 lg:block">
                {rows.length === 0 ? (
                  <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                    Нет строк по выбранным фильтрам.
                  </div>
                ) : (
                  <table className="min-w-full border-collapse text-left text-[13px]">
                    <thead className="sticky top-0 z-20">
                      <tr>
                        {columnLabels.map((label) => {
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
                            />
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {sortedRows.map((row, index) => {
                        const startTint = tintStyle(row.dev_start_days);
                        const endTint = tintStyle(row.dev_end_days);
                        return (
                        <tr
                          key={`${row.project}-${row.task_id ?? row.task}-${index}`}
                          className="odd:bg-[#fcfcfd] hover:bg-[#f3f4f6] dark:odd:bg-white/[0.02] dark:hover:bg-slate-800/40"
                        >
                          <td className={`${TD} text-left font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong`}>
                            {row.project}
                          </td>
                          {showLots ? (
                            <td className={`${TD} max-w-xs truncate text-left`}>{row.task}</td>
                          ) : (
                            <>
                              <td className={`${TD} tabular-nums`}>{row.task_id ?? ""}</td>
                              <td className={`${TD} tabular-nums`}>{row.level ?? ""}</td>
                              <td className={`${TD} max-w-xs truncate text-left text-tremor-content-strong dark:text-dark-tremor-content-strong`}>
                                {row.task}
                              </td>
                            </>
                          )}
                          <td className={`${TD} tabular-nums`}>
                            {row.pct_complete == null ? "" : `${row.pct_complete}%`}
                          </td>
                          <td className={`${TD} tabular-nums`} style={startTint}>
                            {row.plan_start ?? ""}
                          </td>
                          <td className={`${TD} tabular-nums`} style={startTint}>
                            {row.base_start ?? ""}
                          </td>
                          <td
                            className={`${TD} tabular-nums ${deviationClass(row.dev_start_days)}`}
                            style={startTint}
                          >
                            {row.dev_start}
                          </td>
                          <td className={`${TD} tabular-nums`} style={endTint}>
                            {row.plan_end ?? ""}
                          </td>
                          <td className={`${TD} tabular-nums`} style={endTint}>
                            {row.base_end ?? ""}
                          </td>
                          <td
                            className={`${TD} tabular-nums ${deviationClass(row.dev_end_days)}`}
                            style={endTint}
                          >
                            {row.dev_end}
                          </td>
                          {showReasons ? (
                            <>
                              <td className={`${TD} max-w-xs truncate`}>{row.reason ?? ""}</td>
                              <td className={`${TD} max-w-xs truncate`}>{row.notes ?? ""}</td>
                            </>
                          ) : null}
                        </tr>
                        );
                      })}
                    </tbody>
                  </table>
                )}
              </div>
            </FullscreenPanel>
          </Card>

          <DownloadTableButton
            getTable={() => (data ? buildExport(data) : null)}
            fileStem="project_schedule_tasks"
            disabled={!rows.length}
          />
        </div>
      )}
    </AppShell>
  );
}
