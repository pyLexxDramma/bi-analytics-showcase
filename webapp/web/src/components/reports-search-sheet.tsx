"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import {
  REPORT_ACCORDIONS,
  REPORT_STANDALONE,
  REPORT_TOP_TAB,
} from "@/lib/nav";
import { readRecentReports } from "@/lib/recent-reports";
import { tapFeedback } from "@/lib/haptics";

type FlatReport = { id: string; href: string; label: string; group: string };

const FLAT_REPORTS: FlatReport[] = [
  {
    id: REPORT_TOP_TAB.id,
    href: REPORT_TOP_TAB.href,
    label: REPORT_TOP_TAB.label,
    group: "Основное",
  },
  ...REPORT_ACCORDIONS.flatMap((acc) =>
    acc.items.map((i) => ({
      id: i.id,
      href: i.href,
      label: i.label,
      group: acc.label,
    })),
  ),
  ...REPORT_STANDALONE.map((i) => ({
    id: i.id,
    href: i.href,
    label: i.label,
    group: "Прочее",
  })),
];

function norm(s: string): string {
  return s.toLowerCase().replace(/ё/g, "е").replace(/\s+/g, " ").trim();
}

/**
 * Поиск по отчётам — лист снизу, только мобильный вьюпорт (`lg:hidden`).
 * Источник пунктов — `nav.ts`, поэтому список всегда совпадает с меню.
 */
export function ReportsSearchSheet({
  open,
  onClose,
  onNavigate,
}: {
  open: boolean;
  onClose: () => void;
  onNavigate?: () => void;
}) {
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [query, setQuery] = useState("");
  const [recents, setRecents] = useState<string[]>([]);
  const [dragY, setDragY] = useState(0);
  const startY = useRef<number | null>(null);
  const inputRef = useRef<HTMLInputElement | null>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setDragY(0);
      return;
    }
    setRecents(readRecentReports());
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const focusTimer = window.setTimeout(() => inputRef.current?.focus(), 220);
    return () => {
      window.clearTimeout(focusTimer);
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  const matches = useMemo(() => {
    const q = norm(query);
    if (!q) return FLAT_REPORTS;
    const words = q.split(" ").filter(Boolean);
    return FLAT_REPORTS.filter((r) => {
      const hay = `${norm(r.label)} ${norm(r.group)}`;
      return words.every((w) => hay.includes(w));
    });
  }, [query]);

  const grouped = useMemo(() => {
    const out: Array<{ group: string; items: FlatReport[] }> = [];
    for (const r of matches) {
      const last = out[out.length - 1];
      if (last && last.group === r.group) last.items.push(r);
      else out.push({ group: r.group, items: [r] });
    }
    return out;
  }, [matches]);

  const recentItems = useMemo(
    () =>
      query.trim()
        ? []
        : recents
            .map((href) => FLAT_REPORTS.find((r) => r.href === href))
            .filter((r): r is FlatReport => Boolean(r) && r!.href !== pathname),
    [recents, query, pathname],
  );

  if (!mounted || !open) return null;

  const close = () => {
    tapFeedback();
    onClose();
  };

  const go = () => {
    tapFeedback();
    onClose();
    onNavigate?.();
  };

  const itemClass = (href: string) =>
    `flex min-h-11 items-center gap-2 rounded-xl border px-3 py-2.5 text-[0.9375rem] leading-snug ${
      pathname === href || pathname.startsWith(`${href}/`)
        ? "border-emerald-300 bg-[#e8f5e9] font-semibold text-emerald-900 dark:border-emerald-700 dark:bg-emerald-950/40 dark:text-emerald-100"
        : "border-gray-200 bg-white text-gray-800 dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
    }`;

  return createPortal(
    <div
      className="bi-sheet-root lg:hidden"
      role="dialog"
      aria-modal="true"
      aria-label="Поиск по отчётам"
    >
      <button
        type="button"
        className="bi-sheet-backdrop"
        aria-label="Закрыть поиск"
        onClick={close}
      />
      <div
        className="bi-sheet-panel bi-sheet-panel-full"
        style={dragY ? { transform: `translateY(${dragY}px)` } : undefined}
      >
        <div
          className="bi-sheet-grip-zone"
          onTouchStart={(e) => {
            startY.current = e.touches[0]?.clientY ?? null;
          }}
          onTouchMove={(e) => {
            if (startY.current == null) return;
            setDragY(Math.max(0, (e.touches[0]?.clientY ?? 0) - startY.current));
          }}
          onTouchEnd={() => {
            if (dragY > 110) close();
            setDragY(0);
            startY.current = null;
          }}
        >
          <span className="bi-sheet-grip" aria-hidden />
          <div className="bi-sheet-title">Отчёты</div>
        </div>

        <div className="shrink-0 px-4 pb-2">
          <input
            ref={inputRef}
            type="search"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Поиск отчёта — например, БДДС"
            aria-label="Поиск по отчётам"
            className="h-11 w-full rounded-xl border border-tremor-border bg-tremor-background px-3 text-tremor-default text-tremor-content-strong outline-none focus:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
          />
        </div>

        <div className="bi-sheet-body">
          {recentItems.length > 0 ? (
            <section className="mb-3">
              <div className="mb-1.5 text-[0.6875rem] font-bold uppercase tracking-wide text-gray-500 dark:text-dark-tremor-content">
                Недавние
              </div>
              <div className="flex flex-col gap-1.5">
                {recentItems.map((r) => (
                  <Link
                    key={`recent-${r.id}`}
                    href={r.href}
                    onClick={go}
                    className={itemClass(r.href)}
                  >
                    <span aria-hidden>🕘</span>
                    <span className="min-w-0 flex-1 break-words">{r.label}</span>
                  </Link>
                ))}
              </div>
            </section>
          ) : null}

          {grouped.length === 0 ? (
            <p className="py-6 text-center text-tremor-default text-gray-500 dark:text-dark-tremor-content">
              Ничего не найдено
            </p>
          ) : (
            grouped.map((g) => (
              <section key={g.group} className="mb-3">
                <div className="mb-1.5 text-[0.6875rem] font-bold uppercase tracking-wide text-gray-500 dark:text-dark-tremor-content">
                  {g.group}
                </div>
                <div className="flex flex-col gap-1.5">
                  {g.items.map((r) => (
                    <Link
                      key={r.id}
                      href={r.href}
                      onClick={go}
                      className={itemClass(r.href)}
                    >
                      <span className="min-w-0 flex-1 break-words">{r.label}</span>
                    </Link>
                  ))}
                </div>
              </section>
            ))
          )}
        </div>

        <div className="bi-sheet-actions">
          <button type="button" className="bi-sheet-btn-primary" onClick={close}>
            Закрыть
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
