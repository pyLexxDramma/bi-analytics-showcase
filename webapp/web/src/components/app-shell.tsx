"use client";

import { useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { AppSidebar } from "@/components/app-sidebar";
import { isAuthenticated } from "@/lib/auth";
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
  const router = useRouter();
  const [dark, setDark] = useState(false);
  const [ready, setReady] = useState(false);

  useEffect(() => {
    if (!isAuthenticated()) {
      router.replace("/login");
      return;
    }
    const mode = readTheme();
    setDark(mode === "dark");
    applyThemeClass(mode);
    setReady(true);
  }, [router]);

  const setTheme = (mode: ThemeMode) => {
    setDark(mode === "dark");
    writeTheme(mode);
    applyThemeClass(mode);
  };

  if (!ready) {
    return (
      <div className="flex min-h-full items-center justify-center bg-slate-50 text-slate-500 dark:bg-slate-900 dark:text-slate-400">
        Проверка сессии…
      </div>
    );
  }

  return (
    <div className="min-h-full bg-tremor-background-muted text-tremor-content-strong dark:bg-dark-tremor-background-muted dark:text-dark-tremor-content-strong lg:flex">
      <AppSidebar />
      <div className="flex-1 overflow-x-hidden text-tremor-content-strong dark:text-dark-tremor-content-strong">
        <div className="mx-auto max-w-7xl px-4 py-8 sm:px-6 lg:px-8">
          <header className="mb-8 flex items-center justify-between gap-4">
            <div>
              <h1 className="text-2xl font-bold tracking-tight text-tremor-content-strong dark:text-dark-tremor-content-strong">
                {title}
              </h1>
              {subtitle ? (
                <p className="mt-1 text-tremor-default text-tremor-content dark:text-dark-tremor-content">
                  {subtitle}
                </p>
              ) : null}
            </div>
            <button
              type="button"
              onClick={() => setTheme(dark ? "light" : "dark")}
              className="rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default font-medium text-tremor-content-emphasis shadow-tremor-input transition hover:bg-tremor-background-subtle dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
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
