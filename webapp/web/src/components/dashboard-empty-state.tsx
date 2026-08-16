"use client";

import type { ReactNode } from "react";

/**
 * Единый empty-state отчётов. Только UI — не меняет данные и фильтры сам.
 */
export function DashboardEmptyState({
  message,
  onReset,
  resetLabel = "Сбросить фильтры",
  className = "",
}: {
  message: ReactNode;
  onReset?: () => void;
  resetLabel?: string;
  className?: string;
}) {
  return (
    <div
      className={`bi-empty-state flex flex-col items-center justify-center gap-3 rounded-xl border border-dashed border-tremor-border bg-tremor-background-muted/40 px-4 py-10 text-center dark:border-dark-tremor-border dark:bg-dark-tremor-background-muted/30 ${className}`}
      role="status"
    >
      <p className="max-w-md text-sm text-tremor-content dark:text-dark-tremor-content">
        {message}
      </p>
      {onReset ? (
        <button
          type="button"
          onClick={onReset}
          className="rounded-md border border-tremor-border bg-tremor-background px-3 py-1.5 text-sm font-medium text-tremor-content-strong hover:bg-tremor-background-muted dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
        >
          {resetLabel}
        </button>
      ) : null}
    </div>
  );
}
