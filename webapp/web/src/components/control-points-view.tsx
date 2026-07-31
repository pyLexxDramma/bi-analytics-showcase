"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, Text } from "@tremor/react";
import { fetchControlPoints, type ControlPointsPayload } from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import type { ExportTable } from "@/lib/table-export";

const CELL = "border border-[#cbd5e1] dark:border-[#5a6f82]";
const EDGE_L = "border-l-[3px] border-l-[#94a3b8] dark:border-l-white";
const EDGE_R = "border-r-[3px] border-r-[#94a3b8] dark:border-r-white";
const HEAD = "bg-[#dcfce7] text-[#14532d] dark:bg-[#1a3328] dark:text-[#f0f4f8]";

function deviationClass(cell: { otkl_days: number | null } | undefined) {
  if (cell?.otkl_days == null) return "text-tremor-content dark:text-dark-tremor-content";
  return cell.otkl_days < 0
    ? "font-semibold text-[#b91c1c] dark:text-rose-300"
    : "font-semibold text-[#15803d] dark:text-emerald-300";
}

function buildExport(data: ControlPointsPayload): ExportTable {
  const header = ["Проект"];
  const subheader = [""];
  for (const group of data.groups) {
    for (const milestone of group.milestones) {
      header.push(milestone.title, "", "", "");
      subheader.push("●", "План", "Факт", "Откл.");
    }
  }
  const rows = data.projects.map((project) => {
    const row = [project.project];
    for (const group of data.groups) {
      for (const milestone of group.milestones) {
        const cell = project.cells[milestone.slug];
        row.push(cell?.status === "ok" ? "●" : "●", cell?.plan ?? "Н/Д", cell?.fact ?? "Н/Д", cell?.otkl ?? "Н/Д");
      }
    }
    return row;
  });
  return { header: [header, subheader], rows, sheetName: "Контрольные точки" };
}

function ControlPointsTable({
  group,
  projects,
}: {
  group: ControlPointsPayload["groups"][number];
  projects: ControlPointsPayload["projects"];
}) {
  return (
    <Card className="overflow-hidden rounded-xl p-0">
      <FullscreenPanel disabled={!projects.length}>
        <div className="overflow-x-auto p-1 pt-10">
          <table className="min-w-max border-separate border-spacing-0 border-[3px] border-[#94a3b8] text-center text-xs dark:border-white">
            <thead>
              <tr>
                <th
                  rowSpan={2}
                  className="sticky left-0 z-30 min-w-48 border-[3px] border-[#94a3b8] bg-[#e8f0fe] px-3 py-2 text-center font-bold text-[#111827] dark:border-white dark:bg-[#1a3328] dark:text-[#f0f4f8]"
                >
                  Проект
                </th>
                {group.milestones.map((milestone) => (
                  <th key={milestone.slug} colSpan={4} className={`${CELL} ${EDGE_L} ${EDGE_R} ${HEAD} px-2 py-2 font-bold`}>
                    {milestone.title}
                  </th>
                ))}
              </tr>
              <tr className="text-[10px] uppercase">
                {group.milestones.flatMap((milestone) =>
                  ["●", "План", "Факт", "Откл."].map((label, index) => (
                    <th
                      key={`${milestone.slug}-${label}`}
                      className={`${CELL} ${HEAD} ${index === 0 ? EDGE_L : ""} ${index === 3 ? EDGE_R : ""} px-2 py-1.5 font-semibold`}
                    >
                      {label}
                    </th>
                  )),
                )}
              </tr>
            </thead>
            <tbody>
              {projects.map((project) => (
                <tr key={project.project}>
                  <td className={`sticky left-0 z-10 ${CELL} ${EDGE_R} bg-[#f9fafb] px-3 py-2 text-left font-bold text-[#111827] dark:bg-[#161f2b] dark:text-[#f0f4f8]`}>
                    {project.project}
                  </td>
                  {group.milestones.flatMap((milestone) => {
                    const cell = project.cells[milestone.slug];
                    const body = `${CELL} bg-white px-2 py-2 tabular-nums dark:bg-[#0c1219]`;
                    return [
                      <td key={`${milestone.slug}-status`} className={`${body} ${EDGE_L} w-8`}>
                        <span className={`inline-block h-3 w-3 rounded-full ${cell?.status === "ok" ? "bg-emerald-500" : "bg-rose-500"}`} aria-label={cell?.status === "ok" ? "В срок" : "Просрочено"} />
                      </td>,
                      <td key={`${milestone.slug}-plan`} className={`${body} font-semibold ${cell?.pct_complete_100 ? "text-orange-600 dark:text-[#f09355]" : ""}`}>{cell?.plan ?? "Н/Д"}</td>,
                      <td key={`${milestone.slug}-fact`} className={`${body} font-semibold ${cell?.pct_complete_100 ? "text-orange-600 dark:text-[#f09355]" : ""}`}>{cell?.fact ?? "Н/Д"}</td>,
                      <td key={`${milestone.slug}-otkl`} className={`${body} ${EDGE_R} ${deviationClass(cell)}`}>{cell?.otkl ?? "Н/Д"}</td>,
                    ];
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </FullscreenPanel>
    </Card>
  );
}

export function ControlPointsView() {
  const [project, setProject] = useState("Все");
  const [data, setData] = useState<ControlPointsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const load = useCallback(async (nextProject: string) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchControlPoints(nextProject));
    } catch (cause) {
      setData(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(project);
  }, [load, project]);

  const projects = data?.projects ?? [];
  const metaError = data?.meta.error;

  return (
    <AppShell title="Контрольные точки">
      <Card className="mb-6 rounded-xl">
        <button type="button" onClick={() => setFiltersOpen((value) => !value)} aria-expanded={filtersOpen} className="flex w-full items-center gap-2 text-left text-sm font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
          <span className="text-xs">{filtersOpen ? "▾" : "▸"}</span>
          Фильтры
        </button>
        {filtersOpen ? (
          <div className="mt-3 grid gap-3 md:grid-cols-[minmax(0,320px)_auto] md:items-end">
            <label className="block text-sm">
              <Text>Проект</Text>
              <select className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background" value={project} onChange={(event) => setProject(event.target.value)}>
                {(data?.filters.projects ?? ["Все"]).map((item) => <option key={item} value={item}>{item}</option>)}
              </select>
            </label>
            <button type="button" onClick={() => setProject("Все")} disabled={project === "Все"} className="rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-sm disabled:opacity-40 dark:border-dark-tremor-border dark:bg-dark-tremor-background">
              Сбросить
            </button>
          </div>
        ) : null}
      </Card>

      {error || metaError ? <Card className="mb-4 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30"><Text className="text-rose-700 dark:text-rose-300">{error || metaError}</Text></Card> : null}
      {!projects.length ? <Card className="rounded-xl"><Text>{loading ? "Загрузка…" : "Нет данных контрольных точек. Сделайте ingest в админке."}</Text></Card> : (
        <div className="space-y-6">
          {(data?.groups ?? []).map((group) => <ControlPointsTable key={group.id} group={group} projects={projects} />)}
          <DownloadTableButton getTable={() => data ? buildExport(data) : null} fileStem="control_points_matrix" />
        </div>
      )}
    </AppShell>
  );
}
