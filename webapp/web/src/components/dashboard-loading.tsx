"use client";

import { useEffect, useState } from "react";

/** Показывать оверлей сразу (delay 0) или после `delayMs`. */
export function useDelayedLoading(loading: boolean, delayMs = 0): boolean {
  const [show, setShow] = useState(() => Boolean(loading) && delayMs <= 0);

  useEffect(() => {
    if (!loading) {
      setShow(false);
      return;
    }
    if (delayMs <= 0) {
      setShow(true);
      return;
    }
    const id = window.setTimeout(() => setShow(true), delayMs);
    return () => window.clearTimeout(id);
  }, [loading, delayMs]);

  return show;
}

/** Текст для долгих запросов (БДДС, ГДРС). */
export function useSlowLoadingHint(loading: boolean, delayMs = 9000): boolean {
  const [slow, setSlow] = useState(false);
  useEffect(() => {
    if (!loading) {
      setSlow(false);
      return;
    }
    const id = window.setTimeout(() => setSlow(true), delayMs);
    return () => window.clearTimeout(id);
  }, [loading, delayMs]);
  return slow;
}

/**
 * Статичный каркас ровно на 1 видимый экран: только flex/fr, без фиксированных
 * высот, которые выталкивают скролл. Скролл страницы гасится на хосте.
 */
export function DashboardSkeleton({
  slowHint = false,
  fill = false,
}: {
  slowHint?: boolean;
  fill?: boolean;
}) {
  return (
    <div
      className={`${
        fill ? "relative h-full w-full" : "absolute inset-0 z-[1100]"
      } box-border flex max-h-full min-h-0 flex-col overflow-hidden bg-tremor-background-muted py-3 lg:py-4 dark:bg-dark-tremor-background-muted`}
      aria-busy="true"
      aria-live="polite"
      role="status"
    >
      <span className="sr-only">Загрузка дашборда</span>

      <div className="mb-2 flex h-4 shrink-0 items-center justify-center">
        {slowHint ? (
          <p className="truncate text-center text-xs text-tremor-content dark:text-dark-tremor-content">
            <span className="lg:hidden">Загрузка может занять 15–30 с</span>
            <span className="hidden lg:inline">
              Загрузка может занять 15–30 с — данные не изменятся
            </span>
          </p>
        ) : null}
      </div>

      <div className="bi-skeleton mb-2 h-9 w-full shrink-0 rounded-xl lg:mb-3 lg:h-10" aria-hidden />

      <div
        className="mb-2 hidden shrink-0 grid-cols-3 gap-2 lg:mb-3 lg:grid lg:gap-3"
        aria-hidden
      >
        <div className="bi-skeleton h-14 rounded-xl" />
        <div className="bi-skeleton h-14 rounded-xl" />
        <div className="bi-skeleton h-14 rounded-xl" />
      </div>

      {/* Две зоны делят оставшуюся высоту — без basis-% и без px-высот графиков */}
      <div
        className="mb-2 grid min-h-0 flex-[1.15] grid-cols-1 gap-2 lg:mb-3 lg:grid-cols-2 lg:gap-3"
        aria-hidden
      >
        <div className="bi-skeleton h-full min-h-0 rounded-xl" />
        <div className="bi-skeleton hidden h-full min-h-0 rounded-xl lg:block" />
      </div>

      <div className="flex min-h-0 flex-1 flex-col gap-1.5 lg:hidden" aria-hidden>
        {[0, 1, 2].map((i) => (
          <div key={i} className="flex min-h-0 flex-1 flex-col gap-1">
            <div className="bi-skeleton h-2.5 w-1/2 shrink-0 rounded" />
            <div className="grid min-h-0 flex-1 grid-cols-2 gap-1">
              <div className="bi-skeleton h-full min-h-0 rounded-md" />
              <div className="bi-skeleton h-full min-h-0 rounded-md" />
            </div>
          </div>
        ))}
      </div>

      <div className="hidden min-h-0 flex-1 flex-col gap-1.5 lg:flex" aria-hidden>
        <div className="bi-skeleton h-3.5 w-1/5 shrink-0 rounded" />
        {[0, 1, 2, 3, 4, 5, 6].map((row) => (
          <div key={row} className="bi-skeleton min-h-0 flex-1 rounded-md" />
        ))}
      </div>
    </div>
  );
}
