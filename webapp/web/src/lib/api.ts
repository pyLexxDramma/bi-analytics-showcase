export const API_BASE =
  process.env.NEXT_PUBLIC_API_BASE?.replace(/\/$/, "") ||
  "http://127.0.0.1:8000";

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
  const url = `${API_BASE}/api/debit-credit${qs.toString() ? `?${qs}` : ""}`;
  const res = await fetch(url, { cache: "no-store" });
  if (!res.ok) {
    throw new Error(`API ${res.status}: ${url}`);
  }
  return res.json();
}
