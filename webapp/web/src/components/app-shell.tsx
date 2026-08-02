"use client";

import { useEffect, useState } from "react";
import { AppSidebar } from "@/components/app-sidebar";
import {
  applyThemeClass,
  readTheme,
  writeTheme,
  type ThemeMode,
} from "@/lib/theme";

export function AppShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  const [dark, setDark] = useState(true);
  const [menuOpen, setMenuOpen] = useState(false);

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

  const setTheme = (mode: ThemeMode) => {
    setDark(mode === "dark");
    writeTheme(mode);
    applyThemeClass(mode);
  };

  const closeMenu = () => setMenuOpen(false);

  return (
    <div className="min-h-screen bg-tremor-background-muted text-tremor-content-strong dark:bg-dark-tremor-background-muted dark:text-dark-tremor-content-strong lg:flex">
      {/* Desktop: sticky sidebar in flow */}
      <div className="hidden lg:block">
        <AppSidebar />
      </div>

      {/* Mobile/tablet: drawer overlay */}
      {menuOpen ? (
        <div className="fixed inset-0 z-50 lg:hidden" role="dialog" aria-modal="true">
          <button
            type="button"
            className="absolute inset-0 bg-black/45"
            aria-label="Закрыть меню"
            onClick={closeMenu}
          />
          <div className="absolute inset-y-0 left-0 flex w-[min(100%,280px)] max-w-[85vw] shadow-xl">
            <AppSidebar onNavigate={closeMenu} className="h-full w-full" />
          </div>
        </div>
      ) : null}

      <div className="flex-1 overflow-x-hidden text-tremor-content-strong dark:text-dark-tremor-content-strong">
        <div className="mx-auto max-w-7xl px-4 py-6 sm:px-6 sm:py-8 lg:px-8">
          <header className="mb-6 flex items-center justify-between gap-3 sm:mb-8">
            <div className="flex min-w-0 items-start gap-3">
              <button
                type="button"
                onClick={() => setMenuOpen(true)}
                className="mt-0.5 inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-tremor-default border border-tremor-border bg-tremor-background text-lg font-semibold text-tremor-content-emphasis shadow-tremor-input lg:hidden dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis"
                aria-label="Открыть меню"
                aria-expanded={menuOpen}
              >
                ☰
              </button>
              <div className="min-w-0">
                <h1 className="text-xl font-bold tracking-tight text-tremor-content-strong sm:text-2xl dark:text-dark-tremor-content-strong">
                  {title}
                </h1>
                {subtitle ? (
                  <p className="mt-1 text-tremor-default text-tremor-content dark:text-dark-tremor-content">
                    {subtitle}
                  </p>
                ) : null}
              </div>
            </div>
            <button
              type="button"
              onClick={() => setTheme(dark ? "light" : "dark")}
              className="shrink-0 rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default font-medium text-tremor-content-emphasis shadow-tremor-input transition hover:bg-tremor-background-subtle dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
            >
              {dark ? "☀ Светлая" : "🌙 Тёмная"}
            </button>
          </header>
          {children}
        </div>
      </div>
    </div>
  );
}
