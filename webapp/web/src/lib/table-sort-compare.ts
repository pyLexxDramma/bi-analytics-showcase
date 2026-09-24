/**
 * Компаратор ячеек таблиц: строгое число / текст (ru), пустые всегда в конце.
 */

const EMPTY_DASH = "—";

/** null, undefined, "", «—», пробелы — пустое для сортировки. */
export function isEmptySortValue(raw: unknown): boolean {
  if (raw == null) return true;
  if (typeof raw === "number") return !Number.isFinite(raw);
  const s = String(raw).trim();
  return s === "" || s === EMPTY_DASH;
}

/**
 * Числом только если ячейка целиком число:
 * пробелы / \u00a0 / \u202f — разряды; запятая или точка — десятичный знак;
 * необязательный +/− / unicode minus \u2212.
 */
export function parseStrictSortableNumber(raw: unknown): number | null {
  if (typeof raw === "number" && Number.isFinite(raw)) return raw;
  if (raw == null) return null;
  const trimmed = String(raw)
    .trim()
    .replace(/\u2212/g, "-");
  if (!trimmed || trimmed === EMPTY_DASH || trimmed.toLowerCase() === "nan") {
    return null;
  }
  const compact = trimmed.replace(/[\s\u00a0\u202f]/g, "");
  if (!/^[+-]?\d+(?:[.,]\d+)?$/.test(compact)) return null;
  const n = Number(compact.replace(",", "."));
  return Number.isFinite(n) ? n : null;
}

/** Сравнение двух непустых значений. Пустые сюда не передавать. */
export function compareSortableValues(a: unknown, b: unknown): number {
  const na = parseStrictSortableNumber(a);
  const nb = parseStrictSortableNumber(b);
  if (na != null && nb != null) return na - nb;
  return String(a).localeCompare(String(b), "ru", {
    numeric: true,
    sensitivity: "base",
  });
}

/**
 * Компаратор для Array.sort: пустые всегда в конце при любом направлении.
 * Переворот desc — после проверки пустых, не ломая порядок двух непустых.
 */
export function compareSortEntries(
  a: unknown,
  b: unknown,
  asc: boolean,
): number {
  const emptyA = isEmptySortValue(a);
  const emptyB = isEmptySortValue(b);
  if (emptyA && emptyB) return 0;
  if (emptyA) return 1;
  if (emptyB) return -1;
  const cmp = compareSortableValues(a, b);
  return asc ? cmp : -cmp;
}
