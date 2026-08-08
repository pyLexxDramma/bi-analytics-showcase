"use client";

import { usePathname, useRouter } from "next/navigation";
import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { readRecentReports } from "@/lib/recent-reports";
import { recentReports, searchReports, type FlatReport } from "@/lib/reports-index";

const HINT = "Ctrl + K";
const OPEN_EVENT = "bi:open-command-palette";

/** Открыть палитру мышью — из кнопки в шапке. */
export function openCommandPalette(): void {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

type Row = { report: FlatReport; recent: boolean };

/** Не перехватывать одиночные клавиши, пока пользователь набирает текст. */
export function isTypingTarget(target: EventTarget | null): boolean {
  if (!(target instanceof HTMLElement)) return false;
  if (target.isContentEditable) return true;
  const tag = target.tagName;
  return tag === "INPUT" || tag === "TEXTAREA" || tag === "SELECT";
}

/**
 * Быстрый переход по отчётам с клавиатуры — только десктоп: на телефоне ту же
 * роль играет лист `ReportsSearchSheet`. Источник пунктов общий (`nav.ts`).
 */
export function CommandPalette() {
  const router = useRouter();
  const pathname = usePathname();
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const [recents, setRecents] = useState<string[]>([]);
  const inputRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const restoreRef = useRef<HTMLElement | null>(null);

  useEffect(() => setMounted(true), []);

  const close = useCallback(() => {
    setOpen(false);
    restoreRef.current?.focus?.();
  }, []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      const combo = (event.ctrlKey || event.metaKey) && event.key.toLowerCase() === "k";
      // «/» — привычный шорткат поиска, но только когда курсор не в поле ввода
      const slash =
        event.key === "/" &&
        !event.ctrlKey &&
        !event.metaKey &&
        !event.altKey &&
        !isTypingTarget(event.target);
      if (!combo && !slash) return;
      if (window.matchMedia("(max-width: 1023px)").matches) return;
      event.preventDefault();
      setOpen((state) => {
        if (state) return false;
        restoreRef.current =
          document.activeElement instanceof HTMLElement
            ? document.activeElement
            : null;
        return true;
      });
    };
    const onRequest = () => {
      restoreRef.current =
        document.activeElement instanceof HTMLElement
          ? document.activeElement
          : null;
      setOpen(true);
    };
    document.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, onRequest);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, onRequest);
    };
  }, []);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActive(0);
      return;
    }
    setRecents(readRecentReports());
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    const timer = window.setTimeout(() => inputRef.current?.focus(), 0);
    return () => {
      window.clearTimeout(timer);
      document.body.style.overflow = prev;
    };
  }, [open]);

  const rows: Row[] = useMemo(() => {
    const found = searchReports(query);
    if (query.trim()) return found.map((report) => ({ report, recent: false }));
    const recent = recentReports(recents, pathname);
    const rest = found.filter(
      (report) => !recent.some((item) => item.href === report.href),
    );
    return [
      ...recent.map((report) => ({ report, recent: true })),
      ...rest.map((report) => ({ report, recent: false })),
    ];
  }, [query, recents, pathname]);

  useEffect(() => {
    setActive((index) => (index >= rows.length ? 0 : index));
  }, [rows.length]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  if (!mounted || !open) return null;

  const go = (report: FlatReport) => {
    close();
    router.push(report.href);
  };

  const onKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape") {
      event.preventDefault();
      close();
      return;
    }
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => (rows.length ? (index + 1) % rows.length : 0));
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) =>
        rows.length ? (index - 1 + rows.length) % rows.length : 0,
      );
      return;
    }
    if (event.key === "Enter") {
      event.preventDefault();
      const row = rows[active];
      if (row) go(row.report);
    }
  };

  const firstNonRecent = rows.findIndex((row) => !row.recent);

  return createPortal(
    <div
      className="fixed inset-0 z-[70] hidden items-start justify-center p-6 pt-[12vh] lg:flex"
      role="dialog"
      aria-modal="true"
      aria-label="Поиск по отчётам"
    >
      <button
        type="button"
        aria-label="Закрыть поиск"
        onClick={close}
        className="absolute inset-0 cursor-default bg-slate-900/40 backdrop-blur-[2px]"
      />
      <div
        className="relative w-full max-w-xl overflow-hidden rounded-xl border border-tremor-border bg-tremor-background shadow-2xl dark:border-dark-tremor-border dark:bg-dark-tremor-background"
        onKeyDown={onKeyDown}
      >
        <div className="flex items-center gap-2 border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
          <span aria-hidden className="text-tremor-content">
            🔎
          </span>
          <input
            ref={inputRef}
            type="text"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value);
              setActive(0);
            }}
            placeholder="Отчёт или раздел — например, БДДС"
            aria-label="Поиск по отчётам"
            className="min-w-0 flex-1 bg-transparent text-tremor-default text-tremor-content-strong outline-none placeholder:text-tremor-content dark:text-dark-tremor-content-strong"
          />
          <kbd className="rounded border border-tremor-border px-1.5 py-0.5 text-xs text-tremor-content dark:border-dark-tremor-border dark:text-dark-tremor-content">
            Esc
          </kbd>
        </div>

        <div ref={listRef} className="max-h-[52vh] overflow-y-auto p-2">
          {rows.length === 0 ? (
            <p className="px-2 py-8 text-center text-tremor-default text-tremor-content dark:text-dark-tremor-content">
              Ничего не найдено
            </p>
          ) : (
            rows.map((row, index) => (
              <div key={row.report.href}>
                {index === 0 && row.recent ? (
                  <div className="px-2 pb-1 pt-2 text-[0.6875rem] font-bold uppercase tracking-wide text-tremor-content dark:text-dark-tremor-content">
                    Недавние
                  </div>
                ) : null}
                {index === firstNonRecent && firstNonRecent > 0 ? (
                  <div className="px-2 pb-1 pt-3 text-[0.6875rem] font-bold uppercase tracking-wide text-tremor-content dark:text-dark-tremor-content">
                    Все отчёты
                  </div>
                ) : null}
                <button
                  type="button"
                  data-index={index}
                  onMouseEnter={() => setActive(index)}
                  onClick={() => go(row.report)}
                  className={`flex w-full items-center gap-2 rounded-lg px-2.5 py-2 text-left text-tremor-default ${
                    index === active
                      ? "bg-tremor-background-subtle text-tremor-content-strong dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content-strong"
                      : "text-tremor-content-emphasis dark:text-dark-tremor-content-emphasis"
                  }`}
                >
                  <span className="min-w-0 flex-1 truncate">{row.report.label}</span>
                  <span className="shrink-0 text-xs text-tremor-content dark:text-dark-tremor-content">
                    {row.report.group}
                  </span>
                </button>
              </div>
            ))
          )}
        </div>

        <div className="flex items-center justify-between border-t border-tremor-border px-4 py-2 text-xs text-tremor-content dark:border-dark-tremor-border dark:text-dark-tremor-content">
          <span>↑↓ — выбор, Enter — открыть</span>
          <span>
            {HINT} · «/» · «?» — шпаргалка
          </span>
        </div>
      </div>
    </div>,
    document.body,
  );
}
