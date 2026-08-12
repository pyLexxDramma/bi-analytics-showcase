import type { AuthUser } from "@/lib/auth";
import { authHeaders, logout } from "@/lib/auth";

/** Битый/просроченный Bearer — сброс сессии и на логин (иначе «войти» не даёт из‑за флага в localStorage). */
function redirectIfAuthExpired(status: number | undefined, detail: string) {
  if (status !== 401 || typeof window === "undefined") return;
  if (window.location.pathname.startsWith("/login")) return;
  logout();
  const q = detail
    ? `?reason=${encodeURIComponent(detail.slice(0, 120))}`
    : "";
  window.location.assign(`/login${q}`);
}

export const API_BASE = (
  process.env.NEXT_PUBLIC_API_BASE ?? ""
).replace(/\/$/, "");

function apiUrl(path: string): string {
  const p = path.startsWith("/") ? path : `/${path}`;
  return API_BASE ? `${API_BASE}${p}` : p;
}

/** Тяжёлые отчёты на холодном кэше считаются минутами — но не бесконечно. */
export const DEFAULT_TIMEOUT_MS = 120_000;

export type AssistantSession = {
  id: string;
  title: string;
  busy: boolean;
  error?: string | null;
  created_at: string;
  updated_at: string;
};

export type AssistantMessage = {
  id: string;
  role: "user" | "assistant";
  text: string;
  images: string[];
  created_at?: string | number | null;
};

export type AssistantQuestion = {
  id: string;
  text: string;
  options: Array<{ label: string; value: string; description: string }>;
};

export type AssistantMessagesPayload = {
  items: AssistantMessage[];
  busy: boolean;
  question: AssistantQuestion | null;
  error?: string | null;
};

export class ApiError extends Error {
  readonly status: number;
  readonly url: string;
  readonly timeout: boolean;
  readonly aborted: boolean;

  constructor(
    message: string,
    { status = 0, url = "", timeout = false, aborted = false } = {},
  ) {
    super(message);
    this.name = "ApiError";
    this.status = status;
    this.url = url;
    this.timeout = timeout;
    this.aborted = aborted;
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
  headers?: Record<string, string>;
  signal?: AbortSignal;
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
    search.set(key, value ? "true" : "false");
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

function mergeSignals(
  timeoutMs: number,
  external?: AbortSignal,
): AbortSignal | undefined {
  const timed = abortSignal(timeoutMs);
  if (!external) return timed;
  if (!timed) return external;
  if (typeof AbortSignal !== "undefined" && "any" in AbortSignal) {
    return AbortSignal.any([external, timed]);
  }
  return external;
}

export async function apiGet<T>(
  path: string,
  params: QueryParams = {},
  {
    timeoutMs = DEFAULT_TIMEOUT_MS,
    arrayFormat = "repeat",
    headers = {},
    signal,
  }: ApiGetOptions = {},
): Promise<T> {
  const search = new URLSearchParams();
  Object.entries(params).forEach(([key, value]) => {
    appendParam(search, key, value, arrayFormat);
  });
  const qs = search.toString();
  const url = apiUrl(`${path}${qs ? `?${qs}` : ""}`);

  let res: Response;
  try {
    res = await fetch(url, {
      cache: "no-store",
      signal: mergeSignals(timeoutMs, signal),
      headers: { ...authHeaders(), ...headers },
    });
  } catch (err) {
    if (signal?.aborted) {
      throw new ApiError("Запрос отменён", { url, aborted: true });
    }
    const isTimeout =
      err instanceof DOMException && err.name === "TimeoutError";
    if (isTimeout) {
      throw new ApiError(
        `Превышено время ожидания (${Math.round(timeoutMs / 1000)} с): ${path}. ` +
          "Отчёт ещё считается — обновите страницу через минуту.",
        { url, timeout: true },
      );
    }
    const isAbort =
      err instanceof DOMException && err.name === "AbortError";
    if (isAbort) {
      throw new ApiError("Запрос отменён", { url, aborted: true });
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
    redirectIfAuthExpired(res.status, detail);
    throw new ApiError(detail || `API ${res.status}: ${url}`, {
      status: res.status,
      url,
    });
  }
  return (await res.json()) as T;
}

type ApiPostOptions = {
  timeoutMs?: number;
  headers?: Record<string, string>;
};

export async function apiPost<T>(
  path: string,
  body: unknown = {},
  { timeoutMs = DEFAULT_TIMEOUT_MS, headers = {} }: ApiPostOptions = {},
): Promise<T> {
  const url = apiUrl(path.startsWith("/") ? path : `/${path}`);
  let res: Response;
  try {
    res = await fetch(url, {
      method: "POST",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...headers,
      },
      body: JSON.stringify(body),
      signal: abortSignal(timeoutMs),
    });
  } catch (err) {
    throw new ApiError(
      `Нет связи с API (${path}): ${err instanceof Error ? err.message : String(err)}`,
      { url },
    );
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((b) => (typeof b?.detail === "string" ? b.detail : ""))
      .catch(() => "");
    redirectIfAuthExpired(res.status, detail);
    throw new ApiError(detail || `API ${res.status}: ${url}`, {
      status: res.status,
      url,
    });
  }
  return (await res.json()) as T;
}

export async function apiPut<T>(
  path: string,
  body: unknown = {},
  { timeoutMs = DEFAULT_TIMEOUT_MS, headers = {} }: ApiPostOptions = {},
): Promise<T> {
  const url = apiUrl(path.startsWith("/") ? path : `/${path}`);
  let res: Response;
  try {
    res = await fetch(url, {
      method: "PUT",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...headers,
      },
      body: JSON.stringify(body),
      signal: abortSignal(timeoutMs),
    });
  } catch (err) {
    throw new ApiError(
      `Нет связи с API (${path}): ${err instanceof Error ? err.message : String(err)}`,
      { url },
    );
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((b) => (typeof b?.detail === "string" ? b.detail : ""))
      .catch(() => "");
    redirectIfAuthExpired(res.status, detail);
    throw new ApiError(detail || `API ${res.status}: ${url}`, {
      status: res.status,
      url,
    });
  }
  return (await res.json()) as T;
}

export async function apiDelete<T>(
  path: string,
  body: unknown = {},
  { timeoutMs = DEFAULT_TIMEOUT_MS, headers = {} }: ApiPostOptions = {},
): Promise<T> {
  const url = apiUrl(path.startsWith("/") ? path : `/${path}`);
  let res: Response;
  try {
    res = await fetch(url, {
      method: "DELETE",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...headers,
      },
      body: JSON.stringify(body),
      signal: abortSignal(timeoutMs),
    });
  } catch (err) {
    throw new ApiError(
      `Нет связи с API (${path}): ${err instanceof Error ? err.message : String(err)}`,
      { url },
    );
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((b) => (typeof b?.detail === "string" ? b.detail : ""))
      .catch(() => "");
    redirectIfAuthExpired(res.status, detail);
    throw new ApiError(detail || `API ${res.status}: ${url}`, {
      status: res.status,
      url,
    });
  }
  if (res.status === 204) return {} as T;
  return (await res.json()) as T;
}

export async function apiPatch<T>(
  path: string,
  body: unknown = {},
  { timeoutMs = DEFAULT_TIMEOUT_MS, headers = {} }: ApiPostOptions = {},
): Promise<T> {
  const url = apiUrl(path.startsWith("/") ? path : `/${path}`);
  let res: Response;
  try {
    res = await fetch(url, {
      method: "PATCH",
      cache: "no-store",
      headers: {
        "Content-Type": "application/json",
        ...authHeaders(),
        ...headers,
      },
      body: JSON.stringify(body),
      signal: abortSignal(timeoutMs),
    });
  } catch (err) {
    throw new ApiError(
      `Нет связи с API (${path}): ${err instanceof Error ? err.message : String(err)}`,
      { url },
    );
  }
  if (!res.ok) {
    const detail = await res
      .json()
      .then((b) => (typeof b?.detail === "string" ? b.detail : ""))
      .catch(() => "");
    redirectIfAuthExpired(res.status, detail);
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
    version_id: number | null;
    source: string;
    data_mode: string;
    parity: string;
    warning: string | null;
  };
  filters: {
    projects: string[];
    contractors: string[];
    /** Уникальные № договора для автоподсказок (как datalist в main). */
    contract_nos?: string[];
    date_min: string | null;
    date_max: string | null;
    applied?: Record<string, string | null | undefined>;
  };
  chart: {
    rows: Array<
      | {
          label: string;
          Аванс: number;
          "КС-2": number;
          "Отклонение ≥0": number;
          "Отклонение <0": number;
        }
      | {
          label: string;
          value: number;
          color: string;
        }
    >;
    mode: "group" | "stack";
    /** by_metric — только при Все/Все/без договора; иначе by_contractor. */
    aggregation?: "by_contractor" | "by_metric";
    caption: string;
    unit?: string;
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
    advance_ks2: number;
    advance_pct: number | null;
    advance_tone?: "green" | "yellow" | "red";
  }>;
  totals: {
    contract_sum: number;
    advance: number;
    ks2: number;
    fulfilled: number;
    paid: number;
    balance: number;
    advance_ks2: number;
    advance_pct?: number | null;
    advance_tone?: "green" | "yellow" | "red";
  };
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
    parity: string;
    error?: string | null;
    version_id?: number | null;
    rows_1c?: number;
    db?: { active_version_id?: number | null; exists?: boolean };
  };
  filters: {
    projects: string[];
    date_min: string | null;
    date_max: string | null;
    groups: Array<{ id: string; label: string }>;
    views: Array<{ id: string; label: string }>;
    dev_bases: Array<{ id: string; label: string }>;
    applied: {
      project: string;
      date_from: string | null;
      date_to: string | null;
      group: "month" | "quarter" | "year";
      view: "monthly" | "cumulative";
      dev_base: "plan" | "fact";
      hide_deviation: boolean;
      hide_zero: boolean;
    };
  };
  tremor: {
    by_period: Array<{
      period: string;
      plan: number;
      fact: number;
      forecast: number;
      deviation: number;
    }>;
  };
  period_rows: Array<{
    period: string;
    plan: number;
    fact: number;
    forecast: number;
    deviation: number;
    kind?: "total";
  }>;
  status_rows: Array<{
    month: string;
    project: string;
    plan_mln: number;
    fact_mln: number;
    forecast_mln: number;
    deviation_mln: number;
    status: string;
  }>;
  totals: {
    plan: number;
    fact: number;
    forecast: number;
    deviation: number;
  };
  labels: {
    period_column: string;
    deviation_column: string;
    chart_title: string;
    period_table_title: string;
    status_table_title: string;
    total_period: string;
    edit_banner: string;
  };
  hints?: string[];
  validation_errors?: string[];
  lot_recalc?: BddsPlanFactLotRecalc | null;
  applied?: boolean;
  ok?: boolean;
};

export type BddsPlanFactEditRow = {
  "Раздел": string;
  "Лот": string;
  "Условие распределения": string;
  "План. начало": string;
  "План. окончание": string;
  "БДДС план (утверждённый), млн руб.": number;
  "БДДС факт, млн руб.": number;
  "A, %": number;
  "B, %": number;
  "C, %": number;
};

export type BddsPlanFactEditorPayload = {
  project: string;
  project_norm: string;
  can_edit: boolean;
  help_md: string;
  dist_options: string[];
  columns: string[];
  rows: BddsPlanFactEditRow[];
  baseline_rows: BddsPlanFactEditRow[];
  src_sig: number[];
  applied: boolean;
  visible_indices: number[];
  total_rows: number;
  visible_rows: number;
  hidden_struct_rows: number;
  error?: string;
};

export type BddsPlanFactLotRecalcRow = {
  lot: string;
  plan_mln: number;
  fact_mln: number;
  forecast_uniform_mln: number;
  forecast_cond_mln: number;
  delta_mln: number;
};

export type BddsPlanFactLotRecalc = {
  period_choices: string[];
  selected_period: string;
  forecast_uniform_column: string;
  forecast_cond_column: string;
  delta_column: string;
  caption: string;
  rows: BddsPlanFactLotRecalcRow[];
};

export type BddsPlanFactEditBody = {
  project: string;
  rows: BddsPlanFactEditRow[];
  date_from?: string;
  date_to?: string;
  group?: "month" | "quarter" | "year";
  view?: "monthly" | "cumulative";
  dev_base?: "plan" | "fact";
  hide_deviation?: boolean;
  hide_zero?: boolean | null;
  lot_recalc_period?: string;
};

export type BddsPlanFactQuery = {
  project?: string;
  date_from?: string;
  date_to?: string;
  group?: "month" | "quarter" | "year";
  view?: "monthly" | "cumulative";
  dev_base?: "plan" | "fact";
  hide_deviation?: boolean;
  hide_zero?: boolean;
};

export async function fetchBddsPlanFact(
  query: BddsPlanFactQuery = {},
  signal?: AbortSignal,
): Promise<BddsPlanFactPayload> {
  const params: QueryParams = {};
  if (query.project) params.project = query.project;
  if (query.date_from) params.date_from = query.date_from;
  if (query.date_to) params.date_to = query.date_to;
  if (query.group) params.group = query.group;
  if (query.view) params.view = query.view;
  if (query.dev_base) params.dev_base = query.dev_base;
  if (query.hide_deviation) params.hide_deviation = true;
  if (query.hide_zero !== undefined) params.hide_zero = query.hide_zero;
  return apiGet<BddsPlanFactPayload>("/api/bdds-plan-fact", params, {
    headers: authHeaders(),
    signal,
  });
}

export async function fetchBddsPlanFactEditor(
  project: string,
  showStruct = false,
): Promise<BddsPlanFactEditorPayload> {
  const params: QueryParams = { project, show_struct: String(showStruct) };
  return apiGet<BddsPlanFactEditorPayload>("/api/bdds-plan-fact/editor", params, {
    headers: authHeaders(),
  });
}

function bddsEditBody(
  project: string,
  rows: BddsPlanFactEditRow[],
  query: BddsPlanFactQuery & { lot_recalc_period?: string },
): BddsPlanFactEditBody {
  return {
    project,
    rows,
    date_from: query.date_from,
    date_to: query.date_to,
    group: query.group,
    view: query.view,
    dev_base: query.dev_base,
    hide_deviation: query.hide_deviation,
    hide_zero: query.hide_zero ?? undefined,
    lot_recalc_period: query.lot_recalc_period,
  };
}

export async function previewBddsPlanFact(
  project: string,
  rows: BddsPlanFactEditRow[],
  query: BddsPlanFactQuery & { lot_recalc_period?: string } = {},
): Promise<BddsPlanFactPayload> {
  return apiPost<BddsPlanFactPayload>(
    "/api/bdds-plan-fact/preview",
    bddsEditBody(project, rows, query),
    { headers: authHeaders(), timeoutMs: 120_000 },
  );
}

export async function applyBddsPlanFactEdits(
  project: string,
  rows: BddsPlanFactEditRow[],
  query: BddsPlanFactQuery & { lot_recalc_period?: string } = {},
): Promise<BddsPlanFactPayload> {
  return apiPost<BddsPlanFactPayload>(
    "/api/bdds-plan-fact/apply",
    bddsEditBody(project, rows, query),
    { headers: authHeaders(), timeoutMs: 120_000 },
  );
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
      covenant_mode?: boolean;
    };
  };
  gantt: {
    range_start: string | null;
    range_end: string | null;
    capped: boolean;
    plan_color: string;
    fact_color: string;
    label_pct: boolean;
    covenant_mode?: boolean;
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
      base_start?: string | null;
      base_start_label?: string | null;
      plan_start?: string | null;
      plan_start_label?: string | null;
      base_end: string | null;
      base_end_label?: string | null;
      plan_end: string | null;
      plan_end_label?: string | null;
      dev_end_days: number | null;
    }>;
  };
  covenant_table?: {
    columns: string[];
    rows: Array<{
      project?: string;
      task: string;
      task_id: string | null;
      base_end: string | null;
      plan_end: string | null;
      dev_end_days: number | null;
      dev_end?: string | null;
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
      forecast: number | null;
      fact?: number;
    }>;
    monthly: Array<{
      month: string;
      month_label: string;
      plan: number;
      fact: number;
      done?: number;
      overdue?: number;
      rest?: number;
      fact_inc?: number;
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
        /** Сдано с опозданием: жёлтый+красный + зелёная стрелка в UI. */
        late_complete?: boolean;
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
    /** Выдано в производство работ (как сегмент pie). */
    issued_production?: number;
    /** Всего разделов − выдано в производство. */
    not_issued?: number;
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
      /** Стык с фактом → дальше по «Прогнозной дате выдачи»; null до стыка. */
      forecast?: number | null;
    }>;
    monthly: Array<{
      month: string;
      month_label: string;
      plan: number;
      fact: number;
      done?: number;
      overdue?: number;
      rest?: number;
      fact_inc?: number;
      /** Выдано − план к дате (≥0 зелёный, <0 красный). */
      delta?: number;
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
    version_id: number | null;
    data_mode: string;
    source: "web_data.db";
    parity: "main_dashboard_predpisania";
    warning: string | null;
    generated_at?: string;
  };
  filters: {
    projects: string[];
    contractors: string[];
    /** Уникальные № договора для автоподсказок (как datalist в main). */
    contract_nos?: string[];
    date_min: string | null;
    date_max: string | null;
    applied: {
      projects: string[];
      contractors: string[];
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
      name: string;
      status: string;
      value: number;
      count: number;
      share_pct: number;
    }>;
    by_object: Array<
      { object: string; total: number } & Record<string, number | string>
    >;
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
    resolved: boolean;
    row_tone: "overdue" | "resolved" | "neutral";
    status_chip: "overdue" | "ok" | "warn";
  }>;
};

export async function fetchPrescriptions(
  params: QueryParams = {},
): Promise<PrescriptionsPayload> {
  return apiGet<PrescriptionsPayload>("/api/prescriptions", params, {
    arrayFormat: "comma",
  });
}

export type ExecutiveDocsPayload = {
  meta: {
    rows: number;
    table_rows?: number;
    version_id?: number | null;
    data_mode: string;
    source: "web_data.db";
    parity?: string;
    warning: string | null;
    generated_at?: string;
  };
  filters: {
    projects: string[];
    contractors: string[];
    doc_kinds: string[];
    catalog: Array<Record<string, string | number>>;
    date_min: string | null;
    date_max: string | null;
    granularities: Array<{ id: string; label: string }>;
    applied: {
      project?: string;
      contractor?: string;
      doc_kind?: string;
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
    status_display?: string;
    status_chip?: string;
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

export type DataFreshness = {
  stale: boolean;
  missing?: boolean;
  label: string;
  age_hours: number | null;
  stale_after_hours?: number;
  active_version_id?: number | null;
  active_version_created_at?: string | null;
  data_mode?: string;
  auto_sync_eligible?: boolean;
  checked_at?: string;
};

export type AdminDataStatus = {
  data_mode: string;
  web_dir: string;
  files: number;
  latest_mtime: number | null;
  ftp_configured: boolean;
  db?: AdminDbStatus;
  freshness?: DataFreshness;
};

export async function fetchAdminDataStatus(): Promise<AdminDataStatus> {
  return apiGet<AdminDataStatus>("/api/admin/data-status", {}, {
    timeoutMs: 30_000,
  });
}

export type EnsureFreshResult = {
  ok: boolean;
  action: string;
  message?: string;
  async?: boolean;
  job_id?: string;
  cooldown_hours_left?: number;
  freshness?: DataFreshness;
  status?: AdminDataStatus;
};

/** Проверить свежесть; при устаревании запустить FTP→БД (с cooldown на сервере). */
export async function postEnsureFresh(
  token?: string | null,
  opts?: { force?: boolean; background?: boolean },
): Promise<EnsureFreshResult> {
  const q = new URLSearchParams();
  if (opts?.force) q.set("force", "true");
  if (opts?.background === false) q.set("background", "false");
  const qs = q.toString() ? `?${q}` : "";
  return postAdminAction(`/api/admin/ensure-fresh${qs}`, token) as Promise<EnsureFreshResult>;
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

async function adminHeaders(token?: string | null): Promise<Record<string, string>> {
  const headers: Record<string, string> = { ...authHeaders() };
  const t = (token || "").trim();
  if (t) headers["X-Admin-Token"] = t;
  return headers;
}

async function postAdminAction(
  path: string,
  token?: string | null,
): Promise<AdminSyncResult> {
  const url = apiUrl(path);
  const res = await fetch(url, {
    method: "POST",
    cache: "no-store",
    headers: await adminHeaders(token),
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
  token?: string | null,
  force = false,
): Promise<AdminSyncResult> {
  const qs = force ? "?force=true" : "";
  return postAdminAction(`/api/admin/sync${qs}`, token);
}

/** web/ → web_data.db (без FTP; synthetic и ftp). */
export async function postAdminIngest(token?: string | null): Promise<AdminSyncResult> {
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
  token: string | null | undefined,
  versionId: number,
): Promise<AdminSyncResult> {
  return postAdminAction(`/api/admin/versions/${versionId}/activate`, token);
}

export async function fetchAdminJob(
  token: string | null | undefined,
  jobId: string,
): Promise<AdminJob> {
  const url = apiUrl(`/api/admin/jobs/${encodeURIComponent(jobId)}`);
  const res = await fetch(url, {
    cache: "no-store",
    headers: await adminHeaders(token),
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

export type SnapshotExportInfo = {
  ok: boolean;
  snapshot_date?: string | null;
  files_count?: number;
  archive_ready?: boolean;
  archive_name?: string | null;
  archive_size_bytes?: number | null;
  archive_built_at?: string | null;
  archive_snapshot_date?: string | null;
  error?: string;
};

/** Свежий слепок FTP (файлы самой новой даты) — скачать tar.gz. */
export async function downloadSnapshotExport(
  token?: string | null,
  opts?: { rebuild?: boolean },
): Promise<{ filename: string; blob: Blob }> {
  const q = opts?.rebuild ? "?rebuild=true" : "";
  const url = apiUrl(`/api/admin/snapshot-export/download${q}`);
  const res = await fetch(url, {
    cache: "no-store",
    headers: await adminHeaders(token),
    signal: abortSignal(180_000),
  });
  if (!res.ok) {
    const body = await res.json().catch(() => ({}));
    const detail =
      typeof body?.detail === "string"
        ? body.detail
        : `API ${res.status}: ${url}`;
    throw new ApiError(detail, { status: res.status, url });
  }
  const disposition = res.headers.get("Content-Disposition") || "";
  const match = /filename\*?=(?:UTF-8''|")?([^\";]+)/i.exec(disposition);
  const filename = match
    ? decodeURIComponent(match[1]!.replace(/"/g, ""))
    : "showcase_ftp_snapshot.tar.gz";
  const blob = await res.blob();
  return { filename, blob };
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

export type AuthStatusPayload = {
  users_db_exists: boolean;
  initialized: boolean;
};

export async function fetchAuthStatus(): Promise<AuthStatusPayload> {
  return apiGet<AuthStatusPayload>("/api/auth/status", {}, { timeoutMs: 15_000 });
}

export async function postAuthLogin(
  username: string,
  password: string,
): Promise<{ ok: boolean; user: AuthUser; token: string; expires_in: number }> {
  return apiPost("/api/auth/login", { username, password });
}

export async function fetchAuthMe(): Promise<{ ok: boolean; user: AuthUser }> {
  return apiGet("/api/auth/me", {}, { headers: authHeaders(), timeoutMs: 15_000 });
}

export async function fetchMyDefaultFilters(
  navId: string,
): Promise<{ ok: boolean; nav_id: string; filters: Record<string, unknown> }> {
  return apiGet(
    "/api/auth/default-filters",
    { nav_id: navId },
    { headers: authHeaders(), timeoutMs: 15_000 },
  );
}

export async function postProfilePassword(
  oldPassword: string,
  newPassword: string,
): Promise<{ ok: boolean; message: string }> {
  return apiPost(
    "/api/profile/password",
    { old_password: oldPassword, new_password: newPassword },
    { headers: authHeaders() },
  );
}

export async function postProfileEmail(
  newEmail: string | null,
): Promise<{ ok: boolean; message: string; email?: string | null }> {
  return apiPost(
    "/api/profile/email",
    { new_email: newEmail },
    { headers: authHeaders() },
  );
}

export type SettingsUser = {
  id: number;
  username: string;
  role: string;
  role_label: string;
  email: string | null;
  created_at: string | null;
  created_at_fmt: string;
  last_login: string | null;
  last_login_fmt: string;
  is_active: boolean;
};

export async function fetchSettingsUsers(): Promise<{ items: SettingsUser[] }> {
  return apiGet("/api/settings/users", {}, { headers: authHeaders() });
}

export async function postSettingsUser(body: {
  username: string;
  password: string;
  role: string;
  email?: string;
}): Promise<{ ok: boolean }> {
  return apiPost("/api/settings/users", body, { headers: authHeaders() });
}

export async function postSettingsChangeRole(body: {
  user_id: number;
  new_role: string;
}): Promise<{ ok: boolean }> {
  return apiPost("/api/settings/users/change-role", body, {
    headers: authHeaders(),
  });
}

export async function deleteSettingsUser(userId: number): Promise<{ ok: boolean; message?: string }> {
  return apiDelete(`/api/settings/users/${userId}`, {}, { headers: authHeaders() });
}

export type SettingsStats = {
  total_users: number;
  active_users: number;
  users_with_login: number;
  total_logs: number;
  roles: Array<{ role: string; role_label: string; count: number }>;
};

export async function fetchSettingsStats(): Promise<SettingsStats> {
  return apiGet("/api/settings/stats", {}, { headers: authHeaders() });
}

export type SettingsLogRow = {
  id: number;
  username: string;
  action: string;
  action_key?: string;
  details: string;
  ip_address: string;
  created_at: string;
  created_at_fmt: string;
};

export async function fetchSettingsLogs(params: {
  username?: string;
  action?: string;
  limit?: number;
  date_from?: string;
  date_to?: string;
}): Promise<{
  items: SettingsLogRow[];
  filters: { usernames: string[]; actions: string[] };
}> {
  return apiGet("/api/settings/logs", params, { headers: authHeaders() });
}

export type SettingsRole = {
  code: string;
  label: string;
  is_system?: boolean;
  can_admin?: boolean;
  reports?: string[];
  projects?: string[];
  created_at?: string | null;
};

export async function fetchSettingsRoles(): Promise<{
  items: SettingsRole[];
}> {
  return apiGet("/api/settings/roles", {}, { headers: authHeaders() });
}

export async function fetchReportCatalog(): Promise<{
  items: Array<{ id: string; title: string; path: string }>;
}> {
  return apiGet("/api/settings/report-catalog", {}, { headers: authHeaders() });
}

export async function postSettingsRole(body: {
  code: string;
  label: string;
  reports?: string[];
  can_admin?: boolean;
}): Promise<{ ok: boolean; item: SettingsRole }> {
  return apiPost("/api/settings/roles", body, { headers: authHeaders() });
}

export async function patchSettingsRole(
  code: string,
  body: {
    label?: string;
    reports?: string[];
    projects?: string[];
    can_admin?: boolean;
  },
): Promise<{ ok: boolean; item: SettingsRole }> {
  return apiPatch(`/api/settings/roles/${encodeURIComponent(code)}`, body, {
    headers: authHeaders(),
  });
}

export async function fetchUserProjects(userId: number): Promise<{
  user_id: number;
  projects: string[];
  unrestricted: boolean;
}> {
  return apiGet(`/api/settings/users/${userId}/projects`, {}, { headers: authHeaders() });
}

export async function putUserProjects(
  userId: number,
  projects: string[],
): Promise<{ ok: boolean; projects: string[]; unrestricted: boolean }> {
  return apiPut(
    `/api/settings/users/${userId}/projects`,
    { projects },
    { headers: authHeaders() },
  );
}

export async function deleteSettingsRole(code: string): Promise<{ ok: boolean }> {
  return apiDelete(`/api/settings/roles/${encodeURIComponent(code)}`, {}, {
    headers: authHeaders(),
  });
}

export type DefaultFilterRow = {
  role: string;
  role_label: string;
  report_name: string;
  filter_key: string;
  filter_value: string | null;
  filter_type: string;
  filter_type_label: string;
  updated_at: string | null;
  updated_by: string | null;
};

export async function fetchSettingsFilters(params?: {
  role?: string;
  report_name?: string;
}): Promise<{
  items: DefaultFilterRow[];
  reports: string[];
  filter_types: Record<string, string>;
  roles: Record<string, string>;
}> {
  return apiGet("/api/settings/filters", params || {}, { headers: authHeaders() });
}

export async function postSettingsFilter(body: {
  role: string;
  report_name: string;
  filter_key: string;
  filter_value?: string;
  filter_type?: string;
}): Promise<{ ok: boolean }> {
  return apiPost("/api/settings/filters", body, { headers: authHeaders() });
}

export async function deleteSettingsFilter(body: {
  role: string;
  report_name: string;
  filter_key: string;
}): Promise<{ ok: boolean }> {
  return apiDelete("/api/settings/filters", body, { headers: authHeaders() });
}

export async function postSettingsCopyFilters(body: {
  source_role: string;
  target_role: string;
  report_name?: string | null;
}): Promise<{ ok: boolean }> {
  return apiPost("/api/settings/filters/copy", body, { headers: authHeaders() });
}

export async function fetchReportConfig(): Promise<{
  values: Record<string, string>;
  descriptions: Record<string, string>;
}> {
  return apiGet("/api/settings/report-config", {}, { headers: authHeaders() });
}

export async function putReportConfig(
  values: Record<string, string | undefined>,
): Promise<{ ok: boolean }> {
  return apiPut("/api/settings/report-config", values, { headers: authHeaders() });
}

export type AskAiLinkRequest = {
  nav_id?: string;
  report?: string;
  /** free = чат без экрана (сайдбар «ИИ помощник»). */
  mode?: "screen" | "free";
  q?: string;
  ctx?: string;
  project?: string;
  period?: string;
  filters?: Record<string, string> | string;
  src?: string;
};

export type AskAiLinkResponse = {
  ok: boolean;
  url: string;
  report: string;
  nav_id?: string | null;
  ts: number;
  exp?: number;
  expires_in: number;
  projects?: string;
  reports?: string;
};

/** Подписанная ссылка XCA Ask AI (генерируется на API в момент клика). */
export async function postAskAiLink(
  body: AskAiLinkRequest,
): Promise<AskAiLinkResponse> {
  return apiPost("/api/ask-ai/link", body, {
    headers: authHeaders(),
    timeoutMs: 15_000,
  });
}

export async function fetchAssistantHealth(): Promise<{
  ok: boolean;
  error?: string;
}> {
  return apiGet("/api/assistant/health", {}, {
    headers: authHeaders(),
    timeoutMs: 10_000,
  });
}

export async function fetchAssistantSessions(): Promise<{
  items: AssistantSession[];
}> {
  return apiGet("/api/assistant/sessions", {}, { headers: authHeaders() });
}

export async function createAssistantSession(): Promise<AssistantSession> {
  return apiPost("/api/assistant/sessions", {}, { headers: authHeaders() });
}

export async function deleteAssistantSession(sessionId: string): Promise<void> {
  await apiDelete(`/api/assistant/sessions/${sessionId}`, {}, {
    headers: authHeaders(),
  });
}

export async function fetchAssistantMessages(
  sessionId: string,
  signal?: AbortSignal,
): Promise<AssistantMessagesPayload> {
  return apiGet(`/api/assistant/sessions/${sessionId}/messages`, {}, {
    headers: authHeaders(),
    timeoutMs: 35_000,
    signal,
  });
}

export async function sendAssistantMessage(
  sessionId: string,
  text: string,
): Promise<{ ok: boolean; busy: boolean }> {
  return apiPost(`/api/assistant/sessions/${sessionId}/messages`, { text }, {
    headers: authHeaders(),
    timeoutMs: 35_000,
  });
}

export async function cancelAssistantMessage(
  sessionId: string,
): Promise<{ ok: boolean }> {
  return apiPost(`/api/assistant/sessions/${sessionId}/cancel`, {}, {
    headers: authHeaders(),
  });
}

export async function replyAssistantQuestion(
  sessionId: string,
  questionId: string,
  answer: string,
): Promise<{ ok: boolean; busy: boolean }> {
  return apiPost(`/api/assistant/sessions/${sessionId}/question`, {
    question_id: questionId,
    answer,
  }, { headers: authHeaders() });
}
