"use client";

import { useMemo, type ComponentProps } from "react";
import Plotly from "plotly.js-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";

/**
 * Plotly-компонент для графиков паритета с [main]: там графики строятся на Plotly,
 * и только он даёт ту же панель инструментов (PNG, зум, панорама, выделение,
 * автомасштаб, сброс). Отдельный модуль — чтобы грузить его через `next/dynamic`
 * с `ssr: false` (plotly.js трогает `window` на импорте).
 *
 * Hover/tooltip и серая подсветка категории отключены глобально на всех дашбордах
 * (подписи значений на графике остаются).
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

function withoutHoverLayout(layout: PlotProps["layout"]): PlotProps["layout"] {
  const base =
    layout && typeof layout === "object" ? { ...(layout as object) } : {};
  return {
    ...base,
    hovermode: false,
  } as PlotProps["layout"];
}

export default function PlotlyFigure(props: PlotProps) {
  const data = useMemo(() => withoutHoverData(props.data), [props.data]);
  const layout = useMemo(
    () => withoutHoverLayout(props.layout),
    [props.layout],
  );
  return <RawPlotlyFigure {...props} data={data} layout={layout} />;
}
