"use client";

import { useEffect, useState } from "react";
import { FiltersApply } from "@/components/dashboard-filters";
import { tapFeedback } from "@/lib/haptics";

/**
 * Плавающая панель «Применить» — когда черновик фильтров не применён
 * и панель фильтров ушла за верх экрана.
 */
export function FilterStickyBar({
  anchorRef,
  pending,
  onApply,
  applyDisabled,
}: {
  anchorRef: React.RefObject<HTMLElement | null>;
  pending: boolean;
  onApply: () => void;
  applyDisabled?: boolean;
}) {
  const [show, setShow] = useState(false);

  useEffect(() => {
    const el = anchorRef.current;
    if (!el || !pending) {
      setShow(false);
      return;
    }
    const obs = new IntersectionObserver(
      ([entry]) => {
        setShow(!entry.isIntersecting);
      },
      { root: null, threshold: 0, rootMargin: "-56px 0px 0px 0px" },
    );
    obs.observe(el);
    return () => obs.disconnect();
  }, [anchorRef, pending]);

  if (!pending || !show) return null;

  return (
    <div
      className="bi-filter-sticky-bar fixed inset-x-0 z-[55] flex justify-center px-3 lg:justify-end lg:pr-8"
      style={{
        top: "max(0.5rem, env(safe-area-inset-top, 0px))",
      }}
      role="region"
      aria-label="Неприменённые фильтры"
    >
      <div className="flex max-w-md flex-1 items-center justify-between gap-3 rounded-xl border border-amber-300 bg-amber-50 px-3 py-2 shadow-lg dark:border-amber-700 dark:bg-amber-950/90 lg:max-w-sm lg:flex-none">
        <span className="text-sm text-amber-950 dark:text-amber-100">
          Есть несохранённые фильтры
        </span>
        <FiltersApply
          disabled={applyDisabled}
          onClick={() => {
            tapFeedback();
            onApply();
          }}
        />
      </div>
    </div>
  );
}
