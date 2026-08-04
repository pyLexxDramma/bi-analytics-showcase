"use client";

import { useEffect, useState } from "react";

/** Та же граница, что у Tailwind `lg` и медиазапросов в `globals.css`. */
export const MOBILE_MEDIA_QUERY = "(max-width: 1023px)";
export const LANDSCAPE_MEDIA_QUERY = "(orientation: landscape)";

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

/** Альбомная ориентация — для широкого режима ганта после «Развернуть». */
export function useIsLandscape(): boolean {
  const [landscape, setLandscape] = useState(false);

  useEffect(() => {
    const mq = window.matchMedia(LANDSCAPE_MEDIA_QUERY);
    const sync = () => setLandscape(mq.matches);
    sync();
    mq.addEventListener("change", sync);
    return () => mq.removeEventListener("change", sync);
  }, []);

  return landscape;
}
