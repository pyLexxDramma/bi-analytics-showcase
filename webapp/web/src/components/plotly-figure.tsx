"use client";

import Plotly from "plotly.js-dist-min";
import createPlotlyComponent from "react-plotly.js/factory";

/**
 * Plotly-компонент для графиков паритета с [main]: там графики строятся на Plotly,
 * и только он даёт ту же панель инструментов (PNG, зум, панорама, выделение,
 * автомасштаб, сброс). Отдельный модуль — чтобы грузить его через `next/dynamic`
 * с `ssr: false` (plotly.js трогает `window` на импорте).
 */
const PlotlyFigure = createPlotlyComponent(Plotly);

export default PlotlyFigure;
