"use client";

import { Children, useEffect, useState, type ReactNode } from "react";
import { StatusPill, type StatusPillTone } from "@/components/status-pill";
import { tapFeedback } from "@/lib/haptics";

/** Shared mobile card shell (customer presentation style). */

export function MobileEntityCard({
  title,
  badge,
  badgeTone = "neutral",
  children,
  more,
  moreLabel = "Подробнее",
  className = "",
}: {
  title: ReactNode;
  badge?: ReactNode;
  badgeTone?: StatusPillTone;
  children: ReactNode;
  /** Второстепенные метрики: скрыты, раскрываются тапом (mobile v2). */
  more?: ReactNode;
  moreLabel?: string;
  className?: string;
}) {
  const [expanded, setExpanded] = useState(false);
  return (
    <article
      className={`bi-mobile-card overflow-hidden rounded-xl border-[3px] border-[#94a3b8] bg-tremor-background shadow-sm dark:border-slate-400 dark:bg-dark-tremor-background ${className}`}
    >
      <header className="flex flex-wrap items-center justify-between gap-2 border-b-2 border-[#94a3b8] bg-slate-100 px-3 py-2.5 dark:border-slate-400 dark:bg-slate-800">
        <h3 className="text-sm font-bold leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong">
          {title}
        </h3>
        {badge != null ? (
          typeof badge === "string" || typeof badge === "number" ? (
            <StatusPill tone={badgeTone}>{badge}</StatusPill>
          ) : (
            badge
          )
        ) : null}
      </header>
      <div className="px-3 py-3">
        {children}
        {more != null ? (
          <>
            {expanded ? <div className="mt-2">{more}</div> : null}
            <button
              type="button"
              onClick={() => {
                tapFeedback();
                setExpanded((v) => !v);
              }}
              aria-expanded={expanded}
              className="bi-card-more mt-2"
            >
              {expanded ? "Свернуть" : moreLabel}
              <span aria-hidden>{expanded ? " ▴" : " ▾"}</span>
            </button>
          </>
        ) : null}
      </div>
    </article>
  );
}

export function MobileMetricGrid({
  items,
  columns = 3,
}: {
  items: Array<{
    label: string;
    value: ReactNode;
    className?: string;
    /** Desktop-like cell tint: date blue / bad red / ok green */
    highlight?: "none" | "date" | "bad" | "ok";
  }>;
  columns?: 2 | 3 | 4;
}) {
  const cols =
    columns === 2 ? "grid-cols-2" : columns === 4 ? "grid-cols-2 sm:grid-cols-4" : "grid-cols-3";
  return (
    <div className={`grid gap-2 text-center text-[11px] ${cols}`}>
      {items.map((item) => {
        const hl = item.highlight ?? "none";
        // Непрозрачные пары фон/текст: на тёмной теме тинты с альфой давали серую кашу
        const cellTint =
          hl === "date"
            ? "bg-[#dbeafe] text-slate-900 dark:bg-[#1e3a5f] dark:text-slate-50"
            : hl === "bad"
              ? "bg-rose-100 text-rose-950 dark:bg-rose-900 dark:text-rose-50"
              : hl === "ok"
                ? "bg-emerald-100 text-emerald-950 dark:bg-emerald-900 dark:text-emerald-50"
                : "bg-slate-50 text-slate-900 dark:bg-slate-800 dark:text-slate-50";
        return (
          <div
            key={item.label}
            className={`rounded-lg border-2 border-[#cbd5e1] px-1.5 py-2 dark:border-slate-500 ${cellTint}`}
          >
            <div className="mb-1 font-bold uppercase tracking-wide opacity-70">
              {item.label}
            </div>
            <div className={`font-semibold tabular-nums ${item.className ?? ""}`}>
              {item.value}
            </div>
          </div>
        );
      })}
    </div>
  );
}

/**
 * Mobile v2: длинные стеки (ДЗ/КЗ — сотни договоров) рендерятся порциями,
 * иначе телефон «думает» на первом кадре и скролл дёргается.
 * `pinned` — сводная карточка (ИТОГО) над списком, видна без прокрутки.
 */
export function MobileCardStack({
  children,
  pinned,
  pageSize = 40,
  compact = false,
}: {
  children: ReactNode;
  pinned?: ReactNode;
  pageSize?: number;
  /** Раньше: отступ под кнопку fullscreen; на mobile кнопка скрыта. */
  compact?: boolean;
}) {
  const items = Children.toArray(children);
  const [limit, setLimit] = useState(pageSize);

  useEffect(() => {
    setLimit(pageSize);
  }, [pageSize, items.length]);

  const visible = items.slice(0, limit);
  const rest = items.length - visible.length;

  return (
    <div
      className={`flex flex-col gap-3 px-2 pb-2 lg:hidden ${compact ? "pt-2" : "pt-3"}`}
    >
      {pinned}
      {visible}
      {rest > 0 ? (
        <div className="flex gap-2">
          <button
            type="button"
            className="bi-card-more-btn flex-1"
            onClick={() => {
              tapFeedback();
              setLimit((v) => v + pageSize);
            }}
          >
            Показать ещё {Math.min(rest, pageSize)}
          </button>
          <button
            type="button"
            className="bi-card-more-btn"
            onClick={() => {
              tapFeedback();
              setLimit(items.length);
            }}
          >
            Все {items.length}
          </button>
        </div>
      ) : null}
    </div>
  );
}

/** Сегментированный контрол сортировки карточек (mobile v2). */
export function MobileSortControl<T extends string>({
  value,
  options,
  onChange,
  desc,
  onToggleDir,
}: {
  value: T;
  options: Array<{ value: T; label: string }>;
  onChange: (next: T) => void;
  desc: boolean;
  onToggleDir: () => void;
}) {
  return (
    <div className="mb-3 flex items-center gap-2 px-2 lg:hidden">
      <div className="bi-segmented flex-1">
        {options.map((opt) => (
          <button
            key={opt.value}
            type="button"
            onClick={() => {
              tapFeedback();
              onChange(opt.value);
            }}
            aria-pressed={value === opt.value}
            className={value === opt.value ? "bi-segmented-on" : ""}
          >
            {opt.label}
          </button>
        ))}
      </div>
      <button
        type="button"
        onClick={() => {
          tapFeedback();
          onToggleDir();
        }}
        className="bi-card-more-btn"
        aria-label={desc ? "По убыванию" : "По возрастанию"}
      >
        {desc ? "↓" : "↑"}
      </button>
    </div>
  );
}
