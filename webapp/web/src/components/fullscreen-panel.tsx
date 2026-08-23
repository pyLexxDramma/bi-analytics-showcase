"use client";

import {
  useCallback,
  useEffect,
  useRef,
  useState,
  type ReactNode,
} from "react";
import { ChartPngButton } from "@/components/chart-png-button";
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
 * Зум матриц/графиков «на весь экран» как в [main]: выход по ✕ и Esc.
 * Desktop (`lg+`): Fullscreen API + кнопка ⛶.
 * Mobile (`<lg`): кнопка скрыта.
 *
 * BUG-012/019/020+: в active — отдельная шапка с ✕ (не поверх таблицы/графика);
 * контент flex-1 min-h-0 на всю высоту.
 */
export function FullscreenPanel({
  children,
  disabled = false,
  toolbar,
  fill = false,
  /** Имя файла без расширения для кнопки PNG в тулбаре. */
  pngFileStem,
  /** Plotly-зум/панорама в развёрнутом виде. Для ганта — false. */
  chartGestures = true,
  /** false — содержимое прокручивает себя само (у таблицы свой `bi-table-scroll`). */
  scroll = true,
  className = "",
}: {
  children: ReactNode | ((active: boolean) => ReactNode);
  disabled?: boolean;
  toolbar?: ReactNode;
  fill?: boolean;
  pngFileStem?: string;
  chartGestures?: boolean;
  scroll?: boolean;
  className?: string;
}) {
  const hostRef = useRef<HTMLDivElement | null>(null);
  const mobile = useIsMobileViewport();
  const [nativeActive, setNativeActive] = useState(false);
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

  useEffect(() => {
    const kick = () => window.dispatchEvent(new Event("resize"));
    const ids = [0, 80, 200].map((ms) => window.setTimeout(kick, ms));
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
      /* браузер отказал */
    }
  }, [mobile]);

  const inlineBar = !fill && !active;

  return (
    <div
      ref={hostRef}
      className={`relative min-w-0 max-w-full bg-tremor-background dark:bg-dark-tremor-background ${
        fill ? "bi-fs-fill" : "bi-fs-table"
      } ${
        active
          ? "bi-fs-active flex h-screen w-screen flex-col overflow-hidden"
          : inlineBar
            ? ""
            : "overflow-x-auto"
      } ${className}`}
    >
      {!active && (toolbar || !mobile) ? (
        <div
          className={`z-[1002] flex items-center gap-1 ${
            inlineBar
              ? toolbar
                ? "justify-between gap-2 border-b border-tremor-border px-3 py-2 dark:border-dark-tremor-border sm:px-4"
                : "justify-end px-2 pt-2"
              : "absolute right-2 top-2 lg:top-12"
          }`}
        >
          {toolbar}
          {pngFileStem ? (
            <ChartPngButton hostRef={hostRef} fileStem={pngFileStem} />
          ) : null}
          {!mobile ? (
            <FsToggleButton active={false} disabled={disabled} onClick={() => void toggle()} />
          ) : null}
        </div>
      ) : null}

      {active ? (
        <div className="bi-fs-chrome z-[1002] flex shrink-0 items-center justify-end gap-2 border-b border-tremor-border bg-tremor-background px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background">
          {toolbar}
          {pngFileStem ? (
            <ChartPngButton hostRef={hostRef} fileStem={pngFileStem} />
          ) : null}
          <FsToggleButton active disabled={disabled} onClick={() => void toggle()} />
        </div>
      ) : null}

      <div
        className={
          active
            ? fill
              ? "bi-fs-body bi-fs-body-fill flex min-h-0 min-w-0 flex-1 flex-col items-stretch justify-center overflow-hidden py-3 pl-5 pr-3"
              : "bi-fs-body bi-fs-body-table flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden p-3"
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

function FsToggleButton({
  active,
  disabled,
  onClick,
}: {
  active: boolean;
  disabled?: boolean;
  onClick: () => void;
}) {
  return (
    <button
      type="button"
      title={active ? "Выйти из полного экрана (Esc)" : "На весь экран"}
      onClick={onClick}
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
  );
}
