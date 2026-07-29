"use client";

import { useCallback, useEffect, useState } from "react";
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
import { fetchDebitCredit, type DebitCreditPayload } from "@/lib/api";
import { formatMln, formatRub } from "@/lib/format";
import { AppShell } from "@/components/app-shell";

type Filters = {
  project: string;
  contractor: string;
  contract_q: string;
};

const toneText: Record<string, string> = {
  neutral: "text-tremor-content-strong dark:text-dark-tremor-content-strong",
  info: "text-blue-600 dark:text-blue-400",
  warn: "text-amber-600 dark:text-amber-400",
};

export function DebitCreditView() {
  const [filters, setFilters] = useState<Filters>({
    project: "Все",
    contractor: "Все",
    contract_q: "",
  });
  const [draftQ, setDraftQ] = useState("");
  const [data, setData] = useState<DebitCreditPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (f: Filters) => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchDebitCredit({
        project: f.project,
        contractor: f.contractor,
        contract_q: f.contract_q || undefined,
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

  const kpis = data?.kpis || {};
  const tremor = data?.tremor;
  const kpiCards = [
    {
      title: "Сумма договоров",
      metric: formatMln(kpis.contract_sum_mln),
      tone: "neutral",
    },
    {
      title: "Авансы выдано",
      metric: formatMln(kpis.advance_mln),
      tone: "info",
    },
    {
      title: "Принято КС-2",
      metric: formatMln(kpis.ks2_mln),
      tone: "warn",
    },
    {
      title: "Средний % аванса",
      metric: `${Number(kpis.advance_pct || 0).toFixed(1)}%`,
      tone: "neutral",
    },
  ];

  return (
    <AppShell
      title="Дебиторка подрядчиков"
      subtitle="Авансы, договоры и приёмка КС-2 · пилот Next.js + FastAPI"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-4">
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
                    setFilters((s) => ({ ...s, contract_q: draftQ.trim() }));
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
        <Text className="mt-3">
          Режим данных: <b>{data?.meta.data_mode || "…"}</b>
          {" · "}
          {loading ? "загрузка…" : `${data?.meta.rows ?? 0} строк`}
        </Text>
      </Card>

      {error ? (
        <Card className="mb-6 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">
            API недоступен (нужен FastAPI на :8000). {error}
          </Text>
        </Card>
      ) : null}

      <div className="space-y-6">
        <Grid numItemsSm={2} numItemsLg={4} className="gap-6">
          {kpiCards.map((kpi) => (
            <Card key={kpi.title} className="rounded-xl">
              <Text>{kpi.title}</Text>
              <Metric className={`mt-2 ${toneText[kpi.tone]}`}>{kpi.metric}</Metric>
            </Card>
          ))}
        </Grid>

        {tremor?.risk_note ? (
          <Card className="rounded-xl border-l-4 border-l-amber-500">
            <Text className="text-tremor-content-strong dark:text-dark-tremor-content-strong">
              ⚠ {tremor.risk_note}
            </Text>
          </Card>
        ) : null}

        <Grid numItemsLg={3} className="gap-6">
          <Card className="rounded-xl lg:col-span-2">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Договор против выданного аванса
            </Title>
            <Text className="mt-1">По подрядчикам, млн ₽</Text>
            <BarChart
              className="mt-6 h-80"
              data={tremor?.contract_vs_advance || []}
              index="label"
              categories={["Стоимость договора", "Аванс выдан"]}
              colors={["cyan", "amber"]}
              valueFormatter={(v) => formatMln(Number(v))}
              yAxisWidth={56}
              showLegend
              showAnimation
              showGridLines
            />
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Авансы по проектам
            </Title>
            <Text className="mt-1">Доля выданных авансов, млн ₽</Text>
            <DonutChart
              className="mt-6 h-52"
              data={tremor?.advance_by_project || []}
              category="advance"
              index="project"
              colors={["blue", "violet", "emerald", "cyan", "amber"]}
              valueFormatter={(v) => formatMln(Number(v))}
            />
            <List className="mt-4">
              {(tremor?.advance_by_project || []).map((d) => (
                <ListItem key={d.project}>
                  <span>{d.project}</span>
                  <span className="font-medium tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                    {formatMln(d.advance)}
                  </span>
                </ListItem>
              ))}
            </List>
          </Card>
        </Grid>

        <Card className="overflow-hidden rounded-xl p-0 text-tremor-content-strong dark:text-dark-tremor-content-strong">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Таблица договоров
            </Title>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-tremor-default text-tremor-content-strong dark:text-dark-tremor-content-strong">
              <thead className="bg-tremor-background-subtle text-tremor-label uppercase text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                <tr>
                  <th className="px-3 py-2">Проект</th>
                  <th className="px-3 py-2">Подрядчик</th>
                  <th className="px-3 py-2">Договор</th>
                  <th className="px-3 py-2">Дата</th>
                  <th className="px-3 py-2 text-right">Сумма</th>
                  <th className="px-3 py-2 text-right">Аванс</th>
                  <th className="px-3 py-2 text-right">КС-2</th>
                  <th className="px-3 py-2 text-right">Остаток</th>
                </tr>
              </thead>
              <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
                {(data?.rows || []).map((r, idx) => (
                  <tr
                    key={`${r.contract}-${idx}`}
                    className="border-t border-tremor-border dark:border-dark-tremor-border"
                  >
                    <td className="px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      {r.project}
                    </td>
                    <td className="px-3 py-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      {r.contractor}
                    </td>
                    <td className="px-3 py-2 font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      {r.contract}
                    </td>
                    <td className="px-3 py-2 text-tremor-content dark:text-dark-tremor-content">
                      {r.contract_date || "—"}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      {formatRub(r.contract_sum)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      {formatRub(r.advance)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      {formatRub(r.ks2)}
                    </td>
                    <td className="px-3 py-2 text-right tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      {formatRub(r.balance)}
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
