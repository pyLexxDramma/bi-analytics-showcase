"use client";

import { useEffect, useRef, useState } from "react";
import { copyTextSync } from "@/lib/clipboard";

/**
 * «Скопировать ссылку» — десктопный аналог мобильного «Поделиться».
 * Адрес содержит выбранные фильтры (`useUrlFilterState`), поэтому коллега
 * открывает ровно тот же срез.
 */
export function CopyLinkButton({ label = "Скопировать ссылку" }: { label?: string }) {
  const [state, setState] = useState<"idle" | "done" | "fail">("idle");
  const timerRef = useRef<number | null>(null);

  useEffect(
    () => () => {
      if (timerRef.current) window.clearTimeout(timerRef.current);
    },
    [],
  );

  const copy = () => {
    const ok = copyTextSync(window.location.href);
    setState(ok ? "done" : "fail");
    if (timerRef.current) window.clearTimeout(timerRef.current);
    timerRef.current = window.setTimeout(() => setState("idle"), 2000);
  };

  return (
    <button
      type="button"
      onClick={copy}
      title="Ссылка откроет этот отчёт с текущими фильтрами"
      className="hidden items-center gap-1.5 rounded-md border border-tremor-border bg-white/90 px-2.5 py-1 text-sm shadow-sm lg:inline-flex dark:border-dark-tremor-border dark:bg-slate-900/90"
    >
      <span aria-hidden>🔗</span>
      {state === "done"
        ? "Ссылка скопирована"
        : state === "fail"
          ? "Не удалось скопировать"
          : label}
    </button>
  );
}
