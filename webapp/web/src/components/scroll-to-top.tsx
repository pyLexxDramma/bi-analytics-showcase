"use client";

import { useEffect, useState } from "react";
import { tapFeedback } from "@/lib/haptics";

const SHOW_AFTER_PX = 280;

/**
 * Кнопка «наверх»: появляется после скролла вниз, скрывается у верха страницы.
 * z-index ниже меню (50) и FiltersSheet (70), чтобы не перекрывать модалки.
 */
export function ScrollToTopButton({ hidden = false }: { hidden?: boolean }) {
  const [visible, setVisible] = useState(false);

  useEffect(() => {
    const sync = () => {
      const y =
        window.scrollY ||
        document.documentElement.scrollTop ||
        document.body.scrollTop ||
        0;
      setVisible(y > SHOW_AFTER_PX);
    };
    sync();
    window.addEventListener("scroll", sync, { passive: true });
    return () => window.removeEventListener("scroll", sync);
  }, []);

  if (hidden || !visible) return null;

  return (
    <button
      type="button"
      className="bi-scroll-top"
      aria-label="Наверх страницы"
      title="Наверх"
      onClick={() => {
        tapFeedback();
        window.scrollTo({ top: 0, behavior: "smooth" });
      }}
    >
      <span aria-hidden>↑</span>
    </button>
  );
}
