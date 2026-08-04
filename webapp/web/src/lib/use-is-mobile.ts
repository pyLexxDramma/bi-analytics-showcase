"use client";

import { useEffect, useState } from "react";

/** Та же граница, что у Tailwind `lg` и медиазапросов в `globals.css`. */
export const MOBILE_MEDIA_QUERY = "(max-width: 1023px)";

/**
 * Mobile v2: правки тач-поведения включаются только на телефонах/планшетах.
 * Desktop (`lg+`) обязан работать ровно как до цикла Mobile v2.
 *
 * До гидратации возвращает `false` — SSR-разметка совпадает с desktop-веткой.
 */
export function useIsMobileViewport(): boolean {
  const [mobile, setMobile] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(MOBILE_MEDIA_QUERY);
    const sync = () => setMobile(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  return mobile;
}
