/** Page-level Ask AI: nav.id → XCA report (зеркало API ask_ai_reports). */

export type AskAiScreen = {
  report: string;
  title: string;
  src: string;
  ctxHint: string;
};

export const ASK_AI_SCREENS: Record<string, AskAiScreen> = {
  "developer-projects": {
    report: "screen_developer_projects",
    title: "Девелоперские проекты",
    src: "developer-projects",
    ctxHint:
      "Матрица девелоперских проектов: статусы, сроки, ключевые метрики по проектам.",
  },
  bdds: {
    report: "screen_bdds",
    title: "БДДС (расходы)",
    src: "finance/bdds",
    ctxHint: "БДДС расходы по периодам. Суммы в рублях.",
  },
  bdr: {
    report: "screen_bdr",
    title: "БДР (расходы)",
    src: "finance/bdr",
    ctxHint: "БДР расходы.",
  },
  "approved-budget": {
    report: "screen_approved_budget",
    title: "Утверждённый бюджет план/факт",
    src: "finance/approved-budget",
    ctxHint: "Утверждённый бюджет план и факт.",
  },
  "bdds-plan-fact": {
    report: "screen_bdds_plan_fact",
    title: "БДДС расходы (план, факт, уточненный план)",
    src: "finance/bdds-plan-fact",
    ctxHint: "План, факт и уточнённый план БДДС.",
  },
  "control-points": {
    report: "screen_control_points",
    title: "Контрольные точки",
    src: "timeline/control-points",
    ctxHint: "Контрольные точки графика.",
  },
  "project-schedule": {
    report: "screen_project_schedule",
    title: "График проекта",
    src: "timeline/project-schedule",
    ctxHint: "График проекта / смещение задач.",
  },
  "deviation-reasons": {
    report: "screen_deviation_reasons",
    title: "Причины отклонений",
    src: "timeline/deviation-reasons",
    ctxHint: "Причины отклонений / срыва.",
  },
  "baseline-deviation": {
    report: "screen_baseline_deviation",
    title: "Отклонение от базового плана",
    src: "timeline/baseline-deviation",
    ctxHint: "Отклонение от базового плана MSP.",
  },
  "project-documentation": {
    report: "screen_project_documentation",
    title: "Проектная документация",
    src: "docs/project-documentation",
    ctxHint: "Проектная документация.",
  },
  "working-documentation": {
    report: "screen_working_documentation",
    title: "Рабочая документация",
    src: "docs/working-documentation",
    ctxHint: "Рабочая документация.",
  },
  "gdrs-people": {
    report: "screen_gdrs_people",
    title: "ГДРС (люди)",
    src: "gdrs/people",
    ctxHint: "ГДРС люди план/факт.",
  },
  "gdrs-equipment": {
    report: "screen_gdrs_equipment",
    title: "ГДРС (техника)",
    src: "gdrs/equipment",
    ctxHint: "ГДРС техника план/факт.",
  },
  prescriptions: {
    report: "screen_prescriptions",
    title: "Предписания по подрядчикам",
    src: "prescriptions",
    ctxHint: "Предписания по подрядчикам.",
  },
  "executive-docs": {
    report: "screen_executive_docs",
    title: "Исполнительная документация",
    src: "executive-docs",
    ctxHint: "Исполнительная документация.",
  },
  "debit-credit": {
    report: "screen_debit_credit",
    title: "Дебиторская и кредиторская задолженность подрядчиков",
    src: "debit-credit",
    ctxHint: "ДЗ/КЗ подрядчиков.",
  },
};

/** Служебные / уже вынесенные в project|period — не дублируем в filters. */
const RESERVED_QUERY_KEYS = new Set([
  "project",
  "projects",
  "period",
  "month",
  "from",
  "to",
  "date_from",
  "date_to",
]);

const ALL_PROJECT_VALUES = new Set(["все", "all", "*", ""]);

function isAllProject(value: string): boolean {
  return ALL_PROJECT_VALUES.has(value.trim().toLowerCase());
}

/**
 * Срез фильтров из query (в момент клика — из window.location.search).
 * См. ASK_AI_XCA_REQUEST.md §1.1.
 */
export function collectAskAiFiltersFromSearch(
  search: string,
): {
  project?: string;
  period?: string;
  filters?: Record<string, string>;
} {
  const params = new URLSearchParams(
    search.startsWith("?") ? search.slice(1) : search,
  );
  const filters: Record<string, string> = {};

  const projectRaw =
    (params.get("project") || params.get("projects") || "").trim();
  const project =
    projectRaw && !isAllProject(projectRaw.split("|")[0] || "")
      ? projectRaw.split("|")[0]
      : undefined;

  const periodDirect = (params.get("period") || params.get("month") || "").trim();
  const from = (params.get("date_from") || params.get("from") || "").trim();
  const to = (params.get("date_to") || params.get("to") || "").trim();
  let period: string | undefined = periodDirect || undefined;
  if (!period && (from || to)) {
    period = `${from}..${to}`;
  }

  params.forEach((value, key) => {
    const k = key.trim();
    const v = value.trim();
    if (!k || !v) return;
    if (RESERVED_QUERY_KEYS.has(k)) return;
    filters[k] = v;
  });

  return {
    project,
    period,
    filters: Object.keys(filters).length ? filters : undefined,
  };
}

export function defaultAskAiQuestion(title: string): string {
  const q = `Объясни дашборд «${title}»`;
  return q.length <= 120 ? q : `${q.slice(0, 119)}…`;
}

export function defaultAskAiCtx(screen: AskAiScreen): string {
  return `Отчёт «${screen.title}». ${screen.ctxHint}`.trim();
}
