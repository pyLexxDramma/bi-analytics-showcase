export function formatMln(v: number | undefined | null): string {
  const n = Number(v || 0);
  return `${n.toLocaleString("ru-RU", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  })} млн ₽`;
}

export function formatRub(v: number | undefined | null): string {
  return Number(v || 0).toLocaleString("ru-RU", {
    maximumFractionDigits: 0,
  });
}
