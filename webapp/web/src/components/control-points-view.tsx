"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text } from "@tremor/react";
import { fetchControlPoints, type ControlPointsPayload } from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import { StatusPill } from "@/components/status-pill";
import {
  FilterChipMulti,
  FilterFieldsRow,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import { multiFilterChips } from "@/lib/filters-summary";
import { useStickyHead } from "@/lib/use-sticky-head";
import { useUrlFilterState } from "@/lib/use-url-filter-state";
import type { ExportTable } from "@/lib/table-export";
import { DashboardEmptyState } from "@/components/dashboard-empty-state";
import { MobileFilterChips, MobilePaneTabs } from "@/components/mobile-ux";

const URL_INITIAL = { projects: [] as string[] };

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
    <div className="flex flex-col gap-3 px-2 pb-2 pt-3 lg:hidden">
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
  const headRef = useStickyHead([group.milestones]);
  const milestoneCount = Math.max(group.milestones.length, 1);
  const dense = milestoneCount >= 5;
  const projectWidthPct = dense ? 10 : 14;
  const statusWidthPct = dense ? 1.6 : 2.5;
  const metricWidthPct =
    (100 - projectWidthPct - statusWidthPct * milestoneCount) / (milestoneCount * 3);
  const edgeL = dense ? "border-l-2 border-l-[#94a3b8] dark:border-l-white" : EDGE_L;
  const edgeR = dense ? "border-r-2 border-r-[#94a3b8] dark:border-r-white" : EDGE_R;
  const cell = dense
    ? "border border-[#cbd5e1] dark:border-[#5a6f82] box-border max-w-0"
    : `${CELL} box-border max-w-0`;

  return (
    <div className="hidden p-1 lg:block">
      <div className="bi-table-scroll w-full min-w-0 max-w-full overflow-hidden">
      <table
        ref={headRef}
        className={`bi-sticky-head bi-sticky-col w-full max-w-full table-fixed border-collapse text-center leading-tight dark:border-white ${
          dense
            ? "border-2 border-[#94a3b8] text-[9px] xl:text-[10px]"
            : "border-[3px] border-[#94a3b8] text-[10px] xl:text-[11px]"
        }`}
      >
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
              className={`sticky left-0 z-30 bg-[#e8f0fe] px-0.5 py-1 text-center font-bold text-[#111827] dark:bg-[#1a3328] dark:text-[#f0f4f8] ${
                dense ? "border-2 border-[#94a3b8] dark:border-white" : "border-[3px] border-[#94a3b8] dark:border-white"
              }`}
            >
              Проект
            </th>
            {group.milestones.map((milestone) => (
              <th
                key={milestone.slug}
                colSpan={4}
                className={`${cell} ${edgeL} ${edgeR} ${HEAD} px-0 py-1 font-bold leading-snug`}
              >
                <span className="line-clamp-2 break-words hyphens-auto">{milestone.title}</span>
              </th>
            ))}
          </tr>
          <tr className="text-[8px] uppercase xl:text-[9px]">
            {group.milestones.flatMap((milestone) =>
              ["●", "План", "Факт", "Откл."].map((label, index) => (
                <th
                  key={`${milestone.slug}-${label}`}
                  className={`${cell} ${HEAD} ${index === 0 ? edgeL : ""} ${index === 3 ? edgeR : ""} px-0 py-0.5 font-semibold`}
                >
                  {label}
                </th>
              )),
            )}
          </tr>
        </thead>
        <tbody>
          {projects.map((project) => (
            <tr key={project.project} className="bi-row-alt">
              <td
                className={`sticky left-0 z-10 bg-[#f9fafb] px-0.5 py-1 text-left font-bold leading-snug text-[#111827] dark:bg-[#161f2b] dark:text-[#f0f4f8] ${
                  dense
                    ? "border border-[#cbd5e1] border-r-2 border-r-[#94a3b8] text-[9px] dark:border-[#5a6f82] dark:border-r-white xl:text-[10px]"
                    : `${CELL} ${EDGE_R} text-[10px] xl:text-[11px]`
                }`}
              >
                <span className="line-clamp-2 break-words">{project.project}</span>
              </td>
              {group.milestones.flatMap((milestone) => {
                const milestoneCell = project.cells[milestone.slug];
                const body = `${cell} bg-white px-0 py-1 text-center tabular-nums dark:bg-[#0c1219]`;
                const dateTone = milestoneCell?.pct_complete_100
                  ? "text-orange-600 dark:text-[#f09355]"
                  : "";
                return [
                  <td key={`${milestone.slug}-status`} className={`${body} ${edgeL}`}>
                    <span
                      className={`mx-auto block rounded-full ${
                        dense ? "h-2 w-2" : "h-2.5 w-2.5"
                      } ${milestoneCell?.status === "ok" ? "bg-emerald-500" : "bg-rose-500"}`}
                      aria-label={milestoneCell?.status === "ok" ? "В срок" : "Просрочено"}
                    />
                  </td>,
                  <td
                    key={`${milestone.slug}-plan`}
                    className={`${body} break-all font-semibold ${dateTone}`}
                  >
                    {milestoneCell?.plan ?? "Н/Д"}
                  </td>,
                  <td
                    key={`${milestone.slug}-fact`}
                    className={`${body} break-all font-semibold ${dateTone}`}
                  >
                    {milestoneCell?.fact ?? "Н/Д"}
                  </td>,
                  <td
                    key={`${milestone.slug}-otkl`}
                    className={`${body} ${edgeR} break-all ${deviationClass(milestoneCell)}`}
                  >
                    {milestoneCell?.otkl ?? "Н/Д"}
                  </td>,
                ];
              })}
            </tr>
          ))}
        </tbody>
      </table>
      </div>
    </div>
  );
}

function ControlPointsGroup({
  group,
  projects,
  mobileProjects,
}: {
  group: Group;
  projects: ProjectRow[];
  mobileProjects: ProjectRow[];
}) {
  const titles = group.milestones.map((m) => m.title).join(" · ");
  return (
    <Card className="overflow-hidden rounded-xl border-[3px] border-[#94a3b8] p-0 dark:border-white">
      <div className="border-b-2 border-[#94a3b8] px-4 py-3 dark:border-white lg:hidden">
        <Text className="text-xs font-semibold text-tremor-content dark:text-dark-tremor-content">
          {titles}
        </Text>
      </div>
      <ControlPointsMobileCards group={group} projects={mobileProjects} />
      <ControlPointsDesktopTable group={group} projects={projects} />
    </Card>
  );
}

export function ControlPointsView() {
  const [selected, setSelected] = useState<string[]>([]);
  const [data, setData] = useState<ControlPointsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [mobileTone, setMobileTone] = useState<"all" | "overdue">("all");
  const [mobileGroup, setMobileGroup] = useState<string>("");

  const load = useCallback(async (projects: string[]) => {
    setLoading(true);
    setError(null);
    try {
      setData(await fetchControlPoints(projects));
    } catch (cause) {
      setData(null);
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(selected);
  }, [load, selected]);

  const urlState = useMemo(() => ({ projects: selected }), [selected]);
  useUrlFilterState(urlState, URL_INITIAL, (patch) => {
    if (patch.projects) setSelected(patch.projects);
  }, { navId: "control-points" });

  const projects = useMemo(() => {
    const rows = data?.projects ?? [];
    if (!selected.length) return rows;
    const allow = new Set(selected);
    return rows.filter((row) => allow.has(row.project));
  }, [data?.projects, selected]);

  const mobileProjects = useMemo(() => {
    return projects.filter((row) => {
      if (mobileTone === "overdue") {
        const overdue = Object.values(row.cells).some(
          (cell) => cell?.status === "bad" || (cell?.otkl_days != null && cell.otkl_days < 0),
        );
        if (!overdue) return false;
      }
      return true;
    });
  }, [projects, mobileTone]);

  const groups = data?.groups ?? [];
  const metaError = data?.meta.error;
  const dirty = selected.length > 0;
  const activeGroupId =
    mobileGroup && groups.some((g) => g.id === mobileGroup)
      ? mobileGroup
      : groups[0]?.id ?? "";

  return (
    <AppShell title="Контрольные точки" loading={loading}>
      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((value) => !value)}
        activeFilters={multiFilterChips("projects", "Проект", selected, setSelected)}
        onReset={dirty ? () => setSelected([]) : undefined}
      >
        <FiltersReset disabled={!dirty} onClick={() => setSelected([])} />
        <FilterFieldsRow cols={2}>
          <FilterChipMulti
            label="Проект"
            values={selected}
            options={data?.filters.projects ?? []}
            onChange={setSelected}
          />
          <div />
        </FilterFieldsRow>
      </FiltersCard>

      {error || metaError ? <Card className="mb-4 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30"><Text className="text-rose-700 dark:text-rose-300">{error || metaError}</Text></Card> : null}
      {!projects.length ? (
        <DashboardEmptyState
          message={
            loading
              ? "Загрузка…"
              : dirty
                ? "Нет данных контрольных точек по выбранным фильтрам."
                : "Нет данных контрольных точек. Сделайте ingest в админке."
          }
          onReset={!loading && dirty ? () => setSelected([]) : undefined}
        />
      ) : (
        <div className="space-y-6">
          <div className="space-y-2 px-0 lg:hidden">
            <MobileFilterChips
              value={mobileTone}
              onChange={setMobileTone}
              options={[
                { id: "all", label: "Все" },
                { id: "overdue", label: "Только просрочка" },
              ]}
            />
            <p className="text-xs text-tremor-content dark:text-dark-tremor-content">
              Показано {mobileProjects.length} из {projects.length}
            </p>
          </div>
          {groups.length > 1 ? (
            <MobilePaneTabs
              value={activeGroupId}
              onChange={setMobileGroup}
              options={groups.map((group, index) => ({
                id: group.id,
                label:
                  group.milestones[0]?.title?.slice(0, 18) ||
                  `Блок ${index + 1}`,
              }))}
            />
          ) : null}
          <FullscreenPanel disabled={!projects.length || !groups.length} scroll={false}>
            {(zoomed) => (
              <div className={`space-y-6 ${zoomed ? "w-full max-w-none p-2 pt-10" : ""}`}>
                {groups.map((group) => (
                  <div
                    key={group.id}
                    className={
                      groups.length <= 1 || group.id === activeGroupId
                        ? "block"
                        : "hidden lg:block"
                    }
                  >
                    <ControlPointsGroup
                      group={group}
                      projects={projects}
                      mobileProjects={mobileProjects}
                    />
                  </div>
                ))}
              </div>
            )}
          </FullscreenPanel>
          <DownloadTableButton getTable={() => (data ? buildExport(data) : null)} fileStem="control_points_matrix" />
        </div>
      )}
    </AppShell>
  );
}
