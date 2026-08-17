"use client";

import { useEffect, useRef, useState, type ReactNode } from "react";
import { createPortal } from "react-dom";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";

/**
 * Bottom sheet для правки одного лота на мобилке.
 * Стиль как FiltersSheet (`bi-sheet-*`), кнопка «Готово» закрывает лист.
 */
export function BddsLotEditSheet({
  open,
  onClose,
  title,
  children,
}: {
  open: boolean;
  onClose: () => void;
  title: string;
  children: ReactNode;
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

  const onTouchStart = (e: React.TouchEvent) => {
    startY.current = e.touches[0]?.clientY ?? null;
  };

  const onTouchMove = (e: React.TouchEvent) => {
    if (startY.current == null) return;
    const delta = (e.touches[0]?.clientY ?? 0) - startY.current;
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
        aria-label="Закрыть"
        onClick={onClose}
      />
      <div
        className="bi-sheet-panel bi-sheet-panel-full"
        style={dragY ? { transform: `translateY(${dragY}px)` } : undefined}
      >
        <div
          className="bi-sheet-grip-zone"
          onTouchStart={onTouchStart}
          onTouchMove={onTouchMove}
          onTouchEnd={onTouchEnd}
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
            Готово
          </button>
        </div>
      </div>
    </div>,
    document.body,
  );
}
