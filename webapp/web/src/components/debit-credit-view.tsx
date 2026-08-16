"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
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
  ContractNoSuggest,
  FilterField,
  FilterChipMulti,
  FilterChipSelect,
  FilterFieldsRow,
  FILTER_SELECT_CLASS,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import { buildFilterChips } from "@/lib/filters-summary";
import { useUrlFilterState } from "@/lib/use-url-filter-state";
import type { ExportTable } from "@/lib/table-export";
import { DashboardEmptyState } from "@/components/dashboard-empty-state";
import { DashboardInsight } from "@/components/dashboard-insight";

type Filters = {
  projects: string[];
  contractor: string;
  contract_q: string;
  date_from: string;
  date_to: string;
  display_view: "Без группировки" | "С группировкой";
};

const initial: Filters = {
  projects: [],
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

/** Заливка ячеек «Допущения %» / «Аванс − КС-2» — как main `_dc_advance_semaphore_bg`. */
function toneCellClass(tone: string | undefined): string {
  if (tone === "green") {
    return "bg-[rgba(34,197,94,0.28)] font-semibold dark:bg-[rgba(70,214,138,0.35)]";
  }
  if (tone === "yellow") {
    return "bg-[rgba(234,179,8,0.35)] font-semibold dark:bg-[rgba(241,196,15,0.32)]";
  }
  if (tone === "red") {
    return "bg-[rgba(248,113,113,0.35)] font-semibold dark:bg-[rgba(255,84,84,0.32)]";
  }
  return "";
}

/** Непрозрачная заливка для sticky-футера — иначе строки просвечивают и «накладываются». */
function toneCellSolid(tone: string | undefined): string {
  if (tone === "green") {
    return "bg-[#86efac] font-semibold text-[#14532d] dark:bg-[#166534] dark:text-[#bbf7d0]";
  }
  if (tone === "yellow") {
    return "bg-[#fde047] font-semibold text-[#713f12] dark:bg-[#a16207] dark:text-[#fef08a]";
  }
  if (tone === "red") {
    return "bg-[#fca5a5] font-semibold text-[#7f1d1d] dark:bg-[#991b1b] dark:text-[#fecaca]";
  }
  return "bg-[#e8eef5] dark:bg-[hsl(209,50%,12%)]";
}

type MobileSortKey = "contractor" | "contract_sum" | "advance_pct" | "advance_ks2";

const MOBILE_SORT_OPTIONS: Array<{ value: MobileSortKey; label: string }> = [
  { value: "contractor", label: "Подрядчик" },
  { value: "contract_sum", label: "Стоимость" },
  { value: "advance_pct", label: "Аванс %" },
  { value: "advance_ks2", label: "Аванс − КС-2" },
];

/** Закреплённые колонки: Проект узкий; Подрядчик/Договор ~вдвое уже, с переносом по словам. */
const DC_W_PROJECT = "9.25rem";
const DC_W_CONTRACTOR = "9rem";
const DC_W_CONTRACT = "9rem";
const DC_LEFT_2 = `calc(${DC_W_PROJECT} + ${DC_W_CONTRACTOR})`;

const DC_BORDER = "border border-[#64748b] dark:border-[#94a3b8]";
const DC_TH = `${DC_BORDER} bg-[#dbe7f3] px-2 py-2.5 text-[1rem] font-semibold leading-snug dark:bg-[hsl(209,55%,14%)] dark:text-[#f8fafc]`;
const DC_TD = `${DC_BORDER} bg-white px-2 py-2 text-[1.125rem] leading-snug text-[#0f172a] dark:bg-[#111827] dark:text-[#f1f5f9]`;
const DC_TD_ALT = `${DC_BORDER} bg-[#eef2f7] px-2 py-2 text-[1.125rem] leading-snug text-[#0f172a] dark:bg-[#0b1220] dark:text-[#f1f5f9]`;
const DC_WRAP =
  "whitespace-normal [overflow-wrap:break-word] [word-break:normal] hyphens-manual";
const DC_STICKY_SHADOW =
  "shadow-[7px_0_10px_-6px_rgba(15,23,42,0.4)] dark:shadow-[7px_0_10px_-6px_rgba(0,0,0,0.7)]";
const DC_NUM = `${DC_BORDER} bi-num whitespace-nowrap px-2 py-2 text-right text-[1.125rem] tabular-nums`;
const DC_FOOT =
  `${DC_BORDER} bg-[#dbe7f3] px-2 py-2.5 text-[1.125rem] font-semibold dark:bg-[hsl(209,55%,14%)] dark:text-[#f8fafc]`;

export function DebitCreditView() {
  const [filters, setFilters] = useState<Filters>(initial);
  const [data, setData] = useState<DebitCreditPayload | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [open, setOpen] = useState(true);
  const [sortKey, setSortKey] = useState<MobileSortKey>("contractor");
  const [sortDesc, setSortDesc] = useState(false);
  const contractOptionsRef = useRef<string[]>([]);

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchDebitCredit({
        projects: next.projects,
        contractor: next.contractor !== "Все" ? next.contractor : undefined,
        contract_q: next.contract_q || undefined,
        date_from: next.date_from || undefined,
        date_to: next.date_to || undefined,
        display_view: next.display_view,
      });
      if (payload.filters.contract_nos?.length) {
        contractOptionsRef.current = payload.filters.contract_nos;
      }
      setData(payload);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setData(null);
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

  const stacked = filters.display_view === "С группировкой";
  const chartAggregation = data?.chart.aggregation ?? "by_contractor";

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
          "Допущения по авансированию",
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
        row.advance_tone ?? "",
        row.ks2,
        row.balance,
        row.advance_ks2,
      ]),
    };
  }, [data]);

  useUrlFilterState(
    filters, initial,
    (patch) => setFilters((s) => ({ ...s, ...patch })),
    { navId: "debit-credit" },
  );

  const activeFilters = buildFilterChips(
    filters,
    initial,
    [
      { key: "projects", name: "Проект" },
      { key: "contractor", name: "Подрядчик" },
      { key: "contract_q", name: "№ договора" },
      { key: "date_from", name: "С", kind: "date" },
      { key: "date_to", name: "По", kind: "date" },
      { key: "display_view", name: "Вид" },
    ],
    (patch) => setFilters((s) => ({ ...s, ...patch })),
  );

  return (
    <AppShell
      title="Дебиторская и кредиторская задолженность подрядчиков"
      subtitle="Авансы, КС-2 и договоры · млн ₽"
     loading={loading}>
      <FiltersCard
        open={open}
        onToggle={() => setOpen((v) => !v)}
        activeFilters={activeFilters}
        onReset={activeFilters.length ? () => setFilters(initial) : undefined}
      >
        <FiltersReset onClick={() => setFilters(initial)} />
        <FilterFieldsRow cols={5}>
          <FilterChipMulti label="Проект" values={filters.projects} options={data?.filters.projects ?? []} onChange={(projects) => setFilters((s) => ({ ...s, projects }))} />
          <FilterChipSelect label="Подрядчик" value={filters.contractor} options={data?.filters.contractors ?? ["Все"]} onChange={(contractor) => setFilters((s) => ({ ...s, contractor }))} />
          <FilterField label="№ договора (частичный поиск)">
            <ContractNoSuggest
              value={filters.contract_q}
              options={contractOptions}
              placeholder="Частичный поиск"
              onChange={(contract_q) =>
                setFilters((s) => ({ ...s, contract_q }))
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

      <DashboardInsight
        text={
          data?.meta.rows != null
            ? `${data.meta.rows} договоров${
                data.meta.version_id != null
                  ? ` · version_id=${data.meta.version_id}`
                  : ""
              }`
            : null
        }
      />

      <FullscreenPanel fill>
        <Card className="mb-6 overflow-visible rounded-xl">
          <div className="rounded-lg border border-sky-200 bg-sky-50 px-3 py-2 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-100">
            {data?.chart.caption ?? "График показывает топ-28 контрагентов/договоров по убыванию значения."}
          </div>
          <div className="mt-4 hidden lg:block">
            <DebitCreditChart
              rows={data?.chart.rows ?? []}
              stacked={stacked}
              aggregation={chartAggregation}
            />
            <DebitCreditChartLegend stacked={stacked} aggregation={chartAggregation} />
          </div>
          <div className="mt-4 lg:hidden">
            <DebitCreditChart
              rows={data?.chart.rows ?? []}
              stacked={stacked}
              compact
              aggregation={chartAggregation}
            />
            <DebitCreditChartLegend stacked={stacked} aggregation={chartAggregation} />
          </div>
          <Text className="mt-3">
            Значения на графике — млн руб.{" "}
            {chartAggregation === "by_metric"
              ? "Сводка по типам сумм (все проекты, подрядчики и договоры): Договор стоимость (син.), обязательства (сер.), КС-2 (тёмн. жёлт.), Аванс (светл. жёлт.), КС-2 − Аванс (сер./красн. ниже 0). Для стека по подрядчикам выберите «С группировкой»."
              : stacked
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
        <FullscreenPanel disabled={!data?.rows?.length} scroll={false}>
          <div className="bi-table-scroll">
            <table className="bi-sticky-head min-w-max border-separate border-spacing-0 text-left">
              <thead>
                <tr>
                  <th
                    className={`bi-sticky-x sticky left-0 ${DC_TH}`}
                    style={{ width: DC_W_PROJECT, minWidth: DC_W_PROJECT, maxWidth: DC_W_PROJECT }}
                  >
                    Проект
                  </th>
                  <th
                    className={`bi-sticky-x sticky ${DC_TH} ${DC_WRAP}`}
                    style={{
                      left: DC_W_PROJECT,
                      width: DC_W_CONTRACTOR,
                      minWidth: DC_W_CONTRACTOR,
                      maxWidth: DC_W_CONTRACTOR,
                    }}
                  >
                    Подрядчик
                  </th>
                  <th
                    className={`bi-sticky-x sticky ${DC_TH} ${DC_WRAP} ${DC_STICKY_SHADOW}`}
                    style={{
                      left: DC_LEFT_2,
                      width: DC_W_CONTRACT,
                      minWidth: DC_W_CONTRACT,
                      maxWidth: DC_W_CONTRACT,
                    }}
                  >
                    Договор
                  </th>
                  {[
                    "Договор стоимость",
                    "Всего выполненных обязательств по платежам",
                    "Аванс",
                    "Допущения по авансированию",
                    "Выполнено (КС-2)",
                    "Остаток",
                    "Аванс − КС-2",
                  ].map((label) => (
                    <th key={label} className={`${DC_TH} whitespace-nowrap`}>
                      {label}
                    </th>
                  ))}
                </tr>
              </thead>
              <tbody>
                {(data?.rows ?? []).map((row, index) => {
                  const stripe = index % 2 === 1 ? DC_TD_ALT : DC_TD;
                  const numStripe =
                    index % 2 === 1
                      ? `${DC_NUM} bg-[#eef2f7] dark:bg-[#0b1220]`
                      : `${DC_NUM} bg-white dark:bg-[#111827]`;
                  return (
                    <tr key={`${row.contract}-${index}`}>
                      <td
                        className={`sticky left-0 z-[2] ${stripe} whitespace-nowrap`}
                        style={{
                          width: DC_W_PROJECT,
                          minWidth: DC_W_PROJECT,
                          maxWidth: DC_W_PROJECT,
                        }}
                      >
                        {row.project}
                      </td>
                      <td
                        className={`sticky z-[2] ${stripe} ${DC_WRAP}`}
                        style={{
                          left: DC_W_PROJECT,
                          width: DC_W_CONTRACTOR,
                          minWidth: DC_W_CONTRACTOR,
                          maxWidth: DC_W_CONTRACTOR,
                        }}
                      >
                        {row.contractor}
                      </td>
                      <td
                        className={`sticky z-[2] ${stripe} ${DC_WRAP} ${DC_STICKY_SHADOW}`}
                        style={{
                          left: DC_LEFT_2,
                          width: DC_W_CONTRACT,
                          minWidth: DC_W_CONTRACT,
                          maxWidth: DC_W_CONTRACT,
                        }}
                      >
                        {row.contract}
                      </td>
                      <td className={numStripe}>{mln(row.contract_sum)}</td>
                      <td className={numStripe}>{mln(row.fulfilled)}</td>
                      <td className={numStripe}>{mln(row.advance)}</td>
                      <td
                        className={`${DC_BORDER} px-2 py-2 text-center text-[1.25rem] ${toneCellClass(row.advance_tone)}`}
                        title="Допущения по авансированию"
                      >
                        {toneDot(row.advance_tone) || "—"}
                      </td>
                      <td className={numStripe}>{mln(row.ks2)}</td>
                      <td className={numStripe}>{mln(row.balance)}</td>
                      <td
                        className={`${DC_BORDER} whitespace-nowrap px-2 py-2 text-left text-[1.125rem] tabular-nums ${toneCellClass(row.advance_tone)}`}
                      >
                        {toneDot(row.advance_tone)} {mln(row.advance_ks2)}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
              <tfoot>
                <tr>
                  <td
                    className={`sticky bottom-0 left-0 z-[12] ${DC_FOOT}`}
                    style={{
                      width: DC_W_PROJECT,
                      minWidth: DC_W_PROJECT,
                      maxWidth: DC_W_PROJECT,
                    }}
                  >
                    ИТОГО
                  </td>
                  <td
                    className={`sticky bottom-0 z-[12] ${DC_FOOT}`}
                    style={{
                      left: DC_W_PROJECT,
                      width: DC_W_CONTRACTOR,
                      minWidth: DC_W_CONTRACTOR,
                      maxWidth: DC_W_CONTRACTOR,
                    }}
                  />
                  <td
                    className={`sticky bottom-0 z-[12] ${DC_FOOT} ${DC_STICKY_SHADOW}`}
                    style={{
                      left: DC_LEFT_2,
                      width: DC_W_CONTRACT,
                      minWidth: DC_W_CONTRACT,
                      maxWidth: DC_W_CONTRACT,
                    }}
                  />
                  <td className={`sticky bottom-0 z-[11] ${DC_FOOT} text-right tabular-nums`}>
                    {mln(data?.totals.contract_sum)}
                  </td>
                  <td className={`sticky bottom-0 z-[11] ${DC_FOOT} text-right tabular-nums`}>
                    {mln(data?.totals.fulfilled)}
                  </td>
                  <td className={`sticky bottom-0 z-[11] ${DC_FOOT} text-right tabular-nums`}>
                    {mln(data?.totals.advance)}
                  </td>
                  <td
                    className={`sticky bottom-0 z-[11] ${DC_BORDER} px-2 py-2.5 text-center text-[1.25rem] ${toneCellSolid(data?.totals.advance_tone)}`}
                    title="Допущения по авансированию"
                  >
                    {toneDot(data?.totals.advance_tone) || "—"}
                  </td>
                  <td className={`sticky bottom-0 z-[11] ${DC_FOOT} text-right tabular-nums`}>
                    {mln(data?.totals.ks2)}
                  </td>
                  <td className={`sticky bottom-0 z-[11] ${DC_FOOT} text-right tabular-nums`}>
                    {mln(data?.totals.balance)}
                  </td>
                  <td
                    className={`sticky bottom-0 z-[11] ${DC_BORDER} px-2 py-2.5 text-left text-[1.125rem] tabular-nums ${toneCellSolid(data?.totals.advance_tone)}`}
                  >
                    {toneDot(data?.totals.advance_tone)}{" "}
                    {mln(data?.totals.advance_ks2)}
                  </td>
                </tr>
              </tfoot>
            </table>
          </div>
        </FullscreenPanel>
        <div className="space-y-2 border-t border-tremor-border p-4 text-sm dark:border-dark-tremor-border">
          <div className="rounded-lg border border-tremor-border bg-tremor-background-muted/60 px-3 py-2.5 dark:border-dark-tremor-border dark:bg-dark-tremor-background-muted/40">
            <p className="font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong">
              Легенда — цветовые индикаторы (Аванс − КС-2):
            </p>
            <ul className="mt-2 flex list-none flex-col gap-1.5 text-tremor-content dark:text-dark-tremor-content">
              <li className="block">🟢 ≤ 0 или &gt; 0, но ≤ 30% стоимости договора</li>
              <li className="block">🟡 &gt; 30% и &lt; 60% стоимости договора</li>
              <li className="block">🔴 ≥ 60% стоимости договора</li>
            </ul>
            <p className="mt-1.5 text-xs text-tremor-content dark:text-dark-tremor-content">
              В колонке «Допущения по авансированию» — только индикатор; колонка «Аванс − КС-2» заливается по тем же порогам.
            </p>
          </div>
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
          <DashboardEmptyState
            message="Нет строк"
            onReset={activeFilters.length ? () => setFilters(initial) : undefined}
          />
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
                  badge={toneDot(data.totals.advance_tone) || "—"}
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
                  badge={toneDot(row.advance_tone) || "—"}
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
          <div className="rounded-lg border border-tremor-border bg-tremor-background-muted/60 px-3 py-2.5 dark:border-dark-tremor-border dark:bg-dark-tremor-background-muted/40">
            <p className="font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong">
              Легенда — цветовые индикаторы (Аванс − КС-2):
            </p>
            <ul className="mt-2 flex list-none flex-col gap-1.5 text-tremor-content dark:text-dark-tremor-content">
              <li className="block">🟢 ≤ 0 или &gt; 0, но ≤ 30% стоимости договора</li>
              <li className="block">🟡 &gt; 30% и &lt; 60% стоимости договора</li>
              <li className="block">🔴 ≥ 60% стоимости договора</li>
            </ul>
          </div>
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
