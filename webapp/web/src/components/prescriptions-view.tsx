"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart,
  Card,
  DonutChart,
  Grid,
  Metric,
  Text,
  Title,
} from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import { fetchPrescriptions, type PrescriptionsPayload } from "@/lib/api";
import {
  FilterCheck,
  FilterChipMulti,
  FilterChecksRow,
  FilterField,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import type { ExportCell, ExportTable } from "@/lib/table-export";

type Filters = {
  projects: string[];
  contractors: string[];
  contract_q: string;
  date_from: string;
  date_to: string;
  hide_resolved: boolean;
};
type SortState = { key: string; asc: boolean } | null;
type TremorColor =
  | "rose"
  | "red"
  | "orange"
  | "emerald"
  | "amber"
  | "yellow"
  | "fuchsia"
  | "slate";

const STATUS_KEYS = [
  "Остановка работ",
  "Критические",
  "Не устранено",
  "Сдано в срок",
  "Устранено с просрочкой",
] as const;

/** Tremor принимает имена палитры, не hex — hex даёт чёрные сегменты. */
const STATUS_TREMOR_COLOR: Record<string, TremorColor> = {
  "Остановка работ": "rose",
  Критические: "red",
  "Не устранено": "orange",
  "Сдано в срок": "emerald",
  "Устранено с просрочкой": "amber",
};

const tableColumns: Array<[string, string]> = [
  ["status", "Статус предписания"],
  ["contractor", "Подрядчик"],
  ["project", "Проект"],
  ["contract_no", "№ договора"],
  ["doc_number", "№ документа"],
  ["pred_number", "№ предписания"],
  ["name", "Наименование"],
  ["issue_date", "Дата выдачи предписания"],
  ["issue_block", "Блок выдачи предписания"],
  ["due_date", "Срок устранения"],
  ["completion_date", "Фактическая дата устранения предписания"],
  ["overdue_days", "Дней просрочки"],
  ["critical", "Критические предписания"],
  ["stop_work", "Остановка работ"],
];

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
  const [filters, setFilters] = useState<Filters>({
    projects: [],
    contractors: [],
    contract_q: "",
    date_from: "",
    date_to: "",
    hide_resolved: false,
  });
  const [data, setData] = useState<PrescriptionsPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [sort, setSort] = useState<SortState>(null);

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchPrescriptions({
          projects: next.projects,
          contractors: next.contractors,
          contract_q: next.contract_q || undefined,
          date_from: next.date_from || undefined,
          date_to: next.date_to || undefined,
          hide_resolved: next.hide_resolved ? "true" : undefined,
        }),
      );
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(filters);
  }, [filters, load]);

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
    () =>
      (data?.tremor.by_contractor ?? []).map((row) => ({
        contractor: row.contractor,
        Всего: row.total,
        Просрочено: row.overdue,
      })),
    [data?.tremor.by_contractor],
  );

  const statusChart = useMemo(
    () =>
      (data?.tremor.by_status ?? []).map((row) => ({
        name: row.name,
        value: row.value,
      })),
    [data?.tremor.by_status],
  );

  const statusColors = useMemo(
    () =>
      statusChart.map(
        (row) => STATUS_TREMOR_COLOR[row.name] ?? ("slate" as TremorColor),
      ),
    [statusChart],
  );

  const objectCategories = useMemo(() => {
    const present = new Set<string>();
    for (const row of data?.tremor.by_object ?? []) {
      for (const key of STATUS_KEYS) {
        if (Number((row as Record<string, unknown>)[key] ?? 0) > 0) present.add(key);
      }
    }
    return STATUS_KEYS.filter((key) => present.has(key));
  }, [data?.tremor.by_object]);

  const objectColors = useMemo(
    () => objectCategories.map((key) => STATUS_TREMOR_COLOR[key] ?? "slate"),
    [objectCategories],
  );

  const objectChart = useMemo(
    () =>
      (data?.tremor.by_object ?? []).map((row) => {
        const out: Record<string, string | number> = { object: row.object };
        for (const key of objectCategories) {
          out[key] = Number((row as Record<string, unknown>)[key] ?? 0);
        }
        return out;
      }),
    [data?.tremor.by_object, objectCategories],
  );

  const reset = () =>
    setFilters({
      projects: [],
      contractors: [],
      contract_q: "",
      date_from: "",
      date_to: "",
      hide_resolved: false,
    });

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
  const circleKpis = [
    ["Всего", kpis?.total, "neutral"],
    ["Неустраненные", kpis?.unresolved, "warn"],
    ["Устраненные", kpis?.resolved, "ok"],
    ["Просроченные неустраненные", kpis?.overdue_unresolved, "danger"],
    ["Критические", kpis?.critical, "danger"],
    ["Остановка работ", kpis?.stop_work, "danger"],
  ] as const;

  return (
    <AppShell
      title="Предписания по подрядчикам"
      subtitle="TESSA · статусы, сроки устранения и критичность"
    >
      <FiltersCard open={filtersOpen} onToggle={() => setFiltersOpen((value) => !value)}>
        <FiltersReset onClick={reset} />
        <FilterFieldsRow cols={5}>
          <FilterChipMulti label="Проекты" options={data?.filters.projects ?? []} values={filters.projects} onChange={(projects) => setFilters((state) => ({ ...state, projects }))} />
          <FilterChipMulti label="Подрядчики" options={data?.filters.contractors ?? []} values={filters.contractors} onChange={(contractors) => setFilters((state) => ({ ...state, contractors }))} />
          <FilterField label="№ договора">
            <input
              value={filters.contract_q}
              onChange={(e) =>
                setFilters((state) => ({
                  ...state,
                  contract_q: e.target.value,
                }))
              }
              className={FILTER_SELECT_CLASS}
              placeholder="Частичный поиск"
            />
          </FilterField>
          <FilterField label="Дата с">
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
              className={FILTER_SELECT_CLASS}
            />
          </FilterField>
          <FilterField label="Дата по">
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
              className={FILTER_SELECT_CLASS}
            />
          </FilterField>
        </FilterFieldsRow>
        <FilterChecksRow cols={5}>
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
        <Grid numItemsSm={2} numItemsLg={4} className="gap-6">
          {(
            [
              ["Всего", kpis?.total, "text-tremor-content-strong"],
              [
                "Устраненные",
                kpis?.resolved,
                "text-emerald-600 dark:text-emerald-400",
              ],
              [
                "Неустраненные",
                kpis?.unresolved,
                "text-orange-600 dark:text-orange-400",
              ],
              [
                "Непросроченные",
                kpis?.non_overdue,
                "text-emerald-600 dark:text-emerald-400",
              ],
            ] as const
          ).map(([title, value, color]) => (
            <Card key={title} className="rounded-xl">
              <Text>{title}</Text>
              <Metric className={`mt-2 ${color}`}>{value ?? "—"}</Metric>
            </Card>
          ))}
        </Grid>

        <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-6">
          {circleKpis.map(([title, value, tone]) => (
            <div
              key={title}
              className={`rounded-xl border p-3 text-center ${
                tone === "danger"
                  ? "border-rose-300"
                  : tone === "warn"
                    ? "border-orange-300"
                    : tone === "ok"
                      ? "border-emerald-300"
                      : "border-tremor-border dark:border-dark-tremor-border"
              }`}
            >
              <div className="text-xl font-bold tabular-nums">{value ?? "—"}</div>
              <Text>{title}</Text>
            </div>
          ))}
        </div>

        <Grid numItemsLg={2} className="gap-6">
          <FullscreenPanel fill>
            <Card className="rounded-xl">
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Предписания по подрядчикам
              </Title>
              <Text className="mt-1">Всего и просроченные неустраненные</Text>
              <BarChart
                className="mt-6 h-96"
                data={contractorChart}
                index="contractor"
                categories={["Всего", "Просрочено"]}
                colors={["orange", "amber"]}
                layout="horizontal"
                valueFormatter={(value) => String(Math.round(Number(value)))}
                showLegend
                showGridLines
                yAxisWidth={160}
              />
            </Card>
          </FullscreenPanel>
          <FullscreenPanel fill>
            <Card className="rounded-xl">
              <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
                Предписания по статусам
              </Title>
              <DonutChart
                className="mt-6 h-72"
                data={statusChart}
                index="name"
                category="value"
                colors={statusColors}
                valueFormatter={(value) => String(Math.round(Number(value)))}
                showLabel
                showAnimation
              />
            </Card>
          </FullscreenPanel>
        </Grid>

        <FullscreenPanel fill>
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Предписания по объектам
            </Title>
            <BarChart
              className="mt-6 h-96"
              data={objectChart}
              index="object"
              categories={[...objectCategories]}
              colors={objectColors}
              stack
              valueFormatter={(value) => String(Math.round(Number(value)))}
              showLegend
              showGridLines
            />
          </Card>
        </FullscreenPanel>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Детальная таблица по предписаниям
            </Title>
          </div>
          <div className="max-h-[36rem] overflow-auto">
            {!rows.length ? (
              <div className="px-4 py-10 text-center text-sm text-tremor-content">
                Нет строк по фильтрам.
              </div>
            ) : (
              <table className="min-w-max border-separate border-spacing-0 text-left text-sm">
                <thead className="sticky top-0 z-10">
                  <tr>
                    {tableColumns.map(([key, label]) => (
                      <th
                        key={key}
                        className="whitespace-nowrap border-b border-tremor-border bg-tremor-background-subtle px-3 py-3 text-xs font-semibold uppercase tracking-wide text-tremor-content dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content"
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
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {rows.map((row, index) => (
                    <tr
                      key={`${row.pred_number}-${index}`}
                      className={
                        row.row_tone === "overdue"
                          ? "bg-rose-50/80 dark:bg-rose-950/25"
                          : row.row_tone === "resolved"
                            ? "bg-emerald-50/60 dark:bg-emerald-950/20"
                            : "bg-tremor-background dark:bg-dark-tremor-background"
                      }
                    >
                      {tableColumns.map(([key]) => (
                        <td
                          key={key}
                          className={`max-w-72 whitespace-nowrap border-b border-tremor-border px-3 py-2 align-middle dark:border-dark-tremor-border ${
                            key === "overdue_days" && row.overdue_days > 0
                              ? "font-semibold text-rose-600 dark:text-rose-400"
                              : "text-tremor-content-strong dark:text-dark-tremor-content-strong"
                          }`}
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
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            )}
          </div>
          <div className="border-t border-tremor-border p-4 dark:border-dark-tremor-border">
            <DownloadTableButton
              getTable={exportTable}
              fileStem="predpisania"
              disabled={!rows.length}
            />
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
