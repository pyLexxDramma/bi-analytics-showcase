"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { BarChart, Card, Grid, Metric, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { fetchGdrsPeople, type GdrsPayload } from "@/lib/api";
import {
  PLAN_FACT_DEVIATION_CATEGORIES,
  withRuPlanFactDeviation,
} from "@/lib/chart-ru";

type Filters = {
  projects: string[];
  contractors: string[];
  months: string[];
  plan_agg: string;
  skud_agg: string;
  /** false until first API response sets defaults */
  ready: boolean;
};

const tableCell =
  "px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong";
const tableCellLeft =
  "px-3 py-2 text-left text-tremor-content-strong dark:text-dark-tremor-content-strong";

function fmtInt(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return Math.round(n).toLocaleString("ru-RU");
}

function fmtPct(n: number | null | undefined): string {
  if (n == null || Number.isNaN(n)) return "—";
  return `${n.toLocaleString("ru-RU", { maximumFractionDigits: 1 })}%`;
}

export function GdrsPeopleView() {
  const [filters, setFilters] = useState<Filters>({
    projects: [],
    contractors: [],
    months: [],
    plan_agg: "Среднее за месяц",
    skud_agg: "Среднее за месяц",
    ready: false,
  });
  const [data, setData] = useState<GdrsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (next: Filters) => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchGdrsPeople({
        projects: next.projects,
        contractors: next.contractors,
        months: next.months,
        plan_agg: next.plan_agg,
        skud_agg: next.skud_agg,
      });
      setData(payload);
      if (!next.ready) {
        const sel = payload.filters.selected;
        setFilters({
          projects: sel.projects ?? [],
          contractors: sel.contractors ?? [],
          months: sel.months?.length
            ? sel.months
            : payload.filters.default_months,
          plan_agg: sel.plan_agg || "Среднее за месяц",
          skud_agg: sel.skud_agg || "Среднее за месяц",
          ready: true,
        });
      }
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(filters);
    // eslint-disable-next-line react-hooks/exhaustive-deps -- reload on filter fields only
  }, [
    filters.ready,
    filters.projects,
    filters.contractors,
    filters.months,
    filters.plan_agg,
    filters.skud_agg,
    load,
  ]);

  const kpis = data?.kpis ?? {
    plan: 0,
    fact: 0,
    deviation: 0,
    delta_pct: null,
  };

  const projectChart = useMemo(
    () =>
      withRuPlanFactDeviation(
        (data?.tremor.by_project ?? []).map((r) => ({
          name: r.name,
          plan: r.plan,
          fact: r.fact,
          deviation: r.deviation,
        })),
      ),
    [data?.tremor.by_project],
  );

  const contractorChart = useMemo(
    () =>
      withRuPlanFactDeviation(
        (data?.tremor.by_contractor ?? []).slice(0, 15).map((r) => ({
          name: r.name,
          plan: r.plan,
          fact: r.fact,
          deviation: r.deviation,
        })),
      ),
    [data?.tremor.by_contractor],
  );

  const toggleMulti = (
    key: "projects" | "contractors" | "months",
    value: string,
  ) => {
    setFilters((s) => {
      const cur = new Set(s[key]);
      if (cur.has(value)) cur.delete(value);
      else cur.add(value);
      return { ...s, [key]: Array.from(cur) };
    });
  };

  return (
    <AppShell
      title="ГДРС (люди)"
      subtitle="План из 1С (договоры) и факт СКУД — среднее число людей в день"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
          <MultiSelect
            label="Проект"
            options={data?.filters.projects ?? []}
            selected={filters.projects}
            placeholder="Все проекты"
            onToggle={(v) => toggleMulti("projects", v)}
            onClear={() => setFilters((s) => ({ ...s, projects: [] }))}
          />
          <MultiSelect
            label="Контрагент"
            options={data?.filters.contractors ?? []}
            selected={filters.contractors}
            placeholder="Все контрагенты"
            onToggle={(v) => toggleMulti("contractors", v)}
            onClear={() => setFilters((s) => ({ ...s, contractors: [] }))}
          />
          <MultiSelect
            label="Месяц"
            options={data?.filters.months ?? []}
            selected={filters.months}
            placeholder="Все месяцы"
            onToggle={(v) => toggleMulti("months", v)}
            onClear={() =>
              setFilters((s) => ({
                ...s,
                months: data?.filters.default_months ?? [],
              }))
            }
          />
          <label className="block text-sm">
            <Text>План</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.plan_agg}
              onChange={(e) =>
                setFilters((s) => ({ ...s, plan_agg: e.target.value }))
              }
            >
              {(data?.filters.agg_options ?? ["Среднее за месяц"]).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>СКУД</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.skud_agg}
              onChange={(e) =>
                setFilters((s) => ({ ...s, skud_agg: e.target.value }))
              }
            >
              {(data?.filters.agg_options ?? ["Среднее за месяц"]).map((o) => (
                <option key={o} value={o}>
                  {o}
                </option>
              ))}
            </select>
          </label>
        </div>
        <Text className="mt-3">
          Режим: <b>{data?.meta.data_mode ?? "…"}</b>
          {data?.meta.period_label ? ` · ${data.meta.period_label}` : ""}
          {" · "}
          {loading ? "загрузка…" : `${data?.meta.rows ?? 0} строк`}
        </Text>
        {data?.meta.warning ? (
          <Text className="mt-2 text-amber-700 dark:text-amber-300">
            {data.meta.warning}
          </Text>
        ) : null}
      </Card>

      {error ? (
        <Card className="mb-6 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            API недоступен. {error}
          </Text>
        </Card>
      ) : null}

      <div className="space-y-6">
        <Grid numItemsSm={2} numItemsLg={4} className="gap-6">
          {[
            ["План", fmtInt(kpis.plan)],
            ["СКУД (факт)", fmtInt(kpis.fact)],
            ["Отклонение", fmtInt(kpis.deviation)],
            ["Отклонение %", fmtPct(kpis.delta_pct)],
          ].map(([title, metric]) => (
            <Card key={title} className="rounded-xl">
              <Text>{title}</Text>
              <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {metric}
              </Metric>
            </Card>
          ))}
        </Grid>

        <Card className="rounded-xl">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            План / Факт / Отклонение по проектам
          </Title>
          <Text className="mt-1">Среднее число людей в день</Text>
          <BarChart
            className="mt-6 h-80"
            data={projectChart}
            index="name"
            categories={[...PLAN_FACT_DEVIATION_CATEGORIES]}
            colors={["blue", "emerald", "rose"]}
            valueFormatter={(v) => fmtInt(Number(v))}
            yAxisWidth={48}
            showLegend
            showAnimation
            showGridLines
          />
        </Card>

        <Card className="rounded-xl overflow-x-auto">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong mb-3">
            ГДРС по выбранным проектам
          </Title>
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-tremor-border dark:border-dark-tremor-border">
                <th className={`${tableCellLeft} font-medium`}>Проект</th>
                <th className={`${tableCell} font-medium`}>План</th>
                <th className={`${tableCell} font-medium`}>Факт</th>
                <th className={`${tableCell} font-medium`}>Отклонение</th>
                <th className={`${tableCell} font-medium`}>Отклонение %</th>
              </tr>
            </thead>
            <tbody>
              {(data?.project_rows ?? []).map((r) => (
                <tr
                  key={r.project}
                  className="border-b border-tremor-border/60 dark:border-dark-tremor-border/60"
                >
                  <td className={tableCellLeft}>{r.project}</td>
                  <td className={tableCell}>{fmtInt(r.plan)}</td>
                  <td className={tableCell}>{fmtInt(r.fact)}</td>
                  <td className={tableCell}>{fmtInt(r.deviation)}</td>
                  <td className={tableCell}>{fmtPct(r.delta_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>

        <Card className="rounded-xl overflow-x-auto">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong mb-3">
            График движения рабочей силы (люди)
            {data?.meta.period_label ? `, ${data.meta.period_label}` : ""}
          </Title>
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-tremor-border dark:border-dark-tremor-border">
                <th className={`${tableCellLeft} font-medium`}>Контрагент</th>
                <th className={`${tableCellLeft} font-medium`}>Вид работ</th>
                <th className={`${tableCell} font-medium`}>План</th>
                <th className={`${tableCell} font-medium`}>СКУД</th>
                <th className={`${tableCell} font-medium`}>Отклонение</th>
                <th className={`${tableCell} font-medium`}>Отклонение %</th>
              </tr>
            </thead>
            <tbody>
              {(data?.matrix_rows ?? []).map((r, i) => {
                const bold =
                  r.kind === "subtotal" || r.kind === "grand_total"
                    ? "font-semibold"
                    : "";
                return (
                  <tr
                    key={`${r.kind}-${r.label}-${i}`}
                    className={`border-b border-tremor-border/60 dark:border-dark-tremor-border/60 ${
                      r.kind === "subtotal"
                        ? "bg-tremor-background-muted/40 dark:bg-dark-tremor-background-muted/40"
                        : ""
                    }`}
                  >
                    <td className={`${tableCellLeft} ${bold}`}>{r.label}</td>
                    <td className={tableCellLeft}>{r.vid_raboty}</td>
                    <td className={`${tableCell} ${bold}`}>{fmtInt(r.plan)}</td>
                    <td className={`${tableCell} ${bold}`}>{fmtInt(r.skud)}</td>
                    <td className={`${tableCell} ${bold}`}>
                      {fmtInt(r.deviation)}
                    </td>
                    <td className={`${tableCell} ${bold}`}>
                      {fmtPct(r.delta_pct)}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        </Card>

        <Card className="rounded-xl">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            План / Факт / Отклонение по контрагентам
          </Title>
          <Text className="mt-1">Топ-15 по плану</Text>
          <BarChart
            className="mt-6 h-96"
            data={contractorChart}
            index="name"
            categories={[...PLAN_FACT_DEVIATION_CATEGORIES]}
            colors={["blue", "emerald", "rose"]}
            valueFormatter={(v) => fmtInt(Number(v))}
            yAxisWidth={48}
            layout="vertical"
            showLegend
            showAnimation
            showGridLines
          />
        </Card>

        <Card className="rounded-xl overflow-x-auto">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong mb-3">
            Распределение по контрагентам
          </Title>
          <table className="min-w-full text-sm">
            <thead>
              <tr className="border-b border-tremor-border dark:border-dark-tremor-border">
                <th className={`${tableCellLeft} font-medium`}>Контрагент</th>
                <th className={`${tableCell} font-medium`}>План</th>
                <th className={`${tableCell} font-medium`}>Факт</th>
                <th className={`${tableCell} font-medium`}>Отклонение</th>
                <th className={`${tableCell} font-medium`}>Доля %</th>
              </tr>
            </thead>
            <tbody>
              {(data?.contractor_rows ?? []).map((r) => (
                <tr
                  key={r.contractor}
                  className="border-b border-tremor-border/60 dark:border-dark-tremor-border/60"
                >
                  <td className={tableCellLeft}>{r.contractor}</td>
                  <td className={tableCell}>{fmtInt(r.plan)}</td>
                  <td className={tableCell}>{fmtInt(r.fact)}</td>
                  <td className={tableCell}>{fmtInt(r.deviation)}</td>
                  <td className={tableCell}>{fmtPct(r.share_pct)}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </Card>
      </div>
    </AppShell>
  );
}

function MultiSelect({
  label,
  options,
  selected,
  placeholder,
  onToggle,
  onClear,
}: {
  label: string;
  options: string[];
  selected: string[];
  placeholder: string;
  onToggle: (v: string) => void;
  onClear: () => void;
}) {
  const [open, setOpen] = useState(false);
  const summary =
    selected.length === 0
      ? placeholder
      : selected.length <= 2
        ? selected.join(", ")
        : `${selected.length} выбрано`;

  return (
    <div className="relative block text-sm">
      <Text>{label}</Text>
      <button
        type="button"
        className="mt-1 flex w-full items-center justify-between rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-left text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
        onClick={() => setOpen((o) => !o)}
      >
        <span className="truncate">{summary}</span>
        <span className="ml-2 text-xs opacity-60">{open ? "▲" : "▼"}</span>
      </button>
      {open ? (
        <div className="absolute z-20 mt-1 max-h-56 w-full overflow-auto rounded-tremor-default border border-tremor-border bg-tremor-background p-2 shadow-lg dark:border-dark-tremor-border dark:bg-dark-tremor-background">
          <button
            type="button"
            className="mb-1 w-full rounded px-2 py-1 text-left text-xs text-tremor-content hover:bg-tremor-background-muted dark:hover:bg-dark-tremor-background-muted"
            onClick={() => {
              onClear();
              setOpen(false);
            }}
          >
            Сбросить
          </button>
          {options.map((o) => (
            <label
              key={o}
              className="flex cursor-pointer items-center gap-2 rounded px-2 py-1 hover:bg-tremor-background-muted dark:hover:bg-dark-tremor-background-muted"
            >
              <input
                type="checkbox"
                checked={selected.includes(o)}
                onChange={() => onToggle(o)}
              />
              <span className="truncate text-tremor-default">{o}</span>
            </label>
          ))}
        </div>
      ) : null}
    </div>
  );
}
