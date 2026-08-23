"use client";

import { REPORT_ACCORDIONS, REPORT_STANDALONE, REPORT_TOP_TAB } from "@/lib/nav";

/** Соседние отчёты в меню — тихий prefetch RSC для быстрого перехода. */
export function prefetchAdjacentReports(pathname: string): void {
  if (typeof window === "undefined") return;
  const hrefs: string[] = [REPORT_TOP_TAB.href];
  for (const acc of REPORT_ACCORDIONS) {
    for (const item of acc.items) hrefs.push(item.href);
  }
  for (const item of REPORT_STANDALONE) hrefs.push(item.href);

  const idx = hrefs.findIndex(
    (h) => pathname === h || pathname.startsWith(`${h}/`),
  );
  if (idx < 0) return;

  const neighbors = [hrefs[idx - 1], hrefs[idx + 1]].filter(Boolean) as string[];
  for (const href of neighbors) {
    try {
      const link = document.createElement("link");
      link.rel = "prefetch";
      link.href = href;
      link.as = "document";
      document.head.append(link);
    } catch {
      /* ignore */
    }
  }
}
