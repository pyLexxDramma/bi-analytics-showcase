"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import {
  fetchDeveloperProjects,
  type DeveloperProjectsCell,
  type DeveloperProjectsPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  FilterChipMulti,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import { multiFilterChips } from "@/lib/filters-summary";
import { useUrlFilterState } from "@/lib/use-url-filter-state";
import type { ExportTable } from "@/lib/table-export";

const URL_INITIAL = { projects: [] as string[] };

type MatrixColumn = DeveloperProjectsPayload["matrix"]["columns"][number];

/**
 * Сетка матрицы как в [main]: 1px #cbd5e1 внутри, 3px #94a3b8 по рамке и границам
 * блоков (фаза, колонка «Проект», каждая контрольная точка). В тёмной теме — как
 * в тёмном CSS main: 1px #5a6f82 и белые толстые линии.
 */
const CELL = "border border-[#cbd5e1] dark:border-[#5a6f82]";
const EDGE_L = "border-l-[3px] border-l-[#94a3b8] dark:border-l-white";
const EDGE_R = "border-r-[3px] border-r-[#94a3b8] dark:border-r-white";
const EDGE_Y = "border-y-[3px] border-y-[#94a3b8] dark:border-y-white";
const HEAD_BOTTOM = "border-b-2 border-b-[#94a3b8] dark:border-b-[#6b7f94]";
const INVEST_BG = "bg-[#dcfce7] text-[#14532d] dark:bg-emerald-900/40 dark:text-[#f0f4f8]";
const LIFE_BG = "bg-[#e2e8f0] text-[#1f2937] dark:bg-slate-600/50 dark:text-[#f0f4f8]";

function otklClass(cell: DeveloperProjectsCell | undefined): string {
  if (!cell?.otkl || cell.otkl === "Н/Д" || cell.otkl === "—") {
    return "text-tremor-content dark:text-dark-tremor-content";
  }
  const numMatch = String(cell.otkl).replace(",", ".").match(/-?\d+(?:\.\d+)?/);
  const n = numMatch ? Number(numMatch[0]) : null;
  const bad = "font-semibold text-[#b91c1c] dark:text-rose-300";
  const ok = "font-semibold text-[#15803d] dark:text-emerald-300";
  if (n != null && Number.isFinite(n)) return n < 0 ? bad : ok;
  return String(cell.otkl).trim().startsWith("-") ? bad : ok;
}

function dateClass(cell: DeveloperProjectsCell | undefined): string {
  if (cell?.pct_complete_100) {
    return "font-semibold text-[#ea580c] dark:text-[#f09355]";
  }
  return "font-semibold text-[#111827] dark:text-[#fafafa]";
}

function subLabels(
  cell: DeveloperProjectsCell | undefined,
  col: MatrixColumn,
) {
  const fromCell = cell?.subcolumn_labels;
  const fromCol = col.subcolumn_labels;
  return {
    plan: fromCell?.plan || fromCol?.plan || "План",
    fact: fromCell?.fact || fromCol?.fact || "Факт",
    otkl: fromCell?.otkl || fromCol?.otkl || "Откл.",
  };
}

/** Короткие заголовки для table-fixed на 360–400px (полные — в title). */
function shortMobileSubLabel(label: string): string {
  const s = String(label || "").trim();
  if (!s) return "—";
  const lower = s.toLowerCase();
  if (lower.includes("критически просроч")) return "Проср.";
  if (lower.includes("критическ")) return "Крит.";
  if (lower.includes("всего")) return "Всего";
  if (lower === "план" || lower.startsWith("план")) return "План";
  if (lower === "факт" || lower.startsWith("факт")) return "Факт";
  if (lower.startsWith("откл")) return "Откл.";
  if (s.length <= 8) return s;
  return `${s.slice(0, 7)}…`;
}

/** Выгрузка повторяет видимую матрицу: две строки шапки + строка на проект. */
function buildMatrixExport(
  columns: MatrixColumn[],
  projects: DeveloperProjectsPayload["matrix"]["projects"],
): ExportTable {
  const header1: string[] = ["Проект"];
  const header2: string[] = [""];
  for (const col of columns) {
    const labs = subLabels(projects[0]?.cells[col.key], col);
    header1.push(col.label, "", "");
    header2.push(labs.plan, labs.fact, labs.otkl);
  }
  const rows = projects.map((row) => {
    const cells: string[] = [row.project];
    for (const col of columns) {
      const cell = row.cells[col.key];
      cells.push(cell?.plan ?? "Н/Д", cell?.fact ?? "Н/Д", cell?.otkl ?? "Н/Д");
    }
    return cells;
  });
  return { header: [header1, header2], rows, sheetName: "Матрица" };
}

/** Desktop / lg+: широкая матрица как в main. */
function WideMatrixTable({
  columns,
  investCols,
  lifeCols,
  projects,
}: {
  columns: MatrixColumn[];
  investCols: MatrixColumn[];
  lifeCols: MatrixColumn[];
  projects: DeveloperProjectsPayload["matrix"]["projects"];
}) {
  return (
    <table className="min-w-max border-separate border-spacing-0 border-[3px] border-[#94a3b8] text-center text-xs dark:border-white">
      <thead>
        <tr>
          <th
            rowSpan={3}
            className={`sticky left-0 z-30 min-w-48 border-[3px] border-[#94a3b8] bg-[#e8f0fe] px-3 py-2 text-center font-bold text-[#111827] dark:border-white dark:bg-[#1a3328] dark:text-[#f0f4f8]`}
          >
            Проект
          </th>
          {investCols.length ? (
            <th
              colSpan={investCols.length * 3}
              className={`${CELL} ${EDGE_Y} ${EDGE_R} ${INVEST_BG} px-2 py-2 font-bold`}
            >
              Инвестиционная фаза
            </th>
          ) : null}
          {lifeCols.length ? (
            <th
              colSpan={lifeCols.length * 3}
              className={`${CELL} ${EDGE_Y} ${EDGE_L} ${EDGE_R} ${LIFE_BG} px-2 py-2 font-bold`}
            >
              Жизнь проекта
            </th>
          ) : null}
        </tr>
        <tr>
          {columns.map((col) => (
            <th
              key={col.key}
              colSpan={3}
              className={`${CELL} ${EDGE_L} ${EDGE_R} ${
                col.phase === "invest" ? INVEST_BG : LIFE_BG
              } px-2 py-2 font-semibold`}
            >
              {col.label}
            </th>
          ))}
        </tr>
        <tr className="text-[10px] uppercase">
          {columns.flatMap((col) => {
            const sample = projects[0]?.cells[col.key];
            const labs = subLabels(sample, col);
            const blockBg = col.phase === "invest" ? INVEST_BG : LIFE_BG;
            return [labs.plan, labs.fact, labs.otkl].map((label, index) => (
              <th
                key={`${col.key}-${label}-${index}`}
                className={`${CELL} ${HEAD_BOTTOM} ${
                  index === 0 ? EDGE_L : ""
                } ${index === 2 ? EDGE_R : ""} ${blockBg} px-2 py-1.5 font-semibold`}
              >
                {label}
              </th>
            ));
          })}
        </tr>
      </thead>
      <tbody>
        {projects.map((row) => (
          <tr key={row.project}>
            <td
              className={`sticky left-0 z-10 ${CELL} ${EDGE_R} bg-[#f9fafb] px-3 py-2 text-left font-bold text-[#111827] dark:bg-[#161f2b] dark:text-[#f0f4f8]`}
            >
              {row.project}
            </td>
            {columns.flatMap((col) => {
              const cell = row.cells[col.key];
              const body = `${CELL} bg-white px-2 py-2 tabular-nums dark:bg-[#0c1219]`;
              return [
                <td
                  key={`${col.key}-plan`}
                  className={`${body} ${EDGE_L} ${dateClass(cell)}`}
                >
                  {cell?.plan ?? "Н/Д"}
                </td>,
                <td
                  key={`${col.key}-fact`}
                  className={`${body} ${dateClass(cell)}`}
                >
                  {cell?.fact ?? "Н/Д"}
                </td>,
                <td
                  key={`${col.key}-otkl`}
                  className={`${body} ${EDGE_R} ${otklClass(cell)}`}
                >
                  {cell?.otkl ?? "Н/Д"}
                </td>,
              ];
            })}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Знак отклонения в дополнение к цвету — читается и без различения цветов. */
function otklWithSign(raw: string | null | undefined): string {
  const text = (raw ?? "Н/Д").trim();
  if (!text || text === "Н/Д" || text === "—") return text;
  const numMatch = text.replace(",", ".").match(/-?\d+(?:\.\d+)?/);
  const n = numMatch ? Number(numMatch[0]) : null;
  if (n == null || !Number.isFinite(n) || n === 0) return text;
  return `${n < 0 ? "▼" : "▲"} ${text}`;
}

function MobileProjectName({ value }: { value: string }) {
  const match = String(value).trim().match(/^(.*?)\s*(\(\d+\s*этап\))$/i);
  if (!match) return <>{value}</>;
  return (
    <>
      <span className="block">{match[1]}</span>
      <span className="block whitespace-nowrap">{match[2]}</span>
    </>
  );
}

/** Mobile: секции по контрольной точке — скролл только вертикальный. */
function MobileMilestoneSections({
  columns,
  projects,
}: {
  columns: MatrixColumn[];
  projects: DeveloperProjectsPayload["matrix"]["projects"];
}) {
  return (
    <div className="flex flex-col gap-4 px-2 pb-2">
      {columns.map((col) => {
        const labs = subLabels(projects[0]?.cells[col.key], col);
        const blockBg = col.phase === "invest" ? INVEST_BG : LIFE_BG;
        const phaseLabel =
          col.phase === "invest" ? "Инвестиционная фаза" : "Жизнь проекта";
        return (
          <section
            key={col.key}
            className="overflow-hidden rounded-lg border-[3px] border-[#94a3b8] dark:border-slate-400"
          >
            <div className={`${blockBg} border-b-2 border-[#94a3b8] px-3 py-2 dark:border-slate-400`}>
              <div className="text-[11px] font-medium opacity-80">{phaseLabel}</div>
              <div className="text-sm font-bold leading-snug break-words [overflow-wrap:anywhere]">
                {col.label}
              </div>
            </div>
            <table className="w-full table-fixed border-separate border-spacing-0 text-center text-xs">
              {/* Даты формата 28.02.2025 не должны переноситься — колонкам нужен запас */}
              <colgroup>
                <col className="w-[28%]" />
                <col className="w-[24%]" />
                <col className="w-[24%]" />
                <col className="w-[24%]" />
              </colgroup>
              <thead>
                <tr className="text-[10px]">
                  <th
                    className={`${CELL} ${HEAD_BOTTOM} bg-[#e8f0fe] px-1.5 py-1.5 text-left font-bold text-[#111827] dark:bg-[#1a3328] dark:text-[#f0f4f8]`}
                  >
                    Проект
                  </th>
                  {[labs.plan, labs.fact, labs.otkl].map((label) => (
                    <th
                      key={`${col.key}-h-${label}`}
                      title={label}
                      className={`${CELL} ${HEAD_BOTTOM} ${blockBg} px-0.5 py-1.5 text-[9px] font-semibold leading-tight break-words [overflow-wrap:anywhere]`}
                    >
                      {shortMobileSubLabel(label)}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {projects.map((row) => {
                  const cell = row.cells[col.key];
                  const body = `${CELL} whitespace-nowrap bg-white px-0.5 py-2 text-[11px] tabular-nums dark:bg-[#0c1219]`;
                  return (
                    <tr key={`${col.key}-${row.project}`}>
                      <td
                        className={`${CELL} bg-[#f9fafb] px-1.5 py-2 text-left text-[11px] font-bold leading-snug text-[#111827] dark:bg-[#161f2b] dark:text-[#f0f4f8]`}
                      >
                        <MobileProjectName value={row.project} />
                      </td>
                      <td className={`${body} ${dateClass(cell)}`}>
                        {cell?.plan ?? "Н/Д"}
                      </td>
                      <td className={`${body} ${dateClass(cell)}`}>
                        {cell?.fact ?? "Н/Д"}
                      </td>
                      <td className={`${body} ${otklClass(cell)}`}>
                        {otklWithSign(cell?.otkl)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </section>
        );
      })}
    </div>
  );
}

export function DeveloperProjectsView() {
  const [selected, setSelected] = useState<string[]>([]);
  const [data, setData] = useState<DeveloperProjectsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const load = useCallback(async (projects: string[]) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchDeveloperProjects(projects));
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(selected);
  }, [selected, load]);

  const urlState = useMemo(() => ({ projects: selected }), [selected]);
  useUrlFilterState(urlState, URL_INITIAL, (patch) => {
    if (patch.projects) setSelected(patch.projects);
  });

  const columns = useMemo(() => {
    if (data?.matrix.columns?.length) return data.matrix.columns;
    return (data?.matrix.milestones ?? []).map((m) => ({
      key: m.slug,
      label: m.title,
      phase: m.phase,
    }));
  }, [data]);

  const investCols = columns.filter((c) => c.phase === "invest");
  const lifeCols = columns.filter((c) => c.phase !== "invest");
  const hasRows = (data?.matrix.projects.length ?? 0) > 0;

  const matrixExport = () =>
    data?.matrix.projects.length
      ? buildMatrixExport(columns, data.matrix.projects)
      : null;

  const metaError = data?.meta?.error;

  return (
    <AppShell title="Девелоперские проекты" loading={loading}>
      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((state) => !state)}
        activeFilters={multiFilterChips("projects", "Проект", selected, setSelected)}
        onReset={selected.length ? () => setSelected([]) : undefined}
      >
        <FiltersReset disabled={selected.length === 0} onClick={() => setSelected([])} />
        <FilterChipMulti
          label="Проект"
          values={selected}
          options={data?.filters.projects ?? []}
          onChange={setSelected}
        />
      </FiltersCard>

      {(data?.hints?.length ?? 0) > 0 ? (
        <Card className="mb-4 hidden rounded-xl border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30 lg:block">
          <Text className="font-medium text-amber-900 dark:text-amber-200">
            Данные для этого блока неполные — возможны пропуски/приближения:
          </Text>
          <ul className="mt-2 list-disc pl-5 text-sm text-amber-900 dark:text-amber-200">
            {data?.hints?.map((h) => (
              <li key={h}>{h}</li>
            ))}
          </ul>
        </Card>
      ) : null}

      {error || metaError ? (
        <Card className="mb-4 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            {error || metaError}
          </Text>
        </Card>
      ) : null}

      {/* KPI и графики намеренно не выводим: в [main] экран — только матрица. */}

      <Card className="overflow-hidden rounded-xl p-0">
        <div className="flex items-center justify-between border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            Матрица контрольных точек
          </Title>
        </div>
        <FullscreenPanel disabled={!hasRows}>
          <div className="p-1 pt-3 lg:pt-10">
            {!hasRows ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                {loading
                  ? "Загрузка…"
                  : "Нет данных матрицы. Сделайте ingest в админке."}
              </div>
            ) : (
              <>
                <div className="lg:hidden">
                  <MobileMilestoneSections
                    columns={columns}
                    projects={data?.matrix.projects ?? []}
                  />
                </div>
                <div className="hidden overflow-x-auto lg:block">
                  <WideMatrixTable
                    columns={columns}
                    investCols={investCols}
                    lifeCols={lifeCols}
                    projects={data?.matrix.projects ?? []}
                  />
                </div>
              </>
            )}
          </div>
        </FullscreenPanel>
      </Card>

      <div className="mt-3">
        <DownloadTableButton
          getTable={matrixExport}
          fileStem="developer_projects_matrix"
          disabled={!hasRows}
        />
      </div>

      <div
        role="note"
        aria-label="Легенда цветов таблицы"
        className="mt-3 flex flex-wrap items-center gap-x-5 gap-y-1.5 text-xs text-tremor-content dark:text-dark-tremor-content"
      >
        <span className="font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong">
          Легенда:
        </span>
        <span className="flex items-center gap-1.5">
          <span className="font-semibold text-orange-600 dark:text-orange-300">
            100%
          </span>
          План / Факт — задача в MSP выполнена на 100%
        </span>
        <span className="flex items-center gap-1.5">
          <span className="font-semibold text-emerald-700 dark:text-emerald-300">
            +0
          </span>
          Откл. — нулевое или положительное отклонение
        </span>
        <span className="flex items-center gap-1.5">
          <span className="font-semibold text-rose-700 dark:text-rose-300">
            −0
          </span>
          Откл. — отрицательное отклонение (просрочка / недовыполнение)
        </span>
      </div>
    </AppShell>
  );
}
