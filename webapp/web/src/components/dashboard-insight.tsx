"use client";

import type { ReactNode } from "react";

/**
 * Одна строка-вывод над KPI из уже загруженных полей. Без новых API.
 * Если `text` пустой — ничего не рендерим.
 */
export function DashboardInsight({
  text: _text,
  className: _className = "",
}: {
  text: ReactNode | null | undefined;
  className?: string;
}) {
  return null;
}
