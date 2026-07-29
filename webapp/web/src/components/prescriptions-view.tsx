"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import {
  BarChart,
  Card,
  DonutChart,
  Grid,
  List,
  ListItem,
  Metric,
  Text,
  Title,
} from "@tremor/react";
import {
  fetchPrescriptions,
  type PrescriptionsPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { CHART_RU } from "@/lib/chart-ru";

type Filters = {
  project: string;
  contractor: string;
  contract_q: string;
  date_from: string;
  date_to: string;
  hide_resolved: boolean;
};

const toneText: Record<string, string> = {
  neutral: "text-tremor-content-strong dark:text-dark-tremor-content-strong",
  info: "text-blue-600 dark:text-blue-400",
  ok: "text-emerald-600 dark:text-emerald-400",
  warn: "text-amber-600 dark:text-amber-400",
  danger: "text-rose-600 dark:text-rose-400",
};

export function PrescriptionsView() {
  const [filters, setFilters] = useState<Filters>({
    project: "Все",
    contractor: "Все",
    contract_q: "",
    date_from: "",
    date_to: "",
    hide_resolved: false,
  });
  const [draftQ, setDraftQ] = useState("");
  const [data, setData] = useState<PrescriptionsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (f: Filters) => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchPrescriptions({
        project: f.project,
        contractor: f.contractor,
        contract_q: f.contract_q || undefined,
        date_from: f.date_from || undefined,
        date_to: f.date_to || undefined,
        hide_resolved: f.hide_resolved ? "true" : undefined,
      });
      setData(payload);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setData(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    void load(filters);
  }, [filters, load]);

  const kpis = data?.kpis;
  const tremor = data?.tremor;

  const byContractorChart = useMemo(
    () =>
      (tremor?.by_contractor || []).map((r) => ({
        contractor: r.contractor,
        [CHART_RU.total]: r.total,
        [CHART_RU.overdue]: r.overdue,
      })),
    [tremor?.by_contractor],
  );

  const kpiCards = [
    { title: "Всего", metric: String(kpis?.total ?? "—"), tone: "neutral" },
    { title: "Снято", metric: String(kpis?.resolved ?? "—"), tone: "ok" },
    {
      title: "Не снято",
      metric: String(kpis?.unresolved ?? "—"),
      tone: "info",
    },
    {
      title: "Без просрочки",
      metric: String(kpis?.non_overdue ?? "—"),
      tone: "ok",
    },
    {
      title: "Просрочено (открытые)",
      metric: String(kpis?.overdue_unresolved ?? "—"),
      tone: "danger",
    },
    {
      title: "Критичные",
      metric: String(kpis?.critical ?? "—"),
      tone: "warn",
    },
    {
      title: "Остановка работ",
      metric: String(kpis?.stop_work ?? "—"),
      tone: "danger",
    },
  ];

  return (
    <AppShell
      title="Предписания по подрядчикам"
      subtitle="TESSA · статусы, просрочки и критичность"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-6">
          <label className="block text-sm">
            <Text>Проект</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.project}
              onChange={(e) =>
                setFilters((s) => ({ ...s, project: e.target.value }))
              }
            >
              {(data?.filters.projects || ["Все"]).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Подрядчик</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.contractor}
              onChange={(e) =>
                setFilters((s) => ({ ...s, contractor: e.target.value }))
              }
            >
              {(data?.filters.contractors || ["Все"]).map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </select>
          </label>
          <label className="block text-sm">
            <Text>Дата с</Text>
            <input
              type="date"
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.date_from}
              min={data?.filters.date_min || undefined}
              max={data?.filters.date_max || undefined}
              onChange={(e) =>
                setFilters((s) => ({ ...s, date_from: e.target.value }))
              }
            />
          </label>
          <label className="block text-sm">
            <Text>Дата по</Text>
            <input
              type="date"
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.date_to}
              min={data?.filters.date_min || undefined}
              max={data?.filters.date_max || undefined}
              onChange={(e) =>
                setFilters((s) => ({ ...s, date_to: e.target.value }))
              }
            />
          </label>
          <label className="block text-sm md:col-span-2">
            <Text>№ договора</Text>
            <div className="mt-1 flex gap-2">
              <input
                className="w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                placeholder="Частичный поиск"
                value={draftQ}
                onChange={(e) => setDraftQ(e.target.value)}
                onKeyDown={(e) => {
                  if (e.key === "Enter") {
                    setFilters((s) => ({
                      ...s,
                      contract_q: draftQ.trim(),
                    }));
                  }
                }}
              />
              <button
                type="button"
                className="rounded-tremor-default bg-tremor-brand px-4 py-2 text-tremor-default font-medium text-white"
                onClick={() =>
                  setFilters((s) => ({ ...s, contract_q: draftQ.trim() }))
                }
              >
                Найти
              </button>
            </div>
          </label>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={filters.hide_resolved}
            onChange={(e) =>
              setFilters((s) => ({ ...s, hide_resolved: e.target.checked }))
            }
          />
          <Text>Скрыть снятые</Text>
        </label>
        <Text className="mt-3">
          Режим данных: <b>{data?.meta.data_mode || "…"}</b>
          {" · "}
          {loading ? "загрузка…" : `${data?.meta.rows ?? 0} строк`}
          {data?.meta.source ? ` · ${data.meta.source}` : ""}
        </Text>
        {data?.meta.warning ? (
          <Text className="mt-1 text-amber-700 dark:text-amber-300">
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
          {kpiCards.map((kpi) => (
            <Card key={kpi.title} className="rounded-xl">
              <Text>{kpi.title}</Text>
              <Metric className={`mt-2 ${toneText[kpi.tone]}`}>
                {kpi.metric}
              </Metric>
            </Card>
          ))}
        </Grid>

        <Grid numItemsLg={3} className="gap-6">
          <Card className="rounded-xl lg:col-span-2">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              По подрядчикам
            </Title>
            <Text className="mt-1">Всего и просроченные открытые</Text>
            <BarChart
              className="mt-6 h-80"
              data={byContractorChart}
              index="contractor"
              categories={[CHART_RU.total, CHART_RU.overdue]}
              colors={["cyan", "rose"]}
              valueFormatter={(v) => String(Math.round(Number(v)))}
              yAxisWidth={48}
              showLegend
              showAnimation
              showGridLines
            />
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              По статусам
            </Title>
            <Text className="mt-1">Доля предписаний</Text>
            <DonutChart
              className="mt-6 h-52"
              data={tremor?.by_status || []}
              category="count"
              index="status"
              colors={[
                "emerald",
                "amber",
                "rose",
                "cyan",
                "violet",
                "blue",
                "slate",
              ]}
              valueFormatter={(v) => String(Math.round(Number(v)))}
            />
            <List className="mt-4 max-h-48 overflow-y-auto">
              {(tremor?.by_status || []).map((d) => (
                <ListItem key={d.status}>
                  <span className="truncate pr-2">{d.status}</span>
                  <span className="shrink-0 font-medium tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                    {d.count} · {d.share_pct}%
                  </span>
                </ListItem>
              ))}
            </List>
          </Card>
        </Grid>

        <Card className="overflow-hidden rounded-xl p-0 text-tremor-content-strong dark:text-dark-tremor-content-strong">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Таблица предписаний
            </Title>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-tremor-default text-tremor-content-strong dark:text-dark-tremor-content-strong">
              <thead className="bg-tremor-background-subtle text-tremor-label uppercase text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                <tr>
                  <th className="px-3 py-2">Статус</th>
                  <th className="px-3 py-2">Подрядчик</th>
                  <th className="px-3 py-2">Проект</th>
                  <th className="px-3 py-2">Договор</th>
                  <th className="px-3 py-2">№ док.</th>
                  <th className="px-3 py-2">№ предп.</th>
                  <th className="px-3 py-2">Название</th>
                  <th className="px-3 py-2">Выдано</th>
                  <th className="px-3 py-2">Срок</th>
                  <th className="px-3 py-2">Снято</th>
                  <th className="px-3 py-2 text-right">Просрочка, дн</th>
                  <th className="px-3 py-2">Теги</th>
                </tr>
              </thead>
              <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
                {(data?.rows || []).map((r, idx) => (
                  <tr
                    key={`${r.pred_number}-${r.doc_number}-${idx}`}
                    className="border-t border-tremor-border dark:border-dark-tremor-border"
                  >
                    <td className="px-3 py-2 whitespace-nowrap">{r.status}</td>
                    <td className="px-3 py-2 max-w-[10rem] truncate" title={r.contractor}>
                      {r.contractor}
                    </td>
                    <td className="px-3 py-2 max-w-[10rem] truncate" title={r.project}>
                      {r.project}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{r.contract_no}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{r.doc_number}</td>
                    <td className="px-3 py-2 whitespace-nowrap">{r.pred_number}</td>
                    <td className="px-3 py-2 max-w-[14rem] truncate" title={r.name}>
                      {r.name}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.issue_date || "—"}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.due_date || "—"}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.completion_date || "—"}
                    </td>
                    <td
                      className={`px-3 py-2 text-right tabular-nums ${
                        r.overdue_days > 0
                          ? "text-rose-600 dark:text-rose-400 font-medium"
                          : ""
                      }`}
                    >
                      {r.overdue_days}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap text-tremor-content dark:text-dark-tremor-content">
                      {[
                        r.critical ? "критич." : null,
                        r.stop_work ? "остановка" : null,
                      ]
                        .filter(Boolean)
                        .join(" · ") || "—"}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      </div>
    </AppShell>
  );
}
