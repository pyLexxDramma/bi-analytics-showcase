"use client";

import { useEffect, useMemo, useRef, useState, type ComponentProps } from "react";
import Plotly from "plotly.js-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";
import { useChartInteractive } from "@/lib/chart-interaction";
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
    layout && typeof layout === "object" ? { ...(layout as object) } : {};
  return {
    ...base,
    hovermode: false,
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

  const data = useMemo(() => withoutHoverData(props.data), [props.data]);
  const layout = useMemo(
    () => withoutHoverLayout(props.layout, lockGestures),
    [props.layout, lockGestures],
  );
  const config = useMemo(
    () => withoutGestureConfig(props.config, lockGestures),
    [props.config, lockGestures],
  );

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

  // `height: 100%` в контейнере без заданной высоты Plotly вместе с
  // useResizeHandler иногда схлопывает в 0 — график остаётся пустым листом.
  // Числовая высота из layout делает контейнер определённым.
  const heightPx = layoutHeight(props.layout);
  const style =
    heightPx && (props.style?.height == null || props.style.height === "100%")
      ? { ...props.style, height: heightPx }
      : props.style;

  return (
    <RawPlotlyFigure
      {...props}
      data={data}
      layout={layout}
      config={config}
      style={style}
    />
  );
}
