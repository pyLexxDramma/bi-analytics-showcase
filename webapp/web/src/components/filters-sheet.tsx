"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";

/**
 * Mobile v2: панель фильтров на телефоне — лист снизу.
 * Открывается на половину экрана, тянется до полного, закрывается свайпом вниз,
 * по backdrop и по Esc. Кнопки «Сбросить»/«Готово» закреплены снизу.
 *
 * Используется только на `<lg` (см. `FiltersCard`), desktop-аккордеон не меняется.
 */
export function FiltersSheet({
  open,
  onClose,
  title,
  onReset,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  onReset?: () => void;
  children: ReactNode;
}) {
  const [mounted, setMounted] = useState(false);
  const [expanded, setExpanded] = useState(false);
  const [dragY, setDragY] = useState(0);
  const startY = useRef<number | null>(null);
  const scrollRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    if (!open) {
      setExpanded(false);
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

  const onTouchStart = (e: React.TouchEvent) => {
    startY.current = e.touches[0]?.clientY ?? null;
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (startY.current == null) return;
    const delta = (e.touches[0]?.clientY ?? 0) - startY.current;
    // Вверх — раскрыть на полный экран, вниз — тянуть лист к закрытию
    if (delta < -40 && !expanded) {
      setExpanded(true);
      startY.current = e.touches[0]?.clientY ?? null;
      return;
    }
    setDragY(Math.max(0, delta));
  };

  const onTouchEnd = () => {
    if (dragY > 110) {
      tapFeedback();
      onClose();
    }
    setDragY(0);
    startY.current = null;
  };

  return createPortal(
    <div className="bi-sheet-root lg:hidden" role="dialog" aria-modal="true" aria-label={title}>
      <button
        type="button"
        className="bi-sheet-backdrop"
        aria-label="Закрыть фильтры"
        onClick={onClose}
      />
      <div
        className={`bi-sheet-panel ${expanded ? "bi-sheet-panel-full" : ""}`}
        style={dragY ? { transform: `translateY(${dragY}px)` } : undefined}
      >
        <div
          className="bi-sheet-grip-zone"
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
        >
          <span className="bi-sheet-grip" aria-hidden />
          <div className="bi-sheet-title">{title}</div>
        </div>
        <div ref={scrollRef} className="bi-sheet-body">
          {children}
        </div>
        <div className="bi-sheet-actions">
          {onReset ? (
            <button
              type="button"
              className="bi-sheet-btn-ghost"
              onClick={() => {
                confirmFeedback();
                onReset();
              }}
            >
              Сбросить
            </button>
          ) : null}
          <button
            type="button"
            className="bi-sheet-btn-primary"
            onClick={() => {
              confirmFeedback();
              onClose();
            }}
          >
            Готово
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
