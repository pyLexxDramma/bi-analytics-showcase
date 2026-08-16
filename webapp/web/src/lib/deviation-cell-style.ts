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

function blendRgb(
  r: number,
  g: number,
  b: number,
  a: number,
  base: [number, number, number],
): string {
  const mix = (c: number, bc: number) => Math.round(bc * (1 - a) + c * a);
  return `rgb(${mix(r, base[0])}, ${mix(g, base[1])}, ${mix(b, base[2])})`;
}

type DeviationStyleOpts = {
  /** Непрозрачный фон (sticky-колонки) — иначе текст соседних колонок просвечивает. */
  opaque?: boolean;
};

/** Как main `days_deviation_gradient`: просрочка <0 красный, опережение >0 зелёный. */
export function deviationCellStyle(
  value: number | null | undefined,
  vmax: number,
  dark: boolean,
  opts?: DeviationStyleOpts,
): { className: string; style?: CSSProperties } {
  if (value == null || Number.isNaN(value)) {
    return { className: "" };
  }
  const num = Number(value);
  const t = Math.min(Math.abs(num) / Math.max(vmax, 1), 1);
  const base: [number, number, number] = dark ? [17, 24, 39] : [255, 255, 255];
  const opaque = Boolean(opts?.opaque);

  if (num === 0) {
    const a = dark ? 0.35 : 0.22;
    return {
      className: "font-semibold",
      style: dark
        ? {
            backgroundColor: opaque
              ? blendRgb(70, 214, 138, a, base)
              : `rgba(70,214,138,${a})`,
            color: "#b8f5c8",
          }
        : {
            backgroundColor: opaque
              ? blendRgb(34, 197, 94, a, base)
              : `rgba(34,197,94,${a})`,
            color: "#15803d",
          },
    };
  }
  if (num > 0) {
    const alpha = 0.18 + 0.32 * t;
    return {
      className: "font-bold",
      style: dark
        ? {
            backgroundColor: opaque
              ? blendRgb(70, 214, 138, alpha, base)
              : `rgba(70,214,138,${alpha.toFixed(3)})`,
            color: "#00e676",
          }
        : {
            backgroundColor: opaque
              ? blendRgb(34, 197, 94, alpha, base)
              : `rgba(34,197,94,${alpha.toFixed(3)})`,
            color: "#15803d",
          },
    };
  }
  const alphaLight = 0.22 + 0.38 * t;
  const alphaDark = 0.28 + 0.4 * t;
  return {
    className: "font-bold",
    style: dark
      ? {
          backgroundColor: opaque
            ? blendRgb(255, 84, 84, alphaDark, base)
            : `rgba(255,84,84,${alphaDark.toFixed(3)})`,
          color: "#ff6b6b",
        }
      : {
          backgroundColor: opaque
            ? blendRgb(248, 113, 113, alphaLight, base)
            : `rgba(248,113,113,${alphaLight.toFixed(3)})`,
          color: "#b91c1c",
        },
  };
}
