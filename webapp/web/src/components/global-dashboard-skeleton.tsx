"use client";

import { useEffect, useState, useSyncExternalStore } from "react";
import { DashboardSkeleton } from "@/components/dashboard-loading";
import {
  getShowSkeleton,
  subscribeNavLoading,
} from "@/lib/nav-loading";
import { applyWideCanvasAttr, readWideCanvas } from "@/lib/view-prefs";

/**
 * Живёт в root layout — не размонтируется при смене раздела.
 * Ровно 1 видимый экран (`100dvh`), без скролла; ширина как у контента (<> / ><).
 */
export function GlobalDashboardSkeletonHost() {
  const show = useSyncExternalStore(
    subscribeNavLoading,
    getShowSkeleton,
    () => false,
  );
  const [everShown, setEverShown] = useState(false);

  useEffect(() => {
    if (show) setEverShown(true);
  }, [show]);

  useEffect(() => {
    applyWideCanvasAttr(readWideCanvas());
  }, []);

  useEffect(() => {
    document.documentElement.classList.toggle("bi-skeleton-active", show);
    return () => document.documentElement.classList.remove("bi-skeleton-active");
  }, [show]);

  if (!everShown) return null;

  return (
    <div
      className={`bi-global-skeleton fixed inset-x-0 top-0 z-[1100] h-dvh max-h-dvh overflow-hidden bg-tremor-background-muted dark:bg-dark-tremor-background-muted ${
        show ? "" : "invisible pointer-events-none"
      }`}
      aria-hidden={!show}
    >
      {/* Как bi-safe-area в AppShell: max-w-7xl или на всю ширину колонки */}
      <div className="bi-global-skeleton-inner mx-auto box-border h-full w-full px-3 sm:px-6 lg:px-8">
        <DashboardSkeleton slowHint fill />
      </div>
    </div>
  );
}
