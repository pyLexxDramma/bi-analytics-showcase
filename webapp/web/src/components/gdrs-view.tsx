"use client";

import {
  useCallback,
  useEffect,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
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
} from "@/components/dashboard-filters";
import { buildFilterChips, filterChip } from "@/lib/filters-summary";
import { useDeferredUrlFilters } from "@/lib/use-url-filter-state";
import { tapFeedback } from "@/lib/haptics";
import { AclWidgetGate } from "@/lib/use-report-ui-acl";
import { AppShell } from "@/components/app-shell";
import { DashboardInsight } from "@/components/dashboard-insight";
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
  MobileDetailSheet,
  MobilePaneTabs,
  MobileSearchField,
  DashboardTableActions,
  DashboardTableTitle,
} from "@/components/mobile-ux";
import {
  fetchGdrsEquipment,
  fetchGdrsPeople,
  type GdrsPayload,
  type GdrsQuery,
} from "@/lib/api";
import { useRefreshTick } from "@/lib/refresh-context";
import { ChartTableSyncProvider, SyncTableRow } from "@/lib/chart-table-sync";
import { usePersistedTableSort } from "@/lib/use-persisted-table-sort";
import type { ExportCell, ExportTable } from "@/lib/table-export";

type ResourceKind = "people" | "equipment";
type SortState = { key: string; asc: boolean } | null;
type GdrsMobilePane = "charts" | "projects" | "matrix" | "detail";
type GdrsDetail =
  | { kind: "project"; project: string; plan: number; fact: number; deviation: number; delta_pct: number | null }
  | { kind: "matrix"; label: string; vid_raboty: string; plan: number; skud: number; deviation: number; delta_pct: number | null }
  | { kind: "dynamics"; period: string; plan: number; fact: number; deviation: number; delta_pct: number | null }
  | { kind: "contractor"; contractor: string; plan: number; fact: number; deviation: number; share_pct: number | null };

type Filters = {
  projects: string[];
  contractors: string[];
  months: string[];
  plan_agg: string;
  skud_agg: string;
  dyn_agg: string;
  only_with_plan: boolean;
};

/** Ключи фильтров в адресе; months в INITIAL и в draft/applied. */
const INITIAL: Filters = {
  projects: [],
  contractors: [],
  months: [],
  plan_agg: "Среднее за месяц",
  skud_agg: "Среднее за месяц",
  dyn_agg: "День",
  only_with_plan: false,
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

/**
 * Список строк внутри мобильной карточки: первые `limit`, остальное по кнопке.
 * Итоги и графики считаются по полному набору — режется только отображение.
 */
function MobileRowList<T>({
  rows,
  limit = 15,
  render,
}: {
  rows: T[];
  limit?: number;
  render: (row: T, index: number) => ReactNode;
}) {
  const [shown, setShown] = useState(limit);
  const visible = rows.slice(0, shown);
  const rest = rows.length - visible.length;
  return (
    <div className="space-y-2">
      {visible.map((row, index) => render(row, index))}
      {rest > 0 ? (
        <button
          type="button"
          className="bi-card-more"
          onClick={() => {
            tapFeedback();
            setShown(rows.length);
          }}
        >
          Показать все {rows.length}
        </button>
      ) : null}
    </div>
  );
}

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
  borderWidth = 1,
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
  borderWidth?: number;
}) {
  const active = sort?.key === sortKey;
  return (
    <th
      className={`px-2 py-2 text-center text-xs font-semibold ${className}`}
      style={{
        border: `${borderWidth}px solid ${palette.border}`,
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

async function fetchGdrs(
  kind: ResourceKind,
  query: GdrsQuery,
): Promise<GdrsPayload> {
  return kind === "equipment"
    ? fetchGdrsEquipment(query)
    : fetchGdrsPeople(query);
}

export function GdrsView({ resourceKind }: { resourceKind: ResourceKind }) {
  const refreshTick = useRefreshTick();
  const copy = COPY[resourceKind];
  const dark = useIsDark();
  const pal = useMemo(() => gdrsPalette(dark), [dark]);
  const {
    draft: filters,
    setDraft: setFilters,
    applied,
    commit,
    syncBoth,
    pending,
    dirty,
  } = useDeferredUrlFilters(INITIAL, {
    navId: resourceKind === "people" ? "gdrs-people" : "gdrs-equipment",
  });
  const [data, setData] = useState<GdrsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  /** После первого ответа API только подставляем selected — повторный fetch не нужен. */
  const skipNextLoadRef = useRef(false);
  const bootstrappedRef = useRef(false);
  const loadSeqRef = useRef(0);

  const sortScope = resourceKind === "people" ? "gdrs-people" : "gdrs-equipment";
  const [projSort, toggleProjSort] = usePersistedTableSort(`${sortScope}:proj`);
  const [dynSort, toggleDynSort] = usePersistedTableSort(`${sortScope}:dyn`);
  const [ctrSort, toggleCtrSort] = usePersistedTableSort(`${sortScope}:ctr`);
  const [mtxSort, toggleMtxSort] = usePersistedTableSort(`${sortScope}:mtx`);
  const matrixGroupHdrRef = useRef<HTMLTableRowElement>(null);
  const [matrixGroupHdrH, setMatrixGroupHdrH] = useState(40);
  const [mobilePane, setMobilePane] = useState<GdrsMobilePane>("charts");
  const [tableQuery, setTableQuery] = useState("");
  const [detail, setDetail] = useState<GdrsDetail | null>(null);
  const chartsRef = useRef<HTMLDivElement>(null);
  const projectsRef = useRef<HTMLDivElement>(null);
  const matrixRef = useRef<HTMLDivElement>(null);
  const detailRef = useRef<HTMLDivElement>(null);

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
        if (!bootstrappedRef.current) {
          bootstrappedRef.current = true;
          const sel = payload.filters.selected;
          skipNextLoadRef.current = true;
          syncBoth({
            projects: sel.projects ?? next.projects,
            contractors: sel.contractors ?? next.contractors,
            months: next.months.length
              ? next.months
              : sel.months?.length
                ? sel.months
                : payload.filters.default_months,
            plan_agg: sel.plan_agg || next.plan_agg,
            skud_agg: sel.skud_agg || next.skud_agg,
            dyn_agg: sel.dyn_agg || next.dyn_agg,
            only_with_plan: Boolean(sel.only_with_plan ?? next.only_with_plan),
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
    [resourceKind, syncBoth],
  );

  useEffect(() => {
    if (skipNextLoadRef.current) {
      skipNextLoadRef.current = false;
      return;
    }
    void load(applied);
  }, [applied, load, refreshTick]);

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

  const tableQueryNorm = tableQuery.trim().toLowerCase();
  const mobileMatrixRows = useMemo(() => {
    if (!tableQueryNorm) return matrixRows;
    return matrixRows.filter(
      (r) =>
        String(r.label ?? "").toLowerCase().includes(tableQueryNorm) ||
        String(r.vid_raboty ?? "").toLowerCase().includes(tableQueryNorm),
    );
  }, [matrixRows, tableQueryNorm]);
  const mobileDynamicsRows = useMemo(() => {
    if (!tableQueryNorm) return dynamicsRows;
    return dynamicsRows.filter((r) =>
      String(r.period ?? "").toLowerCase().includes(tableQueryNorm),
    );
  }, [dynamicsRows, tableQueryNorm]);
  const mobileContractorRows = useMemo(() => {
    if (!tableQueryNorm) return contractorRows;
    return contractorRows.filter((r) =>
      String(r.contractor ?? "").toLowerCase().includes(tableQueryNorm),
    );
  }, [contractorRows, tableQueryNorm]);

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
    const months = data?.filters.default_months ?? [];
    syncBoth({ ...INITIAL, months });
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

  const showMatrixWeeks =
    Boolean(matrixMeta.show_week_columns && matrixMeta.week_labels.length);
  const matrixHdrStickyTop = showMatrixWeeks ? matrixGroupHdrH || 40 : 0;
  const matrixHdrBorder = dark ? "#94a3b8" : "#4b5563";
  const matrixHdrPal = useMemo(
    () => ({ ...pal, border: matrixHdrBorder }),
    [pal, matrixHdrBorder],
  );

  useLayoutEffect(() => {
    if (!showMatrixWeeks) {
      setMatrixGroupHdrH(0);
      return;
    }
    const el = matrixGroupHdrRef.current;
    if (!el) return;
    const sync = () => {
      const h = Math.ceil(el.getBoundingClientRect().height);
      setMatrixGroupHdrH(h > 0 ? h : 0);
    };
    sync();
    const ro = new ResizeObserver(sync);
    ro.observe(el);
    return () => ro.disconnect();
  }, [showMatrixWeeks, matrixMeta.week_plan_keys.length, matrixMeta.week_skud_keys.length, dark, matrixRows.length]);

  const td = (extra?: CSSProperties): CSSProperties => ({
    border: `1px solid ${pal.borderCell}`,
    padding: "8px 10px",
    color: pal.cellFg,
    ...extra,
  });

  const dev = (n: number | null | undefined) => deviationStyle(n, dark);

  const defaultMonths = data?.filters.default_months ?? [];
  const monthsChanged =
    filters.months.length !== defaultMonths.length ||
    filters.months.some((m) => !defaultMonths.includes(m));

  const activeFilters = [
    ...buildFilterChips(
      filters,
      {
        plan_agg: "Среднее за месяц",
        skud_agg: "Среднее за месяц",
        dyn_agg: "День",
        only_with_plan: false,
      },
      [
        { key: "projects", name: "Проект" },
        { key: "contractors", name: "Контрагент" },
        { key: "plan_agg", name: "План" },
        { key: "skud_agg", name: "СКУД" },
        { key: "dyn_agg", name: "Динамика" },
        { key: "only_with_plan", name: "Только с планом", kind: "flag" },
      ],
      (patch) => setFilters((s) => ({ ...s, ...patch })),
    ),
    ...(monthsChanged
      ? [
          filterChip(
            "months",
            "Месяц",
            filters.months.length ? filters.months.join(", ") : "не выбран",
            () => setFilters((s) => ({ ...s, months: defaultMonths })),
          ),
        ]
      : []),
  ];

  return (
    <AppShell title={copy.title} subtitle={copy.subtitle} loading={loading}>
      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((o) => !o)}
        activeFilters={activeFilters}
        navId={resourceKind === "people" ? "gdrs-people" : "gdrs-equipment"}
        stickyPending
        onApply={commit}
        applyDisabled={!pending}
        onReset={dirty ? resetFilters : undefined}
        resetDisabled={!dirty}
      >
        <FilterFieldsRow cols={5}>
          <FilterChipMulti filterKey="projects" label="Проект" options={data?.filters.projects ?? []} values={filters.projects} onChange={(projects) => setFilters((s) => ({ ...s, projects }))} />
          <FilterChipMulti filterKey="contractors" label="Контрагент" options={data?.filters.contractors ?? []} values={filters.contractors} onChange={(contractors) => setFilters((s) => ({ ...s, contractors }))} />
          <FilterChipMulti filterKey="months" label="Месяц" options={data?.filters.months ?? []} values={filters.months} onChange={(months) => setFilters((s) => ({ ...s, months }))} />
          <FilterChipSelect filterKey="plan_agg" label="План" value={filters.plan_agg} options={data?.filters.agg_options ?? ["Среднее за месяц"]} onChange={(plan_agg) => setFilters((s) => ({ ...s, plan_agg }))} />
          <FilterChipSelect filterKey="skud_agg" label="СКУД" value={filters.skud_agg} options={data?.filters.agg_options ?? ["Среднее за месяц"]} onChange={(skud_agg) => setFilters((s) => ({ ...s, skud_agg }))} />
        </FilterFieldsRow>
        <FilterChecksRow cols={5}>
          <FilterCheck
            filterKey="only_with_plan"
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
        <DashboardInsight
          text={
            data?.kpis
              ? `План ${fmtInt(data.kpis.plan)} · факт ${fmtInt(data.kpis.fact)} · откл. ${fmtSigned(data.kpis.deviation)}`
              : null
          }
        />

        <MobilePaneTabs
          value={mobilePane}
          onChange={setMobilePane}
          options={[
            { id: "charts", label: "Графики" },
            { id: "projects", label: "Проекты" },
            { id: "matrix", label: "Матрица" },
            { id: "detail", label: "Детали" },
          ]}
        />

        <div
          ref={chartsRef}
          className={`scroll-mt-4 space-y-6 ${
            mobilePane === "charts" ? "block" : "hidden lg:block"
          }`}
        >
        <AclWidgetGate widgetId="chart_projects">
        <Card className="rounded-xl">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            ГДРС по выбранным проектам
          </Title>
          <Text className="mt-1">{copy.unitDay}</Text>
          <FullscreenPanel
            className="mt-2"
            fill
            disabled={!(data?.tremor.by_project?.length ?? 0)}
          >
            {(zoomed) => (
              <>
                <div className="hidden lg:block">
                  <GdrsGroupedBarChart
                    rows={data?.tremor.by_project ?? []}
                    fullscreen={zoomed}
                  />
                </div>
                <div className="lg:hidden">
                  <GdrsGroupedBarChart rows={data?.tremor.by_project ?? []} compact />
                </div>
              </>
            )}
          </FullscreenPanel>
        </Card>
        </AclWidgetGate>

        <AclWidgetGate widgetId="table_projects">
        <Card className="hidden overflow-x-auto rounded-xl lg:block">
          <DashboardTableTitle className="mb-0 border-0 px-0 py-0">
            ГДРС по выбранным проектам
          </DashboardTableTitle>
          <FullscreenPanel disabled={!projectRows.length} scroll={false}>
            <div className="bi-table-scroll overflow-auto">
              <table className="min-w-full text-sm" style={{ borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <SortHeader
                      label="Проект"
                      sortKey="project"
                      sort={projSort}
                      onSort={toggleProjSort}
                      palette={pal}
                    />
                    <SortHeader
                      label="План"
                      sortKey="plan"
                      sort={projSort}
                      onSort={toggleProjSort}
                      palette={pal}
                      style={{ backgroundColor: pal.planHdr }}
                    />
                    <SortHeader
                      label="Факт"
                      sortKey="fact"
                      sort={projSort}
                      onSort={toggleProjSort}
                      palette={pal}
                      style={{ backgroundColor: pal.skudHdr }}
                    />
                    <SortHeader
                      label="Отклонение"
                      sortKey="deviation"
                      sort={projSort}
                      onSort={toggleProjSort}
                      palette={pal}
                      style={{ backgroundColor: pal.devHdr }}
                    />
                    <SortHeader
                      label="Отклонение %"
                      sortKey="delta_pct"
                      sort={projSort}
                      onSort={toggleProjSort}
                      palette={pal}
                      style={{ backgroundColor: pal.devHdr }}
                    />
                  </tr>
                </thead>
                <tbody>
                  {projectRows.map((r) => (
                    <tr key={r.project} className="bi-row-alt">
                      <td style={td({ textAlign: "center" })}>{r.project}</td>
                      <td className="bi-num" style={td({ textAlign: "center", backgroundColor: pal.planBg })}>
                        {fmtInt(r.plan)}
                      </td>
                      <td className="bi-num" style={td({ textAlign: "center", backgroundColor: pal.skudBg })}>
                        {fmtInt(r.fact)}
                      </td>
                      <td
                        className="bi-num"
                        style={td({
                          textAlign: "center",
                          ...dev(r.deviation),
                        })}
                      >
                        {fmtSigned(r.deviation)}
                      </td>
                      <td
                        className="bi-num"
                        style={td({
                          textAlign: "center",
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
                          textAlign: "center",
                          fontWeight: 700,
                          backgroundColor: pal.grandBg,
                        })}
                      >
                        Итого
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
                          fontWeight: 700,
                          backgroundColor: pal.planBold,
                        })}
                      >
                        {fmtInt(data.kpis.plan)}
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
                          fontWeight: 700,
                          backgroundColor: pal.skudBold,
                        })}
                      >
                        {fmtInt(data.kpis.fact)}
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
                          fontWeight: 700,
                          ...dev(data.kpis.deviation),
                        })}
                      >
                        {fmtSigned(data.kpis.deviation)}
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
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
            </div>
          </FullscreenPanel>
          <DashboardTableActions className="mt-3 border-0 px-0 py-0">
            <DownloadTableButton
              getTable={exportProjectTable}
              fileStem={`${copy.fileStem}_projects`}
              disabled={!projectRows.length}
            />
          </DashboardTableActions>
        </Card>
        </AclWidgetGate>

        <AclWidgetGate widgetId="pie">
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
        </AclWidgetGate>

        <AclWidgetGate widgetId="matrix">
        <Card className="hidden rounded-xl lg:block">
          <DashboardTableTitle className="mb-0 border-0 px-0 py-0">
            {matrixTitle}
            {data?.meta.period_label ? `, ${data.meta.period_label}` : ""}
          </DashboardTableTitle>
          <FullscreenPanel disabled={!matrixRows.length} scroll={false}>
            <div className="bi-table-scroll w-full min-w-0 overflow-auto overscroll-contain rounded-md border-2 border-slate-500 dark:border-slate-400">
              <table
                className="min-w-full text-sm"
                style={{ borderCollapse: "separate", borderSpacing: 0 }}
              >
              <thead>
                {showMatrixWeeks ? (
                  <tr ref={matrixGroupHdrRef}>
                    <th
                      colSpan={2}
                      style={{
                        border: `2px solid ${matrixHdrBorder}`,
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
                        border: `2px solid ${matrixHdrBorder}`,
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
                        border: `2px solid ${matrixHdrBorder}`,
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
                        border: `2px solid ${matrixHdrBorder}`,
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
                        border: `2px solid ${matrixHdrBorder}`,
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
                    onSort={toggleMtxSort}
                    palette={matrixHdrPal}
                    borderWidth={2}
                    stickyTop={matrixHdrStickyTop}
                    stickyLeft={0}
                    zIndex={6}
                    className="min-w-[12rem] max-w-[14rem]"
                    style={{
                      boxShadow: "2px 0 0 0 rgba(0,0,0,0.06), 0 2px 0 0 rgba(0,0,0,0.12)",
                    }}
                  />
                  <SortHeader
                    label="Вид работ"
                    sortKey="vid_raboty"
                    sort={mtxSort}
                    onSort={toggleMtxSort}
                    palette={matrixHdrPal}
                    borderWidth={2}
                    stickyTop={matrixHdrStickyTop}
                    stickyLeft="12rem"
                    zIndex={6}
                    className="min-w-[10rem] max-w-[14rem]"
                    style={{
                      boxShadow: "2px 0 0 0 rgba(0,0,0,0.06), 0 2px 0 0 rgba(0,0,0,0.12)",
                    }}
                  />
                  <SortHeader
                    label="План"
                    sortKey="plan"
                    sort={mtxSort}
                    onSort={toggleMtxSort}
                    palette={matrixHdrPal}
                    borderWidth={2}
                    stickyTop={matrixHdrStickyTop}
                    zIndex={4}
                    style={{
                      backgroundColor: pal.planHdr,
                      boxShadow: "0 2px 0 0 rgba(0,0,0,0.12)",
                    }}
                  />
                  <SortHeader
                    label="СКУД"
                    sortKey="skud"
                    sort={mtxSort}
                    onSort={toggleMtxSort}
                    palette={matrixHdrPal}
                    borderWidth={2}
                    stickyTop={matrixHdrStickyTop}
                    zIndex={4}
                    style={{
                      backgroundColor: pal.skudHdr,
                      boxShadow: "0 2px 0 0 rgba(0,0,0,0.12)",
                    }}
                  />
                  <SortHeader
                    label="Отклонение"
                    sortKey="deviation"
                    sort={mtxSort}
                    onSort={toggleMtxSort}
                    palette={matrixHdrPal}
                    borderWidth={2}
                    stickyTop={matrixHdrStickyTop}
                    zIndex={4}
                    style={{
                      backgroundColor: pal.devHdr,
                      boxShadow: "0 2px 0 0 rgba(0,0,0,0.12)",
                    }}
                  />
                  <SortHeader
                    label="Отклонение %"
                    sortKey="delta_pct"
                    sort={mtxSort}
                    onSort={toggleMtxSort}
                    palette={matrixHdrPal}
                    borderWidth={2}
                    stickyTop={matrixHdrStickyTop}
                    zIndex={4}
                    style={{
                      backgroundColor: pal.devHdr,
                      boxShadow: "0 2px 0 0 rgba(0,0,0,0.12)",
                    }}
                  />
                  {showMatrixWeeks
                    ? matrixMeta.week_plan_keys.map((k, i) => (
                        <SortHeader
                          key={k}
                          label={matrixMeta.week_labels[i] ?? k}
                          sortKey={k}
                          sort={mtxSort}
                          onSort={toggleMtxSort}
                          palette={matrixHdrPal}
                          borderWidth={2}
                          stickyTop={matrixHdrStickyTop}
                          zIndex={4}
                          style={{
                            backgroundColor: pal.planHdr,
                            boxShadow: "0 2px 0 0 rgba(0,0,0,0.12)",
                          }}
                        />
                      ))
                    : null}
                  {showMatrixWeeks
                    ? matrixMeta.week_skud_keys.map((k, i) => (
                        <SortHeader
                          key={k}
                          label={matrixMeta.week_labels[i] ?? k}
                          sortKey={k}
                          sort={mtxSort}
                          onSort={toggleMtxSort}
                          palette={matrixHdrPal}
                          borderWidth={2}
                          stickyTop={matrixHdrStickyTop}
                          zIndex={4}
                          style={{
                            backgroundColor: pal.skudHdr,
                            boxShadow: "0 2px 0 0 rgba(0,0,0,0.12)",
                          }}
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
                          textAlign: "center",
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
                          textAlign: "center",
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
                          textAlign: "center",
                          fontWeight: bold ? 700 : undefined,
                          backgroundColor: bold ? pal.planBold : pal.planBg,
                        })}
                      >
                        {fmtInt(r.plan)}
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
                          fontWeight: bold ? 700 : undefined,
                          backgroundColor: bold ? pal.skudBold : pal.skudBg,
                        })}
                      >
                        {fmtInt(r.skud)}
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
                          fontWeight: bold ? 700 : undefined,
                          ...dev(r.deviation),
                        })}
                      >
                        {fmtSigned(r.deviation)}
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
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
                                textAlign: "center",
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
                                textAlign: "center",
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
          </FullscreenPanel>
          <DashboardTableActions className="mt-3 border-0 px-0 py-0">
            <DownloadTableButton
              getTable={exportMatrixTable}
              fileStem={`${copy.fileStem}_matrix`}
              disabled={!matrixRows.length}
            />
          </DashboardTableActions>
        </Card>
        </AclWidgetGate>

        <Card className="rounded-xl">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            ГДРС по выбранным контрагентам
          </Title>
          <Text className="mt-1">План, факт и отклонение по всем контрагентам</Text>
          <FullscreenPanel
            className="mt-2"
            fill
            disabled={!(data?.tremor.by_contractor?.length ?? 0)}
          >
            {(zoomed) => (
              <>
                <div className="hidden lg:block">
                  <GdrsGroupedBarChart
                    rows={data?.tremor.by_contractor ?? []}
                    contractors
                    fullscreen={zoomed}
                  />
                </div>
                <div className="lg:hidden">
                  <GdrsGroupedBarChart
                    rows={data?.tremor.by_contractor ?? []}
                    contractors
                    compact
                  />
                </div>
              </>
            )}
          </FullscreenPanel>
        </Card>

        <AclWidgetGate widgetId="dynamics">
        <ChartTableSyncProvider>
        <FullscreenPanel
          fill
          pngFileStem={`${copy.fileStem}_dynamics_chart`}
        >
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
                        syncBoth({ dyn_agg: opt })
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
              <GdrsDynamicsLineChart
                rows={data?.tremor.dynamics ?? []}
                fullscreen={zoomed}
                tableSync
              />
            </div>
            <div className="mt-4 lg:hidden">
              <GdrsDynamicsLineChart
                rows={data?.tremor.dynamics ?? []}
                compact
                tableSync
              />
            </div>
          </Card>}
        </FullscreenPanel>

        <Card className="hidden overflow-x-auto rounded-xl lg:block">
          <DashboardTableTitle className="mb-0 border-0 px-0 py-0">
            Детализация по периодам
          </DashboardTableTitle>
          <FullscreenPanel disabled={!dynamicsRows.length} scroll={false}>
            <div className="bi-table-scroll overflow-auto">
              <table className="min-w-full text-sm" style={{ borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <SortHeader
                      label="Период"
                      sortKey="period"
                      sort={dynSort}
                      onSort={toggleDynSort}
                      palette={pal}
                    />
                    <SortHeader
                      label="План"
                      sortKey="plan"
                      sort={dynSort}
                      onSort={toggleDynSort}
                      palette={pal}
                      style={{ backgroundColor: pal.planHdr }}
                    />
                    <SortHeader
                      label="Факт"
                      sortKey="fact"
                      sort={dynSort}
                      onSort={toggleDynSort}
                      palette={pal}
                      style={{ backgroundColor: pal.skudHdr }}
                    />
                    <SortHeader
                      label="Отклонение"
                      sortKey="deviation"
                      sort={dynSort}
                      onSort={toggleDynSort}
                      palette={pal}
                      style={{ backgroundColor: pal.devHdr }}
                    />
                    <SortHeader
                      label="Отклонение %"
                      sortKey="delta_pct"
                      sort={dynSort}
                      onSort={toggleDynSort}
                      palette={pal}
                      style={{ backgroundColor: pal.devHdr }}
                    />
                  </tr>
                </thead>
                <tbody>
                  {dynamicsRows.map((r) => (
                    <SyncTableRow key={r.period} syncKey={r.period} className="bi-row-alt">
                      <td style={td({ textAlign: "center" })}>{r.period}</td>
                      <td className="bi-num" style={td({ textAlign: "center", backgroundColor: pal.planBg })}>
                        {fmtInt(r.plan)}
                      </td>
                      <td className="bi-num" style={td({ textAlign: "center", backgroundColor: pal.skudBg })}>
                        {fmtInt(r.fact)}
                      </td>
                      <td
                        className="bi-num"
                        style={td({
                          textAlign: "center",
                          ...dev(r.deviation),
                        })}
                      >
                        {fmtSigned(r.deviation)}
                      </td>
                      <td
                        className="bi-num"
                        style={td({
                          textAlign: "center",
                          ...dev(r.delta_pct),
                        })}
                      >
                        {fmtPct(r.delta_pct)}
                      </td>
                    </SyncTableRow>
                  ))}
                </tbody>
              </table>
            </div>
          </FullscreenPanel>
          <DashboardTableActions className="mt-3 border-0 px-0 py-0">
            <DownloadTableButton
              getTable={exportDynamicsTable}
              fileStem={`${copy.fileStem}_dynamics`}
              disabled={!dynamicsRows.length}
            />
          </DashboardTableActions>
        </Card>
        </ChartTableSyncProvider>
        </AclWidgetGate>

        <Card className="hidden overflow-x-auto rounded-xl lg:block">
          <DashboardTableTitle className="mb-0 border-0 px-0 py-0">
            {pieTitle}
          </DashboardTableTitle>
          <FullscreenPanel disabled={!contractorRows.length} scroll={false}>
            <div className="bi-table-scroll overflow-auto">
              <table className="min-w-full text-sm" style={{ borderCollapse: "collapse" }}>
                <thead>
                  <tr>
                    <SortHeader
                      label="Контрагент"
                      sortKey="contractor"
                      sort={ctrSort}
                      onSort={toggleCtrSort}
                      palette={pal}
                    />
                    <SortHeader
                      label="План"
                      sortKey="plan"
                      sort={ctrSort}
                      onSort={toggleCtrSort}
                      palette={pal}
                      style={{ backgroundColor: pal.planHdr }}
                    />
                    <SortHeader
                      label="Факт"
                      sortKey="fact"
                      sort={ctrSort}
                      onSort={toggleCtrSort}
                      palette={pal}
                      style={{ backgroundColor: pal.skudHdr }}
                    />
                    <SortHeader
                      label="Отклонение"
                      sortKey="deviation"
                      sort={ctrSort}
                      onSort={toggleCtrSort}
                      palette={pal}
                      style={{ backgroundColor: pal.devHdr }}
                    />
                    <SortHeader
                      label="Доля %"
                      sortKey="share_pct"
                      sort={ctrSort}
                      onSort={toggleCtrSort}
                      palette={pal}
                      style={{ backgroundColor: pal.devHdr }}
                    />
                  </tr>
                </thead>
                <tbody>
                  {contractorRows.map((r) => (
                    <tr key={r.contractor} className="bi-row-alt">
                      <td style={td({ textAlign: "center" })}>{r.contractor}</td>
                      <td className="bi-num" style={td({ textAlign: "center", backgroundColor: pal.planBg })}>
                        {fmtInt(r.plan)}
                      </td>
                      <td className="bi-num" style={td({ textAlign: "center", backgroundColor: pal.skudBg })}>
                        {fmtInt(r.fact)}
                      </td>
                      <td
                        className="bi-num"
                        style={td({
                          textAlign: "center",
                          ...dev(r.deviation),
                        })}
                      >
                        {fmtSigned(r.deviation)}
                      </td>
                      <td className="bi-num" style={td({ textAlign: "center" })}>
                        {fmtPct(r.share_pct)}
                      </td>
                    </tr>
                  ))}
                  {contractorTotal && contractorRows.length ? (
                    <tr>
                      <td
                        style={td({
                          textAlign: "center",
                          fontWeight: 700,
                          backgroundColor: pal.grandBg,
                        })}
                      >
                        Итого
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
                          fontWeight: 700,
                          backgroundColor: pal.planBold,
                        })}
                      >
                        {fmtInt(contractorTotal.plan)}
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
                          fontWeight: 700,
                          backgroundColor: pal.skudBold,
                        })}
                      >
                        {fmtInt(contractorTotal.fact)}
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
                          fontWeight: 700,
                          ...dev(contractorTotal.deviation),
                        })}
                      >
                        {fmtSigned(contractorTotal.deviation)}
                      </td>
                      <td
                        style={td({
                          textAlign: "center",
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
            </div>
          </FullscreenPanel>
          <DashboardTableActions className="mt-3 border-0 px-0 py-0">
            <DownloadTableButton
              getTable={exportContractorTable}
              fileStem={`${copy.fileStem}_contractors`}
              disabled={!contractorRows.length}
            />
          </DashboardTableActions>
        </Card>
        </div>

        <div
          ref={projectsRef}
          className={`scroll-mt-4 ${
            mobilePane === "projects" ? "block" : "hidden"
          } lg:hidden`}
        >
          <div className="mb-2 space-y-2 px-2">
            <p className="text-xs text-tremor-content dark:text-dark-tremor-content">
              Проектов {projectRows.length}. Тап — детали. Список задаётся в
              «Фильтрах».
            </p>
          </div>
          <MobileCardStack>
            {projectRows.map((row) => (
              <button
                key={row.project}
                type="button"
                className="w-full text-left"
                onClick={() => {
                  tapFeedback();
                  setDetail({
                    kind: "project",
                    project: row.project,
                    plan: row.plan,
                    fact: row.fact,
                    deviation: row.deviation,
                    delta_pct: row.delta_pct,
                  });
                }}
              >
                <MobileEntityCard
                  title={row.project}
                  badge={fmtSigned(row.deviation)}
                  badgeTone={row.deviation < 0 ? "bad" : "ok"}
                >
                  <MobileMetricGrid
                    columns={2}
                    items={[
                      { label: "План", value: fmtInt(row.plan), highlight: "ok" },
                      { label: "СКУД", value: fmtInt(row.fact) },
                    ]}
                  />
                </MobileEntityCard>
              </button>
            ))}
          </MobileCardStack>
        </div>

        <div
          ref={matrixRef}
          className={`scroll-mt-4 ${
            mobilePane === "matrix" ? "block" : "hidden"
          } lg:hidden`}
        >
          <div className="mb-2 space-y-2 px-2">
            <MobileSearchField
              value={tableQuery}
              onChange={setTableQuery}
              placeholder="Поиск контрагента / вида работ"
            />
            <p className="text-xs text-tremor-content dark:text-dark-tremor-content">
              Показано {mobileMatrixRows.length} из {matrixRows.length}. Тап — детали.
            </p>
          </div>
          <MobileCardStack>
            {mobileMatrixRows.map((row, index) => (
              <button
                key={`${row.kind}-${row.label}-${index}`}
                type="button"
                className="w-full text-left"
                onClick={() => {
                  tapFeedback();
                  setDetail({
                    kind: "matrix",
                    label: row.label,
                    vid_raboty: String(row.vid_raboty ?? ""),
                    plan: row.plan,
                    skud: row.skud,
                    deviation: row.deviation,
                    delta_pct: row.delta_pct,
                  });
                }}
              >
                <MobileEntityCard
                  title={row.label}
                  badge={fmtSigned(row.deviation)}
                  badgeTone={row.deviation < 0 ? "bad" : "ok"}
                >
                  <MobileMetricGrid
                    columns={2}
                    items={[
                      { label: "Вид работ", value: row.vid_raboty || "—" },
                      { label: "План", value: fmtInt(row.plan), highlight: "ok" },
                      { label: "СКУД", value: fmtInt(row.skud) },
                      {
                        label: "Откл.",
                        value: fmtSigned(row.deviation),
                        highlight: row.deviation < 0 ? "bad" : "ok",
                      },
                    ]}
                  />
                </MobileEntityCard>
              </button>
            ))}
          </MobileCardStack>
        </div>

        <div
          ref={detailRef}
          className={`scroll-mt-4 space-y-4 ${
            mobilePane === "detail" ? "block" : "hidden"
          } lg:hidden`}
        >
          <div className="space-y-2 px-2">
            <MobileSearchField
              value={tableQuery}
              onChange={setTableQuery}
              placeholder="Поиск периода / контрагента"
            />
          </div>
          <MobileCardStack>
            <MobileEntityCard title="Детализация по периодам">
              <MobileRowList
                rows={mobileDynamicsRows}
                render={(row) => (
                  <button
                    key={row.period}
                    type="button"
                    className="w-full text-left"
                    onClick={() => {
                      tapFeedback();
                      setDetail({
                        kind: "dynamics",
                        period: row.period,
                        plan: row.plan,
                        fact: row.fact,
                        deviation: row.deviation,
                        delta_pct: row.delta_pct,
                      });
                    }}
                  >
                    <MobileMetricGrid
                      columns={4}
                      items={[
                        { label: "Период", value: row.period },
                        { label: "План", value: fmtInt(row.plan), highlight: "ok" },
                        { label: "Факт", value: fmtInt(row.fact) },
                        {
                          label: "Откл.",
                          value: fmtSigned(row.deviation),
                          highlight: row.deviation < 0 ? "bad" : "ok",
                        },
                      ]}
                    />
                  </button>
                )}
              />
            </MobileEntityCard>
            <MobileEntityCard title={pieTitle}>
              <MobileRowList
                rows={mobileContractorRows}
                render={(row) => (
                  <button
                    key={row.contractor}
                    type="button"
                    className="w-full text-left"
                    onClick={() => {
                      tapFeedback();
                      setDetail({
                        kind: "contractor",
                        contractor: row.contractor,
                        plan: row.plan,
                        fact: row.fact,
                        deviation: row.deviation,
                        share_pct: row.share_pct,
                      });
                    }}
                  >
                    <MobileMetricGrid
                      columns={4}
                      items={[
                        { label: "Контрагент", value: row.contractor },
                        { label: "План", value: fmtInt(row.plan), highlight: "ok" },
                        { label: "Факт", value: fmtInt(row.fact) },
                        {
                          label: "Откл.",
                          value: fmtSigned(row.deviation),
                          highlight: row.deviation < 0 ? "bad" : "ok",
                        },
                      ]}
                    />
                  </button>
                )}
              />
            </MobileEntityCard>
          </MobileCardStack>
        </div>

        <MobileDetailSheet
          open={detail != null}
          onClose={() => setDetail(null)}
          title={
            detail?.kind === "project"
              ? detail.project
              : detail?.kind === "matrix"
                ? detail.label
                : detail?.kind === "dynamics"
                  ? detail.period
                  : detail?.kind === "contractor"
                    ? detail.contractor
                    : "Детали"
          }
        >
          {detail?.kind === "project" ? (
            <MobileMetricGrid
              columns={2}
              items={[
                { label: "План", value: fmtInt(detail.plan), highlight: "ok" },
                { label: "СКУД", value: fmtInt(detail.fact) },
                {
                  label: "Отклонение",
                  value: fmtSigned(detail.deviation),
                  highlight: detail.deviation < 0 ? "bad" : "ok",
                },
                { label: "Откл. %", value: fmtPct(detail.delta_pct) },
              ]}
            />
          ) : null}
          {detail?.kind === "matrix" ? (
            <MobileMetricGrid
              columns={2}
              items={[
                { label: "Вид работ", value: detail.vid_raboty || "—" },
                { label: "План", value: fmtInt(detail.plan), highlight: "ok" },
                { label: "СКУД", value: fmtInt(detail.skud) },
                {
                  label: "Отклонение",
                  value: fmtSigned(detail.deviation),
                  highlight: detail.deviation < 0 ? "bad" : "ok",
                },
                { label: "Откл. %", value: fmtPct(detail.delta_pct) },
              ]}
            />
          ) : null}
          {detail?.kind === "dynamics" ? (
            <MobileMetricGrid
              columns={2}
              items={[
                { label: "План", value: fmtInt(detail.plan), highlight: "ok" },
                { label: "Факт", value: fmtInt(detail.fact) },
                {
                  label: "Отклонение",
                  value: fmtSigned(detail.deviation),
                  highlight: detail.deviation < 0 ? "bad" : "ok",
                },
                { label: "Откл. %", value: fmtPct(detail.delta_pct) },
              ]}
            />
          ) : null}
          {detail?.kind === "contractor" ? (
            <MobileMetricGrid
              columns={2}
              items={[
                { label: "План", value: fmtInt(detail.plan), highlight: "ok" },
                { label: "Факт", value: fmtInt(detail.fact) },
                {
                  label: "Отклонение",
                  value: fmtSigned(detail.deviation),
                  highlight: detail.deviation < 0 ? "bad" : "ok",
                },
                { label: "Доля %", value: fmtPct(detail.share_pct) },
              ]}
            />
          ) : null}
        </MobileDetailSheet>
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
