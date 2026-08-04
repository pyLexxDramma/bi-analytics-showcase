"use client";

import {
  useCallback,
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
} from "react";
import {
  Card,
  Text,
  Title,
} from "@tremor/react";
import {
  FilterCheck,
  FilterChipMulti,
  FilterChipSelect,
  FilterChecksRow,
  FilterFieldsRow,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  GdrsContractorsPieChart,
  GdrsDynamicsLineChart,
  GdrsGroupedBarChart,
} from "@/components/gdrs-charts";
import {
  MobileCardStack,
  MobileEntityCard,
  MobileMetricGrid,
} from "@/components/mobile-entity-card";
import {
  fetchGdrsEquipment,
  fetchGdrsPeople,
  type GdrsPayload,
  type GdrsQuery,
} from "@/lib/api";
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
      skudBg: "#f8fafc",
      skudHdr: "#e2e8f0",
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
      skudBg: "rgba(148,163,184,0.15)",
      skudHdr: "rgba(148,163,184,0.32)",
    skudBold: "rgba(100,116,139,0.35)",
    devHdr: "rgba(248,113,113,0.28)",
    subtotalBg: "rgba(148,163,184,0.14)",
    grandBg: "rgba(59,130,246,0.28)",
    linkFg: "#93c5fd",
  };
}

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

function fmtSigned(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  const value = Math.round(n);
  return value > 0 ? `+${value.toLocaleString("ru-RU")}` : value.toLocaleString("ru-RU");
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
  stickyTop = 0,
  stickyLeft,
  zIndex = 2,
  className = "",
}: {
  label: string;
  sortKey: string;
  sort: SortState;
  onSort: (key: string) => void;
  style?: CSSProperties;
  palette: GdrsPalette;
  stickyTop?: number | string;
  stickyLeft?: number | string;
  zIndex?: number;
  className?: string;
}) {
  const active = sort?.key === sortKey;
  return (
    <th
      className={`px-2 py-2 text-center text-xs font-semibold ${className}`}
      style={{
        border: `1px solid ${palette.border}`,
        backgroundColor: palette.thBg,
        color: palette.thFg,
        position: "sticky",
        top: stickyTop,
        left: stickyLeft,
        zIndex,
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
  /** После первого ответа API только подставляем selected — повторный fetch не нужен. */
  const skipNextLoadRef = useRef(false);
  const loadSeqRef = useRef(0);

  const [projSort, setProjSort] = useState<SortState>(null);
  const [dynSort, setDynSort] = useState<SortState>(null);
  const [ctrSort, setCtrSort] = useState<SortState>(null);
  const [mtxSort, setMtxSort] = useState<SortState>(null);

  const load = useCallback(
    async (next: Filters) => {
      const seq = ++loadSeqRef.current;
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
        if (seq !== loadSeqRef.current) return;
        setData(payload);
        if (!next.ready) {
          const sel = payload.filters.selected;
          skipNextLoadRef.current = true;
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
        if (seq !== loadSeqRef.current) return;
        setError(cause instanceof Error ? cause.message : String(cause));
        setData(null);
      } finally {
        if (seq === loadSeqRef.current) setLoading(false);
      }
    },
    [resourceKind],
  );

  useEffect(() => {
    if (skipNextLoadRef.current) {
      skipNextLoadRef.current = false;
      return;
    }
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

  const pieData = data?.tremor.pie ?? data?.pie_rows ?? [];

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

  const contractorTotal = useMemo(() => {
    const rows = data?.contractor_rows ?? [];
    if (!rows.length) return null;
    const plan = rows.reduce((s, r) => s + Number(r.plan || 0), 0);
    const fact = rows.reduce((s, r) => s + Number(r.fact || 0), 0);
    const deviation = fact - plan;
    return {
      plan,
      fact,
      deviation,
      share_pct: 100,
    };
  }, [data?.contractor_rows]);

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
    <AppShell title={copy.title} subtitle={copy.subtitle} loading={loading}>
      <FiltersCard open={filtersOpen} onToggle={() => setFiltersOpen((o) => !o)}>
        <FiltersReset onClick={resetFilters} />
        <FilterFieldsRow cols={5}>
          <FilterChipMulti label="Проект" options={data?.filters.projects ?? []} values={filters.projects} onChange={(projects) => setFilters((s) => ({ ...s, projects }))} />
          <FilterChipMulti label="Контрагент" options={data?.filters.contractors ?? []} values={filters.contractors} onChange={(contractors) => setFilters((s) => ({ ...s, contractors }))} />
          <FilterChipMulti label="Месяц" options={data?.filters.months ?? []} values={filters.months} onChange={(months) => setFilters((s) => ({ ...s, months }))} />
          <FilterChipSelect label="План" value={filters.plan_agg} options={data?.filters.agg_options ?? ["Среднее за месяц"]} onChange={(plan_agg) => setFilters((s) => ({ ...s, plan_agg }))} />
          <FilterChipSelect label="СКУД" value={filters.skud_agg} options={data?.filters.agg_options ?? ["Среднее за месяц"]} onChange={(skud_agg) => setFilters((s) => ({ ...s, skud_agg }))} />
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
        <FullscreenPanel fill>
          {(zoomed) => <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              ГДРС по выбранным проектам
            </Title>
            <Text className="mt-1">{copy.unitDay}</Text>
            <div className="mt-4 hidden lg:block">
              <GdrsGroupedBarChart rows={data?.tremor.by_project ?? []} fullscreen={zoomed} />
            </div>
            <div className="mt-4 lg:hidden">
              <GdrsGroupedBarChart rows={data?.tremor.by_project ?? []} compact />
            </div>
          </Card>}
        </FullscreenPanel>

        <Card className="hidden overflow-x-auto rounded-xl lg:block">
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
                    {fmtSigned(r.deviation)}
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
              {data?.kpis && projectRows.length ? (
                <tr>
                  <td
                    style={td({
                      textAlign: "left",
                      fontWeight: 700,
                      backgroundColor: pal.grandBg,
                    })}
                  >
                    Итого
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      fontWeight: 700,
                      backgroundColor: pal.planBold,
                    })}
                  >
                    {fmtInt(data.kpis.plan)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      fontWeight: 700,
                      backgroundColor: pal.skudBold,
                    })}
                  >
                    {fmtInt(data.kpis.fact)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      fontWeight: 700,
                      ...dev(data.kpis.deviation),
                    })}
                  >
                    {fmtSigned(data.kpis.deviation)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      fontWeight: 700,
                      ...dev(data.kpis.delta_pct),
                    })}
                  >
                    {fmtPct(data.kpis.delta_pct)}
                  </td>
                </tr>
              ) : null}
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
          {(zoomed) => <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {pieTitle}
            </Title>
            <div className="mt-4 hidden lg:block">
              <GdrsContractorsPieChart rows={pieData} fullscreen={zoomed} />
            </div>
            <div className="mt-4 lg:hidden">
              <GdrsContractorsPieChart rows={pieData} compact />
            </div>
          </Card>}
        </FullscreenPanel>

        <Card className="hidden rounded-xl lg:block">
          <div className="mb-3 flex items-center justify-between gap-3">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {matrixTitle}
              {data?.meta.period_label ? `, ${data.meta.period_label}` : ""}
            </Title>
          </div>
          <div className="max-h-[min(70vh,42rem)] w-full min-w-0 overflow-auto overscroll-contain rounded-md border border-tremor-border dark:border-dark-tremor-border">
            <table
              className="min-w-full text-sm"
              style={{ borderCollapse: "separate", borderSpacing: 0 }}
            >
              <thead>
                {matrixMeta.show_week_columns && matrixMeta.week_labels.length ? (
                  <tr>
                    <th
                      colSpan={2}
                      style={{
                        border: `1px solid ${pal.border}`,
                        backgroundColor: pal.thBg,
                        color: pal.thFg,
                        position: "sticky",
                        top: 0,
                        left: 0,
                        zIndex: 6,
                        minWidth: "22rem",
                        boxShadow: "2px 0 0 0 rgba(0,0,0,0.06)",
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
                        position: "sticky",
                        top: 0,
                        zIndex: 5,
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
                        position: "sticky",
                        top: 0,
                        zIndex: 5,
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
                        position: "sticky",
                        top: 0,
                        zIndex: 5,
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
                        position: "sticky",
                        top: 0,
                        zIndex: 5,
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
                    stickyTop={matrixMeta.show_week_columns ? "2.5rem" : 0}
                    stickyLeft={0}
                    zIndex={6}
                    className="min-w-[12rem] max-w-[14rem]"
                    style={{
                      boxShadow: "2px 0 0 0 rgba(0,0,0,0.06)",
                    }}
                  />
                  <SortHeader
                    label="Вид работ"
                    sortKey="vid_raboty"
                    sort={mtxSort}
                    onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                    palette={pal}
                    stickyTop={matrixMeta.show_week_columns ? "2.5rem" : 0}
                    stickyLeft="12rem"
                    zIndex={6}
                    className="min-w-[10rem] max-w-[14rem]"
                    style={{
                      boxShadow: "2px 0 0 0 rgba(0,0,0,0.06)",
                    }}
                  />
                  <SortHeader
                    label="План"
                    sortKey="plan"
                    sort={mtxSort}
                    onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                    palette={pal}
                    stickyTop={matrixMeta.show_week_columns ? "2.5rem" : 0}
                    zIndex={4}
                    style={{ backgroundColor: pal.planHdr }}
                  />
                  <SortHeader
                    label="СКУД"
                    sortKey="skud"
                    sort={mtxSort}
                    onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                    palette={pal}
                    stickyTop={matrixMeta.show_week_columns ? "2.5rem" : 0}
                    zIndex={4}
                    style={{ backgroundColor: pal.skudHdr }}
                  />
                  <SortHeader
                    label="Отклонение"
                    sortKey="deviation"
                    sort={mtxSort}
                    onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                    palette={pal}
                    stickyTop={matrixMeta.show_week_columns ? "2.5rem" : 0}
                    zIndex={4}
                    style={{ backgroundColor: pal.devHdr }}
                  />
                  <SortHeader
                    label="Отклонение %"
                    sortKey="delta_pct"
                    sort={mtxSort}
                    onSort={(k) => setMtxSort((s) => toggleSort(s, k))}
                    palette={pal}
                    stickyTop={matrixMeta.show_week_columns ? "2.5rem" : 0}
                    zIndex={4}
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
                          stickyTop="2.5rem"
                          zIndex={4}
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
                          stickyTop="2.5rem"
                          zIndex={4}
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
                  const stickyBg =
                    rowBg ?? (dark ? "rgb(15 23 42)" : "#ffffff");
                  return (
                    <tr key={`${r.kind}-${r.label}-${i}`}>
                      <td
                        style={td({
                          textAlign: "left",
                          fontWeight: bold ? 700 : 500,
                          backgroundColor: stickyBg,
                          color:
                            r.kind === "row" ? pal.linkFg : undefined,
                          position: "sticky",
                          left: 0,
                          zIndex: 3,
                          minWidth: "12rem",
                          maxWidth: "14rem",
                          boxShadow: "2px 0 0 0 rgba(0,0,0,0.06)",
                        })}
                      >
                        {r.label}
                      </td>
                      <td
                        style={td({
                          textAlign: "left",
                          backgroundColor: stickyBg,
                          position: "sticky",
                          left: "12rem",
                          zIndex: 3,
                          minWidth: "10rem",
                          maxWidth: "14rem",
                          boxShadow: "2px 0 0 0 rgba(0,0,0,0.06)",
                        })}
                      >
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
                        {fmtSigned(r.deviation)}
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
          </div>
          <div className="mt-3">
            <DownloadTableButton
              getTable={exportMatrixTable}
              fileStem={`${copy.fileStem}_matrix`}
              disabled={!matrixRows.length}
            />
          </div>
        </Card>

        <FullscreenPanel fill>
          {(zoomed) => <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              ГДРС по выбранным контрагентам
            </Title>
            <Text className="mt-1">План, факт и отклонение по всем контрагентам</Text>
            <div className="mt-4 hidden lg:block">
              <GdrsGroupedBarChart rows={data?.tremor.by_contractor ?? []} contractors fullscreen={zoomed} />
            </div>
            <div className="mt-4 lg:hidden">
              <GdrsGroupedBarChart rows={data?.tremor.by_contractor ?? []} contractors compact />
            </div>
          </Card>}
        </FullscreenPanel>

        <FullscreenPanel fill>
          {(zoomed) => <Card className="rounded-xl">
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
            <div className="mt-4 hidden lg:block">
              <GdrsDynamicsLineChart rows={data?.tremor.dynamics ?? []} fullscreen={zoomed} />
            </div>
            <div className="mt-4 lg:hidden">
              <GdrsDynamicsLineChart rows={data?.tremor.dynamics ?? []} compact />
            </div>
          </Card>}
        </FullscreenPanel>

        <Card className="hidden overflow-x-auto rounded-xl lg:block">
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
                    {fmtSigned(r.deviation)}
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

        <Card className="hidden overflow-x-auto rounded-xl lg:block">
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
                    {fmtSigned(r.deviation)}
                  </td>
                  <td style={td({ textAlign: "right" })}>
                    {fmtPct(r.share_pct)}
                  </td>
                </tr>
              ))}
              {contractorTotal && contractorRows.length ? (
                <tr>
                  <td
                    style={td({
                      textAlign: "left",
                      fontWeight: 700,
                      backgroundColor: pal.grandBg,
                    })}
                  >
                    Итого
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      fontWeight: 700,
                      backgroundColor: pal.planBold,
                    })}
                  >
                    {fmtInt(contractorTotal.plan)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      fontWeight: 700,
                      backgroundColor: pal.skudBold,
                    })}
                  >
                    {fmtInt(contractorTotal.fact)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      fontWeight: 700,
                      ...dev(contractorTotal.deviation),
                    })}
                  >
                    {fmtSigned(contractorTotal.deviation)}
                  </td>
                  <td
                    style={td({
                      textAlign: "right",
                      fontWeight: 700,
                      backgroundColor: pal.grandBg,
                    })}
                  >
                    {fmtPct(contractorTotal.share_pct)}
                  </td>
                </tr>
              ) : null}
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
        <MobileCardStack>
          <MobileEntityCard title="ГДРС по выбранным проектам">
            <div className="space-y-2">
              {projectRows.map((row) => (
                <MobileMetricGrid
                  key={row.project}
                  columns={4}
                  items={[
                    { label: "Проект", value: row.project },
                    { label: "План", value: fmtInt(row.plan), highlight: "ok" },
                    { label: "СКУД", value: fmtInt(row.fact) },
                    { label: "Откл.", value: fmtSigned(row.deviation), highlight: row.deviation < 0 ? "bad" : "ok" },
                  ]}
                />
              ))}
            </div>
          </MobileEntityCard>
          <MobileEntityCard title={matrixTitle}>
            <div className="space-y-2">
              {matrixRows.map((row, index) => (
                <MobileMetricGrid
                  key={`${row.kind}-${row.label}-${index}`}
                  columns={4}
                  items={[
                    { label: "Контрагент", value: row.label },
                    { label: "План", value: fmtInt(row.plan), highlight: "ok" },
                    { label: "СКУД", value: fmtInt(row.skud) },
                    { label: "Откл.", value: fmtSigned(row.deviation), highlight: row.deviation < 0 ? "bad" : "ok" },
                  ]}
                />
              ))}
            </div>
          </MobileEntityCard>
          <MobileEntityCard title="Детализация по периодам">
            <div className="space-y-2">
              {dynamicsRows.map((row) => (
                <MobileMetricGrid
                  key={row.period}
                  columns={4}
                  items={[
                    { label: "Период", value: row.period },
                    { label: "План", value: fmtInt(row.plan), highlight: "ok" },
                    { label: "Факт", value: fmtInt(row.fact) },
                    { label: "Откл.", value: fmtSigned(row.deviation), highlight: row.deviation < 0 ? "bad" : "ok" },
                  ]}
                />
              ))}
            </div>
          </MobileEntityCard>
          <MobileEntityCard title={pieTitle}>
            <div className="space-y-2">
              {contractorRows.map((row) => (
                <MobileMetricGrid
                  key={row.contractor}
                  columns={4}
                  items={[
                    { label: "Контрагент", value: row.contractor },
                    { label: "План", value: fmtInt(row.plan), highlight: "ok" },
                    { label: "Факт", value: fmtInt(row.fact) },
                    { label: "Откл.", value: fmtSigned(row.deviation), highlight: row.deviation < 0 ? "bad" : "ok" },
                  ]}
                />
              ))}
            </div>
          </MobileEntityCard>
        </MobileCardStack>
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
