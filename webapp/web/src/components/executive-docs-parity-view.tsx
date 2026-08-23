"use client";

import { useCallback, useEffect, useState } from "react";
import {
  Card,
  Text,
  Title,
} from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  fetchExecutiveDocs,
  type ExecutiveDocsPayload,
} from "@/lib/api";
import {
  FilterCheck,
  FilterChipMulti,
  FilterChipSelect,
  FilterChecksRow,
  FilterField,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
} from "@/components/dashboard-filters";
import {
  ExecutiveDynamicsChart,
  ExecutiveObjectsChart,
  ExecutiveOverdueChart,
  ExecutiveStatusChart,
} from "@/components/executive-docs-charts";
import {
  MobileCardStack,
  MobileEntityCard,
  MobileMetricGrid,
} from "@/components/mobile-entity-card";
import { buildFilterChips } from "@/lib/filters-summary";
import { useDeferredUrlFilters } from "@/lib/use-url-filter-state";
import type { ExportCell, ExportTable } from "@/lib/table-export";
import { DashboardEmptyState } from "@/components/dashboard-empty-state";
import { DashboardInsight } from "@/components/dashboard-insight";
import {
  DashboardTableActions,
  DashboardTableTitle,
  MobilePaneTabs,
} from "@/components/mobile-ux";

type Filters = {
  projects: string[];
  contractor: string;
  doc_kind: string;
  date_from: string;
  date_to: string;
  granularity: string;
  hide_overdue_if_signed: boolean;
};

const INITIAL: Filters = {
  projects: [],
  contractor: "Все",
  doc_kind: "Все",
  date_from: "",
  date_to: "",
  granularity: "month",
  hide_overdue_if_signed: true,
};

type TabId = "sum" | "detail" | "dyn";

const DETAIL_COLS: Array<[string, string]> = [
  ["contractor", "Контрагент"],
  ["project", "Объект"],
  ["doc_number", "№ документа"],
  ["kind", "Тип"],
  ["plan_date", "Плановая дата сдачи"],
  ["fact_date", "Факт сдачи"],
  ["submit_late_days", "Просрочка сдачи"],
  ["transfer_date", "Дата передачи заказчику"],
  ["agree_date", "Дата согласования"],
  ["agree_late_days", "Просрочка соглас."],
  ["status_display", "Статус"],
  ["creation_date", "Дата создания"],
];

function chipClass(chip: string | undefined): string {
  switch (chip) {
    case "customer":
      return "bg-amber-100 text-amber-800 dark:bg-amber-500/25 dark:text-amber-200";
    case "contractor":
      return "bg-sky-100 text-sky-800 dark:bg-sky-500/25 dark:text-sky-200";
    case "accepted":
      return "bg-emerald-100 text-emerald-800 dark:bg-emerald-500/25 dark:text-emerald-200";
    case "declined":
      return "bg-rose-100 text-rose-800 dark:bg-rose-500/25 dark:text-rose-200";
    default:
      return "bg-slate-100 text-slate-700 dark:bg-slate-500/25 dark:text-slate-200";
  }
}

function fmtLate(days: number | null | undefined): string {
  if (days == null || Number.isNaN(days)) return "—";
  return `${days} дн.`;
}

export function ExecutiveDocsParityView() {
  const {
    draft: filters,
    setDraft: setFilters,
    applied,
    commit,
    reset,
    syncBoth,
    pending,
    dirty,
  } = useDeferredUrlFilters(INITIAL, { navId: "executive-docs" });
  const [data, setData] = useState<ExecutiveDocsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [tab, setTab] = useState<TabId>("sum");
  const [mobilePane, setMobilePane] = useState<"overdue" | "reports">("overdue");

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchExecutiveDocs({
          projects: next.projects,
          contractor: next.contractor !== "Все" ? next.contractor : undefined,
          doc_kind: next.doc_kind !== "Все" ? next.doc_kind : undefined,
          date_from: next.date_from || undefined,
          date_to: next.date_to || undefined,
          granularity: next.granularity,
          hide_overdue_if_signed: String(next.hide_overdue_if_signed),
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(applied);
  }, [applied, load]);

  useEffect(() => {
    if (
      data?.filters.date_min &&
      data.filters.date_max &&
      !applied.date_from &&
      !applied.date_to
    ) {
      syncBoth({
        date_from: data.filters.date_min,
        date_to: data.filters.date_max,
      });
    }
  }, [
    data?.filters.date_max,
    data?.filters.date_min,
    applied.date_from,
    applied.date_to,
    syncBoth,
  ]);

  // Период по умолчанию подставляется из данных — чипы сравниваем с ним
  const activeFilters = buildFilterChips(
    filters,
    {
      ...INITIAL,
      date_from: data?.filters.date_min ?? "",
      date_to: data?.filters.date_max ?? "",
    },
    [
      { key: "projects", name: "Объект" },
      { key: "contractor", name: "Контрагент" },
      { key: "doc_kind", name: "Вид документа" },
      { key: "date_from", name: "С", kind: "date" },
      { key: "date_to", name: "По", kind: "date" },
      { key: "granularity", name: "Период" },
      {
        key: "hide_overdue_if_signed",
        name: "Просрочка у подписанных",
        kind: "flag",
      },
    ],
    (patch) => setFilters((state) => ({ ...state, ...patch })),
  );

  const exportDetail = useCallback((): ExportTable | null => {
    const rows = data?.rows ?? [];
    if (!rows.length) return null;
    return {
      header: [DETAIL_COLS.map(([, label]) => label)],
      rows: rows.map((row) =>
        DETAIL_COLS.map(([key]) => {
          if (key === "submit_late_days" || key === "agree_late_days") {
            return fmtLate(row[key as keyof typeof row] as number | null);
          }
          if (key === "status_display") {
            return row.status_display ?? row.status;
          }
          return String(row[key as keyof typeof row] ?? "—");
        }),
      ),
    };
  }, [data?.rows]);

  const kpis = data?.kpis;
  const tabBtn = (id: TabId, label: string) => (
    <button
      type="button"
      onClick={() => setTab(id)}
      className={`border-b-2 px-1 pb-2 text-sm font-medium ${
        tab === id
          ? "border-emerald-500 text-emerald-700 dark:text-emerald-300"
          : "border-transparent text-tremor-content hover:text-tremor-content-strong"
      }`}
    >
      {label}
    </button>
  );

  return (
    <AppShell
      title="Исполнительная документация"
      subtitle="TESSA · сдача, согласование и просрочки ИД"
      loading={loading}>
      <FiltersCard
        open={filtersOpen}
        onToggle={() => setFiltersOpen((v) => !v)}
        activeFilters={activeFilters}
        onApply={commit}
        applyDisabled={!pending}
        onReset={dirty ? reset : undefined}
        resetDisabled={!dirty}
      >
        <FilterFieldsRow cols={5}>
          <FilterChipMulti
            label="Проект"
            values={filters.projects}
            options={data?.filters.projects ?? []}
            onChange={(projects) => setFilters((s) => ({ ...s, projects }))}
          />
          {(
            [
              ["Контрагент", "contractor", data?.filters.contractors ?? ["Все"]],
              ["Вид документа", "doc_kind", data?.filters.doc_kinds ?? ["Все"]],
            ] as const
          ).map(([label, key, options]) => (
            <FilterChipSelect
              key={key}
              label={label}
              value={filters[key]}
              options={options}
              onChange={(value) => setFilters((s) => ({ ...s, [key]: value }))}
            />
          ))}
          <FilterField label="Период">
            <div className="mt-1 grid grid-cols-2 gap-2">
              <input
                type="date"
                min={data?.filters.date_min ?? undefined}
                max={filters.date_to || data?.filters.date_max || undefined}
                value={filters.date_from}
                onChange={(e) => setFilters((s) => ({ ...s, date_from: e.target.value }))}
                className={FILTER_SELECT_CLASS.replace(" mt-1", "")}
                aria-label="Период с"
              />
              <input
                type="date"
                min={filters.date_from || data?.filters.date_min || undefined}
                max={data?.filters.date_max ?? undefined}
                value={filters.date_to}
                onChange={(e) => setFilters((s) => ({ ...s, date_to: e.target.value }))}
                className={FILTER_SELECT_CLASS.replace(" mt-1", "")}
                aria-label="Период по"
              />
            </div>
          </FilterField>
          <FilterChipSelect label="Гранулярность" value={filters.granularity} options={(data?.filters.granularities ?? []).map((item) => ({ value: item.id, label: item.label }))} onChange={(granularity) => setFilters((s) => ({ ...s, granularity }))} />
        </FilterFieldsRow>
        <FilterChecksRow cols={5}>
          <FilterCheck
            label="Не отображать просрочку, если ИД сдана (подписана/согласована)"
            checked={filters.hide_overdue_if_signed}
            onChange={(e) =>
              setFilters((s) => ({
                ...s,
                hide_overdue_if_signed: e.target.checked,
              }))
            }
          />
          <div />
          <div />
          <div />
          <div />
        </FilterChecksRow>
        <Text className="mt-3">
          {loading ? "загрузка…" : `${data?.meta.rows ?? 0} документов`}
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
        <FiltersCard
          title="Справочник видов документов ИД"
          open={catalogOpen}
          onToggle={() => setCatalogOpen((v) => !v)}
        >
          <Text className="mb-3 text-xs">
            Соответствие KindName из TESSA группам отчёта. Колонка «Строк в
            данных» — по текущей выгрузке до фильтров.
          </Text>
          <div className="bi-table-scroll overflow-x-auto rounded-lg border border-tremor-border dark:border-dark-tremor-border">
            <table className="bi-sticky-head bi-sticky-col min-w-full text-center text-sm">
              <thead>
                <tr className="bg-tremor-background-subtle dark:bg-dark-tremor-background-subtle">
                  {(
                    data?.filters.catalog?.[0]
                      ? Object.keys(data.filters.catalog[0])
                      : ["KindName", "Группа", "Описание", "В отчёте ИД", "Строк в данных"]
                  ).map((col) => (
                    <th
                      key={col}
                      className="whitespace-nowrap bg-tremor-background-subtle px-3 py-2 text-xs font-semibold uppercase tracking-wide text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content"
                    >
                      {col}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data?.filters.catalog ?? []).map((row, index) => (
                  <tr
                    key={`${String(row.KindName ?? index)}-${index}`}
                    className="border-t border-tremor-border dark:border-dark-tremor-border"
                  >
                    {Object.keys(data?.filters.catalog?.[0] ?? row).map((col) => (
                      <td
                        key={col}
                        className="max-w-xs px-3 py-2 align-top text-tremor-content-strong dark:text-dark-tremor-content-strong"
                      >
                        {String(row[col] ?? "—")}
                      </td>
                    ))}
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
          <DashboardTableActions className="mt-3 border-0 px-0 py-0">
            <DownloadTableButton
              getTable={() => {
                const rows = data?.filters.catalog ?? [];
                if (!rows.length) return null;
                const columns = Object.keys(rows[0]!);
                return {
                  header: [columns],
                  rows: rows.map((row) =>
                    columns.map((col) => row[col] as ExportCell),
                  ),
                } satisfies ExportTable;
              }}
              fileStem="exec_doc_kinds"
              disabled={!data?.filters.catalog?.length}
            />
          </DashboardTableActions>
        </FiltersCard>

        <div className="text-center lg:text-left">
          <Title className="!text-center !text-tremor-content-strong dark:!text-dark-tremor-content-strong lg:!text-left">
            Таблица Исполнительная документация накопительно
          </Title>
        </div>
        <DashboardInsight
          text={
            kpis?.overdue_total != null &&
            kpis?.on_rework != null &&
            kpis?.on_agree != null
              ? `Просрочек ${kpis.overdue_total} · у подрядчика ${kpis.on_rework} · на согласовании ${kpis.on_agree}`
              : null
          }
        />
        <div className="grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-6">
          {(
            [
              [
                "Всего документов",
                kpis?.total_docs,
                "Уникальные документы в текущей выборке",
                "bg-slate-100 border-slate-300 text-slate-800 dark:bg-slate-800/80 dark:border-slate-600 dark:text-slate-100",
                "bi-kpi-neutral",
              ],
              [
                "Отказы",
                kpis?.declined,
                "Документы со статусом отказа",
                "bg-rose-50 border-rose-300 text-rose-950 dark:bg-rose-950/40 dark:border-rose-500/50 dark:text-rose-100",
                "bi-kpi-risk",
              ],
              [
                "На согласовании",
                kpis?.on_agree,
                "Документы у заказчика",
                "bg-amber-50 border-amber-300 text-amber-950 dark:bg-amber-950/40 dark:border-amber-500/50 dark:text-amber-100",
                "bi-kpi-warn",
              ],
              [
                "Принято",
                kpis?.signed,
                "Только статус «Подписан»",
                "bg-emerald-50 border-emerald-300 text-emerald-950 dark:bg-emerald-950/40 dark:border-emerald-500/50 dark:text-emerald-100",
                "bi-kpi-ok",
              ],
              [
                "У подрядчика",
                kpis?.on_rework,
                "Документы на доработке",
                "bg-slate-100 border-slate-300 text-slate-800 dark:bg-slate-800/80 dark:border-slate-600 dark:text-slate-100",
                "bi-kpi-neutral",
              ],
              [
                "Всего просрочек",
                kpis?.overdue_total,
                "Подрядчик + заказчик",
                "bg-rose-50 border-rose-300 text-rose-950 dark:bg-rose-950/40 dark:border-rose-500/50 dark:text-rose-100",
                "bi-kpi-risk",
              ],
            ] as const
          ).map(([title, value, subtitle, color, kpiClass]) => (
            <div
              key={title}
              className={`rounded-[14px] border px-4 py-3.5 shadow-sm ${color} ${kpiClass}`}
            >
              <div className="text-xs font-medium text-slate-500 dark:text-slate-400">
                {title}
              </div>
              <div className="mt-2 text-[28px] font-extrabold leading-none tabular-nums">
                {value ?? "—"}
              </div>
              <div className="mt-2 text-xs leading-snug text-slate-500 dark:text-slate-400">
                {subtitle}
              </div>
            </div>
          ))}
        </div>

        <MobilePaneTabs
          value={mobilePane}
          onChange={setMobilePane}
          options={[
            { id: "overdue", label: "Просрочки" },
            { id: "reports", label: "Отчёты" },
          ]}
        />

        <div
          className={
            mobilePane === "overdue"
              ? "grid gap-6 lg:grid-cols-2"
              : "hidden gap-6 lg:grid lg:grid-cols-2"
          }
        >
          <FullscreenPanel fill>
            <Card className="rounded-xl bi-kpi-risk">
              <Title>Просрочка подрядчика (сдача ИД)</Title>
              <Text className="mt-1">Документов на доработке у подрядчика</Text>
              <div className="mt-1 text-3xl font-bold text-rose-600 dark:text-rose-400">{kpis?.contractor_overdue.count ?? 0}</div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                <div>
                  <Text>До 7 дней</Text>
                  <div className="text-lg font-semibold tabular-nums">{kpis?.contractor_overdue.bucket_0_7 ?? 0}</div>
                </div>
                <div>
                  <Text>7–30 дней</Text>
                  <div className="text-lg font-semibold tabular-nums">{kpis?.contractor_overdue.bucket_8_30 ?? 0}</div>
                </div>
                <div>
                  <Text>&gt; 30 дней</Text>
                  <div className="text-lg font-semibold tabular-nums">{kpis?.contractor_overdue.bucket_30_plus ?? 0}</div>
                </div>
              </div>
              <div className="mt-4"><ExecutiveOverdueChart rows={data?.tremor.overdue_contractor ?? []} /></div>
            </Card>
          </FullscreenPanel>
          <FullscreenPanel fill>
            <Card className="rounded-xl bi-kpi-warn">
              <Title>Просрочка заказчика (согласование)</Title>
              <Text className="mt-1">Документов на согласовании у заказчика</Text>
              <div className="mt-1 text-3xl font-bold text-amber-600 dark:text-amber-400">{kpis?.customer_overdue.count ?? 0}</div>
              <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                <div>
                  <Text>До 7 дней</Text>
                  <div className="text-lg font-semibold tabular-nums">{kpis?.customer_overdue.bucket_0_7 ?? 0}</div>
                </div>
                <div>
                  <Text>7–30 дней</Text>
                  <div className="text-lg font-semibold tabular-nums">{kpis?.customer_overdue.bucket_8_30 ?? 0}</div>
                </div>
                <div>
                  <Text>&gt; 30 дней</Text>
                  <div className="text-lg font-semibold tabular-nums">{kpis?.customer_overdue.bucket_30_plus ?? 0}</div>
                </div>
              </div>
              <div className="mt-4"><ExecutiveOverdueChart rows={data?.tremor.overdue_customer ?? []} customer /></div>
            </Card>
          </FullscreenPanel>
        </div>

        <div
          className={
            mobilePane === "reports" ? "block space-y-6" : "hidden space-y-6 lg:block"
          }
        >
        <div className="flex gap-6 border-b border-tremor-border dark:border-dark-tremor-border">
          {tabBtn("sum", "Накопительным итогом")}
          {tabBtn("detail", "Детальный отчёт")}
          {tabBtn("dyn", "Динамика")}
        </div>

        {tab === "sum" ? (
          <div className="space-y-6">
            <FullscreenPanel fill>
              <Card className="rounded-xl">
                <Title>Распределение по статусам</Title>
                <div className="mt-4"><ExecutiveStatusChart rows={data?.tremor.by_status ?? []} /></div>
              </Card>
            </FullscreenPanel>
            <FullscreenPanel fill>
              <Card className="rounded-xl">
                <Title>Документы по объектам</Title>
                <div className="mt-4"><ExecutiveObjectsChart rows={data?.tremor.by_object ?? []} /></div>
              </Card>
            </FullscreenPanel>
          </div>
        ) : null}

        {tab === "dyn" ? (
          <FullscreenPanel fill>
            <Card className="rounded-xl">
              <Title>
                Динамика (
                {(data?.filters.granularities ?? []).find(
                  (g) => g.id === filters.granularity,
                )?.label ?? "месяц"}
                , по дате создания)
              </Title>
              <div className="mt-4"><ExecutiveDynamicsChart rows={data?.tremor.dynamics ?? []} /></div>
              <Text className="mt-2">
                График поступления документов по выбранной гранулярности
              </Text>
            </Card>
          </FullscreenPanel>
        ) : null}

        {tab === "detail" ? (
          <>
            <Card className="hidden overflow-hidden rounded-xl p-0 lg:block">
            <DashboardTableTitle>
              Детальный отчёт по сдаче и согласованию ИД
            </DashboardTableTitle>
            <FullscreenPanel disabled={!data?.rows?.length} scroll={false}>
              <div className="bi-table-scroll">
                {!data?.rows?.length ? (
                  <DashboardEmptyState
                    message="Нет строк"
                    onReset={activeFilters.length ? reset : undefined}
                  />
                ) : (
                  <table className="bi-sticky-head bi-sticky-col min-w-max border-separate border-spacing-0 text-center text-sm">
                    <thead>
                      <tr>
                        {DETAIL_COLS.map(([key, label]) => (
                          <th
                            key={key}
                            className="whitespace-nowrap border-b border-tremor-border bg-tremor-background-subtle px-3 py-3 text-xs font-semibold uppercase tracking-wide dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle"
                          >
                            {label}
                          </th>
                        ))}
                      </tr>
                    </thead>
                    <tbody>
                      {(data?.rows ?? []).map((row, index) => (
                        <tr
                          key={`${row.doc_number}-${index}`}
                          className="bi-row-alt border-t border-tremor-border dark:border-dark-tremor-border"
                        >
                          {DETAIL_COLS.map(([key]) => (
                            <td
                              key={key}
                              className={`whitespace-nowrap px-3 py-2 align-middle${
                                key === "submit_late_days" || key === "agree_late_days"
                                  ? " bi-num"
                                  : ""
                              }`}
                            >
                              {key === "status_display" ? (
                                <span
                                  className={`inline-flex rounded-full px-2.5 py-1 text-xs font-medium ${chipClass(row.status_chip)}`}
                                >
                                  {row.status_display ?? row.status}
                                </span>
                              ) : key === "submit_late_days" ||
                                key === "agree_late_days" ? (
                                fmtLate(
                                  row[key as keyof typeof row] as number | null,
                                )
                              ) : (
                                String(row[key as keyof typeof row] ?? "—")
                              )}
                            </td>
                          ))}
                        </tr>
                      ))}
                    </tbody>
                  </table>
                )}
              </div>
            </FullscreenPanel>
            <DashboardTableActions>
              <DownloadTableButton
                getTable={exportDetail}
                fileStem="executive_docs"
                disabled={!data?.rows?.length}
              />
            </DashboardTableActions>
            </Card>
            <div className="lg:hidden">
            <DashboardTableTitle className="mb-3 border-0 px-2 py-0">
              Детальный отчёт по сдаче и согласованию ИД
            </DashboardTableTitle>
            {!data?.rows?.length ? (
              <DashboardEmptyState
                message="Нет строк"
                onReset={activeFilters.length ? reset : undefined}
              />
            ) : (
              <MobileCardStack compact>
                {data.rows.map((row, index) => (
                  <MobileEntityCard
                    key={`${row.doc_number}-${index}`}
                    title={row.doc_number || "—"}
                    badge={row.status_display ?? row.status}
                    badgeTone={
                      row.status_chip === "accepted"
                        ? "ok"
                        : row.status_chip === "declined"
                          ? "bad"
                          : "warn"
                    }
                  >
                    <MobileMetricGrid
                      columns={2}
                      items={[
                        { label: "Контрагент", value: row.contractor || "—" },
                        { label: "Объект", value: row.project || "—" },
                        { label: "Тип", value: row.kind || "—" },
                        { label: "План сдачи", value: row.plan_date || "—", highlight: "date" },
                        { label: "Факт сдачи", value: row.fact_date || "—", highlight: "date" },
                        {
                          label: "Просрочка сдачи",
                          value: fmtLate(row.submit_late_days),
                          highlight: (row.submit_late_days ?? 0) > 0 ? "bad" : "none",
                          className: (row.submit_late_days ?? 0) > 0 ? "text-rose-600 dark:text-rose-400" : undefined,
                        },
                        { label: "Передача заказчику", value: row.transfer_date || "—", highlight: "date" },
                        { label: "Согласование", value: row.agree_date || "—", highlight: "date" },
                        {
                          label: "Просрочка соглас.",
                          value: fmtLate(row.agree_late_days),
                          highlight: (row.agree_late_days ?? 0) > 0 ? "bad" : "none",
                          className: (row.agree_late_days ?? 0) > 0 ? "text-rose-600 dark:text-rose-400" : undefined,
                        },
                        { label: "Дата создания", value: row.creation_date || "—", highlight: "date" },
                      ]}
                    />
                  </MobileEntityCard>
                ))}
              </MobileCardStack>
            )}
            <DashboardTableActions className="mt-3 border-0 px-2 py-0">
              <DownloadTableButton getTable={exportDetail} fileStem="executive_docs" disabled={!data?.rows?.length} />
            </DashboardTableActions>
            </div>
          </>
        ) : null}
        </div>
      </div>
    </AppShell>
  );
}
