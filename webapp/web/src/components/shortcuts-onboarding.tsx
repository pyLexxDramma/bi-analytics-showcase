"use client";

import { useEffect, useState } from "react";
import { openCommandPalette } from "@/components/command-palette";
import { openShortcutsHelp } from "@/components/shortcuts-help";
import {
  dismissShortcutsHint,
  shouldShowShortcutsHint,
} from "@/lib/onboarding-hints";

/** Одноразовая подсказка про Ctrl+K и ? — только desktop. */
export function ShortcutsOnboarding() {
  const [show, setShow] = useState(false);

  useEffect(() => {
    if (window.matchMedia("(max-width: 1023px)").matches) return;
    if (shouldShowShortcutsHint()) setShow(true);
  }, []);

  if (!show) return null;

  return (
    <div
      className="bi-onboarding-hint fixed bottom-6 right-6 z-[60] hidden max-w-sm rounded-xl border border-sky-200 bg-white p-4 shadow-xl dark:border-sky-800 dark:bg-slate-900 lg:block"
      role="dialog"
      aria-label="Подсказка по горячим клавишам"
    >
      <p className="text-sm font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong">
        Быстрая навигация
      </p>
      <p className="mt-1 text-sm text-tremor-content dark:text-dark-tremor-content">
        <kbd className="rounded border px-1">Ctrl K</kbd> или{" "}
        <kbd className="rounded border px-1">/</kbd> — поиск отчётов.{" "}
        <kbd className="rounded border px-1">?</kbd> — все сочетания.
      </p>
      <div className="mt-3 flex flex-wrap gap-2">
        <button
          type="button"
          className="rounded-lg bg-sky-600 px-3 py-1.5 text-sm text-white"
          onClick={() => {
            dismissShortcutsHint();
            setShow(false);
            openCommandPalette();
          }}
        >
          Попробовать
        </button>
        <button
          type="button"
          className="rounded-lg border px-3 py-1.5 text-sm"
          onClick={() => {
            dismissShortcutsHint();
            setShow(false);
            openShortcutsHelp();
          }}
        >
          Все клавиши
        </button>
        <button
          type="button"
          className="rounded-lg px-3 py-1.5 text-sm text-tremor-content dark:text-dark-tremor-content"
          onClick={() => {
            dismissShortcutsHint();
            setShow(false);
          }}
        >
          Закрыть
        </button>
      </div>
    </div>
  );
}
