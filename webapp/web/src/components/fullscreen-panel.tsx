"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ChartInteractiveProvider } from "@/lib/chart-interaction";
import { tapFeedback } from "@/lib/haptics";
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
 * Mobile v2: на `<lg` вместо Fullscreen API (iOS Safari не разворачивает `div`)
 * используется fixed-оверлей; внутри него графику возвращается зум/панорама.
 * Desktop-ветка — прежний Fullscreen API, без изменений.
 */
export function FullscreenPanel({
  children,
  disabled = false,
  toolbar,
  fill = false,
  className = "",
}: {
  /** Функция получает признак фуллскрина — контент может увеличить масштаб. */
  children: ReactNode | ((active: boolean) => ReactNode);
  disabled?: boolean;
  /** Кнопки рядом с зумом (например «Скачать таблицу»). */
  toolbar?: ReactNode;
  /** Растянуть контент на весь экран вместо центрирования (графики). */
  fill?: boolean;
  className?: string;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mobile = useIsMobileViewport();
  const [nativeActive, setNativeActive] = useState(false);
  const [overlayActive, setOverlayActive] = useState(false);
  const active = mobile ? overlayActive : nativeActive;

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

  useEffect(() => {
    if (!mobile) setOverlayActive(false);
  }, [mobile]);

  useEffect(() => {
    if (!overlayActive) return;
    const onKey = (e: KeyboardEvent) => {
      if (e.key === "Escape") setOverlayActive(false);
    };
    document.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden";
    return () => {
      document.removeEventListener("keydown", onKey);
      document.body.style.overflow = prev;
    };
  }, [overlayActive]);

  const toggle = useCallback(async () => {
    if (mobile) {
      tapFeedback();
      setOverlayActive((v) => !v);
      return;
    }
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
        active
          ? mobile
            ? "bi-fs-mobile-overlay fixed inset-0 z-[60] overflow-auto"
            : "h-screen w-screen overflow-auto"
          : "overflow-x-auto"
      } ${className}`}
    >
      <div
        className={`z-40 flex items-center gap-1 ${
          active
            ? "fixed right-3 top-3 lg:top-12"
            : fill
              ? // ниже Plotly modebar (~28px), не в одном ряду с иконками
                "absolute right-2 top-2 lg:top-12"
              : // таблицы: контент обычно с pt-10 под кнопку
                "absolute right-2 top-2 lg:top-10"
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
      {/* min-w-fit — иначе при контенте шире экрана justify-center срезает левый край */}
      <div
        className={
          active
            ? fill
              ? "h-full w-full"
              : "flex min-h-full min-w-fit items-center justify-center p-4"
            : ""
        }
      >
        <ChartInteractiveProvider active={active}>
          {typeof children === "function" ? children(active) : children}
        </ChartInteractiveProvider>
      </div>
    </div>
  );
}
