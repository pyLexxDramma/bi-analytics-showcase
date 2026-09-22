"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import { AppShell } from "@/components/app-shell";
import {
  fetchTopDashboard,
  type TopDashboardPayload,
  type TopIdRow,
  type TopProject,
  type TopSchedRow,
} from "@/lib/api";
import { TOP_DASHBOARD_MOCK } from "@/lib/top-dashboard-mock";
import { useRefreshTick } from "@/lib/refresh-context";
import "./top-dashboard-view.css";

function getIndicator(planVal: number, factVal: number): "green" | "yellow" | "red" {
  if (!planVal) return factVal ? "red" : "green";
  const ratio = factVal / planVal;
  if (ratio >= 0.95) return "green";
  if (ratio >= 0.8) return "yellow";
  return "red";
}

function ValPair({
  plan,
  fact,
  unit = "",
  planLabel = "план",
  factLabel = "факт",
}: {
  plan: string | number;
  fact: string | number;
  unit?: string;
  planLabel?: string;
  factLabel?: string;
}) {
  return (
    <>
      <span className="val-group">
        <span>
          {plan}
          {unit}
        </span>
        <span className="val-sublabel">{planLabel}</span>
      </span>
      <span className="val-sep">/</span>
      <span className="val-group">
        <span>
          {fact}
          {unit}
        </span>
        <span className="val-sublabel">{factLabel}</span>
      </span>
    </>
  );
}

function statusText(status: string): string {
  if (status === "critical") return "Критический";
  if (status === "warning") return "Требует внимания";
  return "В норме";
}

function bgClass(status: string): string {
  if (status === "critical") return "bg-critical";
  if (status === "warning") return "bg-warning";
  return "bg-good";
}

function covenantOf(p: TopProject, name: string): TopSchedRow | undefined {
  const aliases: Record<string, string[]> = {
    ЗОС: ["ЗОС"],
    "Право 1": ["Право 1"],
    "Выкуп ЗУ": ["ВЫКУП ЗУ", "Выкуп ЗУ"],
    "Право 2": ["Право 2"],
  };
  const keys = aliases[name] || [name];
  const rows = p.cardCovenants?.length ? p.cardCovenants : p.covenants || [];
  return rows.find((c) =>
    keys.some((k) => c.name.toLowerCase() === k.toLowerCase()),
  );
}

function overdueRows(rows: TopIdRow[] | undefined, emptyLabel: string) {
  if (!rows?.length) {
    return (
      <tr>
        <td colSpan={3}>{emptyLabel}</td>
      </tr>
    );
  }
  return rows.map((row, idx) =>
    row.more ? (
      <tr key={`more-${idx}`}>
        <td colSpan={3}>{row.days}</td>
      </tr>
    ) : (
      <tr key={`${row.doc}-${idx}`}>
        <td>{row.contractor}</td>
        <td>{row.doc}</td>
        <td>{row.days}</td>
      </tr>
    ),
  );
}

function KpiStrip({ projects }: { projects: TopProject[] }) {
  const n = Math.max(projects.length, 1);
  const totalDdsPlan = projects.reduce((s, p) => s + p.dds.plan, 0);
  const totalDdsFact = projects.reduce((s, p) => s + p.dds.fact, 0);
  const totalBdrPlan = projects.reduce((s, p) => s + p.bdr.plan, 0);
  const totalBdrFact = projects.reduce((s, p) => s + p.bdr.fact, 0);
  const totalLaborPlan = projects.reduce((s, p) => s + p.labor.plan, 0);
  const totalLaborFact = projects.reduce((s, p) => s + p.labor.fact, 0);
  const totalEquipPlan = projects.reduce((s, p) => s + p.equip.plan, 0);
  const totalEquipFact = projects.reduce((s, p) => s + p.equip.fact, 0);
  const avgSmrPlan = projects.reduce((s, p) => s + p.smr.planPercent, 0) / n;
  const avgSmrFact = projects.reduce((s, p) => s + p.smr.factPercent, 0) / n;
  const avgRdFact = projects.reduce((s, p) => s + p.rd.factPercent, 0) / n;
  const totalRdPlan = projects.reduce((s, p) => s + p.rd.planSheets, 0);
  const totalRdFact = projects.reduce((s, p) => s + p.rd.factSheets, 0);
  const totalCritOverdue = projects.reduce((s, p) => s + p.prescriptions.critOverdue, 0);
  const totalNonCritOverdue = projects.reduce((s, p) => s + p.prescriptions.nonCritOverdue, 0);
  return (
    <div className="kpi-strip">
      <div className="kpi-item">
        <div className="kpi-label">
          <span className={`indicator-${getIndicator(totalDdsPlan, totalDdsFact)}`} /> БДДС
        </div>
        <div className="kpi-number">
          <ValPair
            plan={(totalDdsPlan / 1000).toFixed(1)}
            fact={(totalDdsFact / 1000).toFixed(1)}
          />{" "}
          млрд
        </div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">
          <span className={`indicator-${getIndicator(totalBdrPlan, totalBdrFact)}`} /> БДР
        </div>
        <div className="kpi-number">
          <ValPair
            plan={(totalBdrPlan / 1000).toFixed(1)}
            fact={(totalBdrFact / 1000).toFixed(1)}
          />{" "}
          млрд
        </div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">
          <span className={`indicator-${getIndicator(totalLaborPlan, totalLaborFact)}`} /> Люди
        </div>
        <div className="kpi-number">
          <ValPair plan={totalLaborPlan} fact={totalLaborFact} />
        </div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">
          <span className={`indicator-${getIndicator(totalEquipPlan, totalEquipFact)}`} /> Техника
        </div>
        <div className="kpi-number">
          <ValPair plan={totalEquipPlan} fact={totalEquipFact} />
        </div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">
          <span className={`indicator-${getIndicator(avgSmrPlan, avgSmrFact)}`} /> % СМР
        </div>
        <div className="kpi-number">
          {Math.round(avgSmrFact)}%{" "}
          <span className="val-sublabel" style={{ display: "inline" }}>
            ({Math.round(avgSmrPlan)}/{Math.round(avgSmrFact)})
          </span>
        </div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">
          <span className={`indicator-${getIndicator(100, avgRdFact)}`} /> % РД
        </div>
        <div className="kpi-number">
          {Math.round(avgRdFact)}%{" "}
          <span className="val-sublabel" style={{ display: "inline" }}>
            ({totalRdPlan}/{totalRdFact})
          </span>
        </div>
      </div>
      <div className="kpi-item">
        <div className="kpi-label">⚠️ Просроченные предписания (крит. и некрит.)</div>
        <div className="kpi-number">
          <ValPair
            plan={totalCritOverdue}
            fact={totalNonCritOverdue}
            planLabel="крит."
            factLabel="не крит."
          />
        </div>
      </div>
    </div>
  );
}

function Cards({ projects }: { projects: TopProject[] }) {
  const sorted = [...projects].sort((a, b) => {
    const order: Record<string, number> = { critical: 0, warning: 1, good: 2 };
    return (order[a.status] ?? 9) - (order[b.status] ?? 9);
  });
  return (
    <div className="projects-grid">
      {sorted.map((p) => {
        const zos = covenantOf(p, "ЗОС");
        const pravo1 = covenantOf(p, "Право 1");
        const vykup = covenantOf(p, "Выкуп ЗУ");
        const pravo2 = covenantOf(p, "Право 2");
        const rvInd = p.rvDate.fact && p.rvDate.fact !== "—" ? "green" : "red";
        const ddsPct = p.dds.plan
          ? (((p.dds.fact - p.dds.plan) / p.dds.plan) * 100).toFixed(0)
          : "0";
        return (
          <div key={p.id} className={`project-card ${bgClass(p.status)}`}>
            <div className="project-header">
              <span className="project-name">🏢 {p.name}</span>
              <span className="status-badge">{statusText(p.status)}</span>
            </div>
            <div className="metric-line">
              <span className="metric-label">
                <span className={`indicator-${getIndicator(p.dds.plan, p.dds.fact)}`} /> БДДС (млн)
              </span>
              <span>
                <ValPair plan={p.dds.plan} fact={p.dds.fact} />{" "}
                <span className="val-sublabel" style={{ display: "inline" }}>
                  ({ddsPct}%)
                </span>
              </span>
            </div>
            <div className="metric-line">
              <span className="metric-label">
                <span className={`indicator-${getIndicator(p.bdr.plan, p.bdr.fact)}`} /> БДР (млн)
              </span>
              <span>
                <ValPair plan={p.bdr.plan} fact={p.bdr.fact} />
              </span>
            </div>
            <div className="metric-line">
              <span className="metric-label">
                <span className={`indicator-${getIndicator(p.labor.plan, p.labor.fact)}`} /> Люди
              </span>
              <span>
                <ValPair plan={p.labor.plan} fact={p.labor.fact} />
              </span>
            </div>
            <div className="metric-line">
              <span className="metric-label">
                <span className={`indicator-${getIndicator(p.equip.plan, p.equip.fact)}`} /> Техника
              </span>
              <span>
                <ValPair plan={p.equip.plan} fact={p.equip.fact} />
              </span>
            </div>
            <div className="metric-line">
              <span className="metric-label">
                <span className={`indicator-${getIndicator(100, p.rd.factPercent)}`} /> РД
              </span>
              <span>
                {p.rd.factPercent}% ({p.rd.factSheets}/{p.rd.planSheets})
              </span>
            </div>
            <div className="metric-line">
              <span className="metric-label">⚠️ Просроченные предписания (крит. и некрит.)</span>
              <span>
                <ValPair
                  plan={p.prescriptions.critOverdue}
                  fact={p.prescriptions.nonCritOverdue}
                  planLabel="крит."
                  factLabel="не крит."
                />
              </span>
            </div>
            <div className="metric-line">
              <span className="metric-label">
                <span className={`indicator-${rvInd}`} /> Срок РВ
              </span>
              <span>
                {p.rvDate.plan} / {p.rvDate.fact}{" "}
                <span
                  className={
                    p.rvDate.delta && p.rvDate.delta.startsWith("+") ? "badge-green" : "badge-red"
                  }
                >
                  {p.rvDate.delta}
                </span>
              </span>
            </div>
            {(
              [
                ["📌 ЗОС", zos],
                ["📌 Право 1", pravo1],
                ["📌 Выкуп ЗУ", vykup],
                ["📌 Право 2", pravo2],
              ] as const
            ).map(([label, row]) => (
              <div className="metric-line" key={label}>
                <span className="metric-label">{label}</span>
                <span>
                  {row?.plan ?? "—"} / {row?.fact ?? "—"}{" "}
                  <span className={row?.statusClass || ""}>({row?.delta ?? "—"})</span>
                </span>
              </div>
            ))}
            {p.rvReason && p.rvReason !== "—" ? (
              <div className="reason-text">
                <strong>📌 Причина смещения срока РВ:</strong> {p.rvReason}
              </div>
            ) : null}
          </div>
        );
      })}
    </div>
  );
}

function Detail({ proj }: { proj: TopProject }) {
  const bgHeader =
    proj.status === "critical" ? "#ffe8e6" : proj.status === "warning" ? "#fff4e5" : "#e6f4ea";
  const execDone = proj.execDocs.done;
  const execTotal = proj.execDocs.total || 0;
  const execRemaining = Math.max(0, execTotal - execDone);
  const execPct = execTotal ? Math.round((execDone / execTotal) * 100) : 0;
  const ddsPct = proj.dds.plan
    ? (((proj.dds.fact - proj.dds.plan) / proj.dds.plan) * 100).toFixed(1)
    : "0.0";

  return (
    <div className="detail-container" style={{ background: bgHeader }}>
      <div
        style={{
          display: "flex",
          justifyContent: "space-between",
          alignItems: "center",
          marginBottom: 24,
        }}
      >
        <h2 style={{ fontWeight: 800 }}>
          🏢 {proj.name} ({proj.short})
        </h2>
        <span className="status-badge" style={{ background: "white" }}>
          {statusText(proj.status)}
        </span>
      </div>
      <DetailInner
        proj={proj}
        ddsPct={ddsPct}
        execPct={execPct}
        execDone={execDone}
        execRemaining={execRemaining}
      />
    </div>
  );
}

type ChartJs = {
  register: (plugin: unknown) => void;
  new (
    ctx: HTMLCanvasElement,
    cfg: Record<string, unknown>,
  ): { destroy: () => void };
};

function loadScript(src: string): Promise<void> {
  return new Promise((resolve, reject) => {
    const found = document.querySelector(`script[src="${src}"]`);
    if (found) {
      if (found.getAttribute("data-loaded") === "1") {
        resolve();
        return;
      }
      found.addEventListener("load", () => resolve(), { once: true });
      found.addEventListener("error", () => reject(new Error(src)), { once: true });
      return;
    }
    const script = document.createElement("script");
    script.src = src;
    script.async = true;
    script.onload = () => {
      script.setAttribute("data-loaded", "1");
      resolve();
    };
    script.onerror = () => reject(new Error(src));
    document.head.appendChild(script);
  });
}

async function loadChartJs(): Promise<ChartJs> {
  await loadScript("https://cdn.jsdelivr.net/npm/chart.js@4.4.0/dist/chart.umd.min.js");
  await loadScript(
    "https://cdn.jsdelivr.net/npm/chartjs-plugin-datalabels@2.0.0/dist/chartjs-plugin-datalabels.min.js",
  );
  const w = window as unknown as {
    Chart?: ChartJs;
    ChartDataLabels?: unknown;
  };
  if (!w.Chart) throw new Error("Chart.js");
  if (w.ChartDataLabels) w.Chart.register(w.ChartDataLabels);
  return w.Chart;
}

function DetailInner({
  proj,
  ddsPct,
  execPct,
  execDone,
  execRemaining,
}: {
  proj: TopProject;
  ddsPct: string;
  execPct: number;
  execDone: number;
  execRemaining: number;
}) {
  const financeRef = useRef<HTMLCanvasElement>(null);
  const resourcesRef = useRef<HTMLCanvasElement>(null);
  const rdRef = useRef<HTMLCanvasElement>(null);
  const prescRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    const charts: Array<{ destroy: () => void }> = [];
    let cancelled = false;
    (async () => {
      const Chart = await loadChartJs();
      if (cancelled) return;
      const bar = { barPercentage: 0.5, categoryPercentage: 0.6 };
      if (financeRef.current) {
        charts.push(
          new Chart(financeRef.current, {
            type: "bar",
            data: {
              labels: ["БДДС", "БДР"],
              datasets: [
                { label: "План (млн)", data: [proj.dds.plan, proj.bdr.plan], backgroundColor: "#6f9fc0", ...bar },
                { label: "Факт (млн)", data: [proj.dds.fact, proj.bdr.fact], backgroundColor: "#e2863b", ...bar },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: true,
              plugins: {
                datalabels: { anchor: "end", align: "top", formatter: (val: number) => val, font: { weight: "bold", size: 10 } },
                legend: { position: "top" },
              },
            },
          }),
        );
      }
      if (resourcesRef.current) {
        charts.push(
          new Chart(resourcesRef.current, {
            type: "bar",
            data: {
              labels: ["Люди (чел)", "Техника (ед)"],
              datasets: [
                { label: "План", data: [proj.labor.plan, proj.equip.plan], backgroundColor: "#6f9fc0", ...bar },
                { label: "Факт", data: [proj.labor.fact, proj.equip.fact], backgroundColor: "#e2863b", ...bar },
              ],
            },
            options: {
              responsive: true,
              maintainAspectRatio: true,
              plugins: {
                datalabels: { anchor: "end", align: "top", formatter: (val: number) => val, font: { weight: "bold", size: 10 } },
              },
            },
          }),
        );
      }
      const rdDone = proj.rd.factSheets;
      const rdRemaining = Math.max(0, proj.rd.planSheets - rdDone);
      if (rdRef.current) {
        charts.push(
          new Chart(rdRef.current, {
            type: "doughnut",
            data: {
              labels: ["Выдано в ПР", "Не выдано"],
              datasets: [{ data: [rdDone, rdRemaining], backgroundColor: ["#2c9baf", "#e2e8f0"] }],
            },
            options: {
              responsive: true,
              plugins: {
                datalabels: {
                  formatter: (val: number) => {
                    const total = rdDone + rdRemaining;
                    return `${val} (${total ? ((val / total) * 100).toFixed(0) : 0}%)`;
                  },
                  color: (ctx: { dataIndex: number }) => (ctx.dataIndex === 0 ? "#fff" : "#1a4c6e"),
                  font: { weight: "bold" },
                },
                legend: { position: "bottom" },
              },
            },
          }),
        );
      }
      if (prescRef.current) {
        charts.push(
          new Chart(prescRef.current, {
            type: "doughnut",
            data: {
              labels: ["Крит.", "Не крит."],
              datasets: [
                {
                  data: [proj.prescriptions.critOverdue, proj.prescriptions.nonCritOverdue],
                  backgroundColor: ["#2c9baf", "#e74c3c"],
                },
              ],
            },
            options: {
              responsive: true,
              plugins: {
                datalabels: { formatter: (val: number) => val, color: "#fff", font: { weight: "bold" } },
                legend: { position: "bottom" },
              },
            },
          }),
        );
      }
    })();
    return () => {
      cancelled = true;
      charts.forEach((c) => c.destroy());
    };
  }, [proj]);

  return (
    <div className="detail-grid">
      <div className="detail-card">
        <div className="card-title">
          <span className={`indicator-${getIndicator(proj.dds.plan, proj.dds.fact)}`} /> Финансы
        </div>
        <div className="flex-between">
          <span>БДДС (млн)</span>
          <span>
            <strong>
              {proj.dds.plan} / {proj.dds.fact}
            </strong>{" "}
            ({ddsPct}%)
          </span>
        </div>
        <div className="flex-between">
          <span>БДР (млн)</span>
          <span>
            {proj.bdr.plan} / {proj.bdr.fact}
          </span>
        </div>
        <div className="chart-container">
          <canvas ref={financeRef} />
        </div>
      </div>
      <div className="detail-card">
        <div className="card-title">
          <span className={`indicator-${getIndicator(proj.labor.plan, proj.labor.fact)}`} /> Трудозатраты
        </div>
        <div className="flex-between">
          <span>Люди</span>
          <span>
            {proj.labor.plan} / {proj.labor.fact}
          </span>
        </div>
        <div className="flex-between">
          <span>Техника</span>
          <span>
            {proj.equip.plan} / {proj.equip.fact}
          </span>
        </div>
        <div className="chart-container">
          <canvas ref={resourcesRef} />
        </div>
      </div>
      <div className="detail-card">
        <div className="card-title">📄 Документация</div>
        <div style={{ marginBottom: 16 }}>
          <strong>Рабочая документация (РД)</strong>
        </div>
        <div className="chart-container">
          <canvas ref={rdRef} />
        </div>
        <div style={{ margin: "16px 0 8px" }}>
          <strong>⚠️ Просроченные предписания (крит. и некрит.)</strong>
        </div>
        <div className="chart-container">
          <canvas ref={prescRef} />
        </div>
        <div style={{ margin: "16px 0 8px" }}>
          <strong>Исполнительная документация</strong>
        </div>
        <div className="progress-bar-wrap">
          <div className="progress-bar-track">
            <div className="progress-bar-fill" style={{ width: `${execPct}%` }}>
              {execPct >= 15 ? `${execPct}%` : ""}
            </div>
          </div>
          <div className="progress-bar-labels">
            <span>
              Выполнено: {execDone} ({execPct}%)
            </span>
            <span>Осталось: {execRemaining}</span>
          </div>
        </div>
        <div style={{ marginTop: 14, fontSize: "0.75rem", fontWeight: 600, color: "#bc3f2c" }}>
          Просрочка подрядчика
        </div>
        <table className="overdue-table">
          <thead>
            <tr>
              <th>Подрядчик</th>
              <th>№ документа</th>
              <th>Просрочка сдачи</th>
            </tr>
          </thead>
          <tbody>{overdueRows(proj.idOverdueContractor, "Нет просрочек")}</tbody>
        </table>
        <div style={{ marginTop: 12, fontSize: "0.75rem", fontWeight: 600, color: "#bc3f2c" }}>
          Просрочка заказчика
        </div>
        <table className="overdue-table">
          <thead>
            <tr>
              <th>Подрядчик</th>
              <th>№ документа</th>
              <th>Просрочка согласования</th>
            </tr>
          </thead>
          <tbody>{overdueRows(proj.idOverdueCustomer, "Нет просрочек")}</tbody>
        </table>
      </div>
      <div className="detail-card">
        <div className="card-title">🏗️ Ход СМР и причины</div>
        <div className="flex-between">
          <span>% СМР план/факт</span>
          <span>
            {proj.smr.planPercent}% / {proj.smr.factPercent}%
          </span>
        </div>
        {proj.rvReason && proj.rvReason !== "—" ? (
          <div className="reason-text">
            <strong>Причина смещения РВ:</strong> {proj.rvReason}
          </div>
        ) : null}
        <div style={{ marginTop: 12 }}>
          <strong>Вехи СМР (план/факт/отклонение)</strong>
        </div>
        <div className="full-list">
          <table className="milestone-table">
            <thead>
              <tr>
                <th>Веха СМР</th>
                <th>План</th>
                <th>Факт</th>
                <th>Отклонение</th>
              </tr>
            </thead>
            <tbody>
              {(proj.milestones || []).map((m) => (
                <tr key={m.name}>
                  <td>{m.name}</td>
                  <td>{m.plan}</td>
                  <td>{m.fact}</td>
                  <td>
                    <span className={m.statusClass}>{m.delta}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
        <div style={{ marginTop: 12 }}>
          <strong>Ковенанты (план/факт/отклонение)</strong>
        </div>
        <div className="full-list">
          <table className="covenant-table">
            <thead>
              <tr>
                <th>Ковенант</th>
                <th>План</th>
                <th>Факт</th>
                <th>Отклонение</th>
              </tr>
            </thead>
            <tbody>
              {(proj.covenants || []).map((c) => (
                <tr key={c.name}>
                  <td>{c.name}</td>
                  <td>{c.plan}</td>
                  <td>{c.fact}</td>
                  <td>
                    <span className={c.statusClass}>{c.delta}</span>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </div>
    </div>
  );
}

export function TopDashboardView() {
  const tick = useRefreshTick();
  const [data, setData] = useState<TopDashboardPayload>(TOP_DASHBOARD_MOCK);
  const [selected, setSelected] = useState("all");

  useEffect(() => {
    let cancelled = false;
    fetchTopDashboard("all")
      .then((payload) => {
        if (cancelled || !payload?.projects?.length) return;
        setData(payload);
      })
      .catch(() => {
        /* оставляем мок прототипа */
      });
    return () => {
      cancelled = true;
    };
  }, [tick]);

  const projects = data.projects || [];
  const visible = useMemo(() => {
    if (selected === "all") return projects;
    return projects.filter((p) => p.id === selected || p.name === selected);
  }, [projects, selected]);
  const one = selected !== "all" && visible.length ? visible[0] : undefined;

  return (
    <AppShell title="ТОП менеджмент">
        <div className="top-dash">
          <div className="dashboard">
            <KpiStrip projects={visible.length ? visible : projects} />
            <div className="filter-bar">
              <div className="filter-selector">
                <label>🔍 Показать:</label>
                <select
                  value={selected}
                  onChange={(e) => setSelected(e.target.value)}
                  onInput={(e) => setSelected((e.target as HTMLSelectElement).value)}
                >
                  <option value="all">📊 Все проекты (сводка)</option>
                  {projects.map((p) => (
                    <option key={p.id} value={p.id}>
                      {p.name}
                    </option>
                  ))}
                </select>
              </div>
            </div>
            {one ? <Detail proj={one} /> : <Cards projects={visible} />}
            <div className="footer-note">
              🟢 зелёный круг — план выполнен, 🔴 красный — отклонение, 🟡 жёлтый — близко к норме. В
              режиме &quot;один проект&quot; — полные таблицы вех и ковенантов (без прокрутки), все факты
              заполнены датами, на диаграммах постоянные числовые подписи.
            </div>
          </div>
        </div>
    </AppShell>
  );
}
