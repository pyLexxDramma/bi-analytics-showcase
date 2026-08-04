"use client";

import { useMemo, type ComponentProps } from "react";
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

export default function PlotlyFigure(props: PlotProps) {
  const mobile = useIsMobileViewport();
  const interactive = useChartInteractive();
  const lockGestures = mobile && !interactive;

  const data = useMemo(() => withoutHoverData(props.data), [props.data]);
  const layout = useMemo(
    () => withoutHoverLayout(props.layout, lockGestures),
    [props.layout, lockGestures],
  );
  const config = useMemo(
    () => withoutGestureConfig(props.config, lockGestures),
    [props.config, lockGestures],
  );

  return (
    <RawPlotlyFigure {...props} data={data} layout={layout} config={config} />
  );
}
