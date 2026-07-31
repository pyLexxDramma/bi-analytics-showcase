"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart, Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import { fetchDebitCredit, type DebitCreditPayload } from "@/lib/api";
import type { ExportTable } from "@/lib/table-export";

type Filters = {
  project: string;
  contractor: string;
  contract_q: string;
  date_from: string;
  date_to: string;
  display_view: "Без группировки" | "С группировкой";
};

const initial: Filters = {
  project: "Все",
  contractor: "Все",
  contract_q: "",
  date_from: "",
  date_to: "",
  display_view: "Без группировки",
};

const GROUP_CATS = ["Аванс", "КС-2", "Отклонение ≥0", "Отклонение <0"] as const;
const STACK_CATS = ["Отклонение ≥0", "КС-2", "Аванс"] as const;

function mln(value: number | null | undefined): string {
  if (value == null || Number.isNaN(Number(value))) return "—";
  return (Number(value) / 1e6).toLocaleString("ru-RU", {
    maximumFractionDigits: 2,
    minimumFractionDigits: 0,
  });
}

function toneDot(tone: string | undefined): string {
  if (tone === "yellow") return "🟡";
  if (tone === "red") return "🔴";
  return "🟢";
}

export function DebitCreditView() {
  const [filters, setFilters] = useState<Filters>(initial);
  const [data, setData] = useState<DebitCreditPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(false);

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      setData(
        await fetchDebitCredit({
          project: next.project !== "Все" ? next.project : undefined,
          contractor: next.contractor !== "Все" ? next.contractor : undefined,
          contract_q: next.contract_q || undefined,
          date_from: next.date_from || undefined,
          date_to: next.date_to || undefined,
          display_view: next.display_view,
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

  const stacked = filters.display_view === "С группировкой";
  const categories = useMemo(
    () => (stacked ? [...STACK_CATS] : [...GROUP_CATS]),
    [stacked],
  );
  const colors = stacked
    ? (["gray", "amber", "blue"] as const)
    : (["blue", "amber", "gray", "rose"] as const);

  const exportTable = useCallback((): ExportTable | null => {
    if (!data?.rows.length) return null;
    return {
      header: [
        [
          "Проект",
          "Подрядчик",
          "Договор",
          "Договор стоимость",
          "Всего выполненных обязательств",
          "Аванс",
          "Допущения по авансированию %",
          "Выполнено (КС-2)",
          "Аванс − КС-2",
        ],
      ],
      rows: data.rows.map((row) => [
        row.project,
        row.contractor,
        row.contract,
        row.contract_sum,
        row.fulfilled,
        row.advance,
        row.advance_pct ?? "",
        row.ks2,
        row.advance_ks2,
      ]),
    };
  }, [data]);

  return (
    <AppShell
      title="Дебиторская и кредиторская задолженность подрядчиков"
      subtitle="Авансы, КС-2 и договоры · млн ₽"
    >
      <Card className="mb-6 rounded-xl">
        <div className="flex items-center justify-between gap-3">
          <button
            type="button"
            onClick={() => setOpen((v) => !v)}
            className="flex flex-1 items-center justify-between text-left"
          >
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Фильтры
            </Title>
            <span>{open ? "▲" : "▼"}</span>
          </button>
          <button
            type="button"
            onClick={() => setFilters(initial)}
            className="rounded-md border border-tremor-border px-3 py-1.5 text-sm dark:border-dark-tremor-border"
          >
            Сбросить
          </button>
        </div>
        {open ? (
          <div className="mt-4 grid gap-3 md:grid-cols-2 lg:grid-cols-5">
            <label className="block text-sm">
              <Text>Проект</Text>
              <select
                className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={filters.project}
                onChange={(e) =>
                  setFilters((s) => ({ ...s, project: e.target.value }))
                }
              >
                {(data?.filters.projects ?? ["Все"]).map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <Text>Подрядчик</Text>
              <select
                className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={filters.contractor}
                onChange={(e) =>
                  setFilters((s) => ({ ...s, contractor: e.target.value }))
                }
              >
                {(data?.filters.contractors ?? ["Все"]).map((v) => (
                  <option key={v}>{v}</option>
                ))}
              </select>
            </label>
            <label className="block text-sm">
              <Text>№ договора</Text>
              <input
                className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                placeholder="Частичный поиск"
                value={filters.contract_q}
                onChange={(e) =>
                  setFilters((s) => ({ ...s, contract_q: e.target.value }))
                }
              />
            </label>
            <label className="block text-sm">
              <Text>Период</Text>
              <div className="mt-1 flex gap-1">
                <input
                  type="date"
                  className="w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-2 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  min={data?.filters.date_min ?? undefined}
                  max={data?.filters.date_max ?? undefined}
                  value={filters.date_from}
                  onChange={(e) =>
                    setFilters((s) => ({ ...s, date_from: e.target.value }))
                  }
                />
                <input
                  type="date"
                  className="w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-2 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  min={data?.filters.date_min ?? undefined}
                  max={data?.filters.date_max ?? undefined}
                  value={filters.date_to}
                  onChange={(e) =>
                    setFilters((s) => ({ ...s, date_to: e.target.value }))
                  }
                />
              </div>
            </label>
            <label className="block text-sm">
              <Text>Отображение</Text>
              <select
                className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={filters.display_view}
                onChange={(e) =>
                  setFilters((s) => ({
                    ...s,
                    display_view: e.target.value as Filters["display_view"],
                  }))
                }
              >
                <option>Без группировки</option>
                <option>С группировкой</option>
              </select>
            </label>
          </div>
        ) : null}
        <Text className="mt-3">
          {loading ? "загрузка…" : `${data?.meta.rows ?? 0} договоров`}
          {data?.meta.version_id != null
            ? ` · version_id=${data.meta.version_id}`
            : ""}
        </Text>
        {data?.meta.warning ? (
          <Text className="mt-1 text-amber-700 dark:text-amber-300">
            {data.meta.warning}
          </Text>
        ) : null}
      </Card>

      {error ? (
        <Card className="mb-6 border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">{error}</Text>
        </Card>
      ) : null}

      <FullscreenPanel fill>
        <Card className="mb-6 rounded-xl">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            Авансы и КС-2
          </Title>
          <Text className="mt-1">
            {data?.chart.caption ?? "…"} · {data?.chart.unit ?? "млн ₽"}
          </Text>
          <BarChart
            className="mt-6 h-96"
            data={data?.chart.rows ?? []}
            index="label"
            categories={categories}
            colors={[...colors]}
            stack={stacked}
            valueFormatter={(v) =>
              Number(v).toLocaleString("ru-RU", { maximumFractionDigits: 1 })
            }
            showLegend
            showGridLines
            yAxisWidth={48}
          />
        </Card>
      </FullscreenPanel>

      <Card className="overflow-hidden rounded-xl p-0">
        <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            Таблица по подрядчику и договору
          </Title>
        </div>
        <div className="max-h-[36rem] overflow-auto">
          <table className="min-w-max border-separate border-spacing-0 text-left text-sm">
            <thead className="sticky top-0 z-10">
              <tr>
                {[
                  "Проект",
                  "Подрядчик",
                  "Договор",
                  "Договор стоимость",
                  "Всего выполненных обязательств",
                  "Аванс",
                  "Допущения по авансированию %",
                  "Выполнено (КС-2)",
                  "Аванс − КС-2",
                ].map((label) => (
                  <th
                    key={label}
                    className="whitespace-nowrap border-b border-tremor-border bg-tremor-background-subtle px-3 py-3 text-xs font-semibold dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle"
                  >
                    {label}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {(data?.rows ?? []).map((row, index) => (
                <tr
                  key={`${row.contract}-${index}`}
                  className="border-t border-tremor-border dark:border-dark-tremor-border"
                >
                  <td className="whitespace-nowrap px-3 py-2">{row.project}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.contractor}</td>
                  <td className="whitespace-nowrap px-3 py-2">{row.contract}</td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                    {mln(row.contract_sum)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                    {mln(row.fulfilled)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                    {mln(row.advance)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                    {toneDot(row.advance_tone)}{" "}
                    {row.advance_pct == null ? "—" : `${row.advance_pct}%`}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                    {mln(row.ks2)}
                  </td>
                  <td className="whitespace-nowrap px-3 py-2 text-right tabular-nums">
                    {mln(row.advance_ks2)}
                  </td>
                </tr>
              ))}
            </tbody>
            <tfoot className="sticky bottom-0 z-10 bg-tremor-background font-semibold dark:bg-dark-tremor-background">
              <tr>
                <td className="border-t border-tremor-border px-3 py-3 dark:border-dark-tremor-border" colSpan={3}>
                  ИТОГО
                </td>
                <td className="border-t border-tremor-border px-3 py-3 text-right tabular-nums dark:border-dark-tremor-border">
                  {mln(data?.totals.contract_sum)}
                </td>
                <td className="border-t border-tremor-border px-3 py-3 text-right tabular-nums dark:border-dark-tremor-border">
                  {mln(data?.totals.fulfilled)}
                </td>
                <td className="border-t border-tremor-border px-3 py-3 text-right tabular-nums dark:border-dark-tremor-border">
                  {mln(data?.totals.advance)}
                </td>
                <td className="border-t border-tremor-border px-3 py-3 text-right tabular-nums dark:border-dark-tremor-border">
                  {toneDot(data?.totals.advance_tone)}{" "}
                  {data?.totals.advance_pct == null
                    ? "—"
                    : `${data.totals.advance_pct}%`}
                </td>
                <td className="border-t border-tremor-border px-3 py-3 text-right tabular-nums dark:border-dark-tremor-border">
                  {mln(data?.totals.ks2)}
                </td>
                <td className="border-t border-tremor-border px-3 py-3 text-right tabular-nums dark:border-dark-tremor-border">
                  {mln(data?.totals.advance_ks2)}
                </td>
              </tr>
            </tfoot>
          </table>
        </div>
        <div className="space-y-2 border-t border-tremor-border p-4 text-sm dark:border-dark-tremor-border">
          <Text>
            Цветовые индикаторы (Аванс − КС-2): 🟢 delta ≤ 0 или ≤ 30% стоимости
            договора · 🟡 &gt; 30% и &lt; 80% · 🔴 ≥ 80%.
          </Text>
          <DownloadTableButton
            getTable={exportTable}
            fileStem="debit_credit"
            disabled={!data?.rows?.length}
          />
        </div>
      </Card>
    </AppShell>
  );
}
