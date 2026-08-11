"use client";

import { useEffect, useState } from "react";
import { usePathname } from "next/navigation";
import { AskAiButton, AskAiTitleChip } from "@/components/ask-ai-button";
import { AppSidebar } from "@/components/app-sidebar";
import { CommandPalette, openCommandPalette } from "@/components/command-palette";
import { DataFreshnessBadge } from "@/components/data-freshness-badge";
import {
  DashboardSkeleton,
  useDelayedLoading,
} from "@/components/dashboard-loading";
import { MobileTabBar } from "@/components/mobile-tab-bar";
import { ReportsSearchSheet } from "@/components/reports-search-sheet";
import { ShortcutsHelp, openShortcutsHelp } from "@/components/shortcuts-help";
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
import {
  readDensity,
  readWideCanvas,
  writeDensity,
  writeWideCanvas,
  type Density,
} from "@/lib/view-prefs";
import { fetchAuthMe } from "@/lib/api";
import { canAccessReport, isAuthenticated, logout, saveAuthSession } from "@/lib/auth";

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
  const [wide, setWide] = useState(false);
  const [density, setDensity] = useState<Density>("comfortable");
  const [accessDenied, setAccessDenied] = useState(false);
  const pathname = usePathname();
  const mobile = useIsMobileViewport();
  const showLoading = useDelayedLoading(loading, mobile ? 400 : 1000);

  useEffect(() => {
    applyThemeClass(readTheme());
    setDark(readTheme() === "dark");
    setWide(readWideCanvas());
    setDensity(readDensity());
  }, []);

  // Битый токен после смены WEBAPP_AUTH_SECRET — сброс, иначе отчёты/логин ломаются.
  useEffect(() => {
    if (!isAuthenticated()) return;
    let cancelled = false;
    void fetchAuthMe()
      .then((data) => {
        if (cancelled) return;
        saveAuthSession(data.user);
        const nav = findNavItem(pathname);
        if (nav && !canAccessReport(nav.id, data.user)) {
          setAccessDenied(true);
        } else {
          setAccessDenied(false);
        }
      })
      .catch(() => {
        if (cancelled) return;
        logout();
        window.location.assign("/login?reason=session");
      });
    return () => {
      cancelled = true;
    };
  }, [pathname]);

  useEffect(() => {
    const nav = findNavItem(pathname);
    if (!nav) {
      setAccessDenied(false);
      return;
    }
    setAccessDenied(!canAccessReport(nav.id));
  }, [pathname]);

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

  const toggleWide = () => {
    setWide((state) => {
      writeWideCanvas(!state);
      return !state;
    });
  };

  const toggleDensity = () => {
    setDensity((state) => {
      const next: Density = state === "compact" ? "comfortable" : "compact";
      writeDensity(next);
      return next;
    });
  };

  return (
    <div
      className={`min-h-screen bg-tremor-background-muted text-tremor-content-strong dark:bg-dark-tremor-background-muted dark:text-dark-tremor-content-strong lg:flex ${
        density === "compact" ? "bi-density-compact" : ""
      }`}
    >
      <div className="hidden lg:block">
        <AppSidebar collapsible />
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
          className={`bi-safe-area bi-has-tabbar mx-auto px-3 py-5 sm:px-6 sm:py-8 lg:px-8 ${
            wide ? "max-w-7xl lg:max-w-none" : "max-w-7xl"
          } ${showLoading ? "pointer-events-none select-none" : ""}`}
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
                <div className="flex min-w-0 items-start gap-2">
                  <h1 className="min-w-0 flex-1 break-words text-lg font-bold tracking-tight text-tremor-content-strong sm:text-2xl dark:text-dark-tremor-content-strong">
                    {title}
                  </h1>
                  <AskAiTitleChip />
                </div>
                {subtitle ? (
                  <p className="mt-1 break-words text-sm text-tremor-content dark:text-dark-tremor-content sm:text-tremor-default">
                    {subtitle}
                  </p>
                ) : null}
                <DataFreshnessBadge />
              </div>
            </div>
            <div className="flex shrink-0 items-center gap-2">
              <AskAiButton />
              <button
                type="button"
                onClick={toggleWide}
                title={
                  wide
                    ? "Вернуть ограниченную ширину"
                    : "Растянуть отчёт во всю ширину экрана"
                }
                aria-pressed={wide}
                className="hidden h-10 w-10 items-center justify-center rounded-tremor-default border border-tremor-border bg-tremor-background text-tremor-default text-tremor-content-emphasis shadow-tremor-input transition hover:bg-tremor-background-subtle lg:inline-flex dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
              >
                <span aria-hidden>{wide ? "><" : "<>"}</span>
                <span className="sr-only">Ширина полотна</span>
              </button>
              <button
                type="button"
                onClick={toggleDensity}
                title={
                  density === "compact"
                    ? "Обычная высота строк"
                    : "Компактные строки — больше данных на экран"
                }
                aria-pressed={density === "compact"}
                className="hidden h-10 w-10 items-center justify-center rounded-tremor-default border border-tremor-border bg-tremor-background text-tremor-default text-tremor-content-emphasis shadow-tremor-input transition hover:bg-tremor-background-subtle lg:inline-flex dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
              >
                <span aria-hidden>{density === "compact" ? "☰" : "≡"}</span>
                <span className="sr-only">Плотность строк</span>
              </button>
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
                onClick={openShortcutsHelp}
                title="Горячие клавиши"
                className="hidden h-10 w-10 items-center justify-center rounded-tremor-default border border-tremor-border bg-tremor-background text-tremor-default text-tremor-content-emphasis shadow-tremor-input transition hover:bg-tremor-background-subtle lg:inline-flex dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
              >
                <span aria-hidden>?</span>
                <span className="sr-only">Горячие клавиши</span>
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
          <div className="min-w-0 max-w-full">
            {accessDenied ? (
              <div className="rounded-xl border border-amber-200 bg-amber-50 px-5 py-8 dark:border-amber-800 dark:bg-amber-950/40">
                <h2 className="text-lg font-semibold text-amber-950 dark:text-amber-100">
                  Нет доступа
                </h2>
                <p className="mt-2 text-sm text-amber-900/80 dark:text-amber-200/80">
                  У вашей роли нет прав на этот дашборд. Выберите другой отчёт в
                  меню или обратитесь к администратору.
                </p>
              </div>
            ) : (
              children
            )}
          </div>
        </div>
        {showLoading ? <DashboardSkeleton wide={!mobile} /> : null}
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
        <ShortcutsHelp />
      </div>
    </div>
  );
}
