"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useState,
  type CSSProperties,
} from "react";
import {
  BarChart,
  Card,
  DonutChart,
  Grid,
  LineChart,
  Metric,
  Text,
  Title,
} from "@tremor/react";
import {
  FilterCheck,
  FilterChecksRow,
  FilterField,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  fetchGdrsEquipment,
  fetchGdrsPeople,
  type GdrsPayload,
  type GdrsQuery,
} from "@/lib/api";
import {
  PLAN_FACT_DEVIATION_CATEGORIES,
  withRuPlanFactDeviation,
} from "@/lib/chart-ru";
import type { ExportCell, ExportTable } from "@/lib/table-export";

type ResourceKind = "people" | "equipment";
type SortState = { key: string; asc: boolean } | null;

type Filters = {
  projects: string[];
  contractors: string[];
  months: string[];
  plan_agg: string;
  skud_agg: string;
  dyn_agg: string;
  only_with_plan: boolean;
  ready: boolean;
};

const BORDER_L = "#d1d5db";
const BORDER_L_CELL = "#e5e7eb";

type GdrsPalette = {
  border: string;
  borderCell: string;
  thBg: string;
  thFg: string;
  cellFg: string;
  planBg: string;
  planHdr: string;
  planBold: string;
  skudBg: string;
  skudHdr: string;
  skudBold: string;
  devHdr: string;
  subtotalBg: string;
  grandBg: string;
  linkFg: string;
};

function gdrsPalette(dark: boolean): GdrsPalette {
  if (!dark) {
    return {
      border: BORDER_L,
      borderCell: BORDER_L_CELL,
      thBg: "#f3f4f6",
      thFg: "#111827",
      cellFg: "#111827",
      planBg: "#ecfdf5",
      planHdr: "#bbf7d0",
      planBold: "#bbf7d0",
      skudBg: "#eff6ff",
      skudHdr: "#bfdbfe",
      skudBold: "#e2e8f0",
      devHdr: "#fecaca",
      subtotalBg: "#f3f4f6",
      grandBg: "#bfdbfe",
      linkFg: "#1d4ed8",
    };
  }
  return {
    border: "#475569",
    borderCell: "#334155",
    thBg: "hsl(209, 55%, 12%)",
    thFg: "#f1f5f9",
    cellFg: "#e2e8f0",
    planBg: "rgba(16,185,129,0.18)",
    planHdr: "rgba(16,185,129,0.32)",
    planBold: "rgba(16,185,129,0.40)",
    skudBg: "rgba(59,130,246,0.18)",
    skudHdr: "rgba(59,130,246,0.32)",
    skudBold: "rgba(100,116,139,0.35)",
    devHdr: "rgba(248,113,113,0.28)",
    subtotalBg: "rgba(148,163,184,0.14)",
    grandBg: "rgba(59,130,246,0.28)",
    linkFg: "#93c5fd",
  };
}

/** Яркие сегменты donut — без slate/gray, которые сливаются с тёмным фоном. */
const DONUT_COLORS = [
  "cyan",
  "violet",
  "amber",
  "emerald",
  "rose",
  "blue",
  "orange",
  "fuchsia",
  "lime",
  "indigo",
  "pink",
] as const;

function useIsDark(): boolean {
  const [dark, setDark] = useState(false);
  useEffect(() => {
    const el = document.documentElement;
    const sync = () => setDark(el.classList.contains("dark"));
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);
  return dark;
}

const COPY: Record<
  ResourceKind,
  {
    title: string;
    subtitle: string;
    unitDay: string;
    matrixTitle: string;
    dynTitle: string;
    pieTitle: string;
    fileStem: string;
  }
> = {
  people: {
    title: "ГДРС (люди)",
    subtitle: "План из 1С (договоры) и факт СКУД — среднее число людей в день",
    unitDay: "Среднее число людей в день",
    matrixTitle: "ГДРС (люди)",
    dynTitle: "Динамика людей",
    pieTitle: "Распределение людей по контрагентам",
    fileStem: "gdrs_people",
  },
  equipment: {
    title: "ГДРС (техника)",
    subtitle:
      "План из 1С (договоры) и факт СКУД — среднее число единиц техники в день",
    unitDay: "Среднее число единиц техники в день",
    matrixTitle: "ГДРС (техника)",
    dynTitle: "Динамика техники",
    pieTitle: "Распределение техники по контрагентам",
    fileStem: "gdrs_equipment",
  },
};

function fmtInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return Math.round(n).toLocaleString("ru-RU");
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`;
}

function deviationStyle(num: number | null | undefined, dark = false) {
  if (num == null || Number.isNaN(num)) return {};
  if (num === 0) {
    return dark
      ? { backgroundColor: "rgba(70,214,138,0.2)", color: "#b8f5c8" }
      : { backgroundColor: "rgba(34,197,94,0.14)", color: "#15803d" };
  }
  if (num > 0) {
    return dark
      ? { backgroundColor: "rgba(70,214,138,0.28)", color: "#00e676" }
      : { backgroundColor: "rgba(34,197,94,0.22)", color: "#15803d" };
  }
  return dark
    ? { backgroundColor: "rgba(255,84,84,0.3)", color: "#ff6b6b" }
    : { backgroundColor: "rgba(248,113,113,0.28)", color: "#b91c1c" };
}

function parseSortableNumber(raw: unknown): number | null {
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (raw == null) return null;
  const s = String(raw).trim().replace("\u2212", "-").replace(",", ".");
  if (!s || s === "—" || s.toLowerCase() === "nan") return null;
  const n = Number(s.replace(/[^\d.+-]/g, ""));
  return Number.isFinite(n) ? n : null;
}

function compareVal(a: unknown, b: unknown): number {
  if (a == null && b == null) return 0;
  if (a == null || a === "" || a === "—") return 1;
  if (b == null || b === "" || b === "—") return -1;
  const na = parseSortableNumber(a);
  const nb = parseSortableNumber(b);
  if (na != null && nb != null) return na - nb;
  return String(a).localeCompare(String(b), "ru", {
    numeric: true,
    sensitivity: "base",
  });
}

function SortHeader({
  label,
  sortKey,
  sort,
  onSort,
  style,
  palette,
}: {
  label: string;
  sortKey: string;
  sort: SortState;
  onSort: (key: string) => void;
  style?: CSSProperties;
  palette: GdrsPalette;
}) {
  const active = sort?.key === sortKey;
  return (
    <th
      className="px-2 py-2 text-center text-xs font-semibold"
      style={{
        border: `1px solid ${palette.border}`,
        backgroundColor: palette.thBg,
        color: palette.thFg,
        position: "sticky",
        top: 0,
        zIndex: 2,
        ...style,
      }}
    >
      <button
        type="button"
        title="Сортировать по колонке"
        onClick={() => onSort(sortKey)}
        className="inline-flex w-full items-center justify-center gap-1"
        style={{ color: "inherit" }}
      >
        <span>{label}</span>
        <span
          className={
            active
              ? "font-bold text-emerald-600 dark:text-emerald-300"
              : "opacity-70"
          }
          aria-hidden
        >
          {active ? (sort?.asc ? "↑" : "↓") : "⇅"}
        </span>
      </button>
    </th>
  );
}

function useSortableRows<T extends Record<string, unknown>>(
  rows: T[],
  sort: SortState,
) {
  return useMemo(() => {
    if (!sort) return rows;
    const next = [...rows];
    next.sort((a, b) => {
      const cmp = compareVal(a[sort.key], b[sort.key]);
      return sort.asc ? cmp : -cmp;
    });
    return next;
  }, [rows, sort]);
}

function toggleSort(prev: SortState, key: string): SortState {
  if (prev?.key === key) return { key, asc: !prev.asc };
  return { key, asc: true };
}

async function fetchGdrs(
  kind: ResourceKind,
  query: GdrsQuery,
): Promise<GdrsPayload> {
  return kind === "equipment"
    ? fetchGdrsEquipment(query)
    : fetchGdrsPeople(query);
}

export function GdrsView({ resourceKind }: { resourceKind: ResourceKind }) {
  const copy = COPY[resourceKind];
  const dark = useIsDark();
  const pal = useMemo(() => gdrsPalette(dark), [dark]);
  const [filters, setFilters] = useState<Filters>({
    projects: [],
    contractors: [],
    months: [],
    plan_agg: "Среднее за месяц",
    skud_agg: "Среднее за месяц",
    dyn_agg: "День",
    only_with_plan: false,
    ready: false,
  });
  const [data, setData] = useState<GdrsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);

  const [projSort, setProjSort] = useState<SortState>(null);
  const [dynSort, setDynSort] = useState<SortState>(null);
  const [ctrSort, setCtrSort] = useState<SortState>(null);
  const [mtxSort, setMtxSort] = useState<SortState>(null);

  const load = useCallback(
    async (next: Filters) => {
      setLoading(true);
      setError(null);
      try {
        const payload = await fetchGdrs(resourceKind, {
          projects: next.projects,
          contractors: next.contractors,
          months: next.months,
          plan_agg: next.plan_agg,
          skud_agg: next.skud_agg,
          dyn_agg: next.dyn_agg,
          only_with_plan: next.only_with_plan,
        });
        setData(payload);
        if (!next.ready) {
          const sel = payload.filters.selected;
          setFilters({
            projects: sel.projects ?? [],
            contractors: sel.contractors ?? [],
            months: sel.months?.length
              ? sel.months
              : payload.filters.default_months,
            plan_agg: sel.plan_agg || "Среднее за месяц",
            skud_agg: sel.skud_agg || "Среднее за месяц",
            dyn_agg: sel.dyn_agg || "День",
            only_with_plan: Boolean(sel.only_with_plan),
            ready: true,
          });
        }
      } catch (cause) {
        setError(cause instanceof Error ? cause.message : String(cause));
        setData(null);
      } finally {
        setLoading(false);
      }
    },
    [resourceKind],
  );

  useEffect(() => {
    void load(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on filter fields only
  }, [
    filters.ready,
    filters.projects,
    filters.contractors,
    filters.months,
    filters.plan_agg,
    filters.skud_agg,
    filters.dyn_agg,
    filters.only_with_plan,
    load,
  ]);

  const kpis = data?.kpis ?? {
    plan: 0,
    fact: 0,
    deviation: 0,
    delta_pct: null,
  };

  const projectChart = useMemo(
    () =>
      withRuPlanFactDeviation(
        (data?.tremor.by_project ?? []).map((r) => ({
          name: r.name,
          plan: r.plan,
          fact: r.fact,
          deviation: r.deviation,
        })),
      ),
    [data?.tremor.by_project],
  );

  const contractorChart = useMemo(
    () =>
      withRuPlanFactDeviation(
        (data?.tremor.by_contractor ?? []).slice(0, 20).map((r) => ({
          name: r.name,
          plan: r.plan,
          fact: r.fact,
          deviation: r.deviation,
        })),
      ),
    [data?.tremor.by_contractor],
  );

  const pieData = data?.tremor.pie ?? data?.pie_rows ?? [];
  const dynamicsChart = useMemo(
    () =>
      (data?.tremor.dynamics ?? []).map((r) => ({
        period: r.period,
        План: r.plan,
        Факт: r.fact,
      })),
    [data?.tremor.dynamics],
  );

  const projectRows = useSortableRows(
    (data?.project_rows ?? []).map((r) => ({ ...r })),
    projSort,
  );
  const dynamicsRows = useSortableRows(
    (data?.dynamics_rows ?? []).map((r) => ({ ...r })),
    dynSort,
  );
  const contractorRows = useSortableRows(
    (data?.contractor_rows ?? []).map((r) => ({ ...r })),
    ctrSort,
  );
  const matrixRows = useSortableRows(
    (data?.matrix_rows ?? []).map((r) => ({ ...r })),
    mtxSort,
  );

  const matrixMeta = data?.matrix_meta ?? {
    show_week_columns: false,
    week_labels: [],
    week_plan_keys: [],
    week_skud_keys: [],
  };

  const toggleMulti = (
    key: "projects" | "contractors" | "months",
    value: string,
  ) => {
    setFilters((s) => {
      const cur = new Set(s[key]);
      if (cur.has(value)) cur.delete(value);
      else cur.add(value);
      return { ...s, [key]: Array.from(cur) };
    });
  };

  const resetFilters = () => {
    setFilters((s) => ({
      ...s,
      projects: [],
      contractors: [],
      months: data?.filters.default_months ?? [],
      plan_agg: "Среднее за месяц",
      skud_agg: "Среднее за месяц",
      dyn_agg: "День",
      only_with_plan: false,
    }));
  };

  const exportProjectTable = useCallback((): ExportTable | null => {
    const rows = data?.project_rows ?? [];
    if (!rows.length) return null;
    return {
      header: [["Проект", "План", "Факт", "Отклонение", "Отклонение %"]],
      rows: rows.map(
        (r): ExportCell[] => [
          r.project,
          r.plan,
          r.fact,
          r.deviation,
          r.delta_pct ?? "",
        ],
      ),
    };
  }, [data?.project_rows]);

  const exportMatrixTable = useCallback((): ExportTable | null => {
    const rows = data?.matrix_rows ?? [];
    if (!rows.length) return null;
    const weekPlan = matrixMeta.week_plan_keys ?? [];
    const weekSkud = matrixMeta.week_skud_keys ?? [];
    const weekLabels = matrixMeta.week_labels ?? [];
    const header = [
      "Контрагент",
      "Вид работ",
      "План",
      "СКУД",
      "Отклонение",
      "Отклонение %",
      ...weekPlan.map(
        (_, i) => `План ${weekLabels[i] ?? `${i + 1} нед`}`,
      ),
      ...weekSkud.map(
        (_, i) => `СКУД ${weekLabels[i] ?? `${i + 1} нед`}`,
      ),
    ];
    return {
      header: [header],
      rows: rows.map((r): ExportCell[] => [
        r.label,
        r.vid_raboty,
        r.plan,
        r.skud,
        r.deviation,
        r.delta_pct ?? "",
        ...weekPlan.map((k) => Number((r as Record<string, unknown>)[k] ?? 0)),
        ...weekSkud.map((k) => Number((r as Record<string, unknown>)[k] ?? 0)),
      ]),
    };
  }, [data?.matrix_rows, matrixMeta]);

  const exportDynamicsTable = useCallback((): ExportTable | null => {
    const rows = data?.dynamics_rows ?? [];
    if (!rows.length) return null;
    return {
      header: [["Период", "План", "Факт", "Отклонение", "Отклонение %"]],
      rows: rows.map(
        (r): ExportCell[] => [
          r.period,
          r.plan,
          r.fact,
          r.deviation,
          r.delta_pct ?? "",
        ],
      ),
    };
  }, [data?.dynamics_rows]);

  const exportContractorTable = useCallback((): ExportTable | null => {
    const rows = data?.contractor_rows ?? [];
    if (!rows.length) return null;
    return {
      header: [["Контрагент", "План", "Факт", "Отклонение", "Доля %"]],
      rows: rows.map(
        (r): ExportCell[] => [
          r.contractor,
          r.plan,
          r.fact,
          r.deviation,
          r.share_pct,
        ],
      ),
    };
  }, [data?.contractor_rows]);

  const pieTitle = data?.meta.pie_title ?? copy.pieTitle;
  const dynTitle = data?.meta.dyn_title ?? copy.dynTitle;
  const matrixTitle =
    data?.meta.matrix_title ?? copy.matrixTitle;

  const td = (extra?: CSSProperties): CSSProperties => ({
    border: `1px solid ${pal.borderCell}`,
    padding: "8px 10px",
    color: pal.cellFg,
    ...extra,
  });

  const dev = (n: number | null | undefined) => deviationStyle(n, dark);

  return (
    <AppShell title={copy.title} subtitle={copy.subtitle}>
      <FiltersCard open={filtersOpen} onToggle={() => setFiltersOpen((o) => !o)}>
        <FiltersReset onClick={resetFilters} />
        <FilterFieldsRow cols={5}>
          <MultiSelect
            label="Проект"
            options={data?.filters.projects ?? []}
            selected={filters.projects}
            placeholder="Все проекты"
            onToggle={(v) => toggleMulti("projects", v)}
            onClear={() => setFilters((s) => ({ ...s, projects: [] }))}
          />
          <MultiSelect
            label="Контрагент"
            options={data?.filters.contractors ?? []}
            selected={filters.contractors}
            placeholder="Все контрагенты"
            onToggle={(v) => toggleMulti("contractors", v)}
            onClear={() => setFilters((s) => ({ ...s, contractors: [] }))}
          />
          <MultiSelect
            label="Месяц"
            options={data?.filters.months ?? []}
            selected={filters.months}
            placeholder="Все месяцы"
            onToggle={(v) => toggleMulti("months", v)}
            onClear={() =>
              setFilters((s) => ({
                ...s,
                months: data?.filters.default_months ?? [],
              }))
            }
          />
          <FilterField label="План">
            <select
              className={FILTER_SELECT_CLASS}
              value={filters.plan_agg}
              onChange={(e) =>
                setFilters((s) => ({ ...s, plan_agg: e.target.value }))
              }
            >
              {(data?.filters.agg_options ?? ["Среднее за месяц"]).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </FilterField>
          <FilterField label="СКУД">
            <select
              className={FILTER_SELECT_CLASS}
              value={filters.skud_agg}
              onChange={(e) =>
                setFilters((s) => ({ ...s, skud_agg: e.target.value }))
              }
            >
              {(data?.filters.agg_options ?? ["Среднее за месяц"]).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </FilterField>
        </FilterFieldsRow>
        <FilterChecksRow cols={5}>
          <FilterCheck
            label="Только с планом"
            checked={filters.only_with_plan}
            onChange={(e) =>
              setFilters((s) => ({
                ...s,
                only_with_plan: e.target.checked,
              }))
            }
          />
          <div />
          <div />
          <div />
          <div />
        </FilterChecksRow>
        <Text className="mt-3">
          {data?.meta.period_label ? `${data.meta.period_label} · ` : ""}
          {loading
            ? "загрузка…"
            : `${data?.meta.rows ?? 0} строк`}
          {data?.meta.version_id != null
            ? ` · version_id=${data.meta.version_id}`
            : ""}
        </Text>
        {data?.meta.warning ? (
          <Text className="mt-2 text-amber-700 dark:text-amber-300">
            {data.meta.warning}
          </Text>
        ) : null}
      </FiltersCard>

      {error ? (
        <Card className="mb-6 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            API недоступен. {error}
          </Text>
        </Card>
      ) : null}

      <div className="space-y-6">
        <Grid numItemsSm={2} numItemsLg={4} className="gap-6">
          {[
            ["План", fmtInt(kpis.plan)],
            ["СКУД (факт)", fmtInt(kpis.fact)],
            ["Отклонение", fmtInt(kpis.deviation)],
            ["Отклонение %", fmtPct(kpis.delta_pct)],
          ].map(([title, metric]) => (
            <Card key={title} className="rounded-xl">
              <Text>{title}</Text>
              <Metric
                className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong"
                style={
                  title.startsWith("Отклонение")
                    ? dev(
                        title === "Отклонение %"
                          ? kpis.delta_pct
                          : kpis.deviation,
                      )
                    : undefined
                }
              >
                {metric}
              </Metric>
            </Card>
          ))}
        </Grid>

        <FullscreenPanel fill>
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              ГДРС по выбранным проектам
            </Title>
            <Text className="mt-1">{copy.unitDay}</Text>
            <BarChart
              className="mt-6 h-80"
              data={projectChart}
              index="name"
              categories={[...PLAN_FACT_DEVIATION_CATEGORIES]}
              colors={["blue", "emerald", "rose"]}
              valueFormatter={(v) => fmtInt(Number(v))}
              yAxisWidth={48}
              showLegend
              showAnimation
              showGridLines
            />
          </Card>
        </FullscreenPanel>

        <Card className="rounded-xl overflow-x-auto">
          <div className="mb-3 flex items-center justify-between gap-3">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              ГДРС по выбранным проектам
            </Title>
          </div>
          <table className="min-w-full text-sm" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <SortHeader
                  label="Проект"
                  sortKey="project"
                  sort={projSort}
                  onSort={(k) => setProjSort((s) => toggleSort(s, k))}
                  palette={pal}
                />
                <SortHeader
                  label="План"
                  sortKey="plan"
                  sort={projSort}
                  onSort={(k) => setProjSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.planHdr }}
                />
                <SortHeader
                  label="Факт"
                  sortKey="fact"
                  sort={projSort}
                  onSort={(k) => setProjSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.skudHdr }}
                />
                <SortHeader
                  label="Отклонение"
                  sortKey="deviation"
                  sort={projSort}
                  onSort={(k) => setProjSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.devHdr }}
                />
                <SortHeader
                  label="Отклонение %"
                  sortKey="delta_pct"
                  sort={projSort}
                  onSort={(k) => setProjSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.devHdr }}
                />
              </tr>
            </thead>
            <tbody>
              {projectRows.map((r) => (
                <tr key={r.project}>
                  <td style={td({ textAlign: "left" })}>{r.project}</td>
                  <td style={td({ textAlign: "right", backgroundColor: pal.planBg })}>
                    {fmtInt(r.plan)}
                  </td>
                  <td style={td({ textAlign: "right", backgroundColor: pal.skudBg })}>
                    {fmtInt(r.fact)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      ...dev(r.deviation),
                    })}
                  >
                    {fmtInt(r.deviation)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      ...dev(r.delta_pct),
                    })}
                  >
                    {fmtPct(r.delta_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3">
            <DownloadTableButton
              getTable={exportProjectTable}
              fileStem={`${copy.fileStem}_projects`}
              disabled={!projectRows.length}
            />
          </div>
        </Card>

        <FullscreenPanel fill>
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {pieTitle}
            </Title>
            <DonutChart
              className="mt-6 h-80"
              data={pieData}
              category="value"
              index="name"
              colors={[...DONUT_COLORS]}
              valueFormatter={(v) => fmtInt(Number(v))}
              showLabel
              showAnimation
            />
          </Card>
        </FullscreenPanel>

        <Card className="rounded-xl overflow-x-auto">
          <div className="mb-3 flex items-center justify-between gap-3">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {matrixTitle}
              {data?.meta.period_label ? `, ${data.meta.period_label}` : ""}
            </Title>
          </div>
          <table className="min-w-full text-sm" style={{ borderCollapse: "collapse" }}>
            <thead>
              {matrixMeta.show_week_columns && matrixMeta.week_labels.length ? (
                <tr>
                  <th
                    colSpan={2}
                    style={{
                      border: `1px solid ${pal.border}`,
                      backgroundColor: pal.thBg,
                      color: pal.thFg,
                    }}
                  />
                  <th
                    colSpan={3}
                    style={{
                      border: `1px solid ${pal.border}`,
                      backgroundColor: pal.planHdr,
                      color: pal.thFg,
                      textAlign: "center",
                      fontWeight: 700,
                    }}
                  >
                    План / СКУД / Откл.
                  </th>
                  <th
                    colSpan={1}
                    style={{
                      border: `1px solid ${pal.border}`,
                      backgroundColor: pal.devHdr,
                      color: pal.thFg,
                      textAlign: "center",
                      fontWeight: 700,
                    }}
                  >
                    Доля / откл.
                  </th>
                  <th
                    colSpan={matrixMeta.week_plan_keys.length}
                    style={{
                      border: `1px solid ${pal.border}`,
                      backgroundColor: pal.planHdr,
                      color: pal.thFg,
                      textAlign: "center",
                      fontWeight: 700,
                    }}
                  >
                    План по неделям
                  </th>
                  <th
                    colSpan={matrixMeta.week_skud_keys.length}
                    style={{
                      border: `1px solid ${pal.border}`,
                      backgroundColor: pal.skudHdr,
                      color: pal.thFg,
                      textAlign: "center",
                      fontWeight: 700,
                    }}
                  >
                    СКУД по неделям
                  </th>
                </tr>
              ) : null}
              <tr>
                <SortHeader
                  label="Контрагент"
                  sortKey="label"
                  sort={mtxSort}
                  onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                  palette={pal}
                />
                <SortHeader
                  label="Вид работ"
                  sortKey="vid_raboty"
                  sort={mtxSort}
                  onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                  palette={pal}
                />
                <SortHeader
                  label="План"
                  sortKey="plan"
                  sort={mtxSort}
                  onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.planHdr }}
                />
                <SortHeader
                  label="СКУД"
                  sortKey="skud"
                  sort={mtxSort}
                  onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.skudHdr }}
                />
                <SortHeader
                  label="Отклонение"
                  sortKey="deviation"
                  sort={mtxSort}
                  onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.devHdr }}
                />
                <SortHeader
                  label="Отклонение %"
                  sortKey="delta_pct"
                  sort={mtxSort}
                  onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.devHdr }}
                />
                {matrixMeta.show_week_columns
                  ? matrixMeta.week_plan_keys.map((k, i) => (
                      <SortHeader
                        key={k}
                        label={matrixMeta.week_labels[i] ?? k}
                        sortKey={k}
                        sort={mtxSort}
                        onSort={(key) => setMtxSort((s) => toggleSort(s, key))}
                        palette={pal}
                  style={{ backgroundColor: pal.planHdr }}
                      />
                    ))
                  : null}
                {matrixMeta.show_week_columns
                  ? matrixMeta.week_skud_keys.map((k, i) => (
                      <SortHeader
                        key={k}
                        label={matrixMeta.week_labels[i] ?? k}
                        sortKey={k}
                        sort={mtxSort}
                        onSort={(key) => setMtxSort((s) => toggleSort(s, key))}
                        palette={pal}
                  style={{ backgroundColor: pal.skudHdr }}
                      />
                    ))
                  : null}
              </tr>
            </thead>
            <tbody>
              {matrixRows.map((r, i) => {
                const bold =
                  r.kind === "subtotal" || r.kind === "grand_total";
                const rowBg =
                  r.kind === "grand_total"
                    ? pal.grandBg
                    : r.kind === "subtotal"
                      ? pal.subtotalBg
                      : undefined;
                return (
                  <tr key={`${r.kind}-${r.label}-${i}`}>
                    <td
                      style={td({
                        textAlign: "left",
                        fontWeight: bold ? 700 : 500,
                        backgroundColor: rowBg,
                        color:
                          r.kind === "row" ? pal.linkFg : undefined,
                      })}
                    >
                      {r.label}
                    </td>
                    <td style={td({ textAlign: "left", backgroundColor: rowBg })}>
                      {r.vid_raboty}
                    </td>
                    <td
                      style={td({
                        textAlign: "right",
                        fontWeight: bold ? 700 : undefined,
                        backgroundColor: bold ? pal.planBold : pal.planBg,
                      })}
                    >
                      {fmtInt(r.plan)}
                    </td>
                    <td
                      style={td({
                        textAlign: "right",
                        fontWeight: bold ? 700 : undefined,
                        backgroundColor: bold ? pal.skudBold : pal.skudBg,
                      })}
                    >
                      {fmtInt(r.skud)}
                    </td>
                    <td
                      style={td({
                        textAlign: "right",
                        fontWeight: bold ? 700 : undefined,
                        ...dev(r.deviation),
                      })}
                    >
                      {fmtInt(r.deviation)}
                    </td>
                    <td
                      style={td({
                        textAlign: "right",
                        fontWeight: bold ? 700 : undefined,
                        ...dev(r.delta_pct),
                      })}
                    >
                      {fmtPct(r.delta_pct)}
                    </td>
                    {matrixMeta.show_week_columns
                      ? matrixMeta.week_plan_keys.map((k) => (
                          <td
                            key={k}
                            style={td({
                              textAlign: "right",
                              backgroundColor: pal.planBg,
                            })}
                          >
                            {fmtInt(
                              Number(
                                (r as Record<string, unknown>)[k] ?? 0,
                              ),
                            )}
                          </td>
                        ))
                      : null}
                    {matrixMeta.show_week_columns
                      ? matrixMeta.week_skud_keys.map((k) => (
                          <td
                            key={k}
                            style={td({
                              textAlign: "right",
                              backgroundColor: pal.skudBg,
                            })}
                          >
                            {fmtInt(
                              Number(
                                (r as Record<string, unknown>)[k] ?? 0,
                              ),
                            )}
                          </td>
                        ))
                      : null}
                  </tr>
                );
              })}
            </tbody>
          </table>
          <div className="mt-3">
            <DownloadTableButton
              getTable={exportMatrixTable}
              fileStem={`${copy.fileStem}_matrix`}
              disabled={!matrixRows.length}
            />
          </div>
        </Card>

        <FullscreenPanel fill>
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              ГДРС по выбранным контрагентам
            </Title>
            <Text className="mt-1">Топ по плану</Text>
            <BarChart
              className="mt-6 h-96"
              data={contractorChart}
              index="name"
              categories={[...PLAN_FACT_DEVIATION_CATEGORIES]}
              colors={["blue", "emerald", "rose"]}
              valueFormatter={(v) => fmtInt(Number(v))}
              yAxisWidth={48}
              layout="vertical"
              showLegend
              showAnimation
              showGridLines
            />
          </Card>
        </FullscreenPanel>

        <FullscreenPanel fill>
          <Card className="rounded-xl">
            <div className="flex flex-wrap items-center justify-between gap-3">
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                {dynTitle}
              </Title>
              <div className="flex gap-2">
                {(data?.filters.dyn_agg_options ?? ["День", "Неделя", "Месяц"]).map(
                  (opt) => (
                    <button
                      key={opt}
                      type="button"
                      className={`rounded-full px-3 py-1 text-xs font-medium ${
                        filters.dyn_agg === opt
                          ? "bg-emerald-600 text-white"
                          : "bg-tremor-background-muted text-tremor-content dark:bg-dark-tremor-background-muted"
                      }`}
                      onClick={() =>
                        setFilters((s) => ({ ...s, dyn_agg: opt }))
                      }
                    >
                      {opt}
                    </button>
                  ),
                )}
              </div>
            </div>
            <Text className="mt-1">
              План и факт — среднее за день в периоде группировки
            </Text>
            <LineChart
              className="mt-6 h-80"
              data={dynamicsChart}
              index="period"
              categories={["План", "Факт"]}
              colors={["blue", "emerald"]}
              valueFormatter={(v) => fmtInt(Number(v))}
              yAxisWidth={48}
              showLegend
              showAnimation
              showGridLines
            />
          </Card>
        </FullscreenPanel>

        <Card className="rounded-xl overflow-x-auto">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong mb-3">
            Детализация по периодам
          </Title>
          <table className="min-w-full text-sm" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <SortHeader
                  label="Период"
                  sortKey="period"
                  sort={dynSort}
                  onSort={(k) => setDynSort((s) => toggleSort(s, k))}
                  palette={pal}
                />
                <SortHeader
                  label="План"
                  sortKey="plan"
                  sort={dynSort}
                  onSort={(k) => setDynSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.planHdr }}
                />
                <SortHeader
                  label="Факт"
                  sortKey="fact"
                  sort={dynSort}
                  onSort={(k) => setDynSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.skudHdr }}
                />
                <SortHeader
                  label="Отклонение"
                  sortKey="deviation"
                  sort={dynSort}
                  onSort={(k) => setDynSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.devHdr }}
                />
                <SortHeader
                  label="Отклонение %"
                  sortKey="delta_pct"
                  sort={dynSort}
                  onSort={(k) => setDynSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.devHdr }}
                />
              </tr>
            </thead>
            <tbody>
              {dynamicsRows.map((r) => (
                <tr key={r.period}>
                  <td style={td({ textAlign: "left" })}>{r.period}</td>
                  <td style={td({ textAlign: "right", backgroundColor: pal.planBg })}>
                    {fmtInt(r.plan)}
                  </td>
                  <td style={td({ textAlign: "right", backgroundColor: pal.skudBg })}>
                    {fmtInt(r.fact)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      ...dev(r.deviation),
                    })}
                  >
                    {fmtInt(r.deviation)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      ...dev(r.delta_pct),
                    })}
                  >
                    {fmtPct(r.delta_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3">
            <DownloadTableButton
              getTable={exportDynamicsTable}
              fileStem={`${copy.fileStem}_dynamics`}
              disabled={!dynamicsRows.length}
            />
          </div>
        </Card>

        <Card className="rounded-xl overflow-x-auto">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong mb-3">
            {pieTitle}
          </Title>
          <table className="min-w-full text-sm" style={{ borderCollapse: "collapse" }}>
            <thead>
              <tr>
                <SortHeader
                  label="Контрагент"
                  sortKey="contractor"
                  sort={ctrSort}
                  onSort={(k) => setCtrSort((s) => toggleSort(s, k))}
                  palette={pal}
                />
                <SortHeader
                  label="План"
                  sortKey="plan"
                  sort={ctrSort}
                  onSort={(k) => setCtrSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.planHdr }}
                />
                <SortHeader
                  label="Факт"
                  sortKey="fact"
                  sort={ctrSort}
                  onSort={(k) => setCtrSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.skudHdr }}
                />
                <SortHeader
                  label="Отклонение"
                  sortKey="deviation"
                  sort={ctrSort}
                  onSort={(k) => setCtrSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.devHdr }}
                />
                <SortHeader
                  label="Доля %"
                  sortKey="share_pct"
                  sort={ctrSort}
                  onSort={(k) => setCtrSort((s) => toggleSort(s, k))}
                  palette={pal}
                  style={{ backgroundColor: pal.devHdr }}
                />
              </tr>
            </thead>
            <tbody>
              {contractorRows.map((r) => (
                <tr key={r.contractor}>
                  <td style={td({ textAlign: "left" })}>{r.contractor}</td>
                  <td style={td({ textAlign: "right", backgroundColor: pal.planBg })}>
                    {fmtInt(r.plan)}
                  </td>
                  <td style={td({ textAlign: "right", backgroundColor: pal.skudBg })}>
                    {fmtInt(r.fact)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      ...dev(r.deviation),
                    })}
                  >
                    {fmtInt(r.deviation)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      ...dev(r.deviation),
                    })}
                  >
                    {fmtPct(r.share_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="mt-3">
            <DownloadTableButton
              getTable={exportContractorTable}
              fileStem={`${copy.fileStem}_contractors`}
              disabled={!contractorRows.length}
            />
          </div>
        </Card>
      </div>
    </AppShell>
  );
}

export function GdrsPeopleView() {
  return <GdrsView resourceKind="people" />;
}

export function GdrsEquipmentView() {
  return <GdrsView resourceKind="equipment" />;
}

function MultiSelect({
  label,
  options,
  selected,
  placeholder,
  onToggle,
  onClear,
}: {
  label: string;
  options: string[];
  selected: string[];
  placeholder: string;
  onToggle: (v: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const summary =
    selected.length === 0
      ? placeholder
      : selected.length <= 2
        ? selected.join(", ")
        : `${selected.length} выбрано`;

  return (
    <div className="relative block text-sm">
      <Text>{label}</Text>
      <button
        type="button"
        className="mt-1 flex w-full items-center justify-between rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-left text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="truncate">{summary}</span>
        <span className="ml-2 text-xs opacity-60">{open ? "▲" : "▼"}</span>
      </button>
      {open ? (
        <div className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-tremor-default border border-tremor-border bg-tremor-background p-2 shadow-lg dark:border-dark-tremor-border dark:bg-dark-tremor-background">
          <button
            type="button"
            className="mb-1 w-full rounded px-2 py-1 text-left text-xs text-tremor-content hover:bg-tremor-background-muted dark:hover:bg-dark-tremor-background-muted"
            onClick={() => {
              onClear();
              setOpen(false);
            }}
          >
            Сбросить
          </button>
          {options.map((o) => (
            <label
              key={o}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-tremor-background-muted dark:hover:bg-dark-tremor-background-muted"
            >
              <input
                type="checkbox"
                checked={selected.includes(o)}
                onChange={() => onToggle(o)}
              />
              <span className="truncate text-tremor-default">{o}</span>
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}
