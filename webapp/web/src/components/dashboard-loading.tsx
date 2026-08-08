"use client";

import { useEffect, useState } from "react";

/** Показывать оверлей только если загрузка длится дольше `delayMs`. */
export function useDelayedLoading(loading: boolean, delayMs = 1000): boolean {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (!loading) {
      setShow(false);
      return;
    }
    const id = window.setTimeout(() => setShow(true), delayMs);
    return () => window.clearTimeout(id);
  }, [loading, delayMs]);

  return show;
}

/**
 * Вместо размытого экрана — каркас будущего дашборда: блюр читался как
 * «подвисло», а скелетон показывает, что и где появится. Оверлей, а не замена
 * контента: под ним живёт запрос экрана.
 *
 * На десктопе каркас другой: фильтры, пара графиков в ряд и таблица.
 */
/** Каркас без движения читается как «зависло» — рядом всегда живой индикатор. */
function LoadingBadge() {
  return (
    <div className="pointer-events-none sticky top-4 z-10 mb-3 flex justify-center">
      <span className="inline-flex items-center gap-2 rounded-full border border-tremor-border bg-white/95 px-4 py-2 text-sm font-medium text-tremor-content-strong shadow-lg dark:border-dark-tremor-border dark:bg-slate-900/95 dark:text-dark-tremor-content-strong">
        <span
          className="h-4 w-4 animate-spin rounded-full border-2 border-emerald-600 border-t-transparent dark:border-emerald-400 dark:border-t-transparent"
          aria-hidden
        />
        Загрузка дашборда
      </span>
    </div>
  );
}

export function DashboardSkeleton({ wide = false }: { wide?: boolean }) {
  if (wide) {
    return (
      <div
        className="absolute inset-0 z-40 overflow-hidden bg-tremor-background-muted px-8 pt-2 dark:bg-dark-tremor-background-muted"
        aria-busy="true"
        aria-live="polite"
        role="status"
      >
        <span className="sr-only">Загрузка дашборда</span>
        <LoadingBadge />
        <div className="bi-skeleton mb-4 h-16 w-full rounded-xl" aria-hidden />
        <div className="mb-4 grid grid-cols-2 gap-4">
          <div className="bi-skeleton h-64 rounded-xl" aria-hidden />
          <div className="bi-skeleton h-64 rounded-xl" aria-hidden />
        </div>
        <div className="rounded-xl border border-tremor-border p-4 dark:border-dark-tremor-border">
          <div className="bi-skeleton mb-3 h-5 w-1/4 rounded" aria-hidden />
          {[0, 1, 2, 3, 4, 5].map((row) => (
            <div key={row} className="bi-skeleton mb-2 h-6 w-full rounded" aria-hidden />
          ))}
        </div>
      </div>
    );
  }

  return (
    <div
      className="absolute inset-0 z-40 overflow-hidden bg-tremor-background-muted px-3 pt-2 dark:bg-dark-tremor-background-muted"
      aria-busy="true"
      aria-live="polite"
      role="status"
    >
      <span className="sr-only">Загрузка дашборда</span>
      <LoadingBadge />
      <div className="bi-skeleton mb-4 h-12 w-full rounded-xl" aria-hidden />
      <div className="bi-skeleton mb-4 h-56 w-full rounded-xl" aria-hidden />
      {[0, 1, 2].map((i) => (
        <div key={i} className="mb-3 rounded-xl border border-tremor-border p-3 dark:border-dark-tremor-border">
          <div className="bi-skeleton mb-3 h-4 w-2/3 rounded" aria-hidden />
          <div className="grid grid-cols-2 gap-2">
            <div className="bi-skeleton h-12 rounded-lg" aria-hidden />
            <div className="bi-skeleton h-12 rounded-lg" aria-hidden />
            <div className="bi-skeleton h-12 rounded-lg" aria-hidden />
            <div className="bi-skeleton h-12 rounded-lg" aria-hidden />
          </div>
        </div>
      ))}
    </div>
  );
}

