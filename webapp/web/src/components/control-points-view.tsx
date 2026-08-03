"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, Text } from "@tremor/react";
import { fetchControlPoints, type ControlPointsPayload } from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import { StatusPill } from "@/components/status-pill";
import type { ExportTable } from "@/lib/table-export";

const CELL = "border border-[#cbd5e1] dark:border-[#5a6f82]";
const EDGE_L = "border-l-[3px] border-l-[#94a3b8] dark:border-l-white";
const EDGE_R = "border-r-[3px] border-r-[#94a3b8] dark:border-r-white";
const HEAD = "bg-[#dcfce7] text-[#14532d] dark:bg-[#1a3328] dark:text-[#f0f4f8]";

type MilestoneCell = ControlPointsPayload["projects"][number]["cells"][string];
type Group = ControlPointsPayload["groups"][number];
type ProjectRow = ControlPointsPayload["projects"][number];

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

function statusPill(cell: MilestoneCell | undefined) {
  if (!cell) return <StatusPill tone="neutral">Н/Д</StatusPill>;
  if (cell.status === "ok") return <StatusPill tone="ok">В срок</StatusPill>;
  return <StatusPill tone="bad">Просрочено</StatusPill>;
}

function ControlPointsMobileCards({
  group,
  projects,
}: {
  group: Group;
  projects: ProjectRow[];
}) {
  return (
    <div className="flex flex-col gap-3 px-2 pb-2 pt-10 lg:hidden">
      {projects.map((project) => (
        <article
          key={project.project}
          className="overflow-hidden rounded-xl border-[3px] border-[#94a3b8] bg-tremor-background shadow-sm dark:border-white dark:bg-dark-tremor-background"
        >
          <header className="border-b-2 border-[#94a3b8] bg-slate-50 px-3 py-2.5 dark:border-white dark:bg-slate-900/40">
            <h3 className="text-sm font-bold text-tremor-content-strong dark:text-dark-tremor-content-strong">
              {project.project}
            </h3>
          </header>
          <ul className="divide-y-2 divide-[#cbd5e1] dark:divide-[#5a6f82]">
            {group.milestones.map((milestone) => {
              const cell = project.cells[milestone.slug];
              const dateTone = cell?.pct_complete_100
                ? "text-orange-600 dark:text-[#f09355]"
                : "text-tremor-content-strong dark:text-dark-tremor-content-strong";
              return (
                <li key={milestone.slug} className="px-3 py-3">
                  <div className="mb-2 flex flex-wrap items-center justify-between gap-2">
                    <span className="text-[13px] font-semibold leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      {milestone.title}
                    </span>
                    {statusPill(cell)}
                  </div>
                  <div className="grid grid-cols-3 gap-2 text-center text-[11px]">
                    <div className="rounded-lg border-2 border-[#cbd5e1] bg-slate-50 px-1.5 py-2 dark:border-[#5a6f82] dark:bg-slate-900/50">
                      <div className="mb-1 font-bold uppercase tracking-wide text-tremor-content dark:text-dark-tremor-content">
                        План
                      </div>
                      <div className={`tabular-nums font-semibold ${dateTone}`}>{cell?.plan ?? "Н/Д"}</div>
                    </div>
                    <div className="rounded-lg border-2 border-[#cbd5e1] bg-slate-50 px-1.5 py-2 dark:border-[#5a6f82] dark:bg-slate-900/50">
                      <div className="mb-1 font-bold uppercase tracking-wide text-tremor-content dark:text-dark-tremor-content">
                        Факт
                      </div>
                      <div className={`tabular-nums font-semibold ${dateTone}`}>{cell?.fact ?? "Н/Д"}</div>
                    </div>
                    <div className="rounded-lg border-2 border-[#cbd5e1] bg-slate-50 px-1.5 py-2 dark:border-[#5a6f82] dark:bg-slate-900/50">
                      <div className="mb-1 font-bold uppercase tracking-wide text-tremor-content dark:text-dark-tremor-content">
                        Откл.
                      </div>
                      <div className={`tabular-nums ${deviationClass(cell)}`}>{cell?.otkl ?? "Н/Д"}</div>
                    </div>
                  </div>
                </li>
              );
            })}
          </ul>
        </article>
      ))}
    </div>
  );
}

function ControlPointsDesktopTable({
  group,
  projects,
}: {
  group: Group;
  projects: ProjectRow[];
}) {
  const milestoneCount = Math.max(group.milestones.length, 1);
  const projectWidthPct = milestoneCount >= 5 ? 12 : 14;
  const statusWidthPct = milestoneCount >= 5 ? 2.2 : 2.5;
  const metricWidthPct = (100 - projectWidthPct - statusWidthPct * milestoneCount) / (milestoneCount * 3);

  return (
    <div className="hidden w-full min-w-0 p-1 pt-10 lg:block">
      <table className="w-full table-fixed border-separate border-spacing-0 border-[3px] border-[#94a3b8] text-center text-[10px] leading-tight dark:border-white xl:text-[11px]">
        <colgroup>
          <col style={{ width: `${projectWidthPct}%` }} />
          {group.milestones.flatMap((milestone) => [
            <col key={`${milestone.slug}-s`} style={{ width: `${statusWidthPct}%` }} />,
            <col key={`${milestone.slug}-p`} style={{ width: `${metricWidthPct}%` }} />,
            <col key={`${milestone.slug}-f`} style={{ width: `${metricWidthPct}%` }} />,
            <col key={`${milestone.slug}-o`} style={{ width: `${metricWidthPct}%` }} />,
          ])}
        </colgroup>
        <thead>
          <tr>
            <th
              rowSpan={2}
              className="sticky left-0 z-30 border-[3px] border-[#94a3b8] bg-[#e8f0fe] px-1 py-1.5 text-center font-bold text-[#111827] dark:border-white dark:bg-[#1a3328] dark:text-[#f0f4f8]"
            >
              Проект
            </th>
            {group.milestones.map((milestone) => (
              <th
                key={milestone.slug}
                colSpan={4}
                className={`${CELL} ${EDGE_L} ${EDGE_R} ${HEAD} px-0.5 py-1.5 font-bold leading-snug`}
              >
                <span className="line-clamp-2 break-words">{milestone.title}</span>
              </th>
            ))}
          </tr>
          <tr className="text-[9px] uppercase xl:text-[10px]">
            {group.milestones.flatMap((milestone) =>
              ["●", "План", "Факт", "Откл."].map((label, index) => (
                <th
                  key={`${milestone.slug}-${label}`}
                  className={`${CELL} ${HEAD} ${index === 0 ? EDGE_L : ""} ${index === 3 ? EDGE_R : ""} px-0.5 py-1 font-semibold`}
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
              <td
                className={`sticky left-0 z-10 ${CELL} ${EDGE_R} bg-[#f9fafb] px-1 py-1.5 text-left text-[10px] font-bold leading-snug text-[#111827] xl:text-[11px] dark:bg-[#161f2b] dark:text-[#f0f4f8]`}
              >
                <span className="line-clamp-2 break-words">{project.project}</span>
              </td>
              {group.milestones.flatMap((milestone) => {
                const cell = project.cells[milestone.slug];
                const body = `${CELL} min-w-0 bg-white px-0.5 py-1.5 tabular-nums dark:bg-[#0c1219]`;
                const dateTone = cell?.pct_complete_100 ? "text-orange-600 dark:text-[#f09355]" : "";
                return [
                  <td key={`${milestone.slug}-status`} className={`${body} ${EDGE_L}`}>
                    <span
                      className={`inline-block h-2.5 w-2.5 rounded-full ${cell?.status === "ok" ? "bg-emerald-500" : "bg-rose-500"}`}
                      aria-label={cell?.status === "ok" ? "В срок" : "Просрочено"}
                    />
                  </td>,
                  <td key={`${milestone.slug}-plan`} className={`${body} break-words font-semibold ${dateTone}`}>
                    {cell?.plan ?? "Н/Д"}
                  </td>,
                  <td key={`${milestone.slug}-fact`} className={`${body} break-words font-semibold ${dateTone}`}>
                    {cell?.fact ?? "Н/Д"}
                  </td>,
                  <td key={`${milestone.slug}-otkl`} className={`${body} ${EDGE_R} break-words ${deviationClass(cell)}`}>
                    {cell?.otkl ?? "Н/Д"}
                  </td>,
                ];
              })}
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

function ControlPointsGroup({
  group,
  projects,
}: {
  group: Group;
  projects: ProjectRow[];
}) {
  const titles = group.milestones.map((m) => m.title).join(" · ");
  return (
    <Card className="overflow-hidden rounded-xl border-[3px] border-[#94a3b8] p-0 dark:border-white">
      <div className="border-b-2 border-[#94a3b8] px-4 py-3 dark:border-white lg:hidden">
        <Text className="text-xs font-semibold text-tremor-content dark:text-dark-tremor-content">
          {titles}
        </Text>
      </div>
      <FullscreenPanel disabled={!projects.length} className="!overflow-x-hidden">
        <ControlPointsMobileCards group={group} projects={projects} />
        <ControlPointsDesktopTable group={group} projects={projects} />
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
          {(data?.groups ?? []).map((group) => (
            <ControlPointsGroup key={group.id} group={group} projects={projects} />
          ))}
          <DownloadTableButton getTable={() => (data ? buildExport(data) : null)} fileStem="control_points_matrix" />
        </div>
      )}
    </AppShell>
  );
}
