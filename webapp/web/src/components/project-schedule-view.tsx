"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
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
  const tableRef = useRef<HTMLDivElement>(null);

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

  useUrlFilterState(filters, INITIAL, (patch) =>
    setFilters((prev) => ({ ...prev, ...patch })),
  );

  const dirty = JSON.stringify(filters) !== JSON.stringify(INITIAL);
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

  const activeFilters = buildFilterChips(
    filters,
    INITIAL,
    [
      {
        key: "project",
        name: "Проект",
        clear: { project: "Все", building: "Все" },
      },
      {
        key: "block",
        name: "Блок",
        clear: { block: "Все", building: "Все" },
      },
      { key: "building", name: "Строение" },
      { key: "level", name: "Уровень" },
      { key: "showReasons", name: "Причины отклонений", kind: "flag" },
      { key: "showLots", name: "Лоты", kind: "flag" },
      { key: "labelPct", name: "% на графике", kind: "flag" },
      { key: "hideCompleted", name: "Завершённые скрыты", kind: "flag" },
      { key: "onlyDelay", name: "Только просрочка", kind: "flag" },
    ],
    (patch) => setFilters((prev) => ({ ...prev, ...patch })),
  );

  return (
    <AppShell title="График проекта" loading={loading}>
      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((value) => !value)}
        activeFilters={activeFilters}
        onReset={dirty ? () => setFilters(INITIAL) : undefined}
      >
        <FiltersReset disabled={!dirty} onClick={() => setFilters(INITIAL)} />
        <FilterFieldsRow cols={5}>
          <FilterChipSelect label="Проект" value={filters.project} options={data?.filters.projects ?? ["Все"]} onChange={(project) => setFilters((prev) => ({ ...prev, project, building: "Все" }))} />
          <FilterChipSelect label="Функциональный блок" value={filters.block} options={data?.filters.blocks ?? ["Все"]} onChange={(block) => setFilters((prev) => ({ ...prev, block, building: "Все" }))} />
          <FilterChipSelect label="Строение" value={filters.building} options={data?.filters.buildings ?? ["Все"]} onChange={(building) => setFilters((prev) => ({ ...prev, building }))} />
          <FilterChipSelect label="Уровень отображения задач" value={filters.level} options={(data?.filters.levels ?? [{ id: "Верхний уровень", label: "Верхний уровень" }, { id: "Детальный уровень", label: "Детальный уровень" }]).map((item) => ({ value: item.id, label: item.label }))} disabled={Boolean(data?.filters.applied.level_skipped) || filters.showReasons || filters.showLots} onChange={(level) => setFilters((prev) => ({ ...prev, level }))} />
          <div />
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
            label="Отображать в лотах"
            checked={filters.showLots}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, showLots: event.target.checked }))
            }
          />
          <FilterCheck
            label="Показать %"
            checked={filters.labelPct}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, labelPct: event.target.checked }))
            }
          />
          <FilterCheck
            label="Скрыть задачи с 100% выполнения"
            checked={filters.hideCompleted}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, hideCompleted: event.target.checked }))
            }
          />
          <FilterCheck
            label="Отображать только диаграммы, где отклонение окончания < 0"
            checked={filters.onlyDelay}
            onChange={(event) =>
              setFilters((prev) => ({ ...prev, onlyDelay: event.target.checked }))
            }
          />
        </FilterChecksRow>
      </FiltersCard>

      {error || metaError ? (
        <Card className="mb-4 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">{error || metaError}</Text>
        </Card>
      ) : null}

      {data?.meta.banner ? (
        <Card className="mb-4 hidden rounded-xl border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 lg:block">
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
            <div className="mb-3 flex justify-end lg:hidden">
              <button
                type="button"
                className="inline-flex min-h-10 items-center gap-1.5 rounded-full border border-emerald-200 bg-emerald-50 px-3 py-1.5 text-xs font-semibold text-emerald-800 shadow-sm active:scale-[0.98] dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200"
                onClick={() =>
                  tableRef.current?.scrollIntoView({
                    behavior: "smooth",
                    block: "start",
                  })
                }
              >
                К таблице
                <span aria-hidden>↓</span>
              </button>
            </div>
            {data ? <ProjectScheduleGantt data={data} /> : null}
          </Card>

          <div ref={tableRef} className="scroll-mt-4">
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
                      <div className="mb-2 text-[11px] leading-snug tabular-nums text-tremor-content dark:text-dark-tremor-content">
                        План {(row.base_start || "—")} → {(row.base_end || "—")}
                        <span className="mx-1 opacity-40">·</span>
                        Факт {(row.plan_start || "—")} → {(row.plan_end || "—")}
                      </div>
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
                          {
                            label: "Откл. нач.",
                            value: row.dev_start || "—",
                            className: deviationClass(row.dev_start_days),
                          },
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
              <div className="hidden p-1 pt-10 lg:block">
                <div className="max-h-[32rem] overflow-auto">
                {rows.length === 0 ? (
                  <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                    Нет строк по выбранным фильтрам.
                  </div>
                ) : (
                  <table className="bi-sticky-head bi-sticky-col min-w-full border-collapse text-left text-[13px]">
                    <thead>
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
              </div>
              </FullscreenPanel>
            </Card>
          </div>

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
