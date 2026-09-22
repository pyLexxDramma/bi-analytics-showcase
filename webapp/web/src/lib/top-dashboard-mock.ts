import type { TopDashboardPayload, TopProject, TopSchedRow } from "@/lib/api";

const MILESTONES = [
  "Завершение СМР по блоку А до ЗОС",
  "Завершение СМР по блоку U1. U2 до ЗОС",
  "Завершение СМР по блоку U3. U4 до ЗОС",
  "Завершение СМР по КПП до ЗОС",
  "Завершение СМР по блокам",
  "Завершение СМР по техническим помещениям",
  "Завершение работ по отделке",
  "Завершение работ по эл.сетям + оборудование",
  "Завершение работ по газовым сетям + оборудование",
  "Завершение работ по НВК и оборудование",
  "Завершение СМР по ЗАВОД до ЗОС",
];

const COVENANTS = [
  "ГПЗУ",
  "Стадия П",
  "Корректировка стадии П",
  "стадия РД",
  "СЗЗ",
  "Экспертиза",
  "Корректировка экспертизы",
  "Разрешение РС",
  "КОД, ОТКР. ФИНАНС. (начало финансирования)",
  "СМР (начало)",
  "Корректировка РС",
  "Пуск электричества",
  "Пуск газа",
  "ЗОС",
  "РВ",
  "Право 1",
  "ВЫКУП ЗУ",
  "Право 2",
];

function sched(name: string, plan: string, fact: string, days: number): TopSchedRow {
  const delta = days === 0 ? "0д" : days > 0 ? `-${days}д` : `+${Math.abs(days)}д`;
  return {
    name,
    plan,
    fact,
    delta,
    statusClass: days > 0 ? "delta-negative" : days < 0 ? "delta-positive" : "",
  };
}

function rows(names: string[], start: string, step: number, days: number[]): TopSchedRow[] {
  const [dd, mm, yy] = start.split(".").map(Number);
  const base = new Date(yy, mm - 1, dd);
  return names.map((name, idx) => {
    const plan = new Date(base);
    plan.setDate(base.getDate() + idx * step);
    const fact = new Date(plan);
    const d = days[idx % days.length];
    fact.setDate(plan.getDate() + d);
    const fmt = (x: Date) =>
      `${String(x.getDate()).padStart(2, "0")}.${String(x.getMonth() + 1).padStart(2, "0")}.${x.getFullYear()}`;
    return sched(name, fmt(plan), fmt(fact), d);
  });
}

function project(partial: Omit<TopProject, "milestones" | "covenants"> & { shiftDays: number[] }): TopProject {
  const { shiftDays, ...rest } = partial;
  const covenants = rows(COVENANTS, "01.09.2024", 14, shiftDays);
  const rv = covenants.find((c) => c.name === "РВ");
  return {
    ...rest,
    milestones: rows(MILESTONES, "15.01.2025", 12, shiftDays),
    covenants,
    rvDate: rv
      ? { plan: rv.plan, fact: rv.fact, delta: rv.delta }
      : rest.rvDate,
  };
}

const PROJECTS: TopProject[] = [
  project({
    id: "dmitr",
    name: "Дмитровский 1",
    short: "DMI-1",
    status: "critical",
    dds: { plan: 3200, fact: 3780 },
    bdr: { plan: 2900, fact: 3410 },
    labor: { plan: 320, fact: 184 },
    equip: { plan: 45, fact: 32 },
    smr: { planPercent: 52, factPercent: 47 },
    rd: {
      planSheets: 420,
      factSheets: 286,
      planPercent: 100,
      factPercent: 68,
      customerOverdue: 14,
      contractorOverdue: 23,
    },
    prescriptions: { totalIssued: 24, closed: 12, overdue: 12, critOverdue: 4, nonCritOverdue: 8 },
    execDocs: { total: 180, done: 84 },
    reason: "Срыв поставок металлоконструкций, корректировка стадии П, дефицит кадров",
    rvReason: "Задержка экспертизы и срыв поставок",
    rvDate: { plan: "01.12.2025", fact: "—", delta: "критический сдвиг" },
    shiftDays: [20, 18, 22, 16, 24],
  }),
  project({
    id: "esip",
    name: "Есипово 5",
    short: "ESP-5",
    status: "warning",
    dds: { plan: 2750, fact: 3020 },
    bdr: { plan: 2520, fact: 2790 },
    labor: { plan: 245, fact: 198 },
    equip: { plan: 35, fact: 27 },
    smr: { planPercent: 68, factPercent: 61 },
    rd: {
      planSheets: 490,
      factSheets: 363,
      planPercent: 100,
      factPercent: 74,
      customerOverdue: 18,
      contractorOverdue: 28,
    },
    prescriptions: { totalIssued: 19, closed: 11, overdue: 8, critOverdue: 3, nonCritOverdue: 5 },
    execDocs: { total: 210, done: 128 },
    reason: "Задержка корректировки экспертизы, отставание по СМР",
    rvReason: "Корректировка экспертизы затянулась",
    rvDate: { plan: "20.12.2025", fact: "—", delta: "под риском" },
    shiftDays: [10, 8, 12, 6, 4],
  }),
  project({
    id: "zhuk",
    name: "Жуковский 1",
    short: "ZHK-1",
    status: "warning",
    dds: { plan: 2450, fact: 2670 },
    bdr: { plan: 2280, fact: 2480 },
    labor: { plan: 215, fact: 168 },
    equip: { plan: 32, fact: 24 },
    smr: { planPercent: 64, factPercent: 53 },
    rd: {
      planSheets: 370,
      factSheets: 300,
      planPercent: 100,
      factPercent: 81,
      customerOverdue: 9,
      contractorOverdue: 17,
    },
    prescriptions: { totalIssued: 14, closed: 7, overdue: 7, critOverdue: 2, nonCritOverdue: 5 },
    execDocs: { total: 160, done: 85 },
    reason: "Низкая явка ресурсов по техническим помещениям",
    rvReason: "Отставание по эл.сетям и разрешению РС",
    rvDate: { plan: "01.11.2025", fact: "—", delta: "вероятен сдвиг" },
    shiftDays: [8, -2, 10, 3, 5],
  }),
  project({
    id: "len",
    name: "Ленинский",
    short: "LEN-2",
    status: "good",
    dds: { plan: 2100, fact: 1980 },
    bdr: { plan: 1950, fact: 1840 },
    labor: { plan: 210, fact: 228 },
    equip: { plan: 28, fact: 30 },
    smr: { planPercent: 85, factPercent: 89 },
    rd: {
      planSheets: 315,
      factSheets: 302,
      planPercent: 100,
      factPercent: 96,
      customerOverdue: 2,
      contractorOverdue: 5,
    },
    prescriptions: { totalIssued: 8, closed: 8, overdue: 0, critOverdue: 0, nonCritOverdue: 0 },
    execDocs: { total: 140, done: 125 },
    reason: "Опережение графика, экономия бюджета",
    rvReason: "—",
    rvDate: { plan: "15.10.2025", fact: "10.10.2025", delta: "-5д (опережение)" },
    shiftDays: [-5, -3, -6, 2, -4],
  }),
  project({
    id: "novo",
    name: "Новорижский",
    short: "NOV-R",
    status: "critical",
    dds: { plan: 3800, fact: 4350 },
    bdr: { plan: 3500, fact: 4020 },
    labor: { plan: 350, fact: 205 },
    equip: { plan: 50, fact: 31 },
    smr: { planPercent: 45, factPercent: 29 },
    rd: {
      planSheets: 610,
      factSheets: 342,
      planPercent: 100,
      factPercent: 56,
      customerOverdue: 35,
      contractorOverdue: 52,
    },
    prescriptions: { totalIssued: 32, closed: 12, overdue: 20, critOverdue: 7, nonCritOverdue: 13 },
    execDocs: { total: 260, done: 75 },
    reason: "Критическое отставание по экспертизе, срыв СМР",
    rvReason: "Экспертиза не пройдена, пуск электричества отложен",
    rvDate: { plan: "30.06.2026", fact: "—", delta: "срыв сроков" },
    shiftDays: [40, 35, 42, 28, 38],
  }),
];

export const TOP_DASHBOARD_MOCK: TopDashboardPayload = {
  meta: { source: "mock", parity: "proto_21_09", error: null },
  filters: {
    projects: PROJECTS.map((p) => ({ id: p.id, name: p.name })),
    applied: { project: "all" },
  },
  milestonesCatalog: MILESTONES,
  covenantsCatalog: COVENANTS,
  projects: PROJECTS,
};
