"use client";

import { useEffect, useState } from "react";
import { createPortal } from "react-dom";
import { isTypingTarget } from "@/components/command-palette";

const OPEN_EVENT = "bi:open-shortcuts";

/** Открыть шпаргалку мышью — из кнопки в шапке. */
export function openShortcutsHelp(): void {
  window.dispatchEvent(new Event(OPEN_EVENT));
}

const ROWS: Array<[string, string]> = [
  ["Ctrl + K  /  /", "Поиск по отчётам"],
  ["↑ ↓", "Перебор пунктов в поиске и в списке фильтра"],
  ["Enter", "Открыть отчёт · отметить значение фильтра"],
  ["Home / End", "Первое и последнее значение в списке фильтра"],
  ["Esc", "Закрыть поиск, список фильтра или полноэкранный режим"],
  ["?", "Эта шпаргалка"],
];

/** Список горячих клавиш — только десктоп, на телефоне клавиатуры нет. */
export function ShortcutsHelp() {
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") {
        setOpen(false);
        return;
      }
      if (event.key !== "?" || event.ctrlKey || event.metaKey) return;
      if (isTypingTarget(event.target)) return;
      if (window.matchMedia("(max-width: 1023px)").matches) return;
      event.preventDefault();
      setOpen((state) => !state);
    };
    const onRequest = () => setOpen(true);
    document.addEventListener("keydown", onKey);
    window.addEventListener(OPEN_EVENT, onRequest);
    return () => {
      document.removeEventListener("keydown", onKey);
      window.removeEventListener(OPEN_EVENT, onRequest);
    };
  }, []);

  if (!mounted || !open) return null;

  return createPortal(
    <div
      className="fixed inset-0 z-[75] hidden items-start justify-center p-6 pt-[16vh] lg:flex"
      role="dialog"
      aria-modal="true"
      aria-label="Горячие клавиши"
    >
      <button
        type="button"
        aria-label="Закрыть шпаргалку"
        onClick={() => setOpen(false)}
        className="absolute inset-0 cursor-default bg-slate-900/40 backdrop-blur-[2px]"
      />
      <div className="relative w-full max-w-md overflow-hidden rounded-xl border border-tremor-border bg-tremor-background shadow-2xl dark:border-dark-tremor-border dark:bg-dark-tremor-background">
        <div className="flex items-center justify-between border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
          <span className="text-tremor-default font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
            Горячие клавиши
          </span>
          <kbd className="rounded border border-tremor-border px-1.5 py-0.5 text-xs text-tremor-content dark:border-dark-tremor-border dark:text-dark-tremor-content">
            Esc
          </kbd>
        </div>
        <dl className="divide-y divide-tremor-border p-2 dark:divide-dark-tremor-border">
          {ROWS.map(([keys, text]) => (
            <div key={keys} className="flex items-center gap-3 px-2 py-2">
              <dt className="shrink-0">
                <kbd className="rounded border border-tremor-border px-1.5 py-0.5 text-xs text-tremor-content-emphasis dark:border-dark-tremor-border dark:text-dark-tremor-content-emphasis">
                  {keys}
                </kbd>
              </dt>
              <dd className="min-w-0 flex-1 text-tremor-default text-tremor-content dark:text-dark-tremor-content">
                {text}
              </dd>
            </div>
          ))}
        </dl>
      </div>
    </div>,
    document.body,
  );
}
