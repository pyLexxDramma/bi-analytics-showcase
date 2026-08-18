/** Связка внешней HTML-легенды с Plotly-хостом: клик скрывает/показывает серию. */

export type ChartLegendHostApi = {
  hidden: Set<string>;
  toggle: (name: string) => void;
  subscribe: (listener: () => void) => () => void;
};

const hosts = new WeakMap<HTMLElement, ChartLegendHostApi>();

export function bindChartLegendHost(
  el: HTMLElement,
  api: ChartLegendHostApi,
): () => void {
  hosts.set(el, api);
  return () => {
    hosts.delete(el);
  };
}

export function chartLegendHostFrom(el: HTMLElement | null): ChartLegendHostApi | null {
  let node: HTMLElement | null = el;
  for (let i = 0; i < 10 && node; i += 1) {
    if (node.classList?.contains("bi-plotly-host")) {
      const api = hosts.get(node);
      if (api) return api;
    }
    const nested = node.querySelector?.(".bi-plotly-host") as HTMLElement | null;
    if (nested) {
      const api = hosts.get(nested);
      if (api) return api;
    }
    node = node.parentElement;
  }
  return null;
}
