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
  /** false — содержимое прокручивает себя само (у таблицы свой `bi-table-scroll`). */
  scroll = true,
  className = "",
}: {
  children: ReactNode | ((active: boolean) => ReactNode);
  disabled?: boolean;
  toolbar?: ReactNode;
  fill?: boolean;
  chartGestures?: boolean;
  scroll?: boolean;
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

  // Element fullscreen не меняет window.innerWidth (Safari/Mac особенно).
  // Пинок resize после смены layout — Plotly пересчитывает ширину.
  useEffect(() => {
    const kick = () => window.dispatchEvent(new Event("resize"));
    const ids = [0, 50, 160, 400].map((ms) => window.setTimeout(kick, ms));
    const raf = requestAnimationFrame(() => requestAnimationFrame(kick));
    return () => {
      ids.forEach((id) => window.clearTimeout(id));
      cancelAnimationFrame(raf);
    };
  }, [nativeActive]);

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

  // У таблиц кнопка стоит отдельной строкой над содержимым: поверх шапки она
  // перекрывала последнюю колонку. У графиков угол свободен — там оставляем поверх.
  const inlineBar = !fill && !active;

  return (
    <div
      ref={hostRef}
      className={`relative min-w-0 max-w-full bg-tremor-background dark:bg-dark-tremor-background ${
        fill ? "bi-fs-fill" : "bi-fs-table"
      } ${
        active
          ? fill
            ? "bi-fs-active h-screen w-screen overflow-auto"
            : "bi-fs-active flex h-screen w-screen flex-col overflow-hidden"
          : inlineBar
            ? ""
            : "overflow-x-auto"
      } ${className}`}
    >
      {!mobile ? (
        <div
          // Modebar Plotly держит z-index 1001 и перехватывал клик по ⛶
          className={`z-[1002] flex items-center gap-1 ${
            active
              ? "fixed right-3 top-3 lg:top-12"
              : inlineBar
                ? "justify-end px-2 pt-2"
                : "absolute right-2 top-2 lg:top-12"
          }`}
        >
          {toolbar}
          <button
            type="button"
            title={active ? "Выйти из полного экрана (Esc)" : "На весь экран"}
            onClick={() => void toggle()}
            disabled={disabled}
            aria-label={active ? "Выйти из полного экрана" : "На весь экран"}
            className={`bi-fs-toggle ${active ? "bi-fs-toggle-active" : ""}`}
          >
            {active ? (
              <span className="bi-fs-toggle-icon" aria-hidden>
                ✕
              </span>
            ) : (
              <svg
                className="bi-fs-toggle-icon"
                width="18"
                height="18"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden
              >
                <path
                  d="M8 3H5a2 2 0 0 0-2 2v3M16 3h3a2 2 0 0 1 2 2v3M8 21H5a2 2 0 0 1-2-2v-3M16 21h3a2 2 0 0 0 2-2v-3"
                  stroke="currentColor"
                  strokeWidth="2.25"
                  strokeLinecap="round"
                  strokeLinejoin="round"
                />
              </svg>
            )}
          </button>
        </div>
      ) : null}
      <div
        className={
          active
            ? fill
              ? "h-full w-full"
              : // Таблица короче экрана — по центру по вертикали; высокая — скролл внутри .bi-table-scroll
                "flex min-h-0 min-w-0 flex-1 flex-col justify-center overflow-hidden p-4"
            : inlineBar
              ? `min-w-0 max-w-full ${scroll ? "overflow-x-auto" : "overflow-x-hidden"}`
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
