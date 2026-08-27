import { collectAskAiFiltersFromSearch } from "@/lib/ask-ai-reports";
import type { AuthUser } from "@/lib/auth";
import { accordionIdForPath, findNavItem, REPORT_TOP_TAB } from "@/lib/nav";

const DEFAULT_BUG_FORM_URL =
  "https://winbot.taild98f9b.ts.net:8443/bugform?k=f21915ba03f6a71d";

export type BugReportContext = {
  menugroup: string;
  report: string;
};

/** Значения menugroup — строго как в analytics_bug_form / form.html */
export function resolveBugReportContext(
  pathname: string,
  pageTitle?: string,
): BugReportContext | null {
  if (pathname.startsWith("/settings/admin")) {
    return { menugroup: "Админпанель", report: "Административная панель" };
  }
  if (pathname.startsWith("/settings/profile")) return null;
  if (pathname.startsWith("/ai-assistant")) {
    return { menugroup: "AI-аналитика", report: "ИИ помощник" };
  }
  if (pathname.startsWith("/login")) return null;

  const nav = findNavItem(pathname);
  if (!nav) {
    if (pageTitle?.trim()) {
      return { menugroup: "Другое", report: pageTitle.trim() };
    }
    return null;
  }

  if (nav.id === REPORT_TOP_TAB.id) {
    return { menugroup: "Девелоперские проекты", report: nav.label };
  }
  if (nav.id === "prescriptions") {
    return { menugroup: "Предписания", report: nav.label };
  }
  if (nav.id === "executive-docs") {
    return { menugroup: "ИД", report: nav.label };
  }
  if (nav.id === "gdrs-people" || nav.id === "gdrs-equipment") {
    return { menugroup: "ГДРС", report: nav.label };
  }

  const accordion = accordionIdForPath(pathname);
  if (accordion === "finance") {
    return { menugroup: "Финансы", report: nav.label };
  }
  if (accordion === "timeline") {
    return { menugroup: "Сроки", report: nav.label };
  }
  if (accordion === "project-docs") {
    return { menugroup: "Проектные работы", report: nav.label };
  }

  if (nav.id === "debit-credit") {
    return { menugroup: "Финансы", report: nav.label };
  }

  return { menugroup: "Другое", report: nav.label };
}

export function detectBugReportContour(): string {
  if (typeof window === "undefined") return "Не знаю";
  const host = window.location.hostname.toLowerCase();
  if (host === "ai.conall.ru") return "Боевой";
  if (
    host === "localhost" ||
    host === "127.0.0.1" ||
    host.includes("cloudpub")
  ) {
    return "Тестовый";
  }
  return "Не знаю";
}

export function detectBugReportBrowser(): string {
  if (typeof navigator === "undefined") return "";
  const ua = navigator.userAgent;
  const mobile = /Mobile|Android|iPhone|iPad/i.test(ua);
  let name = "Browser";
  if (/Edg\//i.test(ua)) name = "Edge";
  else if (/Chrome\//i.test(ua) && !/Edg\//i.test(ua)) name = "Chrome";
  else if (/Firefox\//i.test(ua)) name = "Firefox";
  else if (/Safari\//i.test(ua) && !/Chrome\//i.test(ua)) name = "Safari";

  const theme =
    typeof document !== "undefined" &&
    document.documentElement.classList.contains("dark")
      ? "тёмная тема"
      : "светлая тема";

  return `${name}, ${mobile ? "mobile" : "desktop"}, ${theme}`;
}

export function formatBugReportFilters(pathname: string, search: string): string {
  const slice = collectAskAiFiltersFromSearch(search);
  const parts: string[] = [`page=${pathname}`];
  if (slice.project) parts.push(`project=${slice.project}`);
  if (slice.period) parts.push(`period=${slice.period}`);
  if (slice.filters) {
    for (const [key, value] of Object.entries(slice.filters)) {
      parts.push(`${key}=${value}`);
    }
  }
  const raw = search.replace(/^\?/, "").trim();
  if (raw && !slice.filters && !slice.project && !slice.period) {
    parts.push(raw);
  }
  return parts.join("; ");
}

export function formatBugReportReporter(user: AuthUser | null): string {
  if (!user?.username) return "";
  const email = user.email?.trim();
  return email ? `${user.username} (${email})` : user.username;
}

export function buildBugReportUrl(input: {
  context: BugReportContext;
  user: AuthUser | null;
  pathname: string;
  search: string;
}): string {
  const base =
    process.env.NEXT_PUBLIC_BUG_FORM_URL?.trim() || DEFAULT_BUG_FORM_URL;
  const url = new URL(base);

  const reporter = formatBugReportReporter(input.user);
  if (reporter) url.searchParams.set("reporter", reporter);

  url.searchParams.set("menugroup", input.context.menugroup);
  url.searchParams.set("report", input.context.report);

  const role = input.user?.role_label?.trim() || input.user?.role?.trim();
  if (role) url.searchParams.set("role", role);

  const contour = detectBugReportContour();
  if (contour) url.searchParams.set("contour", contour);

  const browser = detectBugReportBrowser();
  if (browser) url.searchParams.set("browser", browser);

  const filters = formatBugReportFilters(input.pathname, input.search);
  if (filters) url.searchParams.set("filters", filters);

  return url.toString();
}
