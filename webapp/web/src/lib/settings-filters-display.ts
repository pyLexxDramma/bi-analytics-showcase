import { FLAT_REPORTS } from "@/lib/reports-index";

/** Старые имена из Streamlit users.db, которых нет в текущем каталоге экранов. */
const HISTORICAL_TITLES = ["Сроки проекта"];

const EXTRA_ALIASES: Record<string, string[]> = {
  bdds: ["БДДС"],
  bdr: ["БДР"],
  "approved-budget": ["Утвержденный бюджет"],
  "bdds-plan-fact": [
    "БДДС (утверждённый/прогнозный)",
    "Прогнозный БДДС",
    "Прогнозный бюджет",
    "Бюджет план/факт",
  ],
  "project-documentation": ["Просрочка выдачи ПД"],
  "working-documentation": ["Просрочка выдачи РД"],
  "gdrs-people": ["ГДРС", "График движения рабочей силы"],
  "gdrs-equipment": ["ГДРС Техника"],
  prescriptions: ["Предписания по строительству", "Неустраненные предписания"],
  "debit-credit": ["Дебиторская и кредиторская задолженность"],
};

const PUNCT = new Set([" ", "\t", "/", "(", ")", ".", ",", "-", "–", "—", ":", "+"]);

function catalog(): Array<{ title: string; aliases: string[] }> {
  return FLAT_REPORTS.map((report) => {
    const aliases = [report.label, report.id, ...(EXTRA_ALIASES[report.id] || [])];
    return { title: report.label, aliases: [...new Set(aliases)] };
  });
}

function garbledMatches(stored: string, candidate: string): boolean {
  if (stored.length !== candidate.length) return false;
  let wild = false;
  for (let i = 0; i < stored.length; i += 1) {
    const a = stored[i];
    const b = candidate[i];
    if (a === b) continue;
    if ((a === "?" || a === "\uFFFD") && !PUNCT.has(b)) {
      wild = true;
      continue;
    }
    return false;
  }
  return wild;
}

export function isGarbledReportName(name: string | null | undefined): boolean {
  const s = (name || "").trim();
  if (!s) return false;
  let wild = 0;
  let letters = 0;
  for (const ch of s) {
    if (ch === "?" || ch === "\uFFFD") wild += 1;
    else if (/\p{L}/u.test(ch)) letters += 1;
  }
  return wild >= 3 && wild >= Math.max(letters, 1);
}

function garbledHits(stored: string, extraTitles: string[] = []): string[] {
  const hits: string[] = [];
  const add = (title: string) => {
    if (title && !hits.includes(title)) hits.push(title);
  };
  for (const row of catalog()) {
    for (const alias of row.aliases) {
      if (/^[\x00-\x7F]+$/.test(alias)) continue;
      if (garbledMatches(stored, alias)) add(row.title);
    }
  }
  for (const title of [...HISTORICAL_TITLES, ...extraTitles]) {
    if (garbledMatches(stored, title)) add(title);
  }
  return hits;
}

export function reportDisplayName(
  stored: string | null | undefined,
  extraTitles: string[] = [],
): string {
  const s = (stored || "").trim();
  if (!s) return "";
  for (const row of catalog()) {
    if (row.aliases.includes(s)) return row.title;
  }
  if (HISTORICAL_TITLES.includes(s)) return s;
  if (s.includes("?") || s.includes("\uFFFD")) {
    const hits = garbledHits(s, extraTitles);
    if (hits.length === 1) return hits[0];
  }
  return s;
}

export function sameReport(
  storedOrLabel: string | null | undefined,
  selectedLabel: string | null | undefined,
): boolean {
  const a = reportDisplayName(storedOrLabel);
  const b = reportDisplayName(selectedLabel);
  return Boolean(a && b && a === b);
}

export function formatFilterValueDisplay(value: string | null | undefined): string {
  if (value == null) return "-";
  const raw = String(value).trim();
  if (!raw) return "-";
  if (raw.startsWith("[") || raw.startsWith("(")) {
    try {
      const parsed = JSON.parse(raw.replace(/'/g, '"'));
      if (Array.isArray(parsed)) {
        const text = parsed.map((x) => String(x).trim()).filter(Boolean).join(", ");
        return text || "-";
      }
    } catch {
      /* keep raw */
    }
  }
  return raw;
}
