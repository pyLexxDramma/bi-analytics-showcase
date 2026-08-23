"use client";

import { useState, type RefObject } from "react";
import { exportChartPng } from "@/lib/chart-export-png";
import { tapFeedback } from "@/lib/haptics";

export function ChartPngButton({
  hostRef,
  fileStem,
  className = "",
}: {
  hostRef: RefObject<HTMLElement | null>;
  fileStem: string;
  className?: string;
}) {
  const [busy, setBusy] = useState(false);

  return (
    <button
      type="button"
      disabled={busy}
      title="Скачать график PNG"
      aria-label="Скачать график PNG"
      className={`bi-chart-tool-btn ${className}`}
      onClick={() => {
        tapFeedback();
        setBusy(true);
        void exportChartPng(hostRef.current, fileStem).finally(() =>
          setBusy(false),
        );
      }}
    >
      {busy ? "…" : "PNG"}
    </button>
  );
}
