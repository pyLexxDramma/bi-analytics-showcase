"use client";

import { useEffect, useState } from "react";
import { AppSidebar } from "@/components/app-sidebar";

export function AppShell({
  title,
  subtitle,
  children,
}: {
  title: string;
  subtitle?: string;
  children: React.ReactNode;
}) {
  const [dark, setDark] = useState(false);

  useEffect(() => {
    const root = document.documentElement;
    if (dark) root.classList.add("dark");
    else root.classList.remove("dark");
  }, [dark]);

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
              onClick={() => setDark((v) => !v)}
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
