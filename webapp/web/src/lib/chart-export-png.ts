"use client";

/** Скачать PNG: Plotly `.js-plotly-plot` или SVG Recharts внутри host. */
export async function exportChartPng(
  host: HTMLElement | null,
  fileStem: string,
): Promise<void> {
  if (!host || typeof window === "undefined") return;

  const plot = host.querySelector(".js-plotly-plot") as
    | (HTMLElement & { data?: unknown })
    | null;
  if (plot?.data) {
    const Plotly = (await import("plotly.js-dist-min")).default;
    await Plotly.downloadImage(
      plot as Parameters<typeof Plotly.downloadImage>[0],
      {
        format: "png",
        filename: fileStem,
        width: Math.max(plot.clientWidth, 900),
        height: Math.max(plot.clientHeight, 480),
      },
    );
    return;
  }

  const svg = host.querySelector("svg.recharts-surface");
  if (!svg) return;

  const xml = new XMLSerializer().serializeToString(svg);
  const blob = new Blob([xml], { type: "image/svg+xml;charset=utf-8" });
  const url = URL.createObjectURL(blob);
  const img = new Image();
  await new Promise<void>((resolve, reject) => {
    img.onload = () => resolve();
    img.onerror = () => reject(new Error("svg"));
    img.src = url;
  });
  const canvas = document.createElement("canvas");
  canvas.width = Math.max(img.width, 900);
  canvas.height = Math.max(img.height, 400);
  const ctx = canvas.getContext("2d");
  if (!ctx) return;
  ctx.fillStyle = "#ffffff";
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(img, 0, 0);
  URL.revokeObjectURL(url);

  const link = document.createElement("a");
  link.download = `${fileStem}.png`;
  link.href = canvas.toDataURL("image/png");
  link.click();
}
