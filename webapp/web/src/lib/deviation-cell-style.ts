import type { CSSProperties } from "react";

export function parseSortableNumber(raw: unknown): number | null {
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (raw == null) return null;
  const s = String(raw).trim().replace("\u2212", "-").replace(",", ".");
  if (!s || s === "—" || s.toLowerCase() === "nan") return null;
  const n = Number(s.replace(/[^\d.+-]/g, ""));
  return Number.isFinite(n) ? n : null;
}

export function isDeviationCol(col: string): boolean {
  const c = col.toLowerCase();
  return c.includes("отклонен") || c.startsWith("отклонение");
}

export function isIdentityCol(col: string): boolean {
  const c = col.trim().toLowerCase().replace(/\s+/g, " ");
  return (
    c === "проект" ||
    c === "№" ||
    c === "№ п.п." ||
    c === "№ п/п" ||
    c === "n" ||
    c.startsWith("№")
  );
}

/** Как main `days_deviation_gradient`: просрочка <0 красный, опережение >0 зелёный. */
export function deviationCellStyle(
  value: number | null | undefined,
  vmax: number,
  dark: boolean,
): { className: string; style?: CSSProperties } {
  if (value == null || Number.isNaN(value)) {
    return { className: "" };
  }
  const num = Number(value);
  const t = Math.min(Math.abs(num) / Math.max(vmax, 1), 1);
  if (num === 0) {
    return {
      className: "font-semibold",
      style: dark
        ? { backgroundColor: "rgba(70,214,138,0.35)", color: "#b8f5c8" }
        : { backgroundColor: "rgba(34,197,94,0.22)", color: "#15803d" },
    };
  }
  if (num > 0) {
    const alpha = 0.18 + 0.32 * t;
    return {
      className: "font-bold",
      style: dark
        ? { backgroundColor: `rgba(70,214,138,${alpha.toFixed(3)})`, color: "#00e676" }
        : { backgroundColor: `rgba(34,197,94,${alpha.toFixed(3)})`, color: "#15803d" },
    };
  }
  const alphaLight = 0.22 + 0.38 * t;
  const alphaDark = 0.28 + 0.4 * t;
  return {
    className: "font-bold",
    style: dark
      ? { backgroundColor: `rgba(255,84,84,${alphaDark.toFixed(3)})`, color: "#ff6b6b" }
      : { backgroundColor: `rgba(248,113,113,${alphaLight.toFixed(3)})`, color: "#b91c1c" },
  };
}
