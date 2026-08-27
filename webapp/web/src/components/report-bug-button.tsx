"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import {
  buildBugReportUrl,
  resolveBugReportContext,
} from "@/lib/bug-report";
import { getAuthSession, type AuthUser } from "@/lib/auth";
import { tapFeedback } from "@/lib/haptics";

/**
 * Desktop-only: открывает баг-форму с автозаполнением контекста страницы.
 * На мобиле не рендерим (класс lg:flex).
 */
export function ReportBugButton({ pageTitle }: { pageTitle?: string }) {
  const pathname = usePathname();
  const [user, setUser] = useState<AuthUser | null>(null);

  useEffect(() => {
    setUser(getAuthSession());
  }, [pathname]);

  const context = resolveBugReportContext(pathname, pageTitle);
  const available = context != null;

  const run = useCallback(() => {
    if (!context) return;
    tapFeedback();
    const url = buildBugReportUrl({
      context,
      user,
      pathname,
      search: typeof window !== "undefined" ? window.location.search : "",
    });
    window.open(url, "_blank", "noopener,noreferrer");
  }, [context, user, pathname]);

  if (!available) return null;

  return (
    <div className="hidden lg:flex lg:flex-col lg:items-end lg:gap-1">
      <button
        type="button"
        onClick={run}
        title="Сообщить об ошибке на этом экране"
        className="report-bug-btn inline-flex h-11 items-center gap-2 rounded-tremor-default px-4 text-tremor-default transition"
      >
        <span aria-hidden className="text-base leading-none">
          !
        </span>
        Сообщить об ошибке
      </button>
    </div>
  );
}
