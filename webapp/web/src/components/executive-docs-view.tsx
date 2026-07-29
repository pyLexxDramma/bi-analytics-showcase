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
  fetchExecutiveDocs,
  type ExecutiveDocsPayload,
} from "@/lib/api";
import { AppShell } from "@/components/app-shell";
import { CHART_RU } from "@/lib/chart-ru";

type Filters = {
  project: string;
  contractor: string;
  date_from: string;
  date_to: string;
  granularity: string;
  hide_overdue_if_signed: boolean;
};

const toneText: Record<string, string> = {
  neutral: "text-tremor-content-strong dark:text-dark-tremor-content-strong",
  info: "text-blue-600 dark:text-blue-400",
  ok: "text-emerald-600 dark:text-emerald-400",
  warn: "text-amber-600 dark:text-amber-400",
  danger: "text-rose-600 dark:text-rose-400",
};

function BucketRow({
  title,
  count,
  b07,
  b830,
  b30,
}: {
  title: string;
  count: number;
  b07: number;
  b830: number;
  b30: number;
}) {
  return (
    <Card className="rounded-xl">
      <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
        {title}
      </Title>
      <Metric className="mt-2 text-rose-600 dark:text-rose-400">{count}</Metric>
      <Text className="mt-1">Документов в просрочке</Text>
      <Grid numItemsSm={3} className="mt-4 gap-3">
        <div>
          <Text>До 7 дн.</Text>
          <p className="text-lg font-semibold tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
            {b07}
          </p>
        </div>
        <div>
          <Text>7–30 дн.</Text>
          <p className="text-lg font-semibold tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
            {b830}
          </p>
        </div>
        <div>
          <Text>&gt; 30 дн.</Text>
          <p className="text-lg font-semibold tabular-nums text-tremor-content-strong dark:text-dark-tremor-content-strong">
            {b30}
          </p>
        </div>
      </Grid>
    </Card>
  );
}

export function ExecutiveDocsView() {
  const [filters, setFilters] = useState<Filters>({
    project: "Все",
    contractor: "Все",
    date_from: "",
    date_to: "",
    granularity: "month",
    hide_overdue_if_signed: true,
  });
  const [data, setData] = useState<ExecutiveDocsPayload | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(true);

  const load = useCallback(async (f: Filters) => {
    setLoading(true);
    setError(null);
    try {
      const payload = await fetchExecutiveDocs({
        project: f.project,
        contractor: f.contractor,
        date_from: f.date_from || undefined,
        date_to: f.date_to || undefined,
        granularity: f.granularity,
        hide_overdue_if_signed: f.hide_overdue_if_signed ? "true" : "false",
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

  const byObjectChart = useMemo(
    () =>
      (tremor?.by_object || []).map((r) => ({
        object: r.object,
        [CHART_RU.docsCount]: r.count,
      })),
    [tremor?.by_object],
  );

  const overdueContrChart = useMemo(
    () =>
      (tremor?.overdue_contractor || []).map((r) => ({
        contractor: r.contractor,
        [CHART_RU.docsCount]: r.count,
      })),
    [tremor?.overdue_contractor],
  );

  const overdueCustChart = useMemo(
    () =>
      (tremor?.overdue_customer || []).map((r) => ({
        contractor: r.contractor,
        [CHART_RU.docsCount]: r.count,
      })),
    [tremor?.overdue_customer],
  );

  const dynamicsChart = useMemo(
    () =>
      (tremor?.dynamics || []).map((r) => ({
        period: r.period,
        [CHART_RU.newDocs]: r.new_docs,
      })),
    [tremor?.dynamics],
  );

  const kpiCards = [
    {
      title: "Всего документов",
      metric: String(kpis?.total_docs ?? "—"),
      tone: "neutral",
    },
    {
      title: "Отказы",
      metric: String(kpis?.declined ?? "—"),
      tone: "danger",
    },
    {
      title: "На согласовании",
      metric: String(kpis?.on_agree ?? "—"),
      tone: "warn",
    },
    {
      title: "Принято",
      metric: String(kpis?.signed ?? "—"),
      tone: "ok",
    },
    {
      title: "У подрядчика",
      metric: String(kpis?.on_rework ?? "—"),
      tone: "info",
    },
    {
      title: "Всего просрочек",
      metric: String(kpis?.overdue_total ?? "—"),
      tone: "danger",
    },
  ];

  return (
    <AppShell
      title="Исполнительная документация"
      subtitle="TESSA · статусы ИД, просрочки подрядчика и заказчика"
    >
      <Card className="mb-6 rounded-xl">
        <div className="grid gap-3 md:grid-cols-3 lg:grid-cols-5">
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
            <Text>Контрагент</Text>
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
          <label className="block text-sm">
            <Text>Гранулярность</Text>
            <select
              className="mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={filters.granularity}
              onChange={(e) =>
                setFilters((s) => ({ ...s, granularity: e.target.value }))
              }
            >
              {(
                data?.filters.granularities || [
                  { id: "month", label: "Месяц" },
                ]
              ).map((g) => (
                <option key={g.id} value={g.id}>
                  {g.label}
                </option>
              ))}
            </select>
          </label>
        </div>
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={filters.hide_overdue_if_signed}
            onChange={(e) =>
              setFilters((s) => ({
                ...s,
                hide_overdue_if_signed: e.target.checked,
              }))
            }
          />
          <Text>
            Не отображать просрочку, если ИД сдана (подписана/согласована)
          </Text>
        </label>
        <Text className="mt-3">
          Режим данных: <b>{data?.meta.data_mode || "…"}</b>
          {" · "}
          {loading
            ? "загрузка…"
            : `${data?.meta.rows ?? 0} док. · таблица ${data?.meta.table_rows ?? 0}`}
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
        <Grid numItemsSm={2} numItemsLg={3} className="gap-6">
          {kpiCards.map((kpi) => (
            <Card key={kpi.title} className="rounded-xl">
              <Text>{kpi.title}</Text>
              <Metric className={`mt-2 ${toneText[kpi.tone]}`}>
                {kpi.metric}
              </Metric>
            </Card>
          ))}
        </Grid>

        <Grid numItemsLg={2} className="gap-6">
          <BucketRow
            title="Просрочка подрядчика (сдача ИД)"
            count={kpis?.contractor_overdue.count ?? 0}
            b07={kpis?.contractor_overdue.bucket_0_7 ?? 0}
            b830={kpis?.contractor_overdue.bucket_8_30 ?? 0}
            b30={kpis?.contractor_overdue.bucket_30_plus ?? 0}
          />
          <BucketRow
            title="Просрочка заказчика (согласование)"
            count={kpis?.customer_overdue.count ?? 0}
            b07={kpis?.customer_overdue.bucket_0_7 ?? 0}
            b830={kpis?.customer_overdue.bucket_8_30 ?? 0}
            b30={kpis?.customer_overdue.bucket_30_plus ?? 0}
          />
        </Grid>

        <Grid numItemsLg={2} className="gap-6">
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              На доработке по подрядчикам
            </Title>
            <BarChart
              className="mt-6 h-72"
              data={overdueContrChart}
              index="contractor"
              categories={[CHART_RU.docsCount]}
              colors={["rose"]}
              valueFormatter={(v) => String(Math.round(Number(v)))}
              yAxisWidth={48}
              showLegend={false}
              showAnimation
              showGridLines
              layout="vertical"
            />
          </Card>
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              На согласовании по контрагентам
            </Title>
            <BarChart
              className="mt-6 h-72"
              data={overdueCustChart}
              index="contractor"
              categories={[CHART_RU.docsCount]}
              colors={["amber"]}
              valueFormatter={(v) => String(Math.round(Number(v)))}
              yAxisWidth={48}
              showLegend={false}
              showAnimation
              showGridLines
              layout="vertical"
            />
          </Card>
        </Grid>

        <Grid numItemsLg={3} className="gap-6">
          <Card className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              По статусам
            </Title>
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
            <List className="mt-4 max-h-40 overflow-y-auto">
              {(tremor?.by_status || []).map((d) => (
                <ListItem key={d.status}>
                  <span className="truncate pr-2">{d.status}</span>
                  <span className="shrink-0 font-medium tabular-nums">
                    {d.count} · {d.share_pct}%
                  </span>
                </ListItem>
              ))}
            </List>
          </Card>
          <Card className="rounded-xl lg:col-span-2">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Документы по объектам
            </Title>
            <BarChart
              className="mt-6 h-80"
              data={byObjectChart}
              index="object"
              categories={[CHART_RU.docsCount]}
              colors={["cyan"]}
              valueFormatter={(v) => String(Math.round(Number(v)))}
              yAxisWidth={48}
              showLegend={false}
              showAnimation
              showGridLines
            />
          </Card>
        </Grid>

        <Card className="rounded-xl">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            Динамика новых документов
          </Title>
          <Text className="mt-1">По дате создания</Text>
          <BarChart
            className="mt-6 h-72"
            data={dynamicsChart}
            index="period"
            categories={[CHART_RU.newDocs]}
            colors={["blue"]}
            valueFormatter={(v) => String(Math.round(Number(v)))}
            yAxisWidth={48}
            showLegend={false}
            showAnimation
            showGridLines
          />
        </Card>

        <Card className="overflow-hidden rounded-xl p-0 text-tremor-content-strong dark:text-dark-tremor-content-strong">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Детальный отчёт (без подписанных)
            </Title>
          </div>
          <div className="overflow-x-auto">
            <table className="min-w-full text-left text-tremor-default">
              <thead className="bg-tremor-background-subtle text-tremor-label uppercase text-tremor-content dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content">
                <tr>
                  <th className="px-3 py-2">Контрагент</th>
                  <th className="px-3 py-2">Объект</th>
                  <th className="px-3 py-2">№ док.</th>
                  <th className="px-3 py-2">Тип</th>
                  <th className="px-3 py-2">План сдачи</th>
                  <th className="px-3 py-2">Факт</th>
                  <th className="px-3 py-2 text-right">Проср. сдачи</th>
                  <th className="px-3 py-2">Передача</th>
                  <th className="px-3 py-2 text-right">Проср. соглас.</th>
                  <th className="px-3 py-2">Статус</th>
                  <th className="px-3 py-2">Создан</th>
                </tr>
              </thead>
              <tbody className="bg-tremor-background dark:bg-dark-tremor-background">
                {(data?.rows || []).map((r, idx) => (
                  <tr
                    key={`${r.doc_number}-${idx}`}
                    className="border-t border-tremor-border dark:border-dark-tremor-border"
                  >
                    <td
                      className="px-3 py-2 max-w-[9rem] truncate"
                      title={r.contractor}
                    >
                      {r.contractor}
                    </td>
                    <td
                      className="px-3 py-2 max-w-[9rem] truncate"
                      title={r.project}
                    >
                      {r.project}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.doc_number}
                    </td>
                    <td
                      className="px-3 py-2 max-w-[8rem] truncate"
                      title={r.kind}
                    >
                      {r.kind}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.plan_date || "—"}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.fact_date || "—"}
                    </td>
                    <td
                      className={`px-3 py-2 text-right tabular-nums ${
                        (r.submit_late_days ?? 0) > 0
                          ? "font-medium text-rose-600 dark:text-rose-400"
                          : ""
                      }`}
                    >
                      {r.submit_late_days == null ? "—" : r.submit_late_days}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.transfer_date || "—"}
                    </td>
                    <td
                      className={`px-3 py-2 text-right tabular-nums ${
                        (r.agree_late_days ?? 0) > 0
                          ? "font-medium text-amber-600 dark:text-amber-400"
                          : ""
                      }`}
                    >
                      {r.agree_late_days == null ? "—" : r.agree_late_days}
                    </td>
                    <td className="px-3 py-2 whitespace-nowrap">{r.status}</td>
                    <td className="px-3 py-2 whitespace-nowrap">
                      {r.creation_date || "—"}
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
