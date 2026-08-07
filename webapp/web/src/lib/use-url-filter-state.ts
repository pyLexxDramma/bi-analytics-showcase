"use client";

import { useEffect, useRef } from "react";

/**
 * Состояние фильтров в query-параметрах: возврат на экран и перезагрузка
 * сохраняют выбор. Работает только на мобильном вьюпорте (`<lg`) — на
 * десктопе адрес и поведение остаются прежними.
 *
 * Значения не пересчитываются: в URL пишется ровно то, что уже в состоянии,
 * а при чтении берутся только ключи, объявленные в `initial`.
 */

const MOBILE_QUERY = "(max-width: 1023px)";
const ARRAY_SEP = "|";

type FilterValues = Record<string, unknown>;

function isMobile(): boolean {
  if (typeof window === "undefined") return false;
  return window.matchMedia(MOBILE_QUERY).matches;
}

function encodeValue(value: unknown): string | null {
  if (Array.isArray(value)) {
    const items = value.filter((v): v is string => typeof v === "string");
    return items.length ? items.join(ARRAY_SEP) : null;
  }
  if (typeof value === "boolean") return value ? "1" : "0";
  if (typeof value === "string") return value || null;
  if (typeof value === "number") return String(value);
  return null;
}

function decodeValue(raw: string, base: unknown): unknown {
  if (Array.isArray(base)) {
    return raw ? raw.split(ARRAY_SEP).filter(Boolean) : [];
  }
  if (typeof base === "boolean" || base === null) {
    if (raw === "1" || raw === "true") return true;
    if (raw === "0" || raw === "false") return false;
    return base;
  }
  if (typeof base === "number") {
    const n = Number(raw);
    return Number.isFinite(n) ? n : base;
  }
  return raw;
}

/** Что можно восстановить из текущего адреса (без побочных эффектов). */
export function readFiltersFromUrl(initial: FilterValues): FilterValues {
  if (typeof window === "undefined" || !isMobile()) return {};
  const params = new URLSearchParams(window.location.search);
  const out: FilterValues = {};
  for (const key of Object.keys(initial)) {
    const raw = params.get(key);
    if (raw == null) continue;
    out[key] = decodeValue(raw, initial[key]);
  }
  return out;
}

export function useUrlFilterState<T extends FilterValues>(
  filters: T,
  initial: T,
  apply: (patch: Partial<T>) => void,
  options: {
    /** Ключи, которые не пишем в адрес (например, служебные флаги). */
    skip?: Array<keyof T & string>;
    /** Вызывается один раз, если что-то восстановлено из адреса. */
    onRestore?: (restored: Partial<T>) => void;
  } = {},
): void {
  const { skip, onRestore } = options;
  const restoredRef = useRef(false);
  const initialRef = useRef(initial);
  const applyRef = useRef(apply);
  const onRestoreRef = useRef(onRestore);
  const skipRef = useRef(skip);
  applyRef.current = apply;
  onRestoreRef.current = onRestore;
  skipRef.current = skip;

  useEffect(() => {
    if (restoredRef.current) return;
    restoredRef.current = true;
    const restored = readFiltersFromUrl(initialRef.current) as Partial<T>;
    const keys = Object.keys(restored);
    if (!keys.length) return;
    applyRef.current(restored);
    onRestoreRef.current?.(restored);
  }, []);

  useEffect(() => {
    if (!restoredRef.current || !isMobile()) return;
    const params = new URLSearchParams();
    for (const key of Object.keys(initialRef.current)) {
      if (skipRef.current?.includes(key as keyof T & string)) continue;
      const value = filters[key];
      const base = initialRef.current[key];
      if (Array.isArray(value) && Array.isArray(base)) {
        if (
          value.length === base.length &&
          value.every((v, i) => v === base[i])
        ) {
          continue;
        }
      } else if (value === base) {
        continue;
      }
      const encoded = encodeValue(value);
      if (encoded != null) params.set(key, encoded);
    }
    const query = params.toString();
    const next = `${window.location.pathname}${query ? `?${query}` : ""}`;
    if (next === `${window.location.pathname}${window.location.search}`) return;
    // history.replaceState вместо router.replace: без ре-рендера и повторных запросов
    window.history.replaceState(window.history.state, "", next);
  }, [filters]);
}
