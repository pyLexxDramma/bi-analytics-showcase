"use client";

import { useCallback, useEffect, useMemo, useState, type CSSProperties } from "react";
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
  fetchWorkingDocumentation,
  type WorkingDocumentationPayload,
  type WorkingDocumentationQuery,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import { CHART_RU } from "@/lib/chart-ru";
import type { ExportCell, ExportTable } from "@/lib/table-export";

const TH =
  "whitespace-nowrap border border-[#cbd5e1] bg-[#f3f4f6] px-2.5 py-2 text-center font-bold text-[#111827] dark:border-[#334155] dark:bg-[hsl(209,72%,6%)] dark:text-[#fafafa]";
const TD =
  "border border-[#cbd5e1] px-2.5 py-1.5 text-center align-middle dark:border-[#334155]";

/** Как `_RD_PIE_STATUS_COLORS` в main — фон ячейки «Статус». */
const STATUS_BG: Record<string, string> = {
  "Выдано в производство работ":
    "bg-[rgba(39,174,96,0.28)] text-[#14532d] dark:bg-[rgba(39,174,96,0.32)] dark:text-[#b8f5c8]",
  "На рассмотрении у ГИП":
    "bg-[rgba(241,196,15,0.32)] text-[#854d0e] dark:bg-[rgba(241,196,15,0.28)] dark:text-[#fde68a]",
  "Возвращено на доработку":
    "bg-[rgba(192,57,43,0.28)] text-[#7f1d1d] dark:bg-[rgba(192,57,43,0.32)] dark:text-[#fecaca]",
  "Не выдано":
    "bg-[rgba(245,169,192,0.45)] text-[#9d174d] dark:bg-[rgba(245,169,192,0.28)] dark:text-[#fbcfe8]",
  "Не выдан":
    "bg-[rgba(245,169,192,0.45)] text-[#9d174d] dark:bg-[rgba(245,169,192,0.28)] dark:text-[#fbcfe8]",
  "Передано подрядчику":
    "bg-[rgba(142,68,173,0.28)] text-[#581c87] dark:bg-[rgba(142,68,173,0.32)] dark:text-[#e9d5ff]",
  "Выдано подрядчику":
    "bg-[rgba(142,68,173,0.28)] text-[#581c87] dark:bg-[rgba(142,68,173,0.32)] dark:text-[#e9d5ff]",
  "На рассмотрении":
    "bg-[rgba(241,196,15,0.32)] text-[#854d0e] dark:bg-[rgba(241,196,15,0.28)] dark:text-[#fde68a]",
  "На доработке":
    "bg-[rgba(230,126,34,0.28)] text-[#9a3412] dark:bg-[rgba(230,126,34,0.32)] dark:text-[#fdba74]",
};

type TabId = "main" | "delay";
type SortState = { key: string; asc: boolean } | null;

const INITIAL = {
  projects: ["Все"] as string[],
  sections: ["Все"] as string[],
  statuses: [] as string[],
  periodMode: "Весь период (за всё время)",
  dateFrom: "",
  dateTo: "",
  metricMode: "Количество разделов",
  showForecast: true,
  viewMode: "project",
};

function joinMulti(values: string[], allToken = "Все"): string | undefined {
  if (!values.length || (values.length === 1 && values[0] === allToken)) return undefined;
  if (values.includes(allToken) && values.length === 1) return undefined;
  return values.filter((v) => v !== allToken).join("|") || undefined;
}

function deviationClass(value: number | null | undefined): string {
  if (value == null || value === 0) {
    return "font-semibold text-[#15803d] dark:text-[#46d68a]";
  }
  return value < 0
    ? "font-semibold text-[hsl(348,100%,45%)] dark:text-[#ff5454]"
    : "font-semibold text-[#15803d] dark:text-[#46d68a]";
}

/** Градиент отклонений как `style_dataframe_for_dark_theme(days_deviation_gradient, days_positive_is_ahead)`. */
function deviationCellStyle(
  value: number | null | undefined,
  vmax: number,
  dark: boolean,
): { className: string; style?: CSSProperties } {
  if (value == null || Number.isNaN(value)) {
    return { className: "" };
  }
  const num = Number(value);
  const t = Math.min(Math.abs(num) / Math.max(vmax, 1), 1);
  if (num === 0) {
    return {
      className: "font-semibold",
      style: dark
        ? { backgroundColor: "rgba(70,214,138,0.35)", color: "#b8f5c8" }
        : { backgroundColor: "rgba(34,197,94,0.18)", color: "#15803d" },
    };
  }
  if (num > 0) {
    const alpha = 0.18 + 0.28 * t;
    return {
      className: "font-bold",
      style: dark
        ? {
            backgroundColor: `rgba(70,214,138,${alpha.toFixed(3)})`,
            color: "#00e676",
          }
        : {
            backgroundColor: `rgba(34,197,94,${alpha.toFixed(3)})`,
            color: "#15803d",
          },
    };
  }
  const alphaLight = 0.16 + 0.24 * t;
  const alphaDark = 0.24 + 0.36 * t;
  return {
    className: "font-bold",
    style: dark
      ? {
          backgroundColor: `rgba(255,84,84,${alphaDark.toFixed(3)})`,
          color: "#ff6b6b",
        }
      : {
          backgroundColor: `rgba(248,113,113,${alphaLight.toFixed(3)})`,
          color: "#b91c1c",
        },
  };
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
}: {
  label: string;
  sortKey: string;
  sort: SortState;
  onSort: (key: string) => void;
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

function statusCellClass(status: string): string {
  const exact = STATUS_BG[status];
  if (exact) return exact;
  const key = Object.keys(STATUS_BG).find((k) =>
    status.toLowerCase().includes(k.toLowerCase()),
  );
  return key ? STATUS_BG[key] : "";
}

function fmtNum(value: number | null | undefined, digits = 0): string {
  if (value == null || Number.isNaN(value)) return "—";
  return value.toLocaleString("ru-RU", {
    maximumFractionDigits: digits,
    minimumFractionDigits: digits,
  });
}

function fmtSigned(value: number | null | undefined): string {
  if (value == null) return "—";
  if (value > 0) return `+${fmtNum(value)}`;
  return fmtNum(value);
}

function MultiSelect({
  label,
  options,
  values,
  onChange,
  allToken = "Все",
}: {
  label: string;
  options: string[];
  values: string[];
  onChange: (next: string[]) => void;
  allToken?: string;
}) {
  const selected = values.length ? values : [allToken];
  return (
    <label className="block text-sm">
      <Text>{label}</Text>
      <select
        multiple
        className="mt-1 max-h-32 w-full rounded-md border border-tremor-border bg-tremor-background px-2 py-1.5 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
        value={selected}
        onChange={(e) => {
          const opts = Array.from(e.target.selectedOptions).map((o) => o.value);
          if (!opts.length || opts.includes(allToken)) {
            onChange([allToken]);
            return;
          }
          onChange(opts);
        }}
      >
        {options.map((item) => (
          <option key={item} value={item}>
            {item}
          </option>
        ))}
      </select>
    </label>
  );
}

function StatusChips({
  options,
  values,
  onChange,
}: {
  options: string[];
  values: string[];
  onChange: (next: string[]) => void;
}) {
  const allSelected = !values.length || values.length === options.length;
  return (
    <div className="flex flex-wrap gap-2">
      <button
        type="button"
        className={`rounded-full px-3 py-1 text-xs font-medium ${
          allSelected
            ? "bg-emerald-600 text-white"
            : "bg-tremor-background-muted text-tremor-content dark:bg-dark-tremor-background-muted"
        }`}
        onClick={() => onChange(options)}
      >
        Все
      </button>
      {options.map((st) => {
        const on = allSelected || values.includes(st);
        return (
          <button
            key={st}
            type="button"
            className={`rounded-full px-3 py-1 text-xs font-medium ${
              on
                ? "bg-sky-600 text-white"
                : "bg-tremor-background-muted text-tremor-content dark:bg-dark-tremor-background-muted"
            }`}
            onClick={() => {
              if (allSelected) {
                onChange([st]);
                return;
              }
              if (on) {
                const next = values.filter((v) => v !== st);
                onChange(next.length ? next : options);
              } else {
                const next = [...values, st];
                onChange(next.length === options.length ? options : next);
              }
            }}
          >
            {st}
          </button>
        );
      })}
    </div>
  );
}

function RdDelayGantt({
  rows,
  rangeStart,
  rangeEnd,
}: {
  rows: WorkingDocumentationPayload["delay"]["gantt"]["rows"];
  rangeStart: string | null;
  rangeEnd: string | null;
}) {
  if (!rows.length) {
    return (
      <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
        Нет данных для графика просрочки.
      </div>
    );
  }
  const lo = rangeStart
    ? Date.parse(rangeStart)
    : Math.min(...rows.map((r) => Date.parse(String(r.start))));
  const hiCandidates = rows.flatMap((r) =>
    [r.delay_end, r.finish, r.base_finish].filter(Boolean).map((d) => Date.parse(String(d))),
  );
  const hi = rangeEnd ? Date.parse(rangeEnd) : Math.max(...hiCandidates);
  const span = Math.max(hi - lo, 1);
  const pct = (iso: string | null | undefined) => {
    if (!iso) return 0;
    return ((Date.parse(iso) - lo) / span) * 100;
  };
  const width = (from: string | null | undefined, to: string | null | undefined) => {
    if (!from || !to) return 0;
    return Math.max(((Date.parse(to) - Date.parse(from)) / span) * 100, 0.4);
  };

  return (
    <div className="space-y-3 px-2 py-2">
      <div className="flex flex-wrap gap-4 text-xs text-tremor-content dark:text-dark-tremor-content">
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#F1C40F]" /> Дата по договору
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#27AE60]" /> Прогноз / факт
        </span>
        <span className="inline-flex items-center gap-1.5">
          <span className="inline-block h-2.5 w-2.5 rounded-sm bg-[#C0392B]" /> Просрочка
        </span>
      </div>
      {rows.map((row) => {
        const baseLeft = pct(row.start);
        const baseW = width(row.start, row.base_finish);
        const green = row.fact_dur > 0 && row.finish && !row.delay_end;
        const red = row.delay_dur > 0 && row.delay_end;
        return (
          <div key={row.label} className="grid grid-cols-[9rem_1fr] items-center gap-2">
            <div className="truncate text-right text-xs font-medium">{row.label}</div>
            <div className="relative h-7 rounded bg-tremor-background-muted dark:bg-dark-tremor-background-muted">
              <div
                className="absolute top-1 h-5 rounded-sm bg-[#F1C40F]"
                style={{ left: `${baseLeft}%`, width: `${baseW}%` }}
                title={row.base_label}
              />
              {green ? (
                <div
                  className="absolute top-1 h-5 rounded-sm bg-[#27AE60]/80"
                  style={{
                    left: `${baseLeft}%`,
                    width: `${width(row.start, row.finish)}%`,
                  }}
                  title={row.fact_label}
                />
              ) : null}
              {red && row.base_finish ? (
                <div
                  className="absolute top-1 h-5 rounded-sm bg-[#C0392B]/85"
                  style={{
                    left: `${pct(row.base_finish)}%`,
                    width: `${width(row.base_finish, row.delay_end)}%`,
                  }}
                  title={row.delay_label}
                />
              ) : null}
            </div>
          </div>
        );
      })}
    </div>
  );
}

function DetailTable({
  columns,
  rows,
  fileStem,
}: {
  columns: string[];
  rows: Array<Record<string, string | number | null>>;
  fileStem: string;
}) {
  const [sort, setSort] = useState<SortState>(null);
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const el = document.documentElement;
    const sync = () => setDark(el.classList.contains("dark"));
    sync();
    const obs = new MutationObserver(sync);
    obs.observe(el, { attributes: true, attributeFilter: ["class"] });
    return () => obs.disconnect();
  }, []);

  const onSort = useCallback((key: string) => {
    setSort((prev) => {
      if (prev?.key === key) {
        return prev.asc ? { key, asc: false } : null;
      }
      return { key, asc: true };
    });
  }, []);

  const sortedRows = useMemo(() => {
    if (!sort) return rows;
    const copy = [...rows];
    copy.sort((a, b) => {
      const cmp = compareVal(a[sort.key], b[sort.key]);
      return sort.asc ? cmp : -cmp;
    });
    return copy;
  }, [rows, sort]);

  const vmaxByCol = useMemo(() => {
    const map: Record<string, number> = {};
    for (const c of columns) {
      if (!c.toLowerCase().includes("отклонен")) continue;
      let vmax = 1;
      for (const row of rows) {
        const n = parseSortableNumber(row[c]);
        if (n != null) vmax = Math.max(vmax, Math.abs(n));
      }
      map[c] = vmax;
    }
    return map;
  }, [columns, rows]);

  const exportTable = useCallback((): ExportTable | null => {
    if (!sortedRows.length || !columns.length) return null;
    const header: ExportCell[][] = [columns];
    const body: ExportCell[][] = sortedRows.map((row) =>
      columns.map((c) => {
        const label = row[`${c}__label`];
        if (label != null && label !== "") return label;
        const v = row[c];
        if (v == null) return "";
        if (typeof v === "number" && c.toLowerCase().includes("отклонен")) {
          return v > 0 ? `+${v}` : String(v);
        }
        return v;
      }),
    );
    return { header, rows: body, sheetName: "РД" };
  }, [sortedRows, columns]);

  return (
    <Card className="rounded-xl p-0">
      <div className="overflow-x-auto">
        <table className="min-w-full border-collapse text-sm">
          <thead>
            <tr>
              {columns.map((c) => (
                <SortHeader
                  key={c}
                  label={c}
                  sortKey={c}
                  sort={sort}
                  onSort={onSort}
                />
              ))}
            </tr>
          </thead>
          <tbody>
            {sortedRows.map((row, i) => (
              <tr key={i} className="hover:bg-black/[0.03] dark:hover:bg-white/[0.03]">
                {columns.map((c) => {
                  const isDev = c.toLowerCase().includes("отклонен");
                  const isStatus = c.toLowerCase() === "статус";
                  const num = isDev ? parseSortableNumber(row[c]) : null;
                  const label =
                    (row[`${c}__label`] as string | undefined) ??
                    (row[c] == null
                      ? "—"
                      : isDev && typeof row[c] === "number"
                        ? (row[c] as number) > 0
                          ? `+${row[c]}`
                          : String(row[c])
                        : String(row[c]));
                  const tint = isDev
                    ? deviationCellStyle(num, vmaxByCol[c] ?? 1, dark)
                    : { className: "", style: undefined };
                  const statusCls =
                    isStatus && label && label !== "—" ? statusCellClass(label) : "";
                  return (
                    <td
                      key={c}
                      className={`${TD} ${tint.className} ${statusCls} ${
                        isDev && !tint.style ? deviationClass(num) : ""
                      }`}
                      style={tint.style}
                    >
                      {label}
                    </td>
                  );
                })}
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <div className="px-4 py-3">
        <DownloadTableButton
          getTable={exportTable}
          fileStem={fileStem}
          disabled={!sortedRows.length}
        />
      </div>
    </Card>
  );
}

export function WorkingDocumentationView() {
  const [tab, setTab] = useState<TabId>("main");
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [filters, setFilters] = useState(INITIAL);
  const [data, setData] = useState<WorkingDocumentationPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    let cancelled = false;
    const allStatuses = data?.filters.statuses ?? [];
    const statusParam =
      filters.statuses.length &&
      allStatuses.length &&
      filters.statuses.length !== allStatuses.length
        ? filters.statuses.join("|")
        : undefined;
    const q: WorkingDocumentationQuery = {
      project: joinMulti(filters.projects),
      section: joinMulti(filters.sections),
      status: statusParam,
      period_mode: filters.periodMode,
      date_from: filters.dateFrom || undefined,
      date_to: filters.dateTo || undefined,
      metric_mode: filters.metricMode,
      show_forecast: filters.showForecast,
      view_mode: filters.viewMode,
      tab,
    };
    setLoading(true);
    fetchWorkingDocumentation(q)
      .then((payload) => {
        if (cancelled) return;
        setData(payload);
        setError(payload.meta.error || null);
        setFilters((f) => {
          if (f.statuses.length) return f;
          if (!payload.filters.statuses.length) return f;
          return { ...f, statuses: payload.filters.statuses };
        });
      })
      .catch((e: unknown) => {
        if (!cancelled) setError(e instanceof Error ? e.message : String(e));
      })
      .finally(() => {
        if (!cancelled) setLoading(false);
      });
    return () => {
      cancelled = true;
    };
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [
    tab,
    filters.projects,
    filters.sections,
    filters.statuses,
    filters.periodMode,
    filters.dateFrom,
    filters.dateTo,
    filters.metricMode,
    filters.showForecast,
    filters.viewMode,
  ]);

  const kpis = data?.kpis;
  const statusMix = data?.tremor.status_mix ?? [];
  const dynamics = useMemo(
    () =>
      (data?.tremor.dynamics ?? []).map((d) => ({
        period_label: d.period_label,
        [CHART_RU.plan]: d.plan,
        [CHART_RU.fact]: d.fact,
      })),
    [data?.tremor.dynamics],
  );
  const monthly = useMemo(
    () =>
      (data?.tremor.monthly ?? []).map((m) => ({
        month_label: m.month_label,
        [CHART_RU.plan]: m.plan,
        [CHART_RU.fact]: m.fact,
        "+факт": m.fact_inc ?? 0,
      })),
    [data?.tremor.monthly],
  );

  const donutColors = statusMix.map((item) => {
    if (item.name.includes("производств")) return "emerald";
    if (item.name.includes("рассмотр")) return "amber";
    if (item.name.includes("доработ")) return "rose";
    return "pink";
  }) as ("emerald" | "amber" | "rose" | "pink")[];

  const resetFilters = () => {
    setFilters({
      ...INITIAL,
      statuses: data?.filters.statuses ?? [],
    });
  };

  return (
    <AppShell title="Рабочая документация">
      <div className="mb-4 flex gap-4 border-b border-tremor-border dark:border-dark-tremor-border">
        {(
          [
            ["main", "Рабочая документация"],
            ["delay", "Просрочка выдачи РД"],
          ] as const
        ).map(([id, label]) => (
          <button
            key={id}
            type="button"
            onClick={() => setTab(id)}
            className={`border-b-2 px-1 pb-2 text-sm font-medium ${
              tab === id
                ? "border-emerald-600 text-emerald-700 dark:border-emerald-400 dark:text-emerald-300"
                : "border-transparent text-tremor-content dark:text-dark-tremor-content"
            }`}
          >
            {label}
          </button>
        ))}
      </div>

      <Card className="mb-6 rounded-xl p-0">
        <button
          type="button"
          className="flex w-full items-center justify-between px-4 py-3 text-left"
          onClick={() => setFiltersOpen((v) => !v)}
          aria-expanded={filtersOpen}
        >
          <span className="text-sm font-semibold">
            {tab === "main" ? "План выдачи РД — фильтры" : "Фильтры"}
          </span>
          <span className="text-xs">{filtersOpen ? "▾" : "▸"}</span>
        </button>
        {filtersOpen ? (
          <div className="space-y-3 border-t border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <button
              type="button"
              className="rounded-md border border-tremor-border px-3 py-1.5 text-sm dark:border-dark-tremor-border"
              onClick={resetFilters}
            >
              Сбросить
            </button>
            <div className="grid gap-3 md:grid-cols-3">
              <MultiSelect
                label="Проекты"
                options={data?.filters.projects ?? ["Все"]}
                values={filters.projects}
                onChange={(projects) => setFilters((f) => ({ ...f, projects }))}
              />
              <MultiSelect
                label="Раздел"
                options={data?.filters.sections ?? ["Все"]}
                values={filters.sections}
                onChange={(sections) => setFilters((f) => ({ ...f, sections }))}
              />
              <label className="block text-sm">
                <Text>Период</Text>
                <select
                  className="mt-1 w-full rounded-md border border-tremor-border bg-tremor-background px-2 py-1.5 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={filters.periodMode}
                  onChange={(e) =>
                    setFilters((f) => ({ ...f, periodMode: e.target.value }))
                  }
                >
                  {(data?.filters.period_modes ?? [INITIAL.periodMode]).map((item) => (
                    <option key={item} value={item}>
                      {item}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            {filters.periodMode !== "Весь период (за всё время)" ? (
              <div className="grid gap-3 md:grid-cols-2">
                <label className="block text-sm">
                  <Text>С</Text>
                  <input
                    type="date"
                    className="mt-1 w-full rounded-md border border-tremor-border px-2 py-1.5 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                    value={filters.dateFrom}
                    min={data?.filters.plan_date_min ?? undefined}
                    max={data?.filters.plan_date_max ?? undefined}
                    onChange={(e) =>
                      setFilters((f) => ({ ...f, dateFrom: e.target.value }))
                    }
                  />
                </label>
                <label className="block text-sm">
                  <Text>По</Text>
                  <input
                    type="date"
                    className="mt-1 w-full rounded-md border border-tremor-border px-2 py-1.5 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                    value={filters.dateTo}
                    min={data?.filters.plan_date_min ?? undefined}
                    max={data?.filters.plan_date_max ?? undefined}
                    onChange={(e) =>
                      setFilters((f) => ({ ...f, dateTo: e.target.value }))
                    }
                  />
                </label>
              </div>
            ) : null}
            <div>
              <Text className="mb-1">Статус</Text>
              <StatusChips
                options={data?.filters.statuses ?? []}
                values={filters.statuses}
                onChange={(statuses) => setFilters((f) => ({ ...f, statuses }))}
              />
            </div>
            <div className="flex flex-wrap items-center gap-4">
              {tab === "delay" ? (
                <label className="block text-sm">
                  <Text>Отображение</Text>
                  <select
                    className="mt-1 rounded-md border border-tremor-border bg-tremor-background px-2 py-1.5 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                    value={filters.viewMode}
                    onChange={(e) =>
                      setFilters((f) => ({ ...f, viewMode: e.target.value }))
                    }
                  >
                    {(data?.filters.view_modes ?? []).map((item) => (
                      <option key={item.id} value={item.id}>
                        {item.label}
                      </option>
                    ))}
                  </select>
                </label>
              ) : null}
              <div className="flex items-center gap-3 text-sm">
                {(data?.filters.metric_modes ?? INITIAL.metricMode).map((m) => (
                  <label key={m} className="inline-flex items-center gap-1.5">
                    <input
                      type="radio"
                      name="rd-metric"
                      checked={filters.metricMode === m}
                      onChange={() => setFilters((f) => ({ ...f, metricMode: m }))}
                    />
                    {m}
                  </label>
                ))}
              </div>
              <label className="inline-flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  checked={filters.showForecast}
                  onChange={(e) =>
                    setFilters((f) => ({ ...f, showForecast: e.target.checked }))
                  }
                />
                Показать прогнозную дату выдачи разделов
              </label>
            </div>
          </div>
        ) : null}
      </Card>

      {error ? (
        <Card className="mb-4 border-rose-300 bg-rose-50 p-4 text-sm text-rose-800 dark:border-rose-800 dark:bg-rose-950/40 dark:text-rose-200">
          {error}
        </Card>
      ) : null}
      {loading && !data ? (
        <Text>Загрузка…</Text>
      ) : (
        <>
          <Grid numItemsSm={1} numItemsMd={3} className="mb-6 gap-4">
            <Card className="rounded-xl">
              <Text>Всего разделов</Text>
              <Metric>{fmtNum(kpis?.total_sections)}</Metric>
            </Card>
            <Card className="rounded-xl">
              <Text>С отклонением (дн. &lt; 0)</Text>
              <Metric>{fmtNum(kpis?.overdue)}</Metric>
            </Card>
            <Card className="rounded-xl">
              <Text>Ср. задержка, дн.</Text>
              <Metric>{fmtNum(kpis?.avg_delay, 1)}</Metric>
            </Card>
          </Grid>

          {tab === "main" ? (
            <>
              <FullscreenPanel title="Исполнение РД" className="mb-6">
                <Card className="rounded-xl">
                  <Title>Исполнение РД</Title>
                  <DonutChart
                    className="mt-4 h-72"
                    data={statusMix}
                    category="value"
                    index="name"
                    colors={donutColors}
                    valueFormatter={(v) => fmtNum(v)}
                    showLabel
                  />
                </Card>
              </FullscreenPanel>

              <FullscreenPanel title="Динамика по месяцам" className="mb-6">
                <Card className="rounded-xl">
                  <Title>Динамика по месяцам</Title>
                  <BarChart
                    className="mt-4 h-80"
                    data={monthly}
                    index="month_label"
                    categories={[CHART_RU.plan, CHART_RU.fact]}
                    colors={["amber", "emerald"]}
                    layout="vertical"
                    valueFormatter={(v) => fmtNum(v)}
                    showLegend
                  />
                </Card>
              </FullscreenPanel>

              <Card className="mb-6 rounded-xl">
                <Title className="mb-4">Динамика выдачи РД</Title>
                <Grid numItemsSm={2} numItemsMd={4} className="mb-4 gap-3">
                  <div>
                    <Text>План по проекту</Text>
                    <Metric className="text-2xl">{fmtNum(kpis?.plan_total)}</Metric>
                  </div>
                  <div>
                    <Text>План на текущую дату</Text>
                    <Metric className="text-2xl">{fmtNum(kpis?.plan_to_date)}</Metric>
                  </div>
                  <div>
                    <Text>Факт на текущую дату</Text>
                    <Metric className="text-2xl">{fmtNum(kpis?.fact_to_date)}</Metric>
                  </div>
                  <div>
                    <Text>Отклонение на текущую дату</Text>
                    <Metric
                      className={`text-2xl ${
                        (kpis?.deviation_to_date ?? 0) > 0
                          ? "font-semibold text-[hsl(348,100%,45%)] dark:text-[#ff5454]"
                          : "font-semibold text-[#15803d] dark:text-[#46d68a]"
                      }`}
                    >
                      {fmtSigned(kpis?.deviation_to_date)}
                    </Metric>
                  </div>
                </Grid>
                <Grid numItemsSm={1} numItemsMd={3} className="mb-4 gap-3">
                  <div>
                    <Text>Плановая производительность / нед.</Text>
                    <p className="text-lg font-semibold">
                      {kpis?.planned_weekly != null ? fmtNum(kpis.planned_weekly, 1) : "—"}
                    </p>
                  </div>
                  <div>
                    <Text>Фактическая производительность / нед.</Text>
                    <p className="text-lg font-semibold">
                      {kpis?.fact_weekly != null ? fmtNum(kpis.fact_weekly, 1) : "—"}
                    </p>
                  </div>
                  <div>
                    <Text>Необходимая производительность / нед.</Text>
                    <p className="text-lg font-semibold">
                      {kpis?.nec_weekly != null ? fmtNum(kpis.nec_weekly, 1) : "—"}
                    </p>
                  </div>
                </Grid>
                <FullscreenPanel title="Динамика выдачи РД (график)">
                  <LineChart
                    className="h-80"
                    data={dynamics}
                    index="period_label"
                    categories={[CHART_RU.plan, CHART_RU.fact]}
                    colors={["blue", "orange"]}
                    valueFormatter={(v) => fmtNum(v)}
                    showLegend
                  />
                </FullscreenPanel>
              </Card>

              <Title className="mb-3">Детальная таблица</Title>
              <DetailTable
                columns={data?.detail_columns ?? []}
                rows={data?.detail_rows ?? []}
                fileStem="rd_detail"
              />
            </>
          ) : (
            <>
              <FullscreenPanel title="График Просрочка выдачи РД" className="mb-6">
                <Card className="rounded-xl p-0">
                  <div className="px-4 pt-4">
                    <Title>График Просрочка выдачи РД</Title>
                  </div>
                  <RdDelayGantt
                    rows={data?.delay.gantt.rows ?? []}
                    rangeStart={data?.delay.gantt.range_start ?? null}
                    rangeEnd={data?.delay.gantt.range_end ?? null}
                  />
                </Card>
              </FullscreenPanel>

              <FullscreenPanel title="Динамика по месяцам" className="mb-6">
                <Card className="rounded-xl">
                  <Title>Динамика по месяцам</Title>
                  <BarChart
                    className="mt-4 h-80"
                    data={monthly}
                    index="month_label"
                    categories={[CHART_RU.plan, CHART_RU.fact]}
                    colors={["amber", "emerald"]}
                    layout="vertical"
                    valueFormatter={(v) => fmtNum(v)}
                    showLegend
                  />
                </Card>
              </FullscreenPanel>

              <Title className="mb-3">Детальная таблица</Title>
              <DetailTable
                columns={data?.delay.detail_columns ?? data?.detail_columns ?? []}
                rows={data?.delay.detail_rows ?? data?.detail_rows ?? []}
                fileStem="rd_delay_detail"
              />
            </>
          )}
        </>
      )}
    </AppShell>
  );
}
