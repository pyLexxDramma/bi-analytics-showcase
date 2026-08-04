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
 * Mobile v2: вместо размытого экрана — каркас будущего дашборда.
 * Блюр всей страницы на телефоне читался как «подвисло»; скелетон показывает,
 * что и где появится. Оверлей, а не замена контента: под ним живёт запрос экрана.
 */
export function DashboardSkeleton() {
  return (
    <div
      className="absolute inset-0 z-40 overflow-hidden bg-tremor-background-muted px-3 pt-2 dark:bg-dark-tremor-background-muted"
      aria-busy="true"
      aria-live="polite"
      role="status"
    >
      <span className="sr-only">Загрузка дашборда</span>
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

export function DashboardLoadingOverlay() {
  return (
    <>
      {/* Блок кликов + затемнение по контенту дашборда */}
      <div
        className="absolute inset-0 z-40 bg-white/35 backdrop-blur-sm dark:bg-slate-950/45"
        aria-hidden
      />
      {/* Баннер всегда в центре текущего viewport */}
      <div
        className="pointer-events-none fixed inset-0 z-50 flex items-center justify-center"
        aria-busy="true"
        aria-live="polite"
        role="status"
      >
        <div className="flex flex-col items-center gap-3 rounded-xl border border-tremor-border bg-white/95 px-6 py-5 shadow-lg dark:border-dark-tremor-border dark:bg-slate-900/95">
          <span
            className="h-10 w-10 animate-spin rounded-full border-[3px] border-emerald-600 border-t-transparent dark:border-emerald-400 dark:border-t-transparent"
            aria-hidden
          />
          <span className="text-sm font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
            Загрузка дашборда
          </span>
        </div>
      </div>
    </>
  );
}
