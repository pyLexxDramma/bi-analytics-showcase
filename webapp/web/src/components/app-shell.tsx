"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { CommandPalette, openCommandPalette } from "@/components/command-palette";
import {
  DashboardLoadingOverlay,
  DashboardSkeleton,
  useDelayedLoading,
} from "@/components/dashboard-loading";
import { MobileTabBar } from "@/components/mobile-tab-bar";
import { ReportsSearchSheet } from "@/components/reports-search-sheet";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";
import { findNavItem } from "@/lib/nav";
import { pushRecentReport } from "@/lib/recent-reports";
import { useIsMobileViewport } from "@/lib/use-is-mobile";
import {
  applyThemeClass,
  readTheme,
  writeTheme,
  type ThemeMode,
} from "@/lib/theme";

export function AppShell({
  title,
  subtitle,
  loading = false,
  children,
}: {
  title: string;
  subtitle?: string;
  /** Пока true — после 1 с блюр + оверлей «Загрузка дашборда». */
  loading?: boolean;
  children: React.ReactNode;
}) {
  const [dark, setDark] = useState(false);
  const [menuOpen, setMenuOpen] = useState(false);
  const [reportsOpen, setReportsOpen] = useState(false);
  const pathname = usePathname();
  const mobile = useIsMobileViewport();
  const showLoading = useDelayedLoading(loading, mobile ? 400 : 1000);
  const showSkeleton = showLoading && mobile;

  useEffect(() => {
    applyThemeClass(readTheme());
    setDark(readTheme() === "dark");
  }, []);

  useEffect(() => {
    if (!menuOpen) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setMenuOpen(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [menuOpen]);

  // «Недавние» в мобильном поиске отчётов
  useEffect(() => {
    const item = findNavItem(pathname);
    if (item) pushRecentReport(item.href);
  }, [pathname]);

  const setTheme = (mode: ThemeMode) => {
    confirmFeedback();
    setDark(mode === "dark");
    writeTheme(mode);
    applyThemeClass(mode);
  };

  const closeMenu = () => {
    tapFeedback();
    setMenuOpen(false);
  };

  return (
    <div className="min-h-screen bg-tremor-background-muted text-tremor-content-strong dark:bg-dark-tremor-background-muted dark:text-dark-tremor-content-strong lg:flex">
      <div className="hidden lg:block">
        <AppSidebar />
      </div>

      {menuOpen ? (
        <div
          className="bi-safe-area fixed inset-0 z-50 flex flex-col bg-[#f8f9fb] dark:bg-dark-tremor-background lg:hidden"
          role="dialog"
          aria-modal="true"
          aria-label="Меню"
        >
          <div className="flex shrink-0 items-center justify-between border-b border-gray-200 px-3 py-2 dark:border-dark-tremor-border">
            <span className="text-sm font-bold text-[#1f2937] dark:text-dark-tremor-content-strong">
              Меню
            </span>
            <div className="flex items-center gap-2">
              <button
                type="button"
                onClick={() => {
                  tapFeedback();
                  setMenuOpen(false);
                  setReportsOpen(true);
                }}
                className="inline-flex h-11 items-center gap-1.5 rounded-md border border-gray-200 bg-white px-3 text-sm font-medium text-[#1f2937] dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
              >
                <span aria-hidden>🔎</span>
                Поиск
              </button>
              <button
                type="button"
                onClick={closeMenu}
                className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-gray-200 bg-white text-lg font-semibold text-[#1f2937] dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
                aria-label="Закрыть меню"
              >
                ✕
              </button>
            </div>
          </div>
          <div className="min-h-0 flex-1 overflow-hidden">
            <AppSidebar
              onNavigate={closeMenu}
              className="h-full w-full border-r-0"
            />
          </div>
        </div>
      ) : null}

      <div className="relative min-h-screen min-w-0 flex-1 overflow-x-hidden text-tremor-content-strong dark:text-dark-tremor-content-strong">
        <div
          className={`bi-safe-area bi-has-tabbar mx-auto max-w-7xl px-3 py-5 sm:px-6 sm:py-8 lg:px-8 ${
            showLoading
              ? showSkeleton
                ? "pointer-events-none select-none"
                : "pointer-events-none select-none blur-[2px]"
              : ""
          }`}
          aria-hidden={showLoading || undefined}
        >
          <header className="mb-5 flex items-start justify-between gap-2 sm:mb-8 sm:items-center sm:gap-3">
            <div className="flex min-w-0 flex-1 items-start gap-2 sm:gap-3">
              <button
                type="button"
                onClick={() => {
                  tapFeedback();
                  setMenuOpen(true);
                }}
                className="mt-0.5 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-tremor-default border border-tremor-border bg-tremor-background text-lg font-semibold text-tremor-content-emphasis shadow-tremor-input lg:hidden dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis"
                aria-label="Открыть меню"
                aria-expanded={menuOpen}
              >
                ☰
              </button>
              <div className="min-w-0 flex-1">
                <h1 className="break-words text-lg font-bold tracking-tight text-tremor-content-strong sm:text-2xl dark:text-dark-tremor-content-strong">
                  {title}
                </h1>
                {subtitle ? (
                  <p className="mt-1 break-words text-sm text-tremor-content dark:text-dark-tremor-content sm:text-tremor-default">
                    {subtitle}
                  </p>
                ) : null}
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <button
                type="button"
                onClick={openCommandPalette}
                title="Поиск по отчётам"
                className="hidden items-center gap-2 rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default font-medium text-tremor-content-emphasis shadow-tremor-input transition hover:bg-tremor-background-subtle lg:inline-flex dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
              >
                <span aria-hidden>🔎</span>
                Поиск
                <kbd className="rounded border border-tremor-border px-1.5 py-0.5 text-xs text-tremor-content dark:border-dark-tremor-border dark:text-dark-tremor-content">
                  Ctrl K
                </kbd>
              </button>
              <button
                type="button"
                onClick={() => setTheme(dark ? "light" : "dark")}
                className="shrink-0 rounded-tremor-default border border-tremor-border bg-tremor-background px-2.5 py-2 text-sm font-medium text-tremor-content-emphasis shadow-tremor-input transition hover:bg-tremor-background-subtle dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle sm:px-3 sm:text-tremor-default"
              >
                {dark ? "☀ Светлая" : "🌙 Тёмная"}
              </button>
            </div>
          </header>
          <div className="min-w-0 max-w-full">{children}</div>
        </div>
        {showLoading ? (
          showSkeleton ? (
            <DashboardSkeleton />
          ) : (
            <DashboardLoadingOverlay />
          )
        ) : null}
        <MobileTabBar
          onOpenMenu={() => setMenuOpen(true)}
          menuOpen={menuOpen}
          onOpenReports={() => setReportsOpen(true)}
        />
        <ReportsSearchSheet
          open={reportsOpen}
          onClose={() => setReportsOpen(false)}
          onNavigate={() => setMenuOpen(false)}
        />
        <CommandPalette />
      </div>
    </div>
  );
}
