"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart, Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  fetchBdds,
  type BddsGroup,
  type BddsPayload,
  type BddsView,
} from "@/lib/api";
import type { ExportTable } from "@/lib/table-export";

type Filters = {
  projects: string[];
  date_from: string;
  date_to: string;
  group: BddsGroup;
  view: BddsView;
  hide_zero: boolean | null;
  show_deviation: boolean;
};

const INITIAL: Filters = {
  projects: [],
  date_from: "",
  date_to: "",
  group: "month",
  view: "monthly",
  hide_zero: null,
  show_deviation: false,
};

const PLAN_SERIES = "БДДС план";
const FACT_SERIES = "БДДС факт";
const DEVIATION_SERIES = "Отклонение";

const inputClass =
  "mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background";
const chipClass =
  "rounded-md border px-2.5 py-1 text-xs border-tremor-border bg-white text-tremor-content-strong dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong";
const chipOnClass =
  "rounded-md border px-2.5 py-1 text-xs border-emerald-600 bg-emerald-50 text-emerald-900 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-200";
const headCell =
  "px-3 py-2 text-tremor-label uppercase text-tremor-content dark:text-dark-tremor-content";

function mln(value: number): string {
  return (Number(value || 0) / 1_000_000).toLocaleString("ru-RU", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
}

function deviationClass(value: number): string {
  if (Math.abs(value) < 10_000) {
    return "text-tremor-content-strong dark:text-dark-tremor-content-strong";
  }
  return value < 0
    ? "font-semibold text-[#b91c1c] dark:text-rose-300"
    : "font-semibold text-[#15803d] dark:text-emerald-300";
}

export function BddsView() {
  const [filters, setFilters] = useState<Filters>(INITIAL);
  const [data, setData] = useState<BddsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchBdds({
          projects: next.projects,
          date_from: next.date_from || undefined,
          date_to: next.date_to || undefined,
          group: next.group,
          view: next.view,
          hide_zero: next.hide_zero ?? undefined,
          show_deviation: next.show_deviation,
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

  const periodLabel = data?.labels.period ?? "Месяц";
  const zeroToggleEnabled =
    filters.group === "month" && filters.view === "monthly";
  // как в main: чекбокс включён по умолчанию, пока не выбран конкретный проект
  const hideZero = filters.hide_zero ?? filters.projects.length === 0;
  const periodRows = data?.period_rows ?? [];
  const projectRows = data?.project_rows ?? [];
  const totals = data?.totals ?? { plan: 0, fact: 0, deviation: 0 };
  const metaError = data?.meta.error ?? null;
  const isFallback = (data?.meta.mode ?? "") !== "synthetic_1c";

  const chartData = useMemo(() => {
    const rows = data?.tremor.by_period ?? [];
    return rows.map((row) => ({
      period: row.period,
      [PLAN_SERIES]: row.plan,
      [FACT_SERIES]: row.fact,
      [DEVIATION_SERIES]: row.deviation,
    }));
  }, [data]);

  const chartCategories = filters.show_deviation
    ? [PLAN_SERIES, FACT_SERIES, DEVIATION_SERIES]
    : [PLAN_SERIES, FACT_SERIES];

  const periodExport = (): ExportTable | null => {
    if (!periodRows.length) return null;
    const rows = periodRows.map((row) => [
      row.project,
      row.period,
      row.kind === "project" ? "" : Number((row.plan / 1_000_000).toFixed(1)),
      row.kind === "project" ? "" : Number((row.fact / 1_000_000).toFixed(1)),
      row.kind === "project"
        ? ""
        : Number((row.deviation / 1_000_000).toFixed(1)),
    ]);
    rows.push([
      "ИТОГО",
      data?.labels.total_period ?? "",
      Number((totals.plan / 1_000_000).toFixed(1)),
      Number((totals.fact / 1_000_000).toFixed(1)),
      Number((totals.deviation / 1_000_000).toFixed(1)),
    ]);
    return {
      header: [
        [
          "Проект",
          periodLabel,
          "План, млн. руб.",
          "Факт, млн. руб.",
          "Отклонение, млн. руб.",
        ],
      ],
      rows,
      sheetName: "БДДС",
    };
  };

  const projectExport = (): ExportTable | null => {
    if (!projectRows.length) return null;
    const rows = projectRows.map((row) => [
      row.project,
      Number((row.plan / 1_000_000).toFixed(1)),
      Number((row.fact / 1_000_000).toFixed(1)),
      Number((row.deviation / 1_000_000).toFixed(1)),
    ]);
    rows.push([
      "ИТОГО",
      Number((totals.plan / 1_000_000).toFixed(1)),
      Number((totals.fact / 1_000_000).toFixed(1)),
      Number((totals.deviation / 1_000_000).toFixed(1)),
    ]);
    return {
      header: [
        [
          "Проект",
          "План, млн. руб.",
          "Факт, млн. руб.",
          "Отклонение, млн. руб.",
        ],
      ],
      rows,
      sheetName: "БДДС по проектам",
    };
  };

  const toggleProject = (name: string) => {
    setFilters((state) => ({
      ...state,
      projects: state.projects.includes(name)
        ? state.projects.filter((p) => p !== name)
        : [...state.projects, name],
    }));
  };

  const dirty =
    filters.projects.length > 0 ||
    filters.date_from !== "" ||
    filters.date_to !== "" ||
    filters.group !== "month" ||
    filters.view !== "monthly" ||
    filters.hide_zero !== null ||
    filters.show_deviation;

  return (
    <AppShell title="БДДС (расходы)">
      <Card className="mb-6 rounded-xl">
        <button
          type="button"
          onClick={() => setFiltersOpen((state) => !state)}
          aria-expanded={filtersOpen}
          className="flex w-full items-center gap-2 text-left text-sm font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong"
        >
          <span className="text-xs">{filtersOpen ? "▾" : "▸"}</span>
          Фильтры
        </button>

        {filtersOpen ? (
          <div className="mt-3">
            <button
              type="button"
              onClick={() => setFilters(INITIAL)}
              disabled={!dirty}
              className="rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-1.5 text-sm disabled:opacity-40 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            >
              Сбросить
            </button>

            <Text className="mt-3">Проект</Text>
            <div className="mt-2 flex flex-wrap gap-2">
              <button
                type="button"
                onClick={() => setFilters((state) => ({ ...state, projects: [] }))}
                className={filters.projects.length === 0 ? chipOnClass : chipClass}
              >
                Все
              </button>
              {(data?.filters.projects ?? []).map((name) => (
                <button
                  key={name}
                  type="button"
                  onClick={() => toggleProject(name)}
                  className={
                    filters.projects.includes(name) ? chipOnClass : chipClass
                  }
                >
                  {name}
                </button>
              ))}
            </div>

            <div className="mt-4 grid gap-3 md:grid-cols-4">
              <label className="block text-sm">
                <Text>Период с</Text>
                <input
                  className={inputClass}
                  type="date"
                  min={data?.filters.date_min ?? undefined}
                  max={data?.filters.date_max ?? undefined}
                  value={filters.date_from}
                  onChange={(event) =>
                    setFilters((state) => ({
                      ...state,
                      date_from: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="block text-sm">
                <Text>Период по</Text>
                <input
                  className={inputClass}
                  type="date"
                  min={data?.filters.date_min ?? undefined}
                  max={data?.filters.date_max ?? undefined}
                  value={filters.date_to}
                  onChange={(event) =>
                    setFilters((state) => ({
                      ...state,
                      date_to: event.target.value,
                    }))
                  }
                />
              </label>
              <label className="block text-sm">
                <Text>Группировать по</Text>
                <select
                  className={inputClass}
                  value={filters.group}
                  onChange={(event) =>
                    setFilters((state) => ({
                      ...state,
                      group: event.target.value as BddsGroup,
                    }))
                  }
                >
                  {(
                    data?.filters.groups ?? [{ id: "month", label: "Месяц" }]
                  ).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="block text-sm">
                <Text>Представление</Text>
                <select
                  className={inputClass}
                  value={filters.view}
                  onChange={(event) =>
                    setFilters((state) => ({
                      ...state,
                      view: event.target.value as BddsView,
                    }))
                  }
                >
                  {(
                    data?.filters.views ?? [
                      { id: "monthly", label: "По месяцам" },
                    ]
                  ).map((item) => (
                    <option key={item.id} value={item.id}>
                      {item.label}
                    </option>
                  ))}
                </select>
              </label>
            </div>

            <div className="mt-4 flex flex-wrap gap-x-6 gap-y-2 text-sm">
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  checked={filters.show_deviation}
                  onChange={(event) =>
                    setFilters((state) => ({
                      ...state,
                      show_deviation: event.target.checked,
                    }))
                  }
                />
                Показать отклонение
              </label>
              <label className="flex items-center gap-2">
                <input
                  type="checkbox"
                  disabled={!zeroToggleEnabled}
                  checked={zeroToggleEnabled ? hideZero : false}
                  onChange={(event) =>
                    setFilters((state) => ({
                      ...state,
                      hide_zero: event.target.checked,
                    }))
                  }
                />
                <span className={zeroToggleEnabled ? "" : "opacity-50"}>
                  Скрывать месяцы, где план и факт равны 0
                </span>
              </label>
            </div>
          </div>
        ) : null}
      </Card>

      {error || metaError ? (
        <Card className="mb-4 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            {error || metaError}
          </Text>
        </Card>
      ) : null}

      {!error && !metaError && data && isFallback ? (
        <Card className="mb-4 rounded-xl border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30">
          <Text className="text-amber-900 dark:text-amber-200">
            Упрощённый режим данных ({data.meta.mode}) — цифры могут отличаться от
            основного дашборда.
          </Text>
        </Card>
      ) : null}

      <div className="space-y-6">
        <Card className="rounded-xl">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            БДДС {filters.view === "cumulative" ? "накопительно" : `по ${periodLabel.toLowerCase()}ам`}
          </Title>
          <Text className="mt-1">млн рублей</Text>
          {mounted ? (
            <BarChart
              className="mt-6 h-96"
              data={chartData}
              index="period"
              categories={chartCategories}
              colors={["blue", "fuchsia", "amber"]}
              valueFormatter={(value) =>
                `${Number(value).toLocaleString("ru-RU", {
                  minimumFractionDigits: 1,
                  maximumFractionDigits: 1,
                })} млн ₽`
              }
              yAxisWidth={72}
              showLegend
              showAnimation
              showGridLines
              noDataText={loading ? "Загрузка…" : "Нет периодов для графика"}
            />
          ) : (
            <div className="mt-6 h-96" />
          )}
        </Card>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              БДДС по периодам
            </Title>
          </div>
          <FullscreenPanel disabled={!periodRows.length}>
            <div className="overflow-x-auto pt-10">
              {!periodRows.length ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "Загрузка…" : "Нет строк по выбранным фильтрам."}
                </div>
              ) : (
                <table className="min-w-full text-left text-tremor-default">
                  <thead className="bg-tremor-background-subtle dark:bg-dark-tremor-background-subtle">
                    <tr>
                      <th className={headCell}>Проект</th>
                      <th className={headCell}>{periodLabel}</th>
                      <th className={`${headCell} text-right`}>План, млн. руб.</th>
                      <th className={`${headCell} text-right`}>Факт, млн. руб.</th>
                      <th className={`${headCell} text-right`}>
                        Отклонение, млн. руб.
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
                    {periodRows.map((row, index) => {
                      const isProject = row.kind === "project";
                      return (
                        <tr
                          key={`${row.project}-${row.period}-${index}`}
                          className={`border-t border-tremor-border dark:border-dark-tremor-border ${
                            isProject
                              ? "bg-tremor-background-subtle font-semibold dark:bg-dark-tremor-background-subtle"
                              : ""
                          }`}
                        >
                          <td className="px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                            {row.project}
                          </td>
                          <td className="px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                            {row.period}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                            {isProject ? "" : mln(row.plan)}
                          </td>
                          <td className="px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                            {isProject ? "" : mln(row.fact)}
                          </td>
                          <td
                            className={`px-3 py-2 text-right tabular-nums ${deviationClass(
                              row.deviation,
                            )}`}
                          >
                            {isProject ? "" : mln(row.deviation)}
                          </td>
                        </tr>
                      );
                    })}
                    <tr className="border-t-2 border-tremor-border bg-tremor-background-subtle font-semibold dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle">
                      <td className="px-3 py-2">ИТОГО</td>
                      <td className="px-3 py-2">{data?.labels.total_period}</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {mln(totals.plan)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {mln(totals.fact)}
                      </td>
                      <td
                        className={`px-3 py-2 text-right tabular-nums ${deviationClass(
                          totals.deviation,
                        )}`}
                      >
                        {mln(totals.deviation)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
          </FullscreenPanel>
        </Card>

        <div>
          <DownloadTableButton
            getTable={periodExport}
            fileStem="bdds_po_periodam"
            disabled={!periodRows.length}
          />
        </div>

        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              БДДС по проектам
            </Title>
          </div>
          <FullscreenPanel disabled={!projectRows.length}>
            <div className="overflow-x-auto pt-10">
              {!projectRows.length ? (
                <div className="px-4 py-10 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
                  {loading ? "Загрузка…" : "Нет строк по выбранным фильтрам."}
                </div>
              ) : (
                <table className="min-w-full text-left text-tremor-default">
                  <thead className="bg-tremor-background-subtle dark:bg-dark-tremor-background-subtle">
                    <tr>
                      <th className={headCell}>Проект</th>
                      <th className={`${headCell} text-right`}>План, млн. руб.</th>
                      <th className={`${headCell} text-right`}>Факт, млн. руб.</th>
                      <th className={`${headCell} text-right`}>
                        Отклонение, млн. руб.
                      </th>
                    </tr>
                  </thead>
                  <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
                    {projectRows.map((row) => (
                      <tr
                        key={row.project}
                        className="border-t border-tremor-border dark:border-dark-tremor-border"
                      >
                        <td className="px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                          {row.project}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                          {mln(row.plan)}
                        </td>
                        <td className="px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                          {mln(row.fact)}
                        </td>
                        <td
                          className={`px-3 py-2 text-right tabular-nums ${deviationClass(
                            row.deviation,
                          )}`}
                        >
                          {mln(row.deviation)}
                        </td>
                      </tr>
                    ))}
                    <tr className="border-t-2 border-tremor-border bg-tremor-background-subtle font-semibold dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle">
                      <td className="px-3 py-2">ИТОГО</td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {mln(totals.plan)}
                      </td>
                      <td className="px-3 py-2 text-right tabular-nums">
                        {mln(totals.fact)}
                      </td>
                      <td
                        className={`px-3 py-2 text-right tabular-nums ${deviationClass(
                          totals.deviation,
                        )}`}
                      >
                        {mln(totals.deviation)}
                      </td>
                    </tr>
                  </tbody>
                </table>
              )}
            </div>
          </FullscreenPanel>
        </Card>

        <div>
          <DownloadTableButton
            getTable={projectExport}
            fileStem="bdds_po_proektam"
            disabled={!projectRows.length}
          />
        </div>
      </div>
    </AppShell>
  );
}
