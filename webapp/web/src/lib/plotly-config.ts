/** Единый Plotly modebar как в [main] `_PLOTLY_CONFIG_FULL_MODEBAR`. */
export const PLOTLY_MODEBAR_BUTTONS = [
  [
    "zoom2d",
    "pan2d",
    "zoomIn2d",
    "zoomOut2d",
    "autoScale2d",
    "resetScale2d",
    "toImage",
  ],
] as const;

/** Убрать select/lasso/hover — лишние кнопки (в т.ч. «табличная» справа). */
export const PLOTLY_MODEBAR_REMOVE = [
  "select2d",
  "lasso2d",
  "hoverClosestCartesian",
  "hoverCompareCartesian",
  "toggleSpikelines",
  "sendDataToCloud",
] as const;

export const PLOTLY_CONFIG = {
  responsive: true,
  displayModeBar: true,
  displaylogo: false,
  scrollZoom: true,
  locale: "ru",
  modeBarButtons: PLOTLY_MODEBAR_BUTTONS as unknown as string[][],
  modeBarButtonsToRemove: [...PLOTLY_MODEBAR_REMOVE],
};

/** Черта y=0 как в main (`CHART_ZEROLINE_COLOR`). */
export const PLOTLY_ZEROLINE = {
  zeroline: true,
  zerolinewidth: 1.5,
  zerolinecolor: "rgba(100, 116, 139, 0.75)",
} as const;

export const PLOTLY_AXIS_LINE = {
  showline: true,
  linewidth: 1,
  linecolor: "rgba(100, 116, 139, 0.65)",
} as const;
