"use client";

import { useEffect, useState } from "react";
import { AppSidebar } from "@/components/app-sidebar";
import {
  DashboardLoadingOverlay,
  DashboardSkeleton,
  useDelayedLoading,
} from "@/components/dashboard-loading";
import { ScrollToTopButton } from "@/components/scroll-to-top";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";
import { useIsMobileViewport } from "@/lib/use-is-mobile";
import {
  applyThemeClass,
  readTheme,
  writeTheme,
  type ThemeMode,
} from "@/lib/theme";

const OPEN_MENU_KEY = "bi_showcase_open_menu";

function isMobileViewport(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia("(max-width: 1023px)").matches;
}

/** Вызвать после логина — на mobile AppShell откроет drawer. */
export function requestMobileMenuOnNextLoad(): void {
  try {
    sessionStorage.setItem(OPEN_MENU_KEY, "1");
  } catch {
    /* ignore */
  }
}

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
  const mobile = useIsMobileViewport();
  const showLoading = useDelayedLoading(loading, mobile ? 400 : 1000);
  const showSkeleton = showLoading && mobile;

  useEffect(() => {
    applyThemeClass(readTheme());
    setDark(readTheme() === "dark");
  }, []);

  useEffect(() => {
    try {
      if (sessionStorage.getItem(OPEN_MENU_KEY) === "1" && isMobileViewport()) {
        sessionStorage.removeItem(OPEN_MENU_KEY);
        setMenuOpen(true);
      }
    } catch {
      /* ignore */
    }
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
            <button
              type="button"
              onClick={closeMenu}
              className="inline-flex h-11 w-11 items-center justify-center rounded-md border border-gray-200 bg-white text-lg font-semibold text-[#1f2937] dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
              aria-label="Закрыть меню"
            >
              ✕
            </button>
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
          className={`bi-safe-area mx-auto max-w-7xl px-3 py-5 sm:px-6 sm:py-8 lg:px-8 ${
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
            <button
              type="button"
              onClick={() => setTheme(dark ? "light" : "dark")}
              className="shrink-0 rounded-tremor-default border border-tremor-border bg-tremor-background px-2.5 py-2 text-sm font-medium text-tremor-content-emphasis shadow-tremor-input transition hover:bg-tremor-background-subtle dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle sm:px-3 sm:text-tremor-default"
            >
              {dark ? "☀ Светлая" : "🌙 Тёмная"}
            </button>
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
        <ScrollToTopButton hidden={menuOpen || showLoading} />
      </div>
    </div>
  );
}
