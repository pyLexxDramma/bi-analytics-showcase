"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { DownloadTableButton } from "@/components/download-table-button";
import { FinanceBarChart } from "@/components/finance-bar-chart";
import { FullscreenPanel } from "@/components/fullscreen-panel";
import { MobileCardStack, MobileEntityCard, MobileMetricGrid } from "@/components/mobile-entity-card";
import { fetchApprovedBudget, type ApprovedBudgetPayload } from "@/lib/api";
import {
  FilterCheck,
  FilterChipMulti,
  FilterChipSelect,
  FilterChecksRow,
  FilterFieldsRow,
  FiltersCard,
  FiltersReset,
} from "@/components/dashboard-filters";
import type { ExportTable } from "@/lib/table-export";

type SortKey = "period" | "project" | "plan" | "fact" | "remainder" | "deviation" | "completion_pct" | "contract_coverage_pct";
type SortState = { key: SortKey; asc: boolean } | null;
type Filters = { projects: string[]; fiz: string; hide_zero: boolean | null; show_deviation: boolean };
type ProjectMetric = "plan" | "fact" | "remainder" | "deviation" | "completion_pct" | "contract_coverage_pct";

const INITIAL: Filters = { projects: [], fiz: "Все", hide_zero: null, show_deviation: false };
const CELL = "border border-[#cbd5e1] dark:border-[#7a9ec4]";
const HEAD = "border border-[#cbd5e1] bg-[#e8f0fe] px-3 py-2 text-xs font-semibold uppercase text-[#111827] dark:border-[#7a9ec4] dark:bg-[#16283a] dark:text-[#f0f4f8]";
const TABLE = "min-w-full border-collapse border-2 border-[#94a3b8] text-left text-tremor-default dark:border-[#7a9ec4]";
const BODY = "px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong";
const TOTAL = "border-t-[3px] border-t-[#94a3b8] bg-[#f1f5f9] font-bold dark:border-t-white dark:bg-[#16283a]";
const projectHeaders: Record<ProjectMetric, string> = {
  plan: "План, млн руб.",
  fact: "Факт, млн руб.",
  remainder: "Остаток, млн руб.",
  deviation: "Отклонение, млн руб.",
  completion_pct: "% выполнения",
  contract_coverage_pct: "% покрытия контрактами",
};

function mln(value: number) {
  return `${(Number(value || 0) / 1_000_000).toFixed(1)} млн. руб.`;
}
/** Число в млн с двумя знаками — как в таблице проектов main. */
function mlnPlain(value: number) {
  return (Number(value || 0) / 1_000_000).toFixed(2);
}
function pct(value: number | null | undefined) {
  return `${Number(value ?? 0).toFixed(1)}%`;
}
function deviationClass(value: number) {
  return Math.abs(value) < 10_000
    ? ""
    : value < 0
      ? "font-semibold text-[#b91c1c] dark:text-rose-300"
      : "font-semibold text-[#15803d] dark:text-emerald-300";
}

function HalfGauge({ gauge }: { gauge: ApprovedBudgetPayload["gauge"] }) {
  const vbW = 480;
  const vbH = 260;
  const cx = vbW / 2;
  const cy = 205;
  const r = 148;
  const strokeRed = 36;
  const strokeGreen = 22;
  const half = Math.PI * r;

  const max = Math.max(Number(gauge.axis_max_mlrd) || Number(gauge.plan_mlrd) || 0.01, 0.01);
  const plan = Math.min(Math.max(Number(gauge.plan_mlrd) || 0, 0), max);
  const fact = Math.min(Math.max(Number(gauge.fact_mlrd) || 0, 0), max);
  const planT = plan / max;
  const factT = fact / max;

  // Верхняя полудуга: в SVG (+y вниз) sweep=1 от левой точки.
  const d = `M ${cx - r} ${cy} A ${r} ${r} 0 0 1 ${cx + r} ${cy}`;

  const at = (t: number, radius: number) => {
    const a = Math.PI * (1 - Math.min(Math.max(t, 0), 1));
    return { x: cx + radius * Math.cos(a), y: cy - radius * Math.sin(a) };
  };

  // Без «0.00 млрд» — только факт сверху и план справа (как на правках пользователя).
  const marks = [
    { t: factT, text: `${fact.toFixed(2)} млрд`, place: "fact" as const },
    { t: planT, text: `${plan.toFixed(2)} млрд`, place: "end" as const },
  ];

  return (
    <div className="mx-auto w-full max-w-xl overflow-visible px-3">
      <svg
        viewBox={`0 0 ${vbW} ${vbH}`}
        className="h-auto w-full overflow-visible"
        role="img"
        aria-label={`Факт ${fact.toFixed(2)} млрд из плана ${plan.toFixed(2)} млрд`}
      >
        {/* Серый трек на всю полудугу */}
        <path d={d} fill="none" stroke="#dcdde1" strokeWidth={strokeRed} strokeLinecap="butt" />
        {/* Красная дуга плана 0 → план */}
        {planT > 0.001 ? (
          <path
            d={d}
            fill="none"
            stroke="#e74c3c"
            strokeWidth={strokeRed}
            strokeLinecap="butt"
            strokeDasharray={`${half * planT} ${half}`}
          />
        ) : null}
        {/* Зелёная дуга факта на ТОМ ЖЕ радиусе, тоньше — «входит» в красную */}
        {factT > 0.001 ? (
          <path
            d={d}
            fill="none"
            stroke="#27ae60"
            strokeWidth={strokeGreen}
            strokeLinecap="butt"
            strokeDasharray={`${half * factT} ${half}`}
          />
        ) : null}

        {marks.map((m) => {
          const tipR = r + strokeRed / 2 + 4;
          const baseR = r - strokeRed / 2;
          const tip = at(m.t, tipR);
          const base = at(m.t, baseR);
          const label =
            m.place === "end"
              ? { x: tip.x + 10, y: tip.y + 4, anchor: "start" as const }
              : { x: tip.x, y: tip.y - 10, anchor: "middle" as const };
          return (
            <g key={`${m.place}-${m.text}`}>
              <line
                x1={base.x}
                y1={base.y}
                x2={tip.x}
                y2={tip.y}
                stroke="currentColor"
                strokeWidth="1.25"
                className="text-[#111827] dark:text-slate-100"
              />
              <text
                x={label.x}
                y={label.y}
                textAnchor={label.anchor}
                dominantBaseline={m.place === "fact" ? "auto" : "middle"}
                fill="currentColor"
                className="text-[#111827] dark:text-slate-100"
                style={{ fontSize: 13, fontFamily: "system-ui, sans-serif" }}
              >
                {m.text}
              </text>
            </g>
          );
        })}

        <text
          x={cx}
          y={cy - 36}
          textAnchor="middle"
          fill="currentColor"
          className="text-[#111827] dark:text-white"
          style={{ fontSize: 30, fontWeight: 700, fontFamily: "system-ui, sans-serif" }}
        >
          {fact.toFixed(2)} млрд
        </text>
      </svg>
    </div>
  );
}

function SortHeader({ label, sortKey, sort, onSort, align = "left" }: { label: string; sortKey: SortKey; sort: SortState; onSort: (key: SortKey) => void; align?: "left" | "right" }) {
  const active = sort?.key === sortKey;
  return <th className={`${HEAD} ${align === "right" ? "text-right" : ""}`}><button type="button" className={`flex w-full gap-1 ${align === "right" ? "justify-end" : ""}`} onClick={() => onSort(sortKey)}><span>{label}</span><span className={active ? "text-emerald-700" : "opacity-60"}>{active ? (sort?.asc ? "↑" : "↓") : "⇅"}</span></button></th>;
}

export function ApprovedBudgetView() {
  const [filters, setFilters] = useState<Filters>(INITIAL);
  const [data, setData] = useState<ApprovedBudgetPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);
  const [filtersOpen, setFiltersOpen] = useState(false);
  const [periodSort, setPeriodSort] = useState<SortState>(null);
  const [projectSort, setProjectSort] = useState<SortState>(null);
  const load = useCallback(async (next: Filters) => {
    setLoading(true); setError(null);
    try { setData(await fetchApprovedBudget({ ...next, hide_zero: next.hide_zero ?? undefined })); }
    catch (cause) { setData(null); setError(cause instanceof Error ? cause.message : String(cause)); }
    finally { setLoading(false); }
  }, []);
  useEffect(() => { void load(filters); }, [filters, load]);
  const hideZero = filters.hide_zero ?? (filters.projects.length === 0 && filters.fiz === "Все");
  const toggleSort = (set: (next: SortState | ((value: SortState) => SortState)) => void) => (key: SortKey) => set((state) => state?.key === key ? (state.asc ? { key, asc: false } : null) : { key, asc: true });
  const sortRows = <T extends Record<string, unknown>>(rows: T[], sort: SortState) => !sort ? rows : [...rows].sort((a, b) => {
    const av = a[sort.key]; const bv = b[sort.key];
    const diff = typeof av === "string" || typeof bv === "string" ? String(av ?? "").localeCompare(String(bv ?? ""), "ru") : Number(av ?? 0) - Number(bv ?? 0);
    return sort.asc ? diff : -diff;
  });
  const periodRows = useMemo(() => sortRows(data?.period_rows ?? [], periodSort), [data, periodSort]);
  const projectRows = useMemo(() => sortRows(data?.project_rows ?? [], projectSort), [data, projectSort]);
  const periodExport = (): ExportTable | null => data ? { header: [["Месяц", "План, млн. руб.", "Факт, млн. руб.", "Отклонение, млн. руб."]], rows: [...data.period_rows.map((row) => [row.period, row.plan / 1e6, row.fact / 1e6, row.deviation / 1e6]), ["ИТОГО", data.totals.plan / 1e6, data.totals.fact / 1e6, data.totals.deviation / 1e6]], sheetName: "Утверждённый бюджет" } : null;
  const projectExport = (): ExportTable | null =>
    data
      ? {
          header: [[
            "Проект",
            "План, млн руб.",
            "Факт, млн руб.",
            "Остаток, млн руб.",
            "Отклонение, млн руб.",
            "% выполнения",
            "% покрытия контрактами",
          ]],
          rows: [
            ...data.project_rows.map((row) => [
              row.project,
              row.plan / 1e6,
              row.fact / 1e6,
              row.remainder / 1e6,
              row.deviation / 1e6,
              row.completion_pct ?? 0,
              row.contract_coverage_pct ?? 0,
            ]),
            [
              "ИТОГО",
              data.totals.plan / 1e6,
              data.totals.fact / 1e6,
              data.totals.remainder / 1e6,
              data.totals.deviation / 1e6,
              data.gauge.fact_pct,
              0,
            ],
          ],
          sheetName: "Утверждённый бюджет по проектам",
        }
      : null;
  const dirty = filters.projects.length > 0 || filters.fiz !== "Все" || filters.hide_zero !== null || filters.show_deviation;
  const gauge = data?.gauge ?? { plan: 0, fact: 0, deviation: 0, plan_mlrd: 0, fact_mlrd: 0, deviation_mlrd: 0, fact_pct: 0, deviation_pct: 0, axis_max_mlrd: 0 };
  return <AppShell title="Утверждённый бюджет план/факт" loading={loading}>
    <FiltersCard open={filtersOpen} onToggle={() => setFiltersOpen((value) => !value)}>
      <FiltersReset disabled={!dirty} onClick={() => setFilters(INITIAL)} />
      <FilterChipMulti label="Проект" values={filters.projects} options={data?.filters.projects ?? []} onChange={(projects) => setFilters((state) => ({ ...state, projects }))} />
      <FilterFieldsRow cols={2}>
        <FilterChipSelect label="ФИЗ" value={filters.fiz} options={["Все", ...(data?.filters.fiz ?? [])]} onChange={(fiz) => setFilters((state) => ({ ...state, fiz }))} />
        <div />
      </FilterFieldsRow>
      <FilterChecksRow cols={2}>
        <FilterCheck label="Показать отклонение" checked={filters.show_deviation} onChange={(event) => setFilters((state) => ({ ...state, show_deviation: event.target.checked }))} />
        <FilterCheck label="Скрывать месяцы, где план и факт равны 0" checked={hideZero} onChange={(event) => setFilters((state) => ({ ...state, hide_zero: event.target.checked }))} />
      </FilterChecksRow>
    </FiltersCard>
    {error || data?.meta.error ? <Card className="mb-4 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30"><Text className="text-rose-700 dark:text-rose-300">{error || data?.meta.error}</Text></Card> : null}
    <div className="space-y-6">
      <Card className="rounded-xl"><Title>Сводный БДДС по проектам</Title><div className="mt-3 grid items-center gap-6 lg:grid-cols-2"><HalfGauge gauge={gauge} /><div className="grid gap-4 sm:grid-cols-3">{[["План", gauge.plan_mlrd, gauge.plan / 1e6, "100%", ""], ["Факт", gauge.fact_mlrd, gauge.fact / 1e6, pct(gauge.fact_pct), "text-emerald-700 dark:text-emerald-300"], ["Отклонение", gauge.deviation_mlrd, gauge.deviation / 1e6, pct(gauge.deviation_pct), "text-rose-700 dark:text-rose-300"]].map(([label, bln, value, percent, color]) => <div key={String(label)} className={String(color)}><Text>{label}</Text><div className="mt-1 text-xl font-bold tabular-nums">{Number(bln).toFixed(2)} млрд</div><Text>{Number(value).toFixed(1)} млн. руб.</Text><Text>{percent}</Text></div>)}</div></div></Card>
      <Card className="rounded-xl"><FullscreenPanel disabled={!data?.tremor.by_period.length} fill>{(zoomed) => <FinanceBarChart rows={data?.tremor.by_period ?? []} planName="БДДС план" factName="БДДС факт" showDeviation={filters.show_deviation} xAxisTitle="Бюджет план/факт/отклонение по месяцам" fullscreen={zoomed} emptyText={loading ? "Загрузка…" : "Нет периодов для графика."} />}</FullscreenPanel></Card>
      <Card className="overflow-hidden rounded-xl border-[3px] border-[#94a3b8] p-0 dark:border-white">
        <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
          <Title>{data?.labels.period_table_title ?? "Сводная таблица по месяцам"}</Title>
        </div>
        <FullscreenPanel disabled={!periodRows.length} className="!overflow-x-hidden">
          <MobileCardStack>
            {periodRows.map((row) => (
              <MobileEntityCard key={row.period} title={row.period}>
                <MobileMetricGrid
                  items={[
                    { label: "План", value: mlnPlain(row.plan) },
                    { label: "Факт", value: mlnPlain(row.fact) },
                    { label: "Откл.", value: mlnPlain(row.deviation), className: deviationClass(row.deviation) },
                  ]}
                />
              </MobileEntityCard>
            ))}
            <MobileEntityCard title="ИТОГО">
              <MobileMetricGrid
                items={[
                  { label: "План", value: mlnPlain(data?.totals.plan ?? 0) },
                  { label: "Факт", value: mlnPlain(data?.totals.fact ?? 0) },
                  {
                    label: "Откл.",
                    value: mlnPlain(data?.totals.deviation ?? 0),
                    className: deviationClass(data?.totals.deviation ?? 0),
                  },
                ]}
              />
              <p className="mt-2 text-[10px] text-tremor-content dark:text-dark-tremor-content">Значения — млн ₽</p>
            </MobileEntityCard>
          </MobileCardStack>
          <div className="hidden overflow-x-auto p-1 pt-10 lg:block">
            <table className={TABLE}>
              <thead>
                <tr>
                  <SortHeader label="Месяц" sortKey="period" sort={periodSort} onSort={toggleSort(setPeriodSort)} />
                  <SortHeader label="План, млн. руб." sortKey="plan" sort={periodSort} onSort={toggleSort(setPeriodSort)} align="right" />
                  <SortHeader label="Факт, млн. руб." sortKey="fact" sort={periodSort} onSort={toggleSort(setPeriodSort)} align="right" />
                  <SortHeader label="Отклонение, млн. руб." sortKey="deviation" sort={periodSort} onSort={toggleSort(setPeriodSort)} align="right" />
                </tr>
              </thead>
              <tbody>
                {periodRows.map((row) => (
                  <tr key={row.period} className="odd:bg-slate-50/60 dark:odd:bg-slate-900/20">
                    <td className={`${CELL} ${BODY}`}>{row.period}</td>
                    <td className={`${CELL} ${BODY} text-right tabular-nums`}>{mln(row.plan)}</td>
                    <td className={`${CELL} ${BODY} text-right tabular-nums`}>{mln(row.fact)}</td>
                    <td className={`${CELL} ${BODY} text-right tabular-nums ${deviationClass(row.deviation)}`}>{mln(row.deviation)}</td>
                  </tr>
                ))}
                <tr className={TOTAL}>
                  <td className={`${CELL} px-3 py-2`}>ИТОГО</td>
                  <td className={`${CELL} ${BODY} text-right`}>{mln(data?.totals.plan ?? 0)}</td>
                  <td className={`${CELL} ${BODY} text-right`}>{mln(data?.totals.fact ?? 0)}</td>
                  <td className={`${CELL} ${BODY} text-right ${deviationClass(data?.totals.deviation ?? 0)}`}>{mln(data?.totals.deviation ?? 0)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </FullscreenPanel>
      </Card>
      <DownloadTableButton getTable={periodExport} fileStem="utverzhdennyy_byudzhet_po_mesyacam" disabled={!periodRows.length} />
      <Card className="overflow-hidden rounded-xl border-[3px] border-[#94a3b8] p-0 dark:border-white">
        <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
          <Title>{data?.labels.project_table_title ?? "Таблица утверждённого бюджет план/факт по проектам"}</Title>
        </div>
        <FullscreenPanel disabled={!projectRows.length} className="!overflow-x-hidden">
          <MobileCardStack>
            {projectRows.map((row) => (
              <MobileEntityCard
                key={row.project}
                title={row.project}
                badge={pct(row.completion_pct)}
                badgeTone={Number(row.completion_pct ?? 0) >= 100 ? "ok" : Number(row.completion_pct ?? 0) >= 50 ? "warn" : "bad"}
              >
                <MobileMetricGrid
                  columns={2}
                  items={[
                    { label: "План", value: mlnPlain(row.plan) },
                    { label: "Факт", value: mlnPlain(row.fact) },
                    { label: "Остаток", value: mlnPlain(row.remainder) },
                    { label: "Откл.", value: mlnPlain(row.deviation), className: deviationClass(row.deviation) },
                    { label: "% вып.", value: pct(row.completion_pct) },
                    { label: "% контр.", value: pct(row.contract_coverage_pct) },
                  ]}
                />
              </MobileEntityCard>
            ))}
            <MobileEntityCard title="ИТОГО" badge={pct(data?.gauge.fact_pct ?? 0)} badgeTone="neutral">
              <MobileMetricGrid
                columns={2}
                items={[
                  { label: "План", value: mlnPlain(data?.totals.plan ?? 0) },
                  { label: "Факт", value: mlnPlain(data?.totals.fact ?? 0) },
                  { label: "Остаток", value: mlnPlain(data?.totals.remainder ?? 0) },
                  {
                    label: "Откл.",
                    value: mlnPlain(data?.totals.deviation ?? 0),
                    className: deviationClass(data?.totals.deviation ?? 0),
                  },
                  { label: "% вып.", value: pct(data?.gauge.fact_pct ?? 0) },
                  { label: "% контр.", value: pct(0) },
                ]}
              />
              <p className="mt-2 text-[10px] text-tremor-content dark:text-dark-tremor-content">Значения — млн ₽</p>
            </MobileEntityCard>
          </MobileCardStack>
          <div className="hidden overflow-x-auto p-1 pt-10 lg:block">
            <table className={TABLE}>
              <thead>
                <tr>
                  <SortHeader label="Проект" sortKey="project" sort={projectSort} onSort={toggleSort(setProjectSort)} />
                  {(
                    ["plan", "fact", "remainder", "deviation", "completion_pct", "contract_coverage_pct"] as ProjectMetric[]
                  ).map((key) => (
                    <SortHeader
                      key={key}
                      label={projectHeaders[key]}
                      sortKey={key}
                      sort={projectSort}
                      onSort={toggleSort(setProjectSort)}
                      align="right"
                    />
                  ))}
                </tr>
              </thead>
              <tbody>
                {projectRows.map((row) => (
                  <tr key={row.project} className="odd:bg-slate-50/60 dark:odd:bg-slate-900/20">
                    <td className={`${CELL} ${BODY}`}>{row.project}</td>
                    <td className={`${CELL} ${BODY} text-right tabular-nums`}>{mlnPlain(row.plan)}</td>
                    <td className={`${CELL} ${BODY} text-right tabular-nums`}>{mlnPlain(row.fact)}</td>
                    <td className={`${CELL} ${BODY} text-right tabular-nums`}>{mlnPlain(row.remainder)}</td>
                    <td className={`${CELL} ${BODY} text-right tabular-nums ${deviationClass(row.deviation)}`}>{mln(row.deviation)}</td>
                    <td className={`${CELL} ${BODY} text-right tabular-nums`}>{pct(row.completion_pct)}</td>
                    <td className={`${CELL} ${BODY} text-right tabular-nums`}>{pct(row.contract_coverage_pct)}</td>
                  </tr>
                ))}
                <tr className={TOTAL}>
                  <td className={`${CELL} px-3 py-2`}>ИТОГО</td>
                  <td className={`${CELL} ${BODY} text-right tabular-nums`}>{mlnPlain(data?.totals.plan ?? 0)}</td>
                  <td className={`${CELL} ${BODY} text-right tabular-nums`}>{mlnPlain(data?.totals.fact ?? 0)}</td>
                  <td className={`${CELL} ${BODY} text-right tabular-nums`}>{mlnPlain(data?.totals.remainder ?? 0)}</td>
                  <td className={`${CELL} ${BODY} text-right tabular-nums ${deviationClass(data?.totals.deviation ?? 0)}`}>{mln(data?.totals.deviation ?? 0)}</td>
                  <td className={`${CELL} ${BODY} text-right tabular-nums`}>{pct(data?.gauge.fact_pct ?? 0)}</td>
                  <td className={`${CELL} ${BODY} text-right tabular-nums`}>{pct(0)}</td>
                </tr>
              </tbody>
            </table>
          </div>
        </FullscreenPanel>
      </Card>
      <DownloadTableButton getTable={projectExport} fileStem="utverzhdennyy_byudzhet_po_proektam" disabled={!projectRows.length} />
      {data?.hints.length ? <Card className="rounded-xl border-amber-300 bg-amber-50 dark:border-amber-800 dark:bg-amber-950/30"><Text className="font-medium text-amber-900 dark:text-amber-200">О данных для план-факта:</Text><ul className="mt-2 list-disc pl-5 text-sm text-amber-900 dark:text-amber-200">{data.hints.map((hint) => <li key={hint}>{hint}</li>)}</ul></Card> : null}
    </div>
  </AppShell>;
}
