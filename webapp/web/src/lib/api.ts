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

export type DeviationReasonsPayload = {
  meta: {
    rows: number;
    source: string;
    data_mode: string;
    files: number;
    rule?: string;
  };
  filters: {
    projects: string[];
    blocks: string[];
    reasons: string[];
    period: { min: string | null; max: string | null };
    applied: {
      project: string;
      block: string;
      reason: string;
      date_from: string | null;
      date_to: string | null;
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
    }>;
    reason_mix: Array<{ name: string; value: number }>;
  };
  rows: Array<{
    task_id: string | null;
    project: string;
    block: string | null;
    building: string | null;
    base_end: string | null;
    plan_end: string | null;
    end_diff_days: number;
    reason: string;
    bucket: string;
    bucket_color: string;
    notes: string | null;
  }>;
};

export type DeviationReasonsQuery = {
  project?: string;
  block?: string;
  reason?: string;
  date_from?: string;
  date_to?: string;
};

export async function fetchDeviationReasons(
  query: DeviationReasonsQuery = {},
): Promise<DeviationReasonsPayload> {
  const params = new URLSearchParams();
  if (query.project && query.project !== "Все") {
    params.set("project", query.project);
  }
  if (query.block && query.block !== "Все") {
    params.set("block", query.block);
  }
  if (query.reason && query.reason !== "Все") {
    params.set("reason", query.reason);
  }
  if (query.date_from) params.set("date_from", query.date_from);
  if (query.date_to) params.set("date_to", query.date_to);
  const qs = params.toString();
  const url = apiUrl(`/api/deviation-reasons${qs ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type BaselineDeviationPayload = {
  meta: {
    rows: number;
    chart_rows: number;
    source: string;
    data_mode: string;
    files: number;
    rule?: string;
  };
  filters: {
    projects: string[];
    blocks: string[];
    buildings: string[];
    levels: Array<{ id: string; label: string }>;
    applied: {
      project: string;
      block: string;
      building: string;
      level: string;
      level_skipped?: boolean;
    };
  };
  kpis: {
    max_abs_dev_days: number;
    zos_rows: Array<{
      project: string;
      task: string;
      base_end: string | null;
      plan_end: string | null;
      dev_end_days: number;
      dev_end: string;
    }>;
  };
  chart: {
    range_start: string | null;
    range_end: string | null;
    capped: boolean;
    rows: Array<{
      project: string;
      task: string;
      label: string;
      base_end: string | null;
      plan_end: string | null;
      dev_end_days: number | null;
    }>;
  };
  rows: Array<{
    project: string;
    task_id: string | null;
    task: string;
    block: string | null;
    building: string | null;
    base_start: string | null;
    plan_start: string | null;
    dev_start: string;
    dev_start_days: number | null;
    base_end: string | null;
    plan_end: string | null;
    dev_end: string;
    dev_end_days: number | null;
    base_dur_days: number | null;
    plan_dur_days: number | null;
    dev_dur: string;
    dev_dur_days: number | null;
  }>;
};

export type BaselineDeviationQuery = {
  project?: string;
  block?: string;
  building?: string;
  level?: string;
};

export async function fetchBaselineDeviation(
  query: BaselineDeviationQuery = {},
): Promise<BaselineDeviationPayload> {
  const params = new URLSearchParams();
  if (query.project && query.project !== "Все") {
    params.set("project", query.project);
  }
  if (query.block && query.block !== "Все") {
    params.set("block", query.block);
  }
  if (query.building && query.building !== "Все") {
    params.set("building", query.building);
  }
  if (query.level) params.set("level", query.level);
  const qs = params.toString();
  const url = apiUrl(`/api/baseline-deviation${qs ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
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
  };
  filters: {
    projects: string[];
    sections: string[];
    granularities: Array<{ id: string; label: string }>;
    applied: {
      project: string;
      section: string;
      granularity: string;
      report_date: string;
    };
  };
  kpis: {
    plan_total: number;
    plan_to_date: number;
    fact_to_date: number;
    deviation_to_date: number;
    current_productivity: number;
    required_productivity: number;
  };
  tremor: {
    status_mix: Array<{ name: string; value: number }>;
    dynamics: Array<{
      period: string;
      period_label: string;
      plan_bp: number;
      forecast: number;
    }>;
  };
  rows: Array<{
    project: string;
    section: string;
    task: string;
    base_end: string | null;
    plan_end: string | null;
    dev_end: string;
    dev_end_days: number | null;
    pct_complete: number | null;
    status: string;
  }>;
};

export type ProjectDocumentationQuery = {
  project?: string;
  section?: string;
  granularity?: string;
  report_date?: string;
};

export async function fetchProjectDocumentation(
  query: ProjectDocumentationQuery = {},
): Promise<ProjectDocumentationPayload> {
  const params = new URLSearchParams();
  if (query.project && query.project !== "Все") {
    params.set("project", query.project);
  }
  if (query.section && query.section !== "Все") {
    params.set("section", query.section);
  }
  if (query.granularity) params.set("granularity", query.granularity);
  if (query.report_date) params.set("report_date", query.report_date);
  const qs = params.toString();
  const url = apiUrl(`/api/project-documentation${qs ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export async function fetchWorkingDocumentation(
  query: ProjectDocumentationQuery = {},
): Promise<ProjectDocumentationPayload> {
  const params = new URLSearchParams();
  if (query.project && query.project !== "Все") {
    params.set("project", query.project);
  }
  if (query.section && query.section !== "Все") {
    params.set("section", query.section);
  }
  if (query.granularity) params.set("granularity", query.granularity);
  if (query.report_date) params.set("report_date", query.report_date);
  const qs = params.toString();
  const url = apiUrl(`/api/working-documentation${qs ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type GdrsPayload = {
  meta: {
    data_mode: string;
    resource_kind: "people" | "equipment";
    unit: string;
    period_label: string;
    rows: number;
    resursi_files: number;
    warning: string | null;
  };
  filters: {
    projects: string[];
    contractors: string[];
    months: string[];
    default_months: string[];
    agg_options: string[];
    selected: {
      projects: string[];
      contractors: string[];
      months: string[];
      plan_agg: string;
      skud_agg: string;
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
  matrix_rows: Array<{
    kind: string;
    label: string;
    vid_raboty: string;
    plan: number;
    skud: number;
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
};

export async function fetchGdrsPeople(
  query: GdrsQuery = {},
): Promise<GdrsPayload> {
  const params = new URLSearchParams();
  if (query.projects?.length) params.set("projects", query.projects.join(","));
  if (query.contractors?.length) {
    params.set("contractors", query.contractors.join(","));
  }
  if (query.months?.length) params.set("months", query.months.join(","));
  if (query.plan_agg) params.set("plan_agg", query.plan_agg);
  if (query.skud_agg) params.set("skud_agg", query.skud_agg);
  const qs = params.toString();
  const url = apiUrl(`/api/gdrs-people${qs ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export async function fetchGdrsEquipment(
  query: GdrsQuery = {},
): Promise<GdrsPayload> {
  const params = new URLSearchParams();
  if (query.projects?.length) params.set("projects", query.projects.join(","));
  if (query.contractors?.length) {
    params.set("contractors", query.contractors.join(","));
  }
  if (query.months?.length) params.set("months", query.months.join(","));
  if (query.plan_agg) params.set("plan_agg", query.plan_agg);
  if (query.skud_agg) params.set("skud_agg", query.skud_agg);
  const qs = params.toString();
  const url = apiUrl(`/api/gdrs-equipment${qs ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
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
  params: Record<string, string | undefined> = {},
): Promise<PrescriptionsPayload> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v && v !== "Все") qs.set(k, v);
  });
  const url = apiUrl(`/api/prescriptions${qs.toString() ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
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
  params: Record<string, string | undefined> = {},
): Promise<ExecutiveDocsPayload> {
  const qs = new URLSearchParams();
  Object.entries(params).forEach(([k, v]) => {
    if (v && v !== "Все") qs.set(k, v);
  });
  const url = apiUrl(`/api/executive-docs${qs.toString() ? `?${qs}` : ""}`);
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type AdminDataStatus = {
  data_mode: string;
  web_dir: string;
  files: number;
  latest_mtime: number | null;
  ftp_configured: boolean;
};

export async function fetchAdminDataStatus(): Promise<AdminDataStatus> {
  const url = apiUrl("/api/admin/data-status");
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}

export type AdminSyncResult = {
  ok: boolean;
  downloaded?: number;
  skipped_same_size?: number;
  files?: number;
  errors?: string[];
  detail?: string;
  [key: string]: unknown;
};

export async function postAdminSync(
  token: string,
  force = false,
): Promise<AdminSyncResult> {
  const qs = force ? "?force=true" : "";
  const url = apiUrl(`/api/admin/sync${qs}`);
  const res = await fetch(url, {
    method: "POST",
    cache: "no-store",
    headers: {
      "X-Admin-Token": token,
    },
  });
  const body = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `API ${res.status}: ${url}`;
    throw new Error(detail);
  }
  return body as AdminSyncResult;
}

export async function fetchHealth(): Promise<{
  ok: boolean;
  version?: string;
  data_mode?: string;
  files?: number;
}> {
  const url = apiUrl("/api/health");
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}
