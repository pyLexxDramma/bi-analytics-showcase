"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import {
  BarChart,
  Card,
  DonutChart,
  Grid,
  Metric,
  Text,
  Title,
} from "@tremor/react";
import {
  fetchDeveloperProjects,
  type DeveloperProjectsCell,
  type DeveloperProjectsPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { CHART_RU, withRuPctComplete } from "@/lib/chart-ru";

type MatrixColumn = DeveloperProjectsPayload["matrix"]["columns"][number];

function otklClass(cell: DeveloperProjectsCell | undefined): string {
  if (!cell?.otkl || cell.otkl === "Н/Д" || cell.otkl === "—") {
    return "text-tremor-content dark:text-dark-tremor-content";
  }
  const numMatch = String(cell.otkl).replace(",", ".").match(/-?\d+(?:\.\d+)?/);
  const n = numMatch ? Number(numMatch[0]) : null;
  if (n != null && Number.isFinite(n)) {
    if (n < 0) return "font-semibold text-rose-700 dark:text-rose-300";
    return "font-semibold text-emerald-700 dark:text-emerald-300";
  }
  if (String(cell.otkl).trim().startsWith("-")) {
    return "font-semibold text-rose-700 dark:text-rose-300";
  }
  return "font-semibold text-emerald-700 dark:text-emerald-300";
}

function dateClass(cell: DeveloperProjectsCell | undefined): string {
  const base =
    "border-b border-r border-tremor-border px-2 py-2 tabular-nums dark:border-dark-tremor-border";
  if (cell?.pct_complete_100) {
    return `${base} font-semibold text-orange-600 dark:text-orange-300`;
  }
  return `${base} font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong`;
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

function csvEscape(value: string): string {
  if (/[;"\n\r]/.test(value)) return `"${value.replace(/"/g, '""')}"`;
  return value;
}

function buildMatrixCsv(
  columns: MatrixColumn[],
  projects: DeveloperProjectsPayload["matrix"]["projects"],
): string {
  const header1 = ["Проект"];
  const header2 = [""];
  for (const col of columns) {
    const labs = subLabels(projects[0]?.cells[col.key], col);
    header1.push(col.label, "", "");
    header2.push(labs.plan, labs.fact, labs.otkl);
  }
  const lines = [
    header1.map((v) => csvEscape(String(v))).join(";"),
    header2.map((v) => csvEscape(String(v))).join(";"),
  ];
  for (const row of projects) {
    const cells = [row.project];
    for (const col of columns) {
      const cell = row.cells[col.key];
      cells.push(cell?.plan ?? "Н/Д", cell?.fact ?? "Н/Д", cell?.otkl ?? "Н/Д");
    }
    lines.push(cells.map((v) => csvEscape(String(v))).join(";"));
  }
  return `\uFEFF${lines.join("\r\n")}`;
}

function downloadBlob(filename: string, blob: Blob) {
  const url = URL.createObjectURL(blob);
  const a = document.createElement("a");
  a.href = url;
  a.download = filename;
  a.click();
  URL.revokeObjectURL(url);
}

export function DeveloperProjectsView() {
  const [selected, setSelected] = useState<string[]>([]);
  const [data, setData] = useState<DeveloperProjectsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [fsActive, setFsActive] = useState(false);
  const [dlOpen, setDlOpen] = useState(false);
  const [chartsReady, setChartsReady] = useState(false);
  const matrixRef = useRef<HTMLDivElement | null>(null);

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
    setChartsReady(true);
  }, []);

  useEffect(() => {
    void load(selected);
  }, [selected, load]);

  useEffect(() => {
    const onFs = () => {
      const el = matrixRef.current;
      const cur =
        document.fullscreenElement ||
        (document as Document & { webkitFullscreenElement?: Element })
          .webkitFullscreenElement;
      setFsActive(!!el && cur === el);
    };
    document.addEventListener("fullscreenchange", onFs);
    document.addEventListener("webkitfullscreenchange", onFs);
    return () => {
      document.removeEventListener("fullscreenchange", onFs);
      document.removeEventListener("webkitfullscreenchange", onFs);
    };
  }, []);

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
  const kpis = data?.kpis;
  const kpiCards = [
    { title: "Проекты", metric: kpis?.projects ?? 0 },
    { title: "Контрольные точки", metric: kpis?.milestones_found ?? 0 },
    {
      title: "Выполнено",
      metric: `${Number(kpis?.completed_pct ?? 0).toFixed(1)}%`,
    },
    { title: "Просрочено", metric: kpis?.overdue ?? 0 },
  ];

  const toggleProject = (name: string) => {
    setSelected((prev) =>
      prev.includes(name) ? prev.filter((p) => p !== name) : [...prev, name],
    );
  };

  const toggleFullscreen = async () => {
    const el = matrixRef.current;
    if (!el) return;
    const doc = document as Document & {
      webkitFullscreenElement?: Element;
      webkitExitFullscreen?: () => Promise<void>;
    };
    const cur = document.fullscreenElement || doc.webkitFullscreenElement;
    try {
      if (cur === el) {
        if (document.exitFullscreen) await document.exitFullscreen();
        else if (doc.webkitExitFullscreen) await doc.webkitExitFullscreen();
      } else {
        const anyEl = el as HTMLElement & {
          webkitRequestFullscreen?: () => Promise<void>;
        };
        if (el.requestFullscreen) await el.requestFullscreen();
        else if (anyEl.webkitRequestFullscreen) await anyEl.webkitRequestFullscreen();
      }
    } catch {
      /* ignore */
    }
  };

  const downloadCsv = () => {
    if (!data?.matrix.projects.length) return;
    const csv = buildMatrixCsv(columns, data.matrix.projects);
    downloadBlob(
      "developer_projects_matrix.csv",
      new Blob([csv], { type: "text/csv;charset=utf-8" }),
    );
    setDlOpen(false);
  };

  const metaError = data?.meta?.error;

  return (
    <AppShell
      title="Девелоперские проекты"
      subtitle="Контрольные точки проектов по актуальным календарным графикам MSP"
    >
      <Card className="mb-6 rounded-xl">
        <Text>Проект</Text>
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
        <Text className="mt-3">
          Режим данных: <b>{data?.meta.data_mode ?? "…"}</b>
          {" · "}
          {loading
            ? "загрузка…"
            : `version_id=${data?.meta.version_id ?? "—"} · ${data?.meta.rows ?? 0} проектов · ${kpis?.milestones_found ?? 0} точек`}
        </Text>
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

      <div className="mb-6 space-y-6">
        <Grid numItemsSm={2} numItemsLg={4} className="gap-6">
          {kpiCards.map((kpi) => (
            <Card key={kpi.title} className="rounded-xl">
              <Text>{kpi.title}</Text>
              <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {kpi.metric}
              </Metric>
            </Card>
          ))}
        </Grid>

        <Grid numItemsLg={3} className="gap-6">
          <Card className="rounded-xl lg:col-span-2">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Выполнение контрольных точек
            </Title>
            <Text className="mt-1">Доля завершённых точек по проектам</Text>
            {chartsReady ? (
              <BarChart
                className="mt-6 h-80"
                data={withRuPctComplete(data?.tremor?.completion_by_project ?? [])}
                index="project"
                categories={[CHART_RU.pctComplete]}
                colors={["emerald"]}
                valueFormatter={(value) => `${Number(value).toFixed(1)}%`}
                yAxisWidth={52}
                showLegend
                showAnimation
                showGridLines
              />
            ) : (
              <div className="mt-6 h-80" aria-hidden />
            )}
          </Card>
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Статусы точек
            </Title>
            <Text className="mt-1">По выбранным проектам</Text>
            {chartsReady ? (
              <DonutChart
                className="mt-6 h-52"
                data={data?.tremor?.status_mix ?? []}
                category="value"
                index="name"
                colors={["emerald", "rose", "slate", "blue"]}
                valueFormatter={(value) => `${value} шт.`}
              />
            ) : (
              <div className="mt-6 h-52" aria-hidden />
            )}
            <Text className="mt-4">
              Без факта: <b>{kpis?.missing_fact ?? 0}</b>
            </Text>
          </Card>
        </Grid>
      </div>

      <Card className="overflow-hidden rounded-xl p-0">
        <div className="flex items-center justify-between border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            Матрица контрольных точек
          </Title>
        </div>
        <div
          ref={matrixRef}
          id="matrix-fs-root"
          className="relative bg-tremor-background dark:bg-dark-tremor-background"
        >
          <div className="absolute right-2 top-2 z-40 flex gap-1">
            <button
              type="button"
              title={fsActive ? "Выйти из полного экрана" : "На весь экран"}
              onClick={() => void toggleFullscreen()}
              disabled={!hasRows}
              className="rounded-md border border-tremor-border bg-white/90 px-2 py-1 text-sm shadow disabled:opacity-40 dark:border-dark-tremor-border dark:bg-slate-900/90"
            >
              {fsActive ? "✕" : "⛶"}
            </button>
          </div>

          <div className="overflow-x-auto p-1 pt-10">
            {!hasRows ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                Нет данных матрицы. Сделайте ingest в админке.
              </div>
            ) : (
              <table className="min-w-max border-separate border-spacing-0 text-center text-xs text-tremor-content-strong dark:text-dark-tremor-content-strong">
                <thead>
                  <tr>
                    <th
                      rowSpan={3}
                      className="sticky left-0 z-30 min-w-48 border-b-2 border-r-2 border-white bg-slate-200 px-3 py-2 text-left font-bold dark:border-slate-700 dark:bg-slate-800"
                    >
                      Проект
                    </th>
                    {investCols.length ? (
                      <th
                        colSpan={investCols.length * 3}
                        className="border-b-2 border-r-2 border-white bg-emerald-100 px-2 py-2 font-bold text-emerald-950 dark:border-slate-700 dark:bg-emerald-950/50 dark:text-emerald-200"
                      >
                        Инвестиционная фаза
                      </th>
                    ) : null}
                    {lifeCols.length ? (
                      <th
                        colSpan={lifeCols.length * 3}
                        className="border-b-2 border-r-2 border-white bg-sky-100 px-2 py-2 font-bold text-sky-950 dark:border-slate-700 dark:bg-sky-950/50 dark:text-sky-200"
                      >
                        Жизнь проекта
                      </th>
                    ) : null}
                  </tr>
                  <tr className="bg-slate-100 dark:bg-slate-800">
                    {columns.map((col) => (
                      <th
                        key={col.key}
                        colSpan={3}
                        className="border-b border-r-2 border-white px-2 py-2 font-semibold dark:border-slate-700"
                      >
                        {col.label}
                      </th>
                    ))}
                  </tr>
                  <tr className="bg-slate-50 text-[10px] uppercase dark:bg-slate-900">
                    {columns.flatMap((col) => {
                      const sample = data?.matrix.projects[0]?.cells[col.key];
                      const labs = subLabels(sample, col);
                      return [labs.plan, labs.fact, labs.otkl].map(
                        (label, index) => (
                          <th
                            key={`${col.key}-${label}-${index}`}
                            className={`border-b px-2 py-1.5 ${
                              index === 2
                                ? "border-r-2 border-white dark:border-r-slate-700"
                                : "border-r border-tremor-border dark:border-dark-tremor-border"
                            }`}
                          >
                            {label}
                          </th>
                        ),
                      );
                    })}
                  </tr>
                </thead>
                <tbody>
                  {(data?.matrix.projects ?? []).map((row, idx) => (
                    <tr
                      key={row.project}
                      className={
                        idx % 2 === 0
                          ? "bg-white dark:bg-dark-tremor-background"
                          : "bg-slate-50 dark:bg-slate-900/40"
                      }
                    >
                      <td className="sticky left-0 z-10 border-b border-r-2 border-white bg-slate-100 px-3 py-2 text-left font-bold dark:border-slate-700 dark:bg-slate-800">
                        {row.project}
                      </td>
                      {columns.flatMap((col) => {
                        const cell = row.cells[col.key];
                        return [
                          <td key={`${col.key}-plan`} className={dateClass(cell)}>
                            {cell?.plan ?? "Н/Д"}
                          </td>,
                          <td key={`${col.key}-fact`} className={dateClass(cell)}>
                            {cell?.fact ?? "Н/Д"}
                          </td>,
                          <td
                            key={`${col.key}-otkl`}
                            className={`border-b border-r-2 border-white px-2 py-2 tabular-nums dark:border-r-slate-700 ${otklClass(cell)}`}
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
        </div>
      </Card>

      <div className="relative mt-3">
        <button
          type="button"
          disabled={!hasRows}
          onClick={() => setDlOpen((v) => !v)}
          className="rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-sm font-medium disabled:opacity-40 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
        >
          Скачать таблицу ▾
        </button>
        {dlOpen ? (
          <div className="absolute left-0 z-50 mt-1 min-w-[160px] rounded-md border border-tremor-border bg-white py-1 shadow-lg dark:border-dark-tremor-border dark:bg-slate-900">
            <button
              type="button"
              className="block w-full px-3 py-2 text-left text-sm hover:bg-slate-100 dark:hover:bg-slate-800"
              onClick={downloadCsv}
            >
              CSV (Excel)
            </button>
          </div>
        ) : null}
      </div>

      <Card className="mt-4 rounded-xl">
        <Title className="!text-sm !text-tremor-content-strong dark:!text-dark-tremor-content-strong">
          Легенда
        </Title>
        <Text className="mt-2">
          <span className="font-semibold text-orange-600">100%</span> —{" "}
          {data?.legend?.pct100 ?? "задача в MSP закрыта на 100%"}
        </Text>
        <Text className="mt-1">
          <span className="font-semibold text-emerald-700">+0</span> —{" "}
          {data?.legend?.pos ?? "нулевое или положительное отклонение"}
        </Text>
        <Text className="mt-1">
          <span className="font-semibold text-rose-700">−</span> —{" "}
          {data?.legend?.neg ?? "отрицательное отклонение"}
        </Text>
      </Card>
    </AppShell>
  );
}
