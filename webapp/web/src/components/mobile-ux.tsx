"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { Search, X } from "lucide-react";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";

/** Вкладки экрана на мобилке (Обзор / Список / …). Desktop не трогает. */
export function MobilePaneTabs<T extends string>({
  value,
  onChange,
  options,
  className = "",
}: {
  value: T;
  onChange: (v: T) => void;
  options: Array<{ id: T; label: string }>;
  className?: string;
}) {
  return (
    <div
      className={`mb-3 flex gap-1 rounded-xl border border-tremor-border bg-tremor-background p-1 dark:border-dark-tremor-border dark:bg-dark-tremor-background lg:hidden ${className}`}
      role="tablist"
    >
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          role="tab"
          aria-selected={value === opt.id}
          className={`min-h-11 flex-1 rounded-lg px-2 text-sm font-medium ${
            value === opt.id
              ? "bg-sky-600 text-white"
              : "text-tremor-content dark:text-dark-tremor-content"
          }`}
          onClick={() => {
            tapFeedback();
            onChange(opt.id);
          }}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

export function MobileSearchField({
  value,
  onChange,
  placeholder = "Поиск…",
  className = "",
}: {
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
  className?: string;
}) {
  return (
    <div className={`relative lg:hidden ${className}`}>
      <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
      <input
        type="search"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        placeholder={placeholder}
        className="min-h-11 w-full rounded-xl border border-tremor-border bg-tremor-background py-2 pl-9 pr-9 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
      />
      {value ? (
        <button
          type="button"
          className="absolute right-2 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500"
          aria-label="Очистить поиск"
          onClick={() => onChange("")}
        >
          <X className="h-4 w-4" />
        </button>
      ) : null}
    </div>
  );
}

export function MobileFilterChips<T extends string>({
  value,
  onChange,
  options,
  className = "",
}: {
  value: T;
  onChange: (v: T) => void;
  options: Array<{ id: T; label: string }>;
  className?: string;
}) {
  return (
    <div className={`flex gap-1.5 overflow-x-auto pb-0.5 lg:hidden ${className}`}>
      {options.map((opt) => (
        <button
          key={opt.id}
          type="button"
          onClick={() => {
            tapFeedback();
            onChange(opt.id);
          }}
          className={`min-h-9 shrink-0 rounded-full px-3 text-xs font-medium ${
            value === opt.id
              ? "bg-sky-600 text-white"
              : "border border-tremor-border text-tremor-content dark:border-dark-tremor-border dark:text-dark-tremor-content"
          }`}
        >
          {opt.label}
        </button>
      ))}
    </div>
  );
}

/** Якоря «к графику / к таблице» на мобилке. */
export function MobileJumpBar({
  items,
  className = "",
}: {
  items: Array<{ label: string; onClick: () => void; accent?: "sky" | "emerald" | "amber" }>;
  className?: string;
}) {
  const accentCls = {
    sky: "border-sky-200 bg-sky-50 text-sky-900 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100",
    emerald:
      "border-emerald-200 bg-emerald-50 text-emerald-800 dark:border-emerald-800 dark:bg-emerald-950/40 dark:text-emerald-200",
    amber:
      "border-amber-200 bg-amber-50 text-amber-900 dark:border-amber-800 dark:bg-amber-950/40 dark:text-amber-100",
  } as const;
  return (
    <div className={`mb-3 flex flex-wrap gap-2 lg:hidden ${className}`}>
      {items.map((item) => (
        <button
          key={item.label}
          type="button"
          className={`inline-flex min-h-10 items-center gap-1.5 rounded-full border px-3 py-1.5 text-xs font-semibold shadow-sm active:scale-[0.98] ${
            accentCls[item.accent ?? "emerald"]
          }`}
          onClick={() => {
            tapFeedback();
            item.onClick();
          }}
        >
          {item.label}
        </button>
      ))}
    </div>
  );
}

/** Универсальный bottom sheet для деталки на мобилке. */
export function MobileDetailSheet({
  open,
  onClose,
  title,
  children,
  actionLabel = "Готово",
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
  actionLabel?: string;
}) {
  const [mounted, setMounted] = useState(false);
  const [dragY, setDragY] = useState(0);
  const startY = useRef<number | null>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) {
      setDragY(0);
      return;
    }
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") onClose();
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [open, onClose]);

  if (!mounted || !open) return null;

  return createPortal(
    <div className="bi-sheet-root lg:hidden" role="dialog" aria-modal="true" aria-label={title}>
      <button
        type="button"
        className="bi-sheet-backdrop"
        aria-label="Закрыть"
        onClick={onClose}
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
            const delta = (e.touches[0]?.clientY ?? 0) - startY.current;
            setDragY(Math.max(0, delta));
          }}
          onTouchEnd={() => {
            if (dragY > 110) {
              tapFeedback();
              onClose();
            }
            setDragY(0);
            startY.current = null;
          }}
        >
          <span className="bi-sheet-grip" aria-hidden />
          <div className="bi-sheet-title break-words">{title}</div>
        </div>
        <div className="bi-sheet-body">{children}</div>
        <div className="bi-sheet-actions">
          <button
            type="button"
            className="bi-sheet-btn-primary w-full"
            onClick={() => {
              confirmFeedback();
              onClose();
            }}
          >
            {actionLabel}
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}

export function scrollToRef(
  ref: React.RefObject<HTMLElement | null>,
  block: ScrollLogicalPosition = "start",
) {
  ref.current?.scrollIntoView({ behavior: "smooth", block });
}
