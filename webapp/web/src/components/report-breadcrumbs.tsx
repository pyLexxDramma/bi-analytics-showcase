"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { findNavTrail } from "@/lib/nav";

/** Раздел → отчёт под заголовком (desktop + mobile). */
export function ReportBreadcrumbs() {
  const pathname = usePathname();
  const trail = findNavTrail(pathname);
  if (trail.length < 2) return null;

  return (
    <nav
      aria-label="Навигация по разделам"
      className="mb-1 flex flex-wrap items-center gap-1 text-xs text-tremor-content dark:text-dark-tremor-content"
    >
      <Link
        href="/developer-projects"
        className="rounded px-0.5 hover:text-tremor-content-strong dark:hover:text-dark-tremor-content-strong"
      >
        Отчёты
      </Link>
      {trail.map((crumb, i) => (
        <span key={`${crumb.label}-${i}`} className="inline-flex items-center gap-1">
          <span aria-hidden className="opacity-50">
            /
          </span>
          {crumb.href ? (
            <Link
              href={crumb.href}
              className="rounded px-0.5 hover:text-tremor-content-strong dark:hover:text-dark-tremor-content-strong"
            >
              {crumb.label}
            </Link>
          ) : (
            <span className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
              {crumb.label}
            </span>
          )}
        </span>
      ))}
    </nav>
  );
}
