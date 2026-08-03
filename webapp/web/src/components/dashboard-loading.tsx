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
