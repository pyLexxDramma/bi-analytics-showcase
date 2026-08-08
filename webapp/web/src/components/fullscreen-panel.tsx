"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ChartInteractiveProvider } from "@/lib/chart-interaction";
import { useIsMobileViewport } from "@/lib/use-is-mobile";

type FullscreenDocument = Document & {
  webkitFullscreenElement?: Element;
  webkitExitFullscreen?: () => Promise<void>;
};

type FullscreenElement = HTMLElement & {
  webkitRequestFullscreen?: () => Promise<void>;
};

/**
 * Зум матриц/графиков «на весь экран» как в [main]: выход по ✕ и Esc,
 * состояние экрана (фильтры, данные) не сбрасывается — меняется только контейнер.
 *
 * Desktop (`lg+`): Fullscreen API + кнопка ⛶.
 * Mobile (`<lg`): кнопка скрыта (временно) — контент как обычно; позже вернём точечно.
 */
export function FullscreenPanel({
  children,
  disabled = false,
  toolbar,
  fill = false,
  /** Plotly-зум/панорама в развёрнутом виде. Для ганта — false: иначе touch-action:none ломает скролл. */
  chartGestures = true,
  className = "",
}: {
  children: ReactNode | ((active: boolean) => ReactNode);
  disabled?: boolean;
  toolbar?: ReactNode;
  fill?: boolean;
  chartGestures?: boolean;
  className?: string;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mobile = useIsMobileViewport();
  const [nativeActive, setNativeActive] = useState(false);
  // Mobile: fullscreen выключен — кнопка не показывается.
  const active = mobile ? false : nativeActive;

  useEffect(() => {
    const sync = () => {
      const host = hostRef.current;
      const doc = document as FullscreenDocument;
      const current = document.fullscreenElement || doc.webkitFullscreenElement;
      setNativeActive(!!host && current === host);
    };
    document.addEventListener("fullscreenchange", sync);
    document.addEventListener("webkitfullscreenchange", sync);
    return () => {
      document.removeEventListener("fullscreenchange", sync);
      document.removeEventListener("webkitfullscreenchange", sync);
    };
  }, []);

  const toggle = useCallback(async () => {
    if (mobile) return;
    const host = hostRef.current;
    if (!host) return;
    const doc = document as FullscreenDocument;
    const current = document.fullscreenElement || doc.webkitFullscreenElement;
    try {
      if (current === host) {
        if (document.exitFullscreen) await document.exitFullscreen();
        else if (doc.webkitExitFullscreen) await doc.webkitExitFullscreen();
        return;
      }
      const el = host as FullscreenElement;
      if (el.requestFullscreen) await el.requestFullscreen();
      else if (el.webkitRequestFullscreen) await el.webkitRequestFullscreen();
    } catch {
      /* браузер отказал в fullscreen — экран остаётся рабочим */
    }
  }, [mobile]);

  return (
    <div
      ref={hostRef}
      className={`relative min-w-0 max-w-full bg-tremor-background dark:bg-dark-tremor-background ${
        fill ? "bi-fs-fill" : "bi-fs-table"
      } ${
        active ? "bi-fs-active h-screen w-screen overflow-auto" : "overflow-x-auto"
      } ${className}`}
    >
      {!mobile ? (
        <div
          className={`z-40 flex items-center gap-1 ${
            active
              ? "fixed right-3 top-3 lg:top-12"
              : fill
                ? "absolute right-2 top-2 lg:top-12"
                : "absolute right-2 top-2 lg:top-10"
          }`}
        >
          {toolbar}
          <button
            type="button"
            title={active ? "Выйти из полного экрана (Esc)" : "На весь экран"}
            onClick={() => void toggle()}
            disabled={disabled}
            aria-label={active ? "Выйти из полного экрана" : "На весь экран"}
            className={`bi-fs-toggle rounded-md border-0 bg-transparent px-2 py-1 text-sm text-slate-500 shadow-none hover:text-teal-700 disabled:opacity-40 dark:text-slate-400 dark:hover:text-teal-300 ${
              active ? "bi-fs-toggle-active" : ""
            }`}
          >
            {active ? "✕" : "⛶"}
          </button>
        </div>
      ) : null}
      <div
        className={
          active
            ? fill
              ? "h-full w-full"
              : "flex min-h-full min-w-fit items-center justify-center p-4"
            : ""
        }
      >
        <ChartInteractiveProvider active={active && chartGestures}>
          {typeof children === "function" ? children(active) : children}
        </ChartInteractiveProvider>
      </div>
    </div>
  );
}
