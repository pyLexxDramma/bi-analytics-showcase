"use client";

import { useEffect, useRef } from "react";

/**
 * На мобиле: потянуть вниз у верхнего края — перезагрузить данные экрана
 * (тот же callback, что и после «Применить»).
 */
export function usePullToRefresh(
  enabled: boolean,
  onRefresh: () => void,
): void {
  const startY = useRef(0);
  const pulling = useRef(false);
  const fired = useRef(false);

  useEffect(() => {
    if (!enabled || typeof window === "undefined") return;
    const mq = window.matchMedia("(max-width: 1023px)");
    if (!mq.matches) return;

    const onStart = (e: TouchEvent) => {
      if (window.scrollY > 8) return;
      startY.current = e.touches[0]?.clientY ?? 0;
      pulling.current = true;
      fired.current = false;
    };

    const onMove = (e: TouchEvent) => {
      if (!pulling.current || fired.current) return;
      const y = e.touches[0]?.clientY ?? 0;
      if (y - startY.current > 90 && window.scrollY <= 8) {
        fired.current = true;
        pulling.current = false;
        onRefresh();
      }
    };

    const onEnd = () => {
      pulling.current = false;
    };

    document.addEventListener("touchstart", onStart, { passive: true });
    document.addEventListener("touchmove", onMove, { passive: true });
    document.addEventListener("touchend", onEnd, { passive: true });
    return () => {
      document.removeEventListener("touchstart", onStart);
      document.removeEventListener("touchmove", onMove);
      document.removeEventListener("touchend", onEnd);
    };
  }, [enabled, onRefresh]);
}
