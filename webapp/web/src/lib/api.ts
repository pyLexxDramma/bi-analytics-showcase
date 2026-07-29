export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? ""
).replace(/\/$/, "");

function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return API_BASE ? `${API_BASE}${p}` : p;
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
  params: Record<string, string | undefined> = {},
): Promise<DebitCreditPayload> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v && v !== "Все") qs.set(k, v);
  });
  const url = apiUrl(`/api/debit-credit${qs.toString() ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type BddsPayload = {
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

export async function fetchBdds(
  params: Record<string, string | undefined> = {},
): Promise<BddsPayload> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value && value !== "Все") qs.set(key, value);
  });
  const url = apiUrl(`/api/bdds${qs.toString() ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type BdrPayload = BddsPayload;

export async function fetchBdr(
  params: Record<string, string | undefined> = {},
): Promise<BdrPayload> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value && value !== "Все") qs.set(key, value);
  });
  const url = apiUrl(`/api/bdr${qs.toString() ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type ApprovedBudgetPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    files: number;
    rule?: string;
  };
  filters: {
    projects: string[];
    applied: { project: string };
  };
  kpis: {
    plan_mln: number;
    fact_mln: number;
    deviation_mln: number;
    remainder_mln: number;
  };
  tremor: {
    by_project: Array<{
      project: string;
      plan: number;
      fact: number;
      deviation: number;
    }>;
  };
  project_rows: Array<{
    project: string;
    plan: number;
    fact: number;
    deviation: number;
    remainder: number;
  }>;
};

export async function fetchApprovedBudget(
  params: Record<string, string | undefined> = {},
): Promise<ApprovedBudgetPayload> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value && value !== "Все") qs.set(key, value);
  });
  const url = apiUrl(`/api/approved-budget${qs.toString() ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
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
  params: Record<string, string | undefined> = {},
): Promise<BddsPlanFactPayload> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    if (value && value !== "Все") qs.set(key, value);
  });
  const url = apiUrl(`/api/bdds-plan-fact${qs.toString() ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type DeveloperProjectsPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    files: number;
  };
  filters: {
    projects: string[];
    applied: { project: string };
  };
  kpis: {
    projects: number;
    milestones_found: number;
    completed_pct: number;
    overdue: number;
    missing_fact: number;
  };
  tremor: {
    completion_by_project: Array<{
      project: string;
      completed: number;
      total: number;
      pct: number;
    }>;
    status_mix: Array<{ name: string; value: number }>;
  };
  matrix: {
    phases: Array<{ id: "invest" | "life"; label: string }>;
    milestones: Array<{
      slug: string;
      title: string;
      phase: "invest" | "life";
    }>;
    projects: Array<{
      project: string;
      cells: Record<
        string,
        {
          plan: string | null;
          fact: string | null;
          otkl: string;
          otkl_days: number | null;
          status: "missing" | "done" | "overdue" | "on_track";
        }
      >;
    }>;
  };
  rows: Array<{
    project: string;
    milestone: string;
    slug: string;
    plan: string | null;
    fact: string | null;
    otkl_days: number | null;
    otkl: string;
    pct_complete: number | null;
    status: "missing" | "done" | "overdue" | "on_track";
  }>;
};

export async function fetchDeveloperProjects(
  project?: string,
): Promise<DeveloperProjectsPayload> {
  const qs = project && project !== "Все" ? `?project=${encodeURIComponent(project)}` : "";
  const url = apiUrl(`/api/developer-projects${qs}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type ControlPointsPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    files: number;
    rule?: string;
  };
  filters: {
    projects: string[];
    applied: { project: string };
  };
  kpis: {
    projects: number;
    milestones_found: number;
    completed_pct: number;
    overdue: number;
    missing_fact: number;
  };
  tremor: {
    completion_by_project: Array<{
      project: string;
      completed: number;
      total: number;
      pct: number;
    }>;
    status_mix: Array<{ name: string; value: number }>;
  };
  matrix: {
    milestones: Array<{ slug: string; title: string }>;
    projects: Array<{
      project: string;
      cells: Record<
        string,
        {
          plan: string | null;
          fact: string | null;
          otkl: string;
          otkl_days: number | null;
          status: "missing" | "done" | "overdue" | "on_track";
        }
      >;
    }>;
  };
  rows: Array<{
    project: string;
    milestone: string;
    slug: string;
    plan: string | null;
    fact: string | null;
    otkl_days: number | null;
    otkl: string;
    pct_complete: number | null;
    status: "missing" | "done" | "overdue" | "on_track";
  }>;
};

export async function fetchControlPoints(
  project?: string,
): Promise<ControlPointsPayload> {
  const qs = project && project !== "Все" ? `?project=${encodeURIComponent(project)}` : "";
  const url = apiUrl(`/api/control-points${qs}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type ProjectSchedulePayload = {
  meta: {
    rows: number;
    gantt_rows: number;
    source: string;
    data_mode: string;
    files: number;
    rule?: string;
  };
  filters: {
    projects: string[];
    levels: Array<{ id: string; label: string }>;
    blocks: string[];
    applied: {
      project: string;
      level: string;
      block: string;
      hide_completed: boolean;
      only_delay: boolean;
      level_skipped?: boolean;
    };
  };
  kpis: {
    tasks: number;
    avg_pct: number;
    delayed: number;
    completed: number;
  };
  gantt: {
    range_start: string | null;
    range_end: string | null;
    capped: boolean;
    rows: Array<{
      project: string;
      task: string;
      label: string;
      pct_complete: number | null;
      baseline: { start: string | null; end: string | null };
      current: { start: string | null; end: string | null };
      dev_end_days: number | null;
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
  }>;
};

export type ProjectScheduleQuery = {
  project?: string;
  level?: string;
  block?: string;
  hide_completed?: boolean;
  only_delay?: boolean;
};

export async function fetchProjectSchedule(
  query: ProjectScheduleQuery = {},
): Promise<ProjectSchedulePayload> {
  const params = new URLSearchParams();
  if (query.project && query.project !== "Все") {
    params.set("project", query.project);
  }
  if (query.level) params.set("level", query.level);
  if (query.block && query.block !== "Все") params.set("block", query.block);
  if (query.hide_completed) params.set("hide_completed", "true");
  if (query.only_delay) params.set("only_delay", "true");
  const qs = params.toString();
  const url = apiUrl(`/api/project-schedule${qs ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}
