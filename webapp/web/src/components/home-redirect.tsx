"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";
import { isAuthenticated } from "@/lib/auth";
import { firstAccessibleReportHref } from "@/lib/reports-index";

/** `/` → первый отчёт, доступный роли (не всегда «Девелоперские проекты»). */
export function HomeRedirect() {
  const router = useRouter();

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    router.replace(firstAccessibleReportHref());
  }, [router]);

  return (
    <p className="p-8 text-center text-sm text-tremor-content dark:text-dark-tremor-content">
      Перенаправление…
    </p>
  );
}
