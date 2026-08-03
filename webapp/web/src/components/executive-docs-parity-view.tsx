"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart,
  Card,
  Grid,
  Metric,
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
  FilterChipSelect,
  FilterChecksRow,
  FilterField,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import type { ExportCell, ExportTable } from "@/lib/table-export";

type Filters = {
  project: string;
  contractor: string;
  doc_kind: string;
  date_from: string;
  date_to: string;
  granularity: string;
  hide_overdue_if_signed: boolean;
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

function statusBarColor(status: string): "orange" | "yellow" | "rose" | "emerald" | "slate" {
  const s = status.toLowerCase();
  if (s.includes("согласован") && !s.includes("на согласован")) return "emerald";
  if (s.includes("подписан")) return "emerald";
  if (s.includes("доработ")) return "yellow";
  if (s.includes("согласован")) return "orange";
  if (s.includes("отказ") || s.includes("отмен")) return "rose";
  return "slate";
}

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
  const [filters, setFilters] = useState<Filters>({
    project: "Все",
    contractor: "Все",
    doc_kind: "Все",
    date_from: "",
    date_to: "",
    granularity: "month",
    hide_overdue_if_signed: true,
  });
  const [data, setData] = useState<ExecutiveDocsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [catalogOpen, setCatalogOpen] = useState(false);
  const [tab, setTab] = useState<TabId>("sum");

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchExecutiveDocs({
          project: next.project !== "Все" ? next.project : undefined,
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
    void load(filters);
  }, [filters, load]);

  const reset = () =>
    setFilters({
      project: "Все",
      contractor: "Все",
      doc_kind: "Все",
      date_from: "",
      date_to: "",
      granularity: "month",
      hide_overdue_if_signed: true,
    });

  const statusChart = useMemo(
    () =>
      (data?.tremor.by_status ?? []).map((row) => ({
        status: row.status,
        Количество: row.count,
      })),
    [data?.tremor.by_status],
  );

  const statusColors = useMemo(
    () => statusChart.map((row) => statusBarColor(row.status)),
    [statusChart],
  );

  const objectChart = useMemo(
    () =>
      (data?.tremor.by_object ?? []).map((row) => ({
        object: row.object,
        Количество: row.count,
      })),
    [data?.tremor.by_object],
  );

  const dynamicsChart = useMemo(
    () =>
      (data?.tremor.dynamics ?? []).map((row) => ({
        period: row.period,
        Количество: row.new_docs,
      })),
    [data?.tremor.dynamics],
  );

  const exportCatalog = useCallback((): ExportTable | null => {
    const catalog = data?.filters.catalog ?? [];
    if (!catalog.length) return null;
    const keys = Object.keys(catalog[0]);
    return {
      header: [keys],
      rows: catalog.map((row) => keys.map((key) => row[key] as ExportCell)),
    };
  }, [data?.filters.catalog]);

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
      <FiltersCard open={filtersOpen} onToggle={() => setFiltersOpen((v) => !v)}>
        <FiltersReset onClick={reset} />
        <FilterFieldsRow cols={5}>
          {(
            [
              ["Проект", "project", data?.filters.projects ?? ["Все"]],
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
          <FilterField label="Период с">
            <input
              type="date"
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_from}
              onChange={(e) =>
                setFilters((s) => ({ ...s, date_from: e.target.value }))
              }
              className={FILTER_SELECT_CLASS}
            />
          </FilterField>
          <FilterField label="Период по">
            <input
              type="date"
              min={data?.filters.date_min ?? undefined}
              max={data?.filters.date_max ?? undefined}
              value={filters.date_to}
              onChange={(e) =>
                setFilters((s) => ({ ...s, date_to: e.target.value }))
              }
              className={FILTER_SELECT_CLASS}
            />
          </FilterField>
        </FilterFieldsRow>
        <FilterFieldsRow cols={5}>
          <FilterChipSelect label="Гранулярность" value={filters.granularity} options={(data?.filters.granularities ?? []).map((item) => ({ value: item.id, label: item.label }))} onChange={(granularity) => setFilters((s) => ({ ...s, granularity }))} />
          <div />
          <div />
          <div />
          <div />
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

      <Card className="mb-6 rounded-xl">
        <button
          type="button"
          onClick={() => setCatalogOpen((v) => !v)}
          className="flex w-full items-center justify-between text-left"
        >
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            Справочник видов документов ИД
          </Title>
          <span>{catalogOpen ? "▲" : "▼"}</span>
        </button>
        {catalogOpen ? (
          <>
            <div className="mt-3 max-h-64 overflow-auto">
              <table className="min-w-full text-left text-sm">
                <thead className="sticky top-0 bg-tremor-background-subtle dark:bg-dark-tremor-background-subtle">
                  <tr>
                    {Object.keys(data?.filters.catalog[0] ?? {}).map((key) => (
                      <th key={key} className="whitespace-nowrap px-3 py-2 text-xs">
                        {key}
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {(data?.filters.catalog ?? []).map((row, index) => (
                    <tr
                      key={index}
                      className="border-t border-tremor-border dark:border-dark-tremor-border"
                    >
                      {Object.values(row).map((value, i) => (
                        <td key={i} className="whitespace-nowrap px-3 py-2">
                          {String(value ?? "—")}
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            <div className="mt-3">
              <DownloadTableButton
                getTable={exportCatalog}
                fileStem="exec_doc_kinds"
                disabled={!data?.filters.catalog?.length}
              />
            </div>
          </>
        ) : null}
      </Card>

      <div className="space-y-6">
        <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
          Исполнительная документация накопительно
        </Title>
        <Grid numItemsSm={2} numItemsLg={3} className="gap-4">
          {(
            [
              ["Всего документов", kpis?.total_docs, "border-sky-300"],
              ["Отказы", kpis?.declined, "border-rose-300"],
              ["На согласовании", kpis?.on_agree, "border-amber-300"],
              ["Принято", kpis?.signed, "border-emerald-300"],
              ["У подрядчика", kpis?.on_rework, "border-cyan-300"],
              ["Всего просрочек", kpis?.overdue_total, "border-rose-400"],
            ] as const
          ).map(([title, value, border]) => (
            <Card key={title} className={`rounded-xl border ${border}`}>
              <Text>{title}</Text>
              <Metric className="mt-2">{value ?? "—"}</Metric>
            </Card>
          ))}
        </Grid>

        <Grid numItemsLg={2} className="gap-6">
          <FullscreenPanel fill>
            <Card className="rounded-xl">
              <Title>Просрочка подрядчика (сдача ИД)</Title>
              <Metric className="mt-2 text-rose-600 dark:text-rose-400">
                {kpis?.contractor_overdue.count ?? 0}
              </Metric>
              <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                <Text>До 7 дней: {kpis?.contractor_overdue.bucket_0_7 ?? 0}</Text>
                <Text>7–30 дней: {kpis?.contractor_overdue.bucket_8_30 ?? 0}</Text>
                <Text>&gt; 30 дней: {kpis?.contractor_overdue.bucket_30_plus ?? 0}</Text>
              </div>
              <BarChart
                className="mt-6 h-72"
                data={(data?.tremor.overdue_contractor ?? []).map((row) => ({
                  contractor: row.contractor,
                  Количество: row.count,
                }))}
                index="contractor"
                categories={["Количество"]}
                colors={["rose"]}
                layout="horizontal"
                showLegend={false}
                yAxisWidth={140}
              />
            </Card>
          </FullscreenPanel>
          <FullscreenPanel fill>
            <Card className="rounded-xl">
              <Title>Просрочка заказчика (согласование)</Title>
              <Metric className="mt-2 text-amber-600 dark:text-amber-400">
                {kpis?.customer_overdue.count ?? 0}
              </Metric>
              <div className="mt-3 grid grid-cols-3 gap-2 text-sm">
                <Text>До 7 дней: {kpis?.customer_overdue.bucket_0_7 ?? 0}</Text>
                <Text>7–30 дней: {kpis?.customer_overdue.bucket_8_30 ?? 0}</Text>
                <Text>&gt; 30 дней: {kpis?.customer_overdue.bucket_30_plus ?? 0}</Text>
              </div>
              <BarChart
                className="mt-6 h-72"
                data={(data?.tremor.overdue_customer ?? []).map((row) => ({
                  contractor: row.contractor,
                  Количество: row.count,
                }))}
                index="contractor"
                categories={["Количество"]}
                colors={["amber"]}
                layout="horizontal"
                showLegend={false}
                yAxisWidth={140}
              />
            </Card>
          </FullscreenPanel>
        </Grid>

        <div className="flex gap-6 border-b border-tremor-border dark:border-dark-tremor-border">
          {tabBtn("sum", "Накопительным итогом")}
          {tabBtn("detail", "Детальный отчёт")}
          {tabBtn("dyn", "Динамика")}
        </div>

        {tab === "sum" ? (
          <Grid numItemsLg={2} className="gap-6">
            <FullscreenPanel fill>
              <Card className="rounded-xl">
                <Title>Распределение по статусам</Title>
                <BarChart
                  className="mt-6 h-80"
                  data={statusChart}
                  index="status"
                  categories={["Количество"]}
                  colors={statusColors}
                  showLegend={false}
                />
              </Card>
            </FullscreenPanel>
            <FullscreenPanel fill>
              <Card className="rounded-xl">
                <Title>Документы по объектам</Title>
                <BarChart
                  className="mt-6 h-80"
                  data={objectChart}
                  index="object"
                  categories={["Количество"]}
                  colors={["teal"]}
                  showLegend={false}
                />
              </Card>
            </FullscreenPanel>
          </Grid>
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
              <BarChart
                className="mt-6 h-96"
                data={dynamicsChart}
                index="period"
                categories={["Количество"]}
                colors={["blue"]}
                showLegend={false}
              />
              <Text className="mt-2">
                График поступления документов по выбранной гранулярности
              </Text>
            </Card>
          </FullscreenPanel>
        ) : null}

        {tab === "detail" ? (
          <Card className="overflow-hidden rounded-xl p-0">
            <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
              <Title>Детальный отчёт по сдаче и согласованию ИД</Title>
            </div>
            <div className="max-h-[36rem] overflow-auto">
              {!data?.rows?.length ? (
                <div className="px-4 py-10 text-center text-sm">Нет строк</div>
              ) : (
                <table className="min-w-max border-separate border-spacing-0 text-left text-sm">
                  <thead className="sticky top-0 z-10">
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
                        className="border-t border-tremor-border dark:border-dark-tremor-border"
                      >
                        {DETAIL_COLS.map(([key]) => (
                          <td
                            key={key}
                            className="whitespace-nowrap px-3 py-2 align-middle"
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
            <div className="border-t border-tremor-border p-4 dark:border-dark-tremor-border">
              <DownloadTableButton
                getTable={exportDetail}
                fileStem="executive_docs"
                disabled={!data?.rows?.length}
              />
            </div>
          </Card>
        ) : null}
      </div>
    </AppShell>
  );
}
