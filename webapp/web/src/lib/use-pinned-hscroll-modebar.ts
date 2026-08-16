"use client";

import { useEffect, useRef } from "react";

/**
 * Modebar Plotly при гориз. скролле широкого графика — всегда справа в viewport
 * (как main `_finance_plotly_hscroll_modebar_pin_*`).
 */
export function usePinnedHScrollModebar(enabled: boolean, rev: string) {
  const wrapRef = useRef<HTMLDivElement | null>(null);
  useEffect(() => {
    if (!enabled) return;
    const wrap = wrapRef.current;
    if (!wrap) return;
    const pin = () => {
      const mb = wrap.querySelector(".modebar") as HTMLElement | null;
      const inner = wrap.querySelector(
        ".js-plotly-plot, .plotly-graph-div",
      ) as HTMLElement | null;
      if (!mb || !inner) return;
      const tx = wrap.scrollLeft + wrap.clientWidth - inner.offsetWidth;
      mb.style.setProperty("transform", `translateX(${tx}px)`, "important");
      mb.style.setProperty("z-index", "1001", "important");
    };
    wrap.addEventListener("scroll", pin, { passive: true });
    window.addEventListener("resize", pin);
    const mo = new MutationObserver(pin);
    mo.observe(wrap, { childList: true, subtree: true });
    const t1 = window.setTimeout(pin, 120);
    const t2 = window.setTimeout(pin, 600);
    const t3 = window.setTimeout(pin, 1500);
    return () => {
      wrap.removeEventListener("scroll", pin);
      window.removeEventListener("resize", pin);
      mo.disconnect();
      window.clearTimeout(t1);
      window.clearTimeout(t2);
      window.clearTimeout(t3);
      const mb = wrap.querySelector(".modebar") as HTMLElement | null;
      mb?.style.removeProperty("transform");
    };
  }, [enabled, rev]);
  return wrapRef;
}
