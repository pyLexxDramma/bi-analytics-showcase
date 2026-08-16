"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import { fetchPrescriptions, type PrescriptionsPayload } from "@/lib/api";
import {
  ContractNoSuggest,
  FilterCheck,
  FilterChipMulti,
  FilterChecksRow,
  FilterField,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import {
  MobileCardStack,
  MobileEntityCard,
  MobileMetricGrid,
} from "@/components/mobile-entity-card";
import {
  PrescriptionsContractorChart,
  PrescriptionsObjectsChart,
  PrescriptionsStatusPieChart,
} from "@/components/prescriptions-charts";
import { buildFilterChips } from "@/lib/filters-summary";
import { useUrlFilterState } from "@/lib/use-url-filter-state";
import type { ExportCell, ExportTable } from "@/lib/table-export";

type Filters = {
  projects: string[];
  contractors: string[];
  contract_q: string;
  date_from: string;
  date_to: string;
  hide_resolved: boolean;
};

const INITIAL: Filters = {
  projects: [],
  contractors: [],
  contract_q: "",
  date_from: "",
  date_to: "",
  hide_resolved: false,
};
type SortState = { key: string; asc: boolean } | null;

const STATUS_KEYS = [
  "Остановка работ",
  "Критические",
  "Не устранено",
  "Сдано в срок",
  "Устранено с просрочкой",
] as const;

const UNRESOLVED_STATUS_KEYS = ["Остановка работ", "Критические", "Не устранено"] as const;

const tableColumns: Array<[string, string]> = [
  ["status", "Статус"],
  ["contractor", "Подрядчик"],
  ["project", "Проект"],
  ["contract_no", "№ договора"],
  ["doc_number", "№ документа"],
  ["pred_number", "№ предписания"],
  ["name", "Наименование"],
  ["issue_date", "Дата выдачи"],
  ["issue_block", "Блок выдачи"],
  ["due_date", "Срок устранения"],
  ["completion_date", "Факт. устранение"],
  ["overdue_days", "Дней просрочки"],
  ["critical", "Критические"],
  ["stop_work", "Остановка работ"],
];

/** Длинный текст: truncate (ellipsis) — не для «Наименование». */
const TRUNCATE_COLS = new Set(["issue_block", "contractor", "contract_no"]);

/** Перенос только у «Наименование»; даты всегда в одну строку, без многоточия. */
const WRAP_COLS = new Set(["name"]);
const DATE_COLS = new Set(["issue_date", "due_date", "completion_date"]);

/** Закреп при горизонтальном скролле: Статус / Подрядчик / Проект. */
const PRED_STICKY: Record<
  string,
  { left: string; width: string; shadow?: boolean }
> = {
  status: { left: "0", width: "9.75rem" },
  contractor: { left: "9.75rem", width: "13.5rem" },
  project: { left: "23.25rem", width: "8.5rem", shadow: true },
};

const PRED_STICKY_SHADOW =
  "shadow-[7px_0_10px_-6px_rgba(15,23,42,0.4)] dark:shadow-[7px_0_10px_-6px_rgba(0,0,0,0.7)]";

function compare(a: unknown, b: unknown) {
  const an = Number(a);
  const bn = Number(b);
  if (Number.isFinite(an) && Number.isFinite(bn)) return an - bn;
  return String(a ?? "").localeCompare(String(b ?? ""), "ru", {
    numeric: true,
    sensitivity: "base",
  });
}

function exportCell(value: unknown): ExportCell {
  return typeof value === "boolean" ? (value ? "Да" : "—") : String(value ?? "");
}

export function PrescriptionsView() {
  const [filters, setFilters] = useState<Filters>(INITIAL);
  const [data, setData] = useState<PrescriptionsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sort, setSort] = useState<SortState>(null);
  const contractOptionsRef = useRef<string[]>([]);

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchPrescriptions({
        projects: next.projects,
        contractors: next.contractors,
        contract_q: next.contract_q || undefined,
        date_from: next.date_from || undefined,
        date_to: next.date_to || undefined,
        hide_resolved: next.hide_resolved ? "true" : undefined,
      });
      if (payload.filters.contract_nos?.length) {
        contractOptionsRef.current = payload.filters.contract_nos;
      }
      setData(payload);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    const delayMs = filters.contract_q ? 320 : 0;
    const timer = window.setTimeout(() => {
      void load(filters);
    }, delayMs);
    return () => window.clearTimeout(timer);
  }, [filters, load]);

  const contractOptions =
    data?.filters.contract_nos?.length
      ? data.filters.contract_nos
      : contractOptionsRef.current;

  const rows = useMemo(() => {
    const next = [...(data?.rows ?? [])];
    if (sort) {
      next.sort(
        (a, b) =>
          (sort.asc ? 1 : -1) *
          compare(a[sort.key as keyof typeof a], b[sort.key as keyof typeof b]),
      );
    }
    return next;
  }, [data?.rows, sort]);

  const contractorChart = useMemo(
    () => data?.tremor.by_contractor ?? [],
    [data?.tremor.by_contractor],
  );

  const statusChart = useMemo(
    () =>
      (data?.tremor.by_status ?? []).map((row) => ({
        status: row.status,
        value: row.value,
        share_pct: row.share_pct,
      })),
    [data?.tremor.by_status],
  );

  const objectStatusKeys = filters.hide_resolved ? UNRESOLVED_STATUS_KEYS : STATUS_KEYS;

  const objectChart = useMemo(
    () =>
      (data?.tremor.by_object ?? []).map((row) => {
        const out: Record<string, string | number> = {
          object: row.object,
          total: Number((row as Record<string, unknown>).total ?? 0),
        };
        for (const key of objectStatusKeys) {
          out[key] = Number((row as Record<string, unknown>)[key] ?? 0);
        }
        return out;
      }) as Array<{ object: string; total: number } & Record<string, number>>,
    [data?.tremor.by_object, objectStatusKeys],
  );

  const reset = () => setFilters(INITIAL);

  useUrlFilterState(
    filters, INITIAL,
    (patch) => setFilters((state) => ({ ...state, ...patch })),
    { navId: "prescriptions" },
  );

  const activeFilters = buildFilterChips(
    filters,
    INITIAL,
    [
      { key: "projects", name: "Проект" },
      { key: "contractors", name: "Подрядчик" },
      { key: "contract_q", name: "№ договора" },
      { key: "date_from", name: "С", kind: "date" },
      { key: "date_to", name: "По", kind: "date" },
      { key: "hide_resolved", name: "Устранённые скрыты", kind: "flag" },
    ],
    (patch) => setFilters((state) => ({ ...state, ...patch })),
  );

  const exportTable = useCallback((): ExportTable | null => {
    if (!rows.length) return null;
    return {
      header: [tableColumns.map(([, label]) => label)],
      rows: rows.map(
        (row): ExportCell[] =>
          tableColumns.map(([key]) => exportCell(row[key as keyof typeof row])),
      ),
    };
  }, [rows]);

  const toggleSort = (key: string) =>
    setSort((previous) =>
      previous?.key === key ? { key, asc: !previous.asc } : { key, asc: true },
    );

  const kpis = data?.kpis;
  const topMetrics = [
    {
      label: "Всего предписаний",
      value: kpis?.total,
      tone: "neutral" as const,
    },
    {
      label: "Устраненные предписания",
      value: kpis?.resolved,
      tone: "ok" as const,
    },
    {
      label: "Неустраненные",
      value: kpis?.unresolved,
      tone: "warn" as const,
    },
    {
      label: "Непросроченные",
      value: kpis?.non_overdue,
      tone: "ok" as const,
    },
  ];
  const keyIndicators = [
    {
      tone: "blue" as const,
      value: kpis?.total,
      title: "Всего предписаний",
      hint: "Все записи в выборке",
    },
    {
      tone: "blue" as const,
      value: kpis?.unresolved,
      title: "Неустраненные предписания",
      hint: "Общее количество",
    },
    {
      tone: "green" as const,
      value: kpis?.resolved,
      title: "Устраненные предписания",
      hint: "Закрыты или устранены",
    },
    {
      tone: "orange" as const,
      value: kpis?.overdue_unresolved,
      title: "Просроченные неустраненные предписания",
      hint: "Неустранённые с истёкшим сроком",
    },
    {
      tone: "red" as const,
      value: kpis?.critical,
      title: "Критические предписания",
      hint: "Неустраненные предписания с тегом «КРИТИЧНЫЙ» в Tessa_Teg (TESSA)",
    },
    {
      tone: "burgundy" as const,
      value: kpis?.stop_work,
      title: "Остановка работ",
      hint: "Неустраненные предписания с тегом «Приостановка работ» в Tessa_Teg (TESSA)",
    },
  ];

  const KeyIndicatorsPanel = ({ className = "" }: { className?: string }) => (
    <div className={`pred-kpi-wrap ${className}`}>
      <div className="pred-kpi-title">Ключевые показатели</div>
      <div className="pred-kpi-circles">
        {keyIndicators.map((item) => (
          <div key={item.title} className="pred-kpi-item">
            <div className={`pred-kpi-circle ${item.tone}`}>
              <span className="n">{item.value ?? "—"}</span>
              <span className="s">всего</span>
            </div>
            <div className="pred-kpi-info">
              <h4>{item.title}</h4>
              <p>{item.hint}</p>
            </div>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <AppShell
      title="Предписания по подрядчикам"
      subtitle="TESSA · статусы, сроки устранения и критичность"
      loading={loading}
    >
      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((value) => !value)}
        activeFilters={activeFilters}
        onReset={activeFilters.length ? reset : undefined}
      >
        <FiltersReset onClick={reset} />
        <FilterFieldsRow cols={4}>
          <FilterChipMulti
            label="Проект"
            options={data?.filters.projects ?? []}
            values={filters.projects}
            onChange={(projects) => setFilters((state) => ({ ...state, projects }))}
            allLabel="Все"
          />
          <FilterChipMulti
            label="Подрядчик"
            options={data?.filters.contractors ?? []}
            values={filters.contractors}
            onChange={(contractors) =>
              setFilters((state) => ({ ...state, contractors }))
            }
            allLabel="Все подрядчики"
          />
          <FilterField label="№ договора (частичный поиск)">
            <ContractNoSuggest
              value={filters.contract_q}
              options={contractOptions}
              placeholder="Все договоры"
              onChange={(contract_q) =>
                setFilters((state) => ({ ...state, contract_q }))
              }
            />
          </FilterField>
          <FilterField label="Период">
            <div className="mt-1 grid grid-cols-2 gap-2">
              <input
                type="date"
                min={data?.filters.date_min ?? undefined}
                max={data?.filters.date_max ?? undefined}
                value={filters.date_from}
                onChange={(e) =>
                  setFilters((state) => ({
                    ...state,
                    date_from: e.target.value,
                  }))
                }
                className={FILTER_SELECT_CLASS.replace(" mt-1", "")}
                aria-label="Дата с"
              />
              <input
                type="date"
                min={data?.filters.date_min ?? undefined}
                max={data?.filters.date_max ?? undefined}
                value={filters.date_to}
                onChange={(e) =>
                  setFilters((state) => ({
                    ...state,
                    date_to: e.target.value,
                  }))
                }
                className={FILTER_SELECT_CLASS.replace(" mt-1", "")}
                aria-label="Дата по"
              />
            </div>
          </FilterField>
        </FilterFieldsRow>
        <FilterChecksRow cols={4}>
          <FilterCheck
            label="Не отображать устраненные предписания"
            checked={filters.hide_resolved}
            onChange={(e) =>
              setFilters((state) => ({
                ...state,
                hide_resolved: e.target.checked,
              }))
            }
          />
          <div />
          <div />
          <div />
        </FilterChecksRow>
        <Text className="mt-3">
          {loading ? "загрузка…" : `${data?.meta.rows ?? 0} строк`}
          {data?.meta.version_id != null
            ? ` · version_id=${data.meta.version_id}`
            : ""}
        </Text>
        {data?.meta.warning ? (
          <Text className="mt-1 text-amber-700 dark:text-amber-300">
            {data.meta.warning}
          </Text>
        ) : null}
      </FiltersCard>

      {error ? (
        <Card className="mb-6 border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            API недоступен: {error}
          </Text>
        </Card>
      ) : null}

      <div className="space-y-6">
        <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
          {topMetrics.map((item) => (
            <div
              key={item.label}
              className="rounded-xl border border-tremor-border bg-tremor-background px-4 py-3 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            >
              <Text className="text-sm text-tremor-content dark:text-dark-tremor-content">
                {item.label}
              </Text>
              <div
                className={`mt-1 text-3xl font-semibold tabular-nums tracking-tight ${
                  item.tone === "ok"
                    ? "text-emerald-600 dark:text-emerald-400"
                    : item.tone === "warn"
                      ? "text-orange-600 dark:text-orange-400"
                      : "text-tremor-content-strong dark:text-dark-tremor-content-strong"
                }`}
              >
                {item.value ?? "—"}
              </div>
            </div>
          ))}
        </div>

        <div className="grid gap-4 lg:grid-cols-[minmax(0,3fr)_minmax(280px,1fr)] lg:items-start">
          <FullscreenPanel fill>
            {(zoomed) => (
              <Card className="rounded-xl">
                <div className="pred-leg mb-2 flex flex-wrap items-center gap-4 text-sm text-tremor-content-strong dark:text-dark-tremor-content-strong">
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      className="inline-block h-3.5 w-3.5 rounded-sm"
                      style={{ background: "#E67E22" }}
                      aria-hidden
                    />
                    <strong>Внутри столбца</strong> — только просроченные (не все).
                  </span>
                  <span className="inline-flex items-center gap-1.5">
                    <span
                      className="inline-flex h-[18px] w-[18px] items-center justify-center rounded-full text-[11px] font-bold text-white"
                      style={{ background: "#3498db" }}
                      aria-hidden
                    >
                      N
                    </span>
                    <strong>Синий пузырёк справа</strong> —{" "}
                    {filters.hide_resolved
                      ? "все неустранённые по подрядчику."
                      : "всего предписаний по подрядчику."}
                  </span>
                </div>
                <div className="mt-2 hidden lg:block">
                  <PrescriptionsContractorChart
                    rows={contractorChart}
                    hideResolved={filters.hide_resolved}
                    fullscreen={zoomed}
                  />
                </div>
                <div className="mt-2 lg:hidden">
                  <PrescriptionsContractorChart
                    rows={contractorChart}
                    hideResolved={filters.hide_resolved}
                    compact
                  />
                </div>
              </Card>
            )}
          </FullscreenPanel>
          <KeyIndicatorsPanel className="hidden lg:block" />
        </div>

        <KeyIndicatorsPanel className="lg:hidden" />

        <FullscreenPanel fill>
          {(zoomed) => (
            <Card className="rounded-xl">
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Предписания по статусам
              </Title>
              <div className="mt-4 hidden lg:block">
                <PrescriptionsStatusPieChart rows={statusChart} fullscreen={zoomed} />
              </div>
              <div className="mt-4 lg:hidden">
                <PrescriptionsStatusPieChart rows={statusChart} compact />
              </div>
            </Card>
          )}
        </FullscreenPanel>

        <FullscreenPanel fill>
          {(zoomed) => (
            <Card className="rounded-xl">
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Предписания по объектам
              </Title>
              <div className="mt-4 hidden lg:block">
                <PrescriptionsObjectsChart
                  rows={objectChart}
                  statusKeys={[...objectStatusKeys]}
                  fullscreen={zoomed}
                />
              </div>
              <div className="mt-4 lg:hidden">
                <PrescriptionsObjectsChart
                  rows={objectChart}
                  statusKeys={[...objectStatusKeys]}
                  compact
                />
              </div>
            </Card>
          )}
        </FullscreenPanel>

        <Card className="hidden overflow-hidden rounded-xl p-0 lg:block">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Детальная таблица по предписаниям
            </Title>
          </div>
          <FullscreenPanel disabled={!rows.length} scroll={false}>
            <div className="bi-table-scroll">
              {!rows.length ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content">
                  Нет строк по фильтрам.
                </div>
              ) : (
                /* shrink-wrap: иначе table width:auto = 100% карточки и колонки раздуваются */
                <div className="w-max max-w-none">
                  <table
                    className="bi-sticky-head border-separate border-spacing-0 text-left text-sm"
                    style={{ width: "max-content" }}
                  >
                    <thead>
                      <tr>
                        {tableColumns.map(([key, label]) => {
                          const sticky = PRED_STICKY[key];
                          return (
                          <th
                            key={key}
                            className={`whitespace-nowrap border-b border-tremor-border bg-[#e8eef5] px-3 py-3 text-xs font-semibold uppercase tracking-wide text-tremor-content dark:border-dark-tremor-border dark:bg-[hsl(209,55%,14%)] dark:text-dark-tremor-content ${
                              sticky
                                ? `bi-sticky-x sticky z-[6] ${sticky.shadow ? PRED_STICKY_SHADOW : ""}`
                                : ""
                            }`}
                            style={
                              sticky
                                ? {
                                    left: sticky.left,
                                    width: sticky.width,
                                    minWidth: sticky.width,
                                    maxWidth: sticky.width,
                                  }
                                : undefined
                            }
                          >
                            <button
                              type="button"
                              onClick={() => toggleSort(key)}
                              className="inline-flex items-center gap-1"
                            >
                              {label}
                              <span aria-hidden>
                                {sort?.key === key ? (sort.asc ? "↑" : "↓") : "⇅"}
                              </span>
                            </button>
                          </th>
                          );
                        })}
                      </tr>
                    </thead>
                    <tbody>
                      {rows.map((row, index) => {
                        const toneBg =
                          row.row_tone === "overdue"
                            ? "bg-[#fff1f2] dark:bg-[#3d1a1a]"
                            : row.row_tone === "resolved"
                              ? "bg-[#ecfdf5] dark:bg-[#14532d]"
                              : "bg-white dark:bg-[#111827]";
                        return (
                          <tr key={`${row.pred_number}-${index}`}>
                            {tableColumns.map(([key]) => {
                              const sticky = PRED_STICKY[key];
                              return (
                              <td
                                key={key}
                                title={
                                  TRUNCATE_COLS.has(key) || WRAP_COLS.has(key)
                                    ? String(row[key as keyof typeof row] ?? "")
                                    : undefined
                                }
                                className={`border-b border-tremor-border px-3 py-2 dark:border-dark-tremor-border ${toneBg} ${
                                  WRAP_COLS.has(key)
                                    ? "max-w-[22rem] whitespace-normal break-words align-top"
                                    : DATE_COLS.has(key)
                                      ? "whitespace-nowrap align-middle"
                                      : TRUNCATE_COLS.has(key)
                                        ? "max-w-[16rem] truncate align-middle"
                                        : "whitespace-nowrap align-middle"
                                } ${
                                  key === "overdue_days" && row.overdue_days > 0
                                    ? "font-semibold text-rose-600 dark:text-rose-400"
                                    : "text-tremor-content-strong dark:text-dark-tremor-content-strong"
                                } ${
                                  sticky
                                    ? `sticky z-[2] ${sticky.shadow ? PRED_STICKY_SHADOW : ""}`
                                    : ""
                                }`}
                                style={
                                  sticky
                                    ? {
                                        left: sticky.left,
                                        width: sticky.width,
                                        minWidth: sticky.width,
                                        maxWidth: sticky.width,
                                        backgroundClip: "padding-box",
                                      }
                                    : undefined
                                }
                              >
                                {key === "status" ? (
                                  <span
                                    className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${
                                      row.status_chip === "overdue"
                                        ? "bg-orange-100 text-orange-800 dark:bg-orange-500/25 dark:text-orange-200"
                                        : row.status_chip === "ok"
                                          ? "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/25 dark:text-emerald-200"
                                          : "bg-amber-100 text-amber-800 dark:bg-amber-500/25 dark:text-amber-200"
                                    }`}
                                  >
                                    {row.status}
                                  </span>
                                ) : key === "critical" || key === "stop_work" ? (
                                  row[key] ? (
                                    "Да"
                                  ) : (
                                    "—"
                                  )
                                ) : (
                                  String(row[key as keyof typeof row] ?? "—")
                                )}
                              </td>
                              );
                            })}
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </div>
          </FullscreenPanel>
          <div className="border-t border-tremor-border p-4 dark:border-dark-tremor-border">
            <DownloadTableButton
              getTable={exportTable}
              fileStem="predpisania"
              disabled={!rows.length}
            />
          </div>
        </Card>

        <div className="lg:hidden">
          <Title className="mb-3 px-2 !text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            Детальная таблица по предписаниям
          </Title>
          {!rows.length ? (
            <Text className="px-2 py-6 text-center">Нет строк по фильтрам.</Text>
          ) : (
            <MobileCardStack compact>
              {rows.map((row, index) => (
                <MobileEntityCard
                  key={`${row.pred_number}-${index}`}
                  title={row.contractor || "—"}
                  badge={row.status}
                  badgeTone={
                    row.status_chip === "overdue"
                      ? "bad"
                      : row.status_chip === "ok"
                        ? "ok"
                        : "warn"
                  }
                  className={
                    row.row_tone === "overdue"
                      ? "!border-rose-400 dark:!border-rose-500"
                      : row.row_tone === "resolved"
                        ? "!border-emerald-400 dark:!border-emerald-500"
                        : ""
                  }
                >
                  <MobileMetricGrid
                    columns={2}
                    items={[
                      { label: "Проект", value: row.project || "—" },
                      { label: "№ договора", value: row.contract_no || "—" },
                      { label: "№ документа", value: row.doc_number || "—" },
                      { label: "№ предписания", value: row.pred_number || "—" },
                      { label: "Дата выдачи", value: row.issue_date || "—", highlight: "date" },
                      { label: "Срок", value: row.due_date || "—", highlight: "date" },
                      {
                        label: "Факт устранения",
                        value: row.completion_date || "—",
                        highlight: "date",
                      },
                      {
                        label: "Дней просрочки",
                        value: row.overdue_days,
                        highlight: row.overdue_days > 0 ? "bad" : "none",
                        className:
                          row.overdue_days > 0
                            ? "text-rose-600 dark:text-rose-400"
                            : undefined,
                      },
                      {
                        label: "Критическое",
                        value: row.critical ? "Да" : "—",
                        highlight: row.critical ? "bad" : "none",
                      },
                      {
                        label: "Остановка",
                        value: row.stop_work ? "Да" : "—",
                        highlight: row.stop_work ? "bad" : "none",
                      },
                    ]}
                  />
                  {row.name ? (
                    <p className="mt-2 text-xs leading-snug text-tremor-content dark:text-dark-tremor-content">
                      {row.name}
                    </p>
                  ) : null}
                </MobileEntityCard>
              ))}
            </MobileCardStack>
          )}
          <div className="mt-3 px-2">
            <DownloadTableButton
              getTable={exportTable}
              fileStem="predpisania"
              disabled={!rows.length}
            />
          </div>
        </div>
      </div>
    </AppShell>
  );
}
