import { REPORT_ACCORDIONS, REPORT_STANDALONE, REPORT_TOP_TAB } from "@/lib/nav";

export type FlatReport = {
  id: string;
  href: string;
  label: string;
  group: string;
};

/** Плоский список отчётов из `nav.ts` — общий для мобильного поиска и палитры. */
export const FLAT_REPORTS: FlatReport[] = [
  {
    id: REPORT_TOP_TAB.id,
    href: REPORT_TOP_TAB.href,
    label: REPORT_TOP_TAB.label,
    group: "Основное",
  },
  ...REPORT_ACCORDIONS.flatMap((acc) =>
    acc.items.map((item) => ({
      id: item.id,
      href: item.href,
      label: item.label,
      group: acc.label,
    })),
  ),
  ...REPORT_STANDALONE.map((item) => ({
    id: item.id,
    href: item.href,
    label: item.label,
    group: "Прочее",
  })),
];

/** «ё» и лишние пробелы не должны мешать поиску. */
export function normalizeQuery(value: string): string {
  return value.toLowerCase().replace(/ё/g, "е").replace(/\s+/g, " ").trim();
}

export function searchReports(query: string): FlatReport[] {
  const q = normalizeQuery(query);
  if (!q) return FLAT_REPORTS;
  const words = q.split(" ").filter(Boolean);
  return FLAT_REPORTS.filter((report) => {
    const hay = `${normalizeQuery(report.label)} ${normalizeQuery(report.group)}`;
    return words.every((word) => hay.includes(word));
  });
}

export function groupReports(
  reports: FlatReport[],
): Array<{ group: string; items: FlatReport[] }> {
  const out: Array<{ group: string; items: FlatReport[] }> = [];
  for (const report of reports) {
    const last = out[out.length - 1];
    if (last && last.group === report.group) last.items.push(report);
    else out.push({ group: report.group, items: [report] });
  }
  return out;
}

export function recentReports(
  hrefs: string[],
  exceptHref?: string,
): FlatReport[] {
  return hrefs
    .map((href) => FLAT_REPORTS.find((report) => report.href === href))
    .filter(
      (report): report is FlatReport =>
        Boolean(report) && report!.href !== exceptHref,
    );
}
