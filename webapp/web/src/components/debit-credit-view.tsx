"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DebitCreditChart, DebitCreditChartLegend } from "@/components/debit-credit-chart";
import { DownloadTableButton } from "@/components/download-table-button";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import {
  MobileCardStack,
  MobileEntityCard,
  MobileMetricGrid,
  MobileSortControl,
} from "@/components/mobile-entity-card";
import { fetchDebitCredit, type DebitCreditPayload } from "@/lib/api";
import {
  FilterField,
  FilterChipSelect,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
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

type MobileSortKey = "contractor" | "contract_sum" | "advance_pct" | "advance_ks2";

const MOBILE_SORT_OPTIONS: Array<{ value: MobileSortKey; label: string }> = [
  { value: "contractor", label: "Подрядчик" },
  { value: "contract_sum", label: "Стоимость" },
  { value: "advance_pct", label: "Аванс %" },
  { value: "advance_ks2", label: "Аванс − КС-2" },
];

export function DebitCreditView() {
  const [filters, setFilters] = useState<Filters>(initial);
  const [data, setData] = useState<DebitCreditPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(true);
  const [sortKey, setSortKey] = useState<MobileSortKey>("contractor");
  const [sortDesc, setSortDesc] = useState(false);

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

  // Сортировка только для мобильных карточек: таблица на desktop идёт в порядке API
  const mobileRows = useMemo(() => {
    const rows = data?.rows ?? [];
    const dir = sortDesc ? -1 : 1;
    return [...rows].sort((a, b) => {
      if (sortKey === "contractor") {
        return dir * a.contractor.localeCompare(b.contractor, "ru");
      }
      const av = Number(a[sortKey] ?? 0);
      const bv = Number(b[sortKey] ?? 0);
      return dir * (av - bv);
    });
  }, [data, sortKey, sortDesc]);
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
          "Остаток",
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
        row.balance,
        row.advance_ks2,
      ]),
    };
  }, [data]);

  return (
    <AppShell
      title="Дебиторская и кредиторская задолженность подрядчиков"
      subtitle="Авансы, КС-2 и договоры · млн ₽"
     loading={loading}>
      <FiltersCard open={open} onToggle={() => setOpen((v) => !v)}>
        <FiltersReset onClick={() => setFilters(initial)} />
        <FilterFieldsRow cols={5}>
          <FilterChipSelect label="Проект" value={filters.project} options={data?.filters.projects ?? ["Все"]} onChange={(project) => setFilters((s) => ({ ...s, project }))} />
          <FilterChipSelect label="Подрядчик" value={filters.contractor} options={data?.filters.contractors ?? ["Все"]} onChange={(contractor) => setFilters((s) => ({ ...s, contractor }))} />
          <FilterField label="№ договора (частичный поиск)">
            <input
              className={FILTER_SELECT_CLASS}
              placeholder="Частичный поиск"
              value={filters.contract_q}
              onChange={(e) =>
                setFilters((s) => ({ ...s, contract_q: e.target.value }))
              }
            />
          </FilterField>
          <FilterField label="Период">
            <div className="grid grid-cols-2 gap-1">
              <input
                type="date"
                className={FILTER_SELECT_CLASS}
                min={data?.filters.date_min ?? undefined}
                max={data?.filters.date_max ?? undefined}
                value={filters.date_from}
                onChange={(e) =>
                  setFilters((s) => ({ ...s, date_from: e.target.value }))
                }
                aria-label="Период с"
              />
              <input
                type="date"
                className={FILTER_SELECT_CLASS}
                min={data?.filters.date_min ?? undefined}
                max={data?.filters.date_max ?? undefined}
                value={filters.date_to}
                onChange={(e) =>
                  setFilters((s) => ({ ...s, date_to: e.target.value }))
                }
                aria-label="Период по"
              />
            </div>
          </FilterField>
          <FilterChipSelect
            label="Вид отображения"
            value={filters.display_view}
            options={["Без группировки", "С группировкой"]}
            onChange={(display_view) => setFilters((s) => ({ ...s, display_view: display_view as Filters["display_view"] }))}
          />
        </FilterFieldsRow>
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
      </FiltersCard>

      {error ? (
        <Card className="mb-6 border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">{error}</Text>
        </Card>
      ) : null}

      <FullscreenPanel fill>
        <Card className="mb-6 overflow-visible rounded-xl">
          <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-100">
            {data?.chart.caption ?? "График показывает топ-28 контрагентов/договоров по убыванию значения."}
          </div>
          <div className="mt-4 hidden lg:block">
            <DebitCreditChart rows={data?.chart.rows ?? []} stacked={stacked} />
            <DebitCreditChartLegend stacked={stacked} />
          </div>
          <div className="mt-4 lg:hidden">
            <DebitCreditChart rows={data?.chart.rows ?? []} stacked={stacked} compact />
            <DebitCreditChartLegend stacked={stacked} />
          </div>
          <Text className="mt-3">
            {stacked
              ? "Суммы по подрядчику. С группировкой (стек): отклонение ≥0 (сер.) → КС-2 (жёлт.) → Аванс (син.)."
              : "Суммы по подрядчику. Без группировки: Аванс (син.), КС-2 (жёлт.), отклонение ≥0 (сер.), отклонение <0 (красн., ниже 0)."}
          </Text>
        </Card>
      </FullscreenPanel>

      <Card className="hidden overflow-hidden rounded-xl p-0 lg:block">
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
                  "Всего выполненных обязательств по платежам",
                  "Аванс",
                  "Допущения по авансированию %",
                  "Выполнено (КС-2)",
                  "Остаток",
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
                    {mln(row.balance)}
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
                  {mln(data?.totals.balance)}
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
      <div className="lg:hidden">
        <Title className="mb-3 px-2 !text-tremor-content-strong dark:!text-dark-tremor-content-strong">
          Таблица по подрядчику и договору
        </Title>
        {!data?.rows.length ? (
          <Text className="px-2 py-6 text-center">Нет строк</Text>
        ) : (
          <>
            <MobileSortControl
              value={sortKey}
              options={MOBILE_SORT_OPTIONS}
              onChange={setSortKey}
              desc={sortDesc}
              onToggleDir={() => setSortDesc((v) => !v)}
            />
            <MobileCardStack
              pinned={
                <MobileEntityCard
                  className="bi-card-pinned"
                  title="ИТОГО"
                  badge={
                    data.totals.advance_pct == null
                      ? "—"
                      : `${data.totals.advance_pct}%`
                  }
                  badgeTone={
                    data.totals.advance_tone === "red"
                      ? "bad"
                      : data.totals.advance_tone === "yellow"
                        ? "warn"
                        : "ok"
                  }
                  more={
                    <MobileMetricGrid
                      columns={2}
                      items={[
                        { label: "Обязательства", value: mln(data.totals.fulfilled) },
                        { label: "Остаток", value: mln(data.totals.balance) },
                      ]}
                    />
                  }
                >
                  <MobileMetricGrid
                    columns={2}
                    items={[
                      { label: "Стоимость", value: mln(data.totals.contract_sum) },
                      { label: "Аванс", value: mln(data.totals.advance) },
                      { label: "КС-2", value: mln(data.totals.ks2) },
                      {
                        label: "Аванс − КС-2",
                        value: `${toneDot(data.totals.advance_tone)} ${mln(data.totals.advance_ks2)}`,
                      },
                    ]}
                  />
                </MobileEntityCard>
              }
            >
              {mobileRows.map((row, index) => (
                <MobileEntityCard
                  key={`${row.contract}-${index}`}
                  title={row.contractor}
                  badge={row.advance_pct == null ? "—" : `${row.advance_pct}%`}
                  badgeTone={
                    row.advance_tone === "red"
                      ? "bad"
                      : row.advance_tone === "yellow"
                        ? "warn"
                        : "ok"
                  }
                  more={
                    <MobileMetricGrid
                      columns={2}
                      items={[
                        { label: "Обязательства", value: mln(row.fulfilled) },
                        { label: "Остаток", value: mln(row.balance) },
                      ]}
                    />
                  }
                >
                  <div className="mb-2 text-xs text-tremor-content dark:text-dark-tremor-content">
                    {row.contract} · {row.project}
                  </div>
                  <MobileMetricGrid
                    columns={2}
                    items={[
                      { label: "Стоимость", value: mln(row.contract_sum) },
                      { label: "Аванс", value: mln(row.advance) },
                      { label: "КС-2", value: mln(row.ks2) },
                      {
                        label: "Аванс − КС-2",
                        value: `${toneDot(row.advance_tone)} ${mln(row.advance_ks2)}`,
                        highlight: row.advance_tone === "red" ? "bad" : "none",
                      },
                    ]}
                  />
                </MobileEntityCard>
              ))}
            </MobileCardStack>
          </>
        )}
        <div className="space-y-2 px-2 pb-3 text-sm">
          <Text>
            Цветовые индикаторы (Аванс − КС-2): 🟢 delta ≤ 0 или ≤ 30% стоимости договора · 🟡 &gt; 30% и &lt; 80% · 🔴 ≥ 80%.
          </Text>
          <DownloadTableButton
            getTable={exportTable}
            fileStem="debit_credit"
            disabled={!data?.rows?.length}
          />
        </div>
      </div>
    </AppShell>
  );
}
