"use client";

import { useCallback, useEffect, useMemo, useRef, useState, type ComponentProps } from "react";
import Plotly from "plotly.js-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";
import { useChartInteractive } from "@/lib/chart-interaction";
import { bindChartLegendHost } from "@/lib/chart-legend-host";
import { useIsMobileViewport } from "@/lib/use-is-mobile";

/**
 * Plotly-компонент для графиков паритета с [main]: там графики строятся на Plotly,
 * и только он даёт ту же панель инструментов (PNG, зум, панорама, выделение,
 * автомасштаб, сброс). Отдельный модуль — чтобы грузить его через `next/dynamic`
 * с `ssr: false` (plotly.js трогает `window` на импорте).
 *
 * Hover/tooltip и серая подсветка категории отключены глобально на всех дашбордах
 * (подписи значений на графике остаются).
 *
 * Mobile v2: на `<lg` полотно не перехватывает жесты (`dragmode: false`,
 * `scrollZoom: false`), иначе палец рисует рамку зума вместо прокрутки страницы.
 * В развёрнутом виде (`ChartInteractiveProvider`) интерактив возвращается.
 * Desktop-поведение не меняется.
 */
const RawPlotlyFigure = createPlotlyComponent(Plotly);

type PlotProps = ComponentProps<typeof RawPlotlyFigure>;

function withoutHoverData(data: PlotProps["data"]): PlotProps["data"] {
  if (!Array.isArray(data)) return data;
  return data.map((trace) => {
    if (!trace || typeof trace !== "object") return trace;
    return {
      ...trace,
      hoverinfo: "skip",
      hovertemplate: null,
    };
  }) as PlotProps["data"];
}

function withoutHoverLayout(
  layout: PlotProps["layout"],
  lockGestures: boolean,
): PlotProps["layout"] {
  const base =
    layout && typeof layout === "object"
      ? { ...(layout as Record<string, unknown>) }
      : {};
  const hasFixedWidth = typeof base.width === "number";
  if (!hasFixedWidth) {
    delete base.width;
    base.autosize = true;
  }
  const prevLegend =
    base.legend && typeof base.legend === "object"
      ? (base.legend as Record<string, unknown>)
      : {};
  return {
    ...base,
    hovermode: false,
    legend: {
      ...prevLegend,
      itemclick: prevLegend.itemclick ?? "toggle",
      itemdoubleclick: prevLegend.itemdoubleclick ?? "toggleothers",
    },
    ...(lockGestures ? { dragmode: false } : {}),
  } as PlotProps["layout"];
}

function withoutGestureConfig(
  config: PlotProps["config"],
  lockGestures: boolean,
): PlotProps["config"] {
  if (!lockGestures) return config;
  const base =
    config && typeof config === "object" ? { ...(config as object) } : {};
  return {
    ...base,
    scrollZoom: false,
    doubleClick: false,
  } as PlotProps["config"];
}

/** Не дать зуму «потерять» данные (BUG-029/032): слишком узкий диапазон → reset. */
function clampZoomRelayout(
  gd: HTMLElement & { layout?: Record<string, unknown> },
  eventData: Record<string, unknown> | undefined,
) {
  if (!eventData || typeof eventData !== "object") return;
  const layout = gd.layout || {};
  const xRange = (eventData["xaxis.range[0]"] != null &&
    eventData["xaxis.range[1]"] != null
    ? [Number(eventData["xaxis.range[0]"]), Number(eventData["xaxis.range[1]"])]
    : (layout.xaxis as { range?: number[] } | undefined)?.range) as
    | number[]
    | undefined;
  if (!xRange || xRange.length < 2) return;
  const span = Math.abs(xRange[1] - xRange[0]);
  if (!Number.isFinite(span) || span >= 0.05) return;
  try {
    Plotly.relayout(gd as Parameters<typeof Plotly.relayout>[0], {
      "xaxis.autorange": true,
      "yaxis.autorange": true,
    });
  } catch {
    /* ignore */
  }
}

function legendNameHidden(name: string, hidden: Set<string>): boolean {
  const n = name.trim();
  if (hidden.has(name) || hidden.has(n)) return true;
  for (const item of hidden) {
    if (item.trim() === n) return true;
  }
  return false;
}

function applyLegendHidden(
  data: PlotProps["data"],
  hidden: Set<string>,
): PlotProps["data"] {
  if (!Array.isArray(data) || hidden.size === 0) {
    if (!Array.isArray(data)) return data;
    return data.map((trace) => {
      if (!trace || typeof trace !== "object") return trace;
      const t = trace as { type?: string; visible?: unknown };
      if (t.type === "pie") return { ...trace, hiddenlabels: [] };
      if (t.visible === "legendonly") return { ...trace, visible: true };
      return trace;
    }) as PlotProps["data"];
  }
  return data.map((trace) => {
    if (!trace || typeof trace !== "object") return trace;
    const t = trace as {
      type?: string;
      name?: string;
      labels?: unknown[];
      visible?: unknown;
    };
    if (t.visible === false) return trace;
    if (t.type === "pie") {
      const labels = (t.labels ?? []).map(String);
      const hiddenlabels = labels.filter((lab) =>
        [...hidden].some((name) => lab === name || lab.startsWith(`${name} (`)),
      );
      return { ...trace, hiddenlabels };
    }
    if (typeof t.name === "string" && legendNameHidden(t.name, hidden)) {
      return { ...trace, visible: "legendonly" };
    }
    if (t.visible === "legendonly") return { ...trace, visible: true };
    return trace;
  }) as PlotProps["data"];
}

/** Высота из layout, если задана числом — плейсхолдер не «прыгает». */
function layoutHeight(layout: PlotProps["layout"]): number | undefined {
  const h = (layout as { height?: unknown } | undefined)?.height;
  return typeof h === "number" ? h : undefined;
}

export default function PlotlyFigure(props: PlotProps) {
  const mobile = useIsMobileViewport();
  const interactive = useChartInteractive();
  const lockGestures = mobile && !interactive;

  // График монтируется, только когда до него доскроллили: на тяжёлых отчётах
  // это заметно ускоряет первый экран. На десктопе запас больше — курсор
  // прокручивает быстрее пальца.
  // Компонент грузится через next/dynamic с ssr: false, поэтому стартуем
  // с заглушки без риска расхождения разметки при гидратации.
  const [visible, setVisible] = useState(false);
  const holderRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (visible) return;
    const el = holderRef.current;
    if (!el || typeof IntersectionObserver === "undefined") {
      setVisible(true);
      return;
    }
    // Заглушка нулевой высоты (layout без числового height) в IntersectionObserver
    // никогда не «пересекается» — график остался бы пустым листом навсегда.
    const margin = mobile ? 320 : 800;
    const rect = el.getBoundingClientRect();
    if (rect.top < window.innerHeight + margin && rect.bottom > -margin) {
      setVisible(true);
      return;
    }
    const io = new IntersectionObserver(
      (entries) => {
        if (entries.some((e) => e.isIntersecting)) {
          setVisible(true);
          io.disconnect();
        }
      },
      { rootMargin: `${margin}px 0px` },
    );
    io.observe(el);
    return () => io.disconnect();
  }, [visible, mobile]);

  // Печать не прокручивает страницу: без этого в PDF попали бы заглушки.
  useEffect(() => {
    if (visible) return;
    const show = () => setVisible(true);
    window.addEventListener("beforeprint", show);
    return () => window.removeEventListener("beforeprint", show);
  }, [visible]);

  const [legendHidden, setLegendHidden] = useState<Set<string>>(() => new Set());
  const legendHiddenRef = useRef(legendHidden);
  legendHiddenRef.current = legendHidden;
  const legendListeners = useRef(new Set<() => void>());

  const toggleLegend = useCallback((name: string) => {
    setLegendHidden((prev) => {
      const next = new Set(prev);
      if (next.has(name)) next.delete(name);
      else next.add(name);
      return next;
    });
  }, []);

  useEffect(() => {
    legendListeners.current.forEach((fn) => fn());
  }, [legendHidden]);

  const data = useMemo(
    () => applyLegendHidden(withoutHoverData(props.data), legendHidden),
    [props.data, legendHidden],
  );
  const layout = useMemo(
    () => withoutHoverLayout(props.layout, lockGestures),
    [props.layout, lockGestures],
  );
  const config = useMemo(
    () => withoutGestureConfig(props.config, lockGestures),
    [props.config, lockGestures],
  );

  // `height: 100%` в контейнере без заданной высоты Plotly вместе с
  // useResizeHandler иногда схлопывает в 0 — график остаётся пустым листом.
  // Числовая высота из layout делает контейнер определённым.
  const heightPx = layoutHeight(props.layout);
  const fillWidth =
    props.style?.width == null ||
    props.style.width === "100%" ||
    props.style.width === "100";
  const style =
    heightPx && (props.style?.height == null || props.style.height === "100%")
      ? {
          ...props.style,
          ...(fillWidth ? { width: "100%" } : {}),
          height: heightPx,
        }
      : props.style;
  const wrapRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    const el = wrapRef.current;
    if (!el) return;
    return bindChartLegendHost(el, {
      get hidden() {
        return legendHiddenRef.current;
      },
      toggle: toggleLegend,
      subscribe: (listener) => {
        legendListeners.current.add(listener);
        return () => {
          legendListeners.current.delete(listener);
        };
      },
    });
  }, [visible, toggleLegend]);

  useEffect(() => {
    if (!visible) return;
    const wrap = wrapRef.current;
    if (!wrap || !fillWidth) return;

    const resize = () => {
      const gd = wrap.querySelector(".js-plotly-plot") as
        | (HTMLElement & { data?: unknown })
        | null;
      if (!gd || !gd.data) return;
      try {
        Plotly.Plots.resize(gd);
      } catch {
        /* график ещё не готов */
      }
    };

    const ro = new ResizeObserver(() => {
      requestAnimationFrame(resize);
    });
    ro.observe(wrap);
    window.addEventListener("resize", resize);
    document.addEventListener("fullscreenchange", resize);
    document.addEventListener("webkitfullscreenchange", resize);
    const t0 = window.setTimeout(resize, 0);
    const t1 = window.setTimeout(resize, 160);
    const t2 = window.setTimeout(resize, 480);
    return () => {
      ro.disconnect();
      window.removeEventListener("resize", resize);
      document.removeEventListener("fullscreenchange", resize);
      document.removeEventListener("webkitfullscreenchange", resize);
      window.clearTimeout(t0);
      window.clearTimeout(t1);
      window.clearTimeout(t2);
    };
  }, [visible, fillWidth, layout, heightPx]);

  if (!visible) {
    return (
      <div
        ref={holderRef}
        className="bi-chart-placeholder bi-skeleton"
        style={{ height: layoutHeight(props.layout) ?? "100%", minHeight: 120 }}
        aria-hidden
      />
    );
  }

  return (
    <div
      ref={wrapRef}
      className="bi-plotly-host min-w-0 w-full"
      style={{ height: heightPx ?? style?.height ?? "100%" }}
    >
      <RawPlotlyFigure
        {...props}
        data={data}
        layout={layout}
        config={config}
        useResizeHandler={fillWidth ? true : props.useResizeHandler}
        style={style}
        onRelayout={(eventData) => {
          props.onRelayout?.(eventData);
          const gd = wrapRef.current?.querySelector(".js-plotly-plot") as
            | (HTMLElement & { layout?: Record<string, unknown> })
            | null;
          if (gd) clampZoomRelayout(gd, eventData as Record<string, unknown>);
        }}
      />
    </div>
  );
}
