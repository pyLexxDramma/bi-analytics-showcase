export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? ""
).replace(/\/$/, "");

function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return API_BASE ? `${API_BASE}${p}` : p;
}

/** Тяжёлые отчёты на холодном кэше считаются минутами — но не бесконечно. */
export const DEFAULT_TIMEOUT_MS = 120_000;

export class ApiError extends Error {
  readonly status: number;
  readonly url: string;
  readonly timeout: boolean;

  constructor(
    message: string,
    { status = 0, url = "", timeout = false } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.url = url;
    this.timeout = timeout;
  }
}

export type QueryValue =
  | string
  | number
  | boolean
  | string[]
  | null
  | undefined;

export type QueryParams = Record<string, QueryValue>;

type ApiGetOptions = {
  timeoutMs?: number;
  /** «Все»/пустой список → параметр не отправляется (фильтр не применён). */
  arrayFormat?: "repeat" | "comma";
};

function appendParam(
  search: URLSearchParams,
  key: string,
  value: QueryValue,
  arrayFormat: "repeat" | "comma",
): void {
  if (value === undefined || value === null || value === "" || value === "Все") {
    return;
  }
  if (Array.isArray(value)) {
    const items = value.filter((v) => v && v !== "Все");
    if (!items.length) return;
    if (arrayFormat === "comma") {
      search.set(key, items.join(","));
    } else {
      items.forEach((item) => search.append(key, item));
    }
    return;
  }
  if (typeof value === "boolean") {
    if (value) search.set(key, "true");
    return;
  }
  search.set(key, String(value));
}

function abortSignal(timeoutMs: number): AbortSignal | undefined {
  if (typeof AbortSignal !== "undefined" && "timeout" in AbortSignal) {
    return AbortSignal.timeout(timeoutMs);
  }
  return undefined;
}

export async function apiGet<T>(
  path: string,
  params: QueryParams = {},
  { timeoutMs = DEFAULT_TIMEOUT_MS, arrayFormat = "repeat" }: ApiGetOptions = {},
): Promise<T> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    appendParam(search, key, value, arrayFormat);
  });
  const qs = search.toString();
  const url = apiUrl(`${path}${qs ? `?${qs}` : ""}`);

  let res: Response;
  try {
    res = await fetch(url, { cache: "no-store", signal: abortSignal(timeoutMs) });
  } catch (err) {
    const aborted =
      err instanceof DOMException &&
      (err.name === "TimeoutError" || err.name === "AbortError");
    if (aborted) {
      throw new ApiError(
        `Превышено время ожидания (${Math.round(timeoutMs / 1000)} с): ${path}. ` +
          "Отчёт ещё считается — обновите страницу через минуту.",
        { url, timeout: true },
      );
    }
    throw new ApiError(
      `Нет связи с API (${path}): ${err instanceof Error ? err.message : String(err)}`,
      { url },
    );
  }

  if (!res.ok) {
    const detail = await res
      .json()
      .then((body) => (typeof body?.detail === "string" ? body.detail : ""))
      .catch(() => "");
    throw new ApiError(detail || `API ${res.status}: ${url}`, {
      status: res.status,
      url,
    });
  }
  return (await res.json()) as T;
}

export type DebitCreditPayload = {
  meta: {
    rows: number;
    generated_at?: string;
    source?: string;
    data_mode?: string;
    pilot?: string;
  };
  filters: {
    projects: string[];
    contractors: string[];
    date_min: string | null;
    date_max: string | null;
    applied?: Record<string, string | null | undefined>;
  };
  kpis: {
    contracts?: number;
    contract_sum_mln?: number;
    advance_mln?: number;
    ks2_mln?: number;
    fulfilled_mln?: number;
    balance_mln?: number;
    deviation_mln?: number;
    advance_pct?: number;
  };
  chart: {
    categories: string[];
    unit?: string;
    series: Array<{
      key: string;
      name: string;
      color: string;
      values: number[];
    }>;
  };
  tremor?: {
    contract_vs_advance: Array<Record<string, string | number>>;
    advance_by_project: Array<{ project: string; advance: number }>;
    risk_note?: string;
  };
  rows: Array<{
    project: string;
    contractor: string;
    contract: string;
    contract_date: string | null;
    contract_sum: number;
    advance: number;
    ks2: number;
    fulfilled: number;
    paid: number;
    balance: number;
    deviation: number;
  }>;
};

export async function fetchDebitCredit(
  params: QueryParams = {},
): Promise<DebitCreditPayload> {
  return apiGet<DebitCreditPayload>("/api/debit-credit", params);
}

/** Упрощённый финансовый payload (`services/finance_period.py`) — БДР до фазы 2.3. */
export type FinancePeriodPayload = {
  meta: { rows: number; source: string; data_mode: string; files: number };
  filters: {
    projects: string[];
    date_min: string | null;
    date_max: string | null;
    applied: {
      project: string;
      date_from: string | null;
      date_to: string | null;
      view: "monthly" | "cumulative";
    };
  };
  kpis: { plan_mln: number; fact_mln: number; deviation_mln: number };
  tremor: {
    by_period: Array<{ period: string; plan: number; fact: number; deviation: number }>;
    by_project: Array<{ project: string; plan: number; fact: number; deviation: number }>;
  };
  period_rows: Array<{ period: string; plan: number; fact: number; deviation: number }>;
  project_rows: Array<{ project: string; plan: number; fact: number; deviation: number }>;
};

export type BddsGroup = "month" | "quarter" | "year";
export type BddsView = "monthly" | "cumulative";

export type BddsTableRow = {
  kind: "project" | "data";
  project: string;
  period: string;
  plan: number;
  fact: number;
  deviation: number;
};

/** #2 БДДС — паритет с `dashboard_budget_by_period` [main]; суммы в рублях. */
export type BddsPayload = {
  meta: {
    source: string;
    data_mode: string;
    parity?: string;
    mode: string;
    error: string | null;
    version_id: number | null;
    rows: number;
    periods?: number;
    db?: { active_version_id?: number | null; exists?: boolean };
  };
  filters: {
    projects: string[];
    date_min: string | null;
    date_max: string | null;
    groups: Array<{ id: BddsGroup; label: string }>;
    views: Array<{ id: BddsView; label: string }>;
    mode?: string;
    empty_means_all?: boolean;
    applied: {
      projects: string[];
      date_from: string | null;
      date_to: string | null;
      group: BddsGroup;
      view: BddsView;
      hide_zero: boolean;
      show_deviation: boolean;
    };
  };
  kpis: {
    plan_mln: number;
    fact_mln: number;
    deviation_mln: number;
    periods: number;
  };
  tremor: {
    by_period: Array<{
      period: string;
      plan: number;
      fact: number;
      deviation: number;
    }>;
    by_project: Array<{
      project: string;
      plan: number;
      fact: number;
      deviation: number;
    }>;
  };
  period_rows: BddsTableRow[];
  project_rows: Array<{
    project: string;
    plan: number;
    fact: number;
    deviation: number;
  }>;
  hints: string[];
  totals: { plan: number; fact: number; deviation: number };
  labels: {
    period: string;
    total_period: string;
    date_suffix: string;
    chart_caption: string;
    period_table_title: string;
    project_table_title: string;
  };
};

export type BddsQuery = {
  projects?: string[];
  date_from?: string;
  date_to?: string;
  group?: BddsGroup;
  view?: BddsView;
  hide_zero?: boolean;
  show_deviation?: boolean;
};

export async function fetchBdds(query: BddsQuery = {}): Promise<BddsPayload> {
  // hide_zero/show_deviation отправляем всегда: false здесь — осознанный выбор, не «фильтр не задан»
  const params: QueryParams = {
    projects: query.projects,
    date_from: query.date_from,
    date_to: query.date_to,
    group: query.group,
    view: query.view,
  };
  if (query.hide_zero !== undefined) params.hide_zero = String(query.hide_zero);
  if (query.show_deviation !== undefined) {
    params.show_deviation = String(query.show_deviation);
  }
  return apiGet<BddsPayload>("/api/bdds", params);
}

export type BdrPayload = BddsPayload;

export async function fetchBdr(query: BddsQuery = {}): Promise<BdrPayload> {
  const params: QueryParams = {
    projects: query.projects,
    date_from: query.date_from,
    date_to: query.date_to,
    group: query.group,
    view: query.view,
  };
  if (query.hide_zero !== undefined) params.hide_zero = String(query.hide_zero);
  if (query.show_deviation !== undefined) {
    params.show_deviation = String(query.show_deviation);
  }
  return apiGet<BdrPayload>("/api/bdr", params);
}

export type ApprovedBudgetPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    parity: string;
    mode: string;
    error: string | null;
    version_id: number | null;
    rows_1c: number;
    db?: { active_version_id?: number | null; exists?: boolean };
  };
  filters: {
    projects: string[];
    fiz: string[];
    mode: string;
    empty_means_all: boolean;
    applied: {
      projects: string[];
      fiz: string;
      hide_zero: boolean;
      show_deviation: boolean;
    };
  };
  kpis: {
    plan_mln: number;
    fact_mln: number;
    deviation_mln: number;
    remainder_mln: number;
  };
  tremor: {
    by_period: Array<{
      period: string;
      plan: number;
      fact: number;
      deviation: number;
    }>;
    by_project: Array<{
      project: string;
      plan: number;
      fact: number;
      deviation: number;
    }>;
  };
  gauge: {
    plan: number;
    fact: number;
    deviation: number;
    plan_mlrd: number;
    fact_mlrd: number;
    deviation_mlrd: number;
    fact_pct: number;
    deviation_pct: number;
    axis_max_mlrd: number;
  };
  period_rows: Array<{
    period: string;
    plan: number;
    fact: number;
    deviation: number;
  }>;
  project_rows: Array<{
    project: string;
    plan: number;
    fact: number;
    deviation: number;
    remainder: number;
    completion_pct: number | null;
    contract_coverage_pct: number | null;
  }>;
  totals: { plan: number; fact: number; deviation: number; remainder: number };
  hints: string[];
  labels: {
    period_table_title: string;
    project_table_title: string;
    total_period: string;
  };
};

export type ApprovedBudgetQuery = {
  projects?: string[];
  fiz?: string;
  hide_zero?: boolean;
  show_deviation?: boolean;
};

export async function fetchApprovedBudget(
  query: ApprovedBudgetQuery = {},
): Promise<ApprovedBudgetPayload> {
  const params: QueryParams = { projects: query.projects, fiz: query.fiz };
  if (query.hide_zero !== undefined) params.hide_zero = String(query.hide_zero);
  if (query.show_deviation !== undefined) params.show_deviation = String(query.show_deviation);
  return apiGet<ApprovedBudgetPayload>("/api/approved-budget", params);
}

export type BddsPlanFactPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    files: number;
    rule?: string;
  };
  filters: {
    projects: string[];
    date_min: string | null;
    date_max: string | null;
    applied: {
      project: string;
      date_from: string | null;
      date_to: string | null;
      view: "monthly" | "cumulative";
    };
  };
  kpis: {
    plan_mln: number;
    fact_mln: number;
    revised_mln: number;
    deviation_mln: number;
  };
  tremor: {
    by_period: Array<{
      period: string;
      plan: number;
      fact: number;
      revised: number;
    }>;
    by_project: Array<{
      project: string;
      plan: number;
      fact: number;
      revised: number;
    }>;
  };
  period_rows: Array<{
    period: string;
    plan: number;
    fact: number;
    revised: number;
    deviation: number;
  }>;
  project_rows: Array<{
    project: string;
    plan: number;
    fact: number;
    revised: number;
    deviation: number;
  }>;
};

export async function fetchBddsPlanFact(
  params: QueryParams = {},
): Promise<BddsPlanFactPayload> {
  return apiGet<BddsPlanFactPayload>("/api/bdds-plan-fact", params);
}

export type DeveloperProjectsCell = {
  plan: string | null;
  fact: string | null;
  otkl: string | null;
  pct_complete_100?: boolean;
  warn?: boolean;
  otkl_fact_lt_plan?: boolean;
  subcolumn_labels?: { plan?: string; fact?: string; otkl?: string } | null;
};

export type DeveloperProjectsPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    parity?: string;
    version_id?: number | null;
    columns?: number;
    cells?: number;
    error?: string | null;
    files?: number;
    db?: { active_version_id?: number | null; exists?: boolean };
  };
  filters: {
    projects: string[];
    applied: { projects: string[]; project?: string };
    mode?: string;
    empty_means_all?: boolean;
  };
  hints?: string[];
  legend?: { pct100?: string; pos?: string; neg?: string };
  kpis?: {
    projects: number;
    milestones_found: number;
    completed_pct: number;
    overdue: number;
    missing_fact: number;
  };
  tremor?: {
    completion_by_project: Array<{
      project: string;
      completed: number;
      total: number;
      pct: number;
    }>;
    status_mix: Array<{ name: string; value: number }>;
  };
  matrix: {
    phases: Array<{ id: "invest" | "life" | string; label: string }>;
    columns: Array<{
      key: string;
      label: string;
      phase: "invest" | "life" | string;
      group?: string;
      subcolumn_labels?: { plan?: string; fact?: string; otkl?: string } | null;
    }>;
    /** @deprecated old simplified payload */
    milestones?: Array<{
      slug: string;
      title: string;
      phase: "invest" | "life";
    }>;
    projects: Array<{
      project: string;
      cells: Record<string, DeveloperProjectsCell>;
    }>;
  };
};

export async function fetchDeveloperProjects(
  projects: string[] = [],
): Promise<DeveloperProjectsPayload> {
  return apiGet<DeveloperProjectsPayload>("/api/developer-projects", {
    projects,
  });
}

export type ControlPointsPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    parity: string;
    version_id: number | null;
    cells?: number;
    error: string | null;
    db: Record<string, unknown>;
  };
  filters: {
    projects: string[];
    applied: { project: string };
  };
  groups: Array<{
    id: string;
    milestones: Array<{ slug: string; title: string }>;
  }>;
  projects: Array<{
    project: string;
    cells: Record<
      string,
      {
        plan: string;
        fact: string;
        otkl: string;
        otkl_days: number | null;
        status: "ok" | "bad";
        pct_complete_100: boolean;
      }
    >;
  }>;
};

export async function fetchControlPoints(
  project?: string,
): Promise<ControlPointsPayload> {
  return apiGet<ControlPointsPayload>("/api/control-points", { project });
}

export type ProjectSchedulePayload = {
  meta: {
    rows: number;
    gantt_rows: number;
    gantt_cap: number;
    source: string;
    data_mode: string;
    version_id: number | null;
    error: string | null;
    banner: string | null;
    rule?: string;
  };
  filters: {
    projects: string[];
    levels: Array<{ id: string; label: string }>;
    blocks: string[];
    buildings: string[];
    applied: {
      project: string;
      level: string;
      block: string;
      building: string;
      show_reasons: boolean;
      show_lots: boolean;
      label_pct: boolean;
      hide_completed: boolean;
      only_delay: boolean;
      level_skipped?: boolean;
      multi_project?: boolean;
    };
  };
  gantt: {
    range_start: string | null;
    range_end: string | null;
    capped: boolean;
    plan_color: string;
    fact_color: string;
    label_pct: boolean;
    rows: Array<{
      project: string | null;
      task: string;
      label: string;
      pct_complete: number | null;
      baseline: {
        start: string | null;
        end: string | null;
        start_label?: string;
        end_label?: string;
      };
      current: {
        start: string | null;
        end: string | null;
        start_label?: string;
        end_label?: string;
      };
    }>;
  };
  rows: Array<{
    project: string;
    task_id: string | null;
    level: number | null;
    task: string;
    pct_complete: number | null;
    plan_start: string | null;
    base_start: string | null;
    dev_start: string;
    dev_start_days: number | null;
    plan_end: string | null;
    base_end: string | null;
    dev_end: string;
    dev_end_days: number | null;
    reason?: string;
    notes?: string;
  }>;
  columns: string[];
};

export type ProjectScheduleQuery = {
  project?: string;
  level?: string;
  block?: string;
  building?: string;
  hide_completed?: boolean;
  only_delay?: boolean;
  show_reasons?: boolean;
  show_lots?: boolean;
  label_pct?: boolean;
};

export async function fetchProjectSchedule(
  query: ProjectScheduleQuery = {},
): Promise<ProjectSchedulePayload> {
  return apiGet<ProjectSchedulePayload>("/api/project-schedule", { ...query });
}

export type DeviationReasonsPayload = {
  meta: {
    rows: number;
    chart_rows?: number;
    source: string;
    data_mode: string;
    parity?: string;
    version_id?: number | null;
    rule?: string;
    error?: string | null;
  };
  filters: {
    projects: string[];
    blocks: string[];
    buildings: string[];
    reasons: string[];
    period: { min: string | null; max: string | null };
    applied: {
      project: string;
      block: string;
      building: string;
      reason: string;
      date_from: string | null;
      date_to: string | null;
      top5: boolean;
    };
  };
  kpis: {
    main_reason: string;
    main_reason_share_pct: number;
    main_reason_count: number;
    tasks: number;
  };
  tremor: {
    by_reason: Array<{
      reason: string;
      reason_full: string;
      count: number;
      pct: number;
      label: string;
    }>;
    reason_mix: Array<{ name: string; value: number; color?: string }>;
    dynamics: {
      by_project_charts: Array<{
        project: string;
        categories: string[];
        colors: Record<string, string>;
        rows: Array<Record<string, string | number>>;
      }>;
      project_month_rows: Array<{
        project: string;
        period: string;
        period_key: string;
        count: number;
      }>;
      project_month_total: number;
      by_project_stack: Array<Record<string, string | number>>;
      stack_projects: string[];
      stack_colors: Record<string, string>;
      summary_rows: Array<{
        project: string;
        reason: string;
        count: number;
        days: number;
      }>;
      summary_totals: { count: number; days: number };
      period_label: string;
    };
  };
  rows: Array<{
    task_id: string | null;
    project: string;
    block: string | null;
    task: string | null;
    building: string | null;
    base_end: string | null;
    plan_end: string | null;
    end_diff_days: number | null;
    reason: string;
    bucket: string;
    bucket_color: string;
    notes: string | null;
  }>;
  columns?: string[];
};

export type DeviationReasonsQuery = {
  project?: string;
  block?: string;
  building?: string;
  reason?: string;
  date_from?: string;
  date_to?: string;
  top5?: boolean;
};

export async function fetchDeviationReasons(
  query: DeviationReasonsQuery = {},
): Promise<DeviationReasonsPayload> {
  const params: Record<string, string | undefined> = {
    project: query.project,
    block: query.block,
    building: query.building,
    reason: query.reason,
    date_from: query.date_from,
    date_to: query.date_to,
  };
  if (query.top5 !== undefined) {
    params.top5 = String(query.top5);
  }
  return apiGet<DeviationReasonsPayload>("/api/deviation-reasons", params);
}

export type BaselineDeviationPayload = {
  meta: {
    rows: number;
    chart_rows: number;
    source: string;
    data_mode: string;
    parity?: string;
    version_id?: number | null;
    rule?: string;
    error?: string | null;
    mode?: string;
    db?: Record<string, unknown>;
    files?: number;
  };
  filters: {
    projects: string[];
    blocks: string[];
    buildings: string[];
    levels: Array<{ id: string; label: string }>;
    reasons: string[];
    label_modes: Array<{ id: string; label: string }>;
    has_lot: boolean;
    applied: {
      project: string;
      block: string;
      building: string;
      level: string;
      reason: string;
      show_reasons: boolean;
      hide_completed: boolean;
      only_covenants: boolean;
      only_neg_end: boolean;
      show_dur: boolean;
      label_mode: string;
      level_skipped?: boolean;
    };
  };
  kpis: {
    metric_task: string;
    max_abs_dev_days: number;
    plates: Array<{
      project: string | null;
      plan_end: string | null;
      fact_end: string | null;
      dev_days: number | null;
      dev: string | null;
      max_abs_dev_days: number;
      task?: string | null;
    }>;
  };
  chart: {
    range_start: string | null;
    range_end: string | null;
    capped: boolean;
    kind: string;
    caption?: string;
    base_color?: string;
    plan_color?: string;
    rows: Array<{
      project: string | null;
      task: string;
      label: string;
      base_end: string | null;
      base_end_label?: string | null;
      plan_end: string | null;
      plan_end_label?: string | null;
      dev_end_days: number | null;
    }>;
  };
  columns: string[];
  rows: Array<{
    project: string;
    task_id: string | null;
    task: string;
    block: string | null;
    building: string | null;
    base_start: string | null;
    plan_start: string | null;
    dev_start?: string | null;
    dev_start_days: number | null;
    base_end: string | null;
    plan_end: string | null;
    dev_end?: string | null;
    dev_end_days: number | null;
    base_dur_days: number | null;
    plan_dur_days: number | null;
    dev_dur?: string | null;
    dev_dur_days: number | null;
    reason?: string | null;
    notes?: string | null;
    level?: number | null;
  }>;
};

export type BaselineDeviationQuery = {
  project?: string;
  block?: string;
  building?: string;
  level?: string;
  reason?: string;
  show_reasons?: boolean;
  hide_completed?: boolean;
  only_covenants?: boolean;
  only_neg_end?: boolean;
  show_dur?: boolean;
  label_mode?: string;
};

export async function fetchBaselineDeviation(
  query: BaselineDeviationQuery = {},
): Promise<BaselineDeviationPayload> {
  const params: Record<string, string | undefined> = {
    project: query.project,
    block: query.block,
    building: query.building,
    level: query.level,
    reason: query.reason,
    label_mode: query.label_mode,
  };
  if (query.show_reasons !== undefined) params.show_reasons = String(query.show_reasons);
  if (query.hide_completed !== undefined) {
    params.hide_completed = String(query.hide_completed);
  }
  if (query.only_covenants !== undefined) {
    params.only_covenants = String(query.only_covenants);
  }
  if (query.only_neg_end !== undefined) params.only_neg_end = String(query.only_neg_end);
  if (query.show_dur !== undefined) params.show_dur = String(query.show_dur);
  return apiGet<BaselineDeviationPayload>("/api/baseline-deviation", params);
}

export type ProjectDocumentationPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    files: number;
    doc_kind: string;
    title: string;
    rule?: string;
    parity?: string;
    version_id?: number | null;
    error?: string | null;
  };
  filters: {
    projects: string[];
    sections: string[];
    periods: string[];
    granularities: Array<{ id: string; label: string }>;
    view_modes: Array<{ id: string; label: string }>;
    status_legend: Array<{ id: string; label: string; tone: string }>;
    applied: {
      project: string;
      section: string;
      period: string;
      granularity: string;
      report_date: string;
      view_mode: string;
      tab: string;
    };
  };
  kpis: {
    plan_total: number;
    plan_to_date: number;
    fact_to_date: number;
    deviation_to_date: number;
    current_productivity: number;
    required_productivity: number;
    productivity_label?: string;
    required_label?: string;
  };
  tremor: {
    status_mix: Array<{ name: string; value: number; color?: string }>;
    dynamics: Array<{
      period: string;
      period_label: string;
      plan_bp: number;
      forecast: number;
      fact?: number;
    }>;
    monthly: Array<{
      month: string;
      month_label: string;
      plan: number;
      fact: number;
    }>;
  };
  rows: Array<{
    n?: number;
    project: string;
    section: string;
    task: string;
    base_end: string | null;
    plan_end: string | null;
    dev_end: string;
    dev_end_days: number | null;
    pct_complete: number | null;
    status: string;
    ahead?: boolean;
  }>;
  delay: {
    gantt: {
      rows: Array<{
        label: string;
        start: string;
        base_finish: string;
        finish: string | null;
        delay_end: string | null;
        base_dur: number;
        fact_dur: number;
        delay_dur: number;
        base_label: string;
        finish_label: string;
      }>;
      range_start: string | null;
      range_end: string | null;
      legend?: Array<{ id: string; label: string; color: string }>;
    };
    cards: Array<{
      project: string;
      overdue: number;
      label: string;
      tone: string;
    }>;
    detail_rows: Array<{
      project: string;
      work_name: string;
      section: string;
      status: string;
      start: string;
      base_start: string;
      finish: string;
      base_finish: string;
      dev_start: string;
      dev_start_days: number | null;
      dev_end: string;
      dev_end_days: number | null;
    }>;
    detail_columns: string[];
    summary_rows: Array<{
      project: string;
      plan: number;
      fact: number;
      overdue: number;
      overdue_label: string;
    }>;
    summary_columns: string[];
  };
};

export type ProjectDocumentationQuery = {
  project?: string;
  section?: string;
  period?: string;
  granularity?: string;
  report_date?: string;
  view_mode?: string;
  tab?: string;
};

export async function fetchProjectDocumentation(
  query: ProjectDocumentationQuery = {},
): Promise<ProjectDocumentationPayload> {
  return apiGet<ProjectDocumentationPayload>("/api/project-documentation", {
    ...query,
  });
}

export type WorkingDocumentationPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    files: number;
    doc_kind: string;
    title: string;
    rule?: string;
    parity?: string;
    version_id?: number | null;
    error?: string | null;
  };
  filters: {
    projects: string[];
    sections: string[];
    statuses: string[];
    period_modes: string[];
    metric_modes: string[];
    view_modes: Array<{ id: string; label: string }>;
    plan_date_min?: string | null;
    plan_date_max?: string | null;
    applied: {
      projects: string[];
      sections: string[];
      statuses: string[];
      period_mode: string;
      date_from: string | null;
      date_to: string | null;
      metric_mode: string;
      show_forecast: boolean;
      view_mode: string;
      tab: string;
    };
  };
  kpis: {
    total_sections: number;
    overdue: number;
    avg_delay: number;
    plan_total: number;
    plan_to_date: number;
    fact_to_date: number;
    deviation_to_date: number;
    planned_weekly: number | null;
    fact_weekly: number | null;
    nec_weekly: number | null;
  };
  tremor: {
    status_mix: Array<{ name: string; value: number; color?: string }>;
    dynamics: Array<{
      period: string;
      period_label: string;
      plan: number;
      fact: number;
    }>;
    monthly: Array<{
      month: string;
      month_label: string;
      plan: number;
      fact: number;
      fact_inc?: number;
    }>;
  };
  detail_rows: Array<Record<string, string | number | null>>;
  detail_columns: string[];
  delay: {
    gantt: {
      rows: Array<{
        label: string;
        start: string | null;
        base_finish: string | null;
        finish: string | null;
        delay_end: string | null;
        base_dur: number;
        fact_dur: number;
        delay_dur: number;
        base_label: string;
        fact_label: string;
        delay_label: string;
      }>;
      range_start: string | null;
      range_end: string | null;
    };
    detail_rows: Array<Record<string, string | number | null>>;
    detail_columns: string[];
  };
};

export type WorkingDocumentationQuery = {
  project?: string;
  section?: string;
  status?: string;
  period_mode?: string;
  date_from?: string;
  date_to?: string;
  metric_mode?: string;
  show_forecast?: boolean;
  view_mode?: string;
  tab?: string;
};

export async function fetchWorkingDocumentation(
  query: WorkingDocumentationQuery = {},
): Promise<WorkingDocumentationPayload> {
  return apiGet<WorkingDocumentationPayload>("/api/working-documentation", {
    ...query,
  });
}

export type GdrsPayload = {
  meta: {
    data_mode: string;
    resource_kind: "people" | "equipment";
    unit: string;
    unit_gen?: string;
    period_label: string;
    rows: number;
    resursi_files: number;
    version_id?: number | null;
    source?: string;
    parity?: string;
    warning: string | null;
    error?: string | null;
    show_week_columns?: boolean;
    week_labels?: string[];
    dyn_title?: string;
    pie_title?: string;
    matrix_title?: string;
  };
  filters: {
    projects: string[];
    contractors: string[];
    months: string[];
    default_months: string[];
    agg_options: string[];
    dyn_agg_options?: string[];
    selected: {
      projects: string[];
      contractors: string[];
      months: string[];
      plan_agg: string;
      skud_agg: string;
      dyn_agg?: string;
      only_with_plan?: boolean;
    };
  };
  kpis: {
    plan: number;
    fact: number;
    deviation: number;
    delta_pct: number | null;
  };
  tremor: {
    by_project: Array<{
      name: string;
      plan: number;
      fact: number;
      deviation: number;
    }>;
    by_contractor: Array<{
      name: string;
      plan: number;
      fact: number;
      deviation: number;
    }>;
    pie?: Array<{ name: string; value: number }>;
    dynamics?: Array<{
      period: string;
      plan: number;
      fact: number;
      name?: string;
    }>;
  };
  project_rows: Array<{
    project: string;
    plan: number;
    fact: number;
    deviation: number;
    delta_pct: number | null;
  }>;
  contractor_rows: Array<{
    contractor: string;
    plan: number;
    fact: number;
    deviation: number;
    share_pct: number;
  }>;
  pie_rows?: Array<{ name: string; value: number }>;
  matrix_rows: Array<{
    kind: string;
    label: string;
    vid_raboty: string;
    plan: number;
    skud: number;
    deviation: number;
    delta_pct: number | null;
    p1?: number;
    p2?: number;
    p3?: number;
    p4?: number;
    p5?: number;
    p6?: number;
    w1?: number;
    w2?: number;
    w3?: number;
    w4?: number;
    w5?: number;
    w6?: number;
  }>;
  matrix_meta?: {
    show_week_columns: boolean;
    week_labels: string[];
    week_plan_keys: string[];
    week_skud_keys: string[];
  };
  dynamics_rows?: Array<{
    period: string;
    plan: number;
    fact: number;
    deviation: number;
    delta_pct: number | null;
  }>;
};

export type GdrsQuery = {
  projects?: string[];
  contractors?: string[];
  months?: string[];
  plan_agg?: string;
  skud_agg?: string;
  dyn_agg?: string;
  only_with_plan?: boolean;
};

/** ГДРС тяжелее прочих экранов — отдельный, больший таймаут. */
const GDRS_TIMEOUT_MS = 300_000;

export async function fetchGdrsPeople(
  query: GdrsQuery = {},
): Promise<GdrsPayload> {
  return apiGet<GdrsPayload>("/api/gdrs-people", { ...query }, {
    arrayFormat: "comma",
    timeoutMs: GDRS_TIMEOUT_MS,
  });
}

export async function fetchGdrsEquipment(
  query: GdrsQuery = {},
): Promise<GdrsPayload> {
  return apiGet<GdrsPayload>("/api/gdrs-equipment", { ...query }, {
    arrayFormat: "comma",
    timeoutMs: GDRS_TIMEOUT_MS,
  });
}

export type PrescriptionsPayload = {
  meta: {
    rows: number;
    data_mode: string;
    source: string | null;
    task_source?: string | null;
    warning: string | null;
    generated_at?: string;
  };
  filters: {
    projects: string[];
    contractors: string[];
    date_min: string | null;
    date_max: string | null;
    applied: {
      project?: string;
      contractor?: string;
      contract_q?: string;
      date_from?: string | null;
      date_to?: string | null;
      hide_resolved?: boolean;
    };
  };
  kpis: {
    total: number;
    resolved: number;
    unresolved: number;
    non_overdue: number;
    overdue_unresolved: number;
    critical: number;
    stop_work: number;
  };
  tremor: {
    by_contractor: Array<{
      contractor: string;
      total: number;
      overdue: number;
    }>;
    by_status: Array<{
      status: string;
      count: number;
      share_pct: number;
    }>;
  };
  rows: Array<{
    status: string;
    contractor: string;
    project: string;
    contract_no: string;
    doc_number: string;
    pred_number: string;
    name: string;
    issue_date: string | null;
    issue_block: string;
    due_date: string | null;
    completion_date: string | null;
    overdue_days: number;
    critical: boolean;
    stop_work: boolean;
  }>;
};

export async function fetchPrescriptions(
  params: QueryParams = {},
): Promise<PrescriptionsPayload> {
  return apiGet<PrescriptionsPayload>("/api/prescriptions", params);
}

export type ExecutiveDocsPayload = {
  meta: {
    rows: number;
    table_rows?: number;
    data_mode: string;
    source: string | null;
    task_source?: string | null;
    warning: string | null;
    generated_at?: string;
  };
  filters: {
    projects: string[];
    contractors: string[];
    date_min: string | null;
    date_max: string | null;
    granularities: Array<{ id: string; label: string }>;
    applied: {
      project?: string;
      contractor?: string;
      date_from?: string | null;
      date_to?: string | null;
      granularity?: string;
      hide_overdue_if_signed?: boolean;
    };
  };
  kpis: {
    total_docs: number;
    declined: number;
    on_agree: number;
    signed: number;
    on_rework: number;
    overdue_total: number;
    contractor_overdue: {
      count: number;
      bucket_0_7: number;
      bucket_8_30: number;
      bucket_30_plus: number;
    };
    customer_overdue: {
      count: number;
      bucket_0_7: number;
      bucket_8_30: number;
      bucket_30_plus: number;
    };
  };
  tremor: {
    by_status: Array<{ status: string; count: number; share_pct: number }>;
    by_object: Array<{ object: string; count: number }>;
    overdue_contractor: Array<{ contractor: string; count: number }>;
    overdue_customer: Array<{ contractor: string; count: number }>;
    dynamics: Array<{ period: string; new_docs: number }>;
  };
  rows: Array<{
    contractor: string;
    project: string;
    doc_number: string;
    kind: string;
    plan_date: string | null;
    fact_date: string | null;
    submit_late_days: number | null;
    transfer_date: string | null;
    agree_date: string | null;
    agree_late_days: number | null;
    status: string;
    creation_date: string | null;
  }>;
};

export async function fetchExecutiveDocs(
  params: QueryParams = {},
): Promise<ExecutiveDocsPayload> {
  return apiGet<ExecutiveDocsPayload>("/api/executive-docs", params);
}

export type AdminDbStatus = {
  web_db_path?: string;
  exists?: boolean;
  size_bytes?: number;
  mtime?: number | null;
  active_version_id?: number | null;
  error?: string;
};

export type AdminDataStatus = {
  data_mode: string;
  web_dir: string;
  files: number;
  latest_mtime: number | null;
  ftp_configured: boolean;
  db?: AdminDbStatus;
};

export async function fetchAdminDataStatus(): Promise<AdminDataStatus> {
  return apiGet<AdminDataStatus>("/api/admin/data-status", {}, {
    timeoutMs: 30_000,
  });
}

export type AdminSyncResult = {
  ok: boolean;
  async?: boolean;
  job_id?: string;
  downloaded?: number;
  skipped_same_size?: number;
  files?: number;
  errors?: string[];
  detail?: string;
  [key: string]: unknown;
};

export type AdminJob = {
  id: string;
  kind: string;
  status: string;
  created_at?: number;
  started_at?: number | null;
  finished_at?: number | null;
  result?: unknown;
  error?: string | null;
};

async function postAdminAction(
  path: string,
  token: string,
): Promise<AdminSyncResult> {
  const url = apiUrl(path);
  const res = await fetch(url, {
    method: "POST",
    cache: "no-store",
    headers: {
      "X-Admin-Token": token,
    },
    signal: abortSignal(60_000),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `API ${res.status}: ${url}`;
    throw new ApiError(detail, { status: res.status, url });
  }
  return body as AdminSyncResult;
}

export async function postAdminSync(
  token: string,
  force = false,
): Promise<AdminSyncResult> {
  const qs = force ? "?force=true" : "";
  return postAdminAction(`/api/admin/sync${qs}`, token);
}

/** web/ → web_data.db (без FTP; synthetic и ftp). */
export async function postAdminIngest(token: string): Promise<AdminSyncResult> {
  return postAdminAction("/api/admin/ingest", token);
}

export type DataVersion = {
  id: number;
  created_at: string;
  label?: string | null;
  status?: string | null;
  files_count: number;
  rows_count: number;
  is_active: boolean;
};

export type DataVersionsPayload = {
  items: DataVersion[];
  active_version_id: number | null;
  error?: string | null;
};

export async function fetchDataVersions(): Promise<DataVersionsPayload> {
  return apiGet<DataVersionsPayload>("/api/versions", {}, { timeoutMs: 30_000 });
}

export async function postActivateVersion(
  token: string,
  versionId: number,
): Promise<AdminSyncResult> {
  return postAdminAction(`/api/admin/versions/${versionId}/activate`, token);
}

export async function fetchAdminJob(
  token: string,
  jobId: string,
): Promise<AdminJob> {
  const url = apiUrl(`/api/admin/jobs/${encodeURIComponent(jobId)}`);
  const res = await fetch(url, {
    cache: "no-store",
    headers: { "X-Admin-Token": token },
    signal: abortSignal(30_000),
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `API ${res.status}: ${url}`;
    throw new ApiError(detail, { status: res.status, url });
  }
  return body as AdminJob;
}

export type HealthPayload = {
  ok: boolean;
  version?: string;
  data_mode?: string;
  files?: number;
  web_db_exists?: boolean;
  active_version_id?: number | null;
};

export async function fetchHealth(): Promise<HealthPayload> {
  return apiGet<HealthPayload>("/api/health", {}, { timeoutMs: 15_000 });
}
