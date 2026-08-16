"use client";

import type { ReactNode } from "react";

/**
 * Одна строка-вывод над KPI из уже загруженных полей. Без новых API.
 * Если `text` пустой — ничего не рендерим.
 */
export function DashboardInsight({
  text,
  className = "",
}: {
  text: ReactNode | null | undefined;
  className?: string;
}) {
  if (text == null || text === false || text === "") return null;
  const empty = typeof text === "string" ? !text.trim() : false;
  if (empty) return null;
  return (
    <div className={`bi-dashboard-insight mb-3 ${className}`} role="status">
      {text}
    </div>
  );
}
