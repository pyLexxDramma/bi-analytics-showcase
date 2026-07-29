/** Russian labels for Tremor chart series (legend = category keys). */

export const CHART_RU = {
  plan: "План",
  fact: "Факт",
  deviation: "Отклонение",
  revised: "Уточнённый план",
  pctComplete: "Выполнено, %",
  contractSum: "Стоимость договора",
  advance: "Аванс выдан",
  reasonCount: "Количество",
  baseEnd: "Базовое окончание",
  planEnd: "Окончание",
} as const;

export const PLAN_FACT_DEVIATION_CATEGORIES = [
  CHART_RU.plan,
  CHART_RU.fact,
  CHART_RU.deviation,
] as const;

export const PLAN_FACT_REVISED_CATEGORIES = [
  CHART_RU.plan,
  CHART_RU.fact,
  CHART_RU.revised,
] as const;

type PlanFactRow = {
  plan: number;
  fact: number;
  deviation: number;
} & Record<string, string | number>;

/** Map API keys plan/fact/deviation → Russian keys for Tremor legends. */
export function withRuPlanFactDeviation<T extends PlanFactRow>(rows: T[]) {
  return rows.map((row) => ({
    ...row,
    [CHART_RU.plan]: row.plan,
    [CHART_RU.fact]: row.fact,
    [CHART_RU.deviation]: row.deviation,
  }));
}

type PlanFactRevisedRow = {
  plan: number;
  fact: number;
  revised: number;
} & Record<string, string | number>;

export function withRuPlanFactRevised<T extends PlanFactRevisedRow>(rows: T[]) {
  return rows.map((row) => ({
    ...row,
    [CHART_RU.plan]: row.plan,
    [CHART_RU.fact]: row.fact,
    [CHART_RU.revised]: row.revised,
  }));
}

export function withRuPctComplete<
  T extends { pct: number } & Record<string, string | number>,
>(rows: T[]) {
  return rows.map((row) => ({
    ...row,
    [CHART_RU.pctComplete]: row.pct,
  }));
}

export function withRuReasonCount<
  T extends { count: number } & Record<string, string | number>,
>(rows: T[]) {
  return rows.map((row) => ({
    ...row,
    [CHART_RU.reasonCount]: row.count,
  }));
}
