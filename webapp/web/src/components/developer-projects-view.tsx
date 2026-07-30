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
import type { ExportTable } from "@/lib/table-export";

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

  const toggleProject = (name: string) => {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name],
    );
  };

  const matrixExport = () =>
    data?.matrix.projects.length
      ? buildMatrixExport(columns, data.matrix.projects)
      : null;

  const metaError = data?.meta?.error;

  return (
    <AppShell title="Девелоперские проекты">
      <Card className="mb-6 rounded-xl">
        <button
          type="button"
          onClick={() => setFiltersOpen((state) => !state)}
          aria-expanded={filtersOpen}
          className="flex w-full items-center gap-2 text-left text-sm font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong"
        >
          <span className="text-xs">{filtersOpen ? "▾" : "▸"}</span>
          Фильтры
        </button>

        {filtersOpen ? (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setSelected([])}
              disabled={selected.length === 0}
              className="rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-1.5 text-sm disabled:opacity-40 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            >
              Сбросить
            </button>

            <Text className="mt-3">Проект</Text>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setSelected([])}
                className={`rounded-md border px-2.5 py-1 text-xs ${
                  selected.length === 0
                    ? "border-emerald-600 bg-emerald-50 text-emerald-900 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-200"
                    : "border-tremor-border bg-white dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                }`}
              >
                Все
              </button>
              {(data?.filters.projects ?? []).map((name) => {
                const on = selected.includes(name);
                return (
                  <button
                    key={name}
                    type="button"
                    onClick={() => toggleProject(name)}
                    className={`rounded-md border px-2.5 py-1 text-xs ${
                      on
                        ? "border-emerald-600 bg-emerald-50 text-emerald-900 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-200"
                        : "border-tremor-border bg-white text-tremor-content-strong dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
                    }`}
                  >
                    {name}
                  </button>
                );
              })}
            </div>
          </div>
        ) : null}
      </Card>

      {(data?.hints?.length ?? 0) > 0 ? (
        <Card className="mb-4 rounded-xl border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30">
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
          <div className="overflow-x-auto p-1 pt-10">
            {!hasRows ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                {loading
                  ? "Загрузка…"
                  : "Нет данных матрицы. Сделайте ingest в админке."}
              </div>
            ) : (
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
                      const sample = data?.matrix.projects[0]?.cells[col.key];
                      const labs = subLabels(sample, col);
                      const blockBg =
                        col.phase === "invest" ? INVEST_BG : LIFE_BG;
                      return [labs.plan, labs.fact, labs.otkl].map(
                        (label, index) => (
                          <th
                            key={`${col.key}-${label}-${index}`}
                            className={`${CELL} ${HEAD_BOTTOM} ${
                              index === 0 ? EDGE_L : ""
                            } ${index === 2 ? EDGE_R : ""} ${blockBg} px-2 py-1.5 font-semibold`}
                          >
                            {label}
                          </th>
                        ),
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {(data?.matrix.projects ?? []).map((row) => (
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
