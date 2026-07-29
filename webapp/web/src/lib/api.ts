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
