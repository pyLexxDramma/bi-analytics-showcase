"use client";

import { useEffect, useRef } from "react";
import { fetchMyDefaultFilters } from "@/lib/api";

/**
 * Состояние фильтров в query-параметрах: возврат на экран, перезагрузка и
 * ссылка коллеге сохраняют выбранный срез. Работает на всех вьюпортах.
 *
 * Значения не пересчитываются: в URL пишется ровно то, что уже в состоянии,
 * а при чтении берутся только ключи, объявленные в `initial`.
 *
 * Опционально `navId`: после URL подтягиваются default_filters роли
 * только для ключей, которых ещё нет в адресе.
 */

const ARRAY_SEP = "|";

type FilterValues = Record<string, unknown>;

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

function coerceDefault(value: unknown, base: unknown): unknown {
  if (Array.isArray(base)) {
    if (Array.isArray(value)) {
      return value.filter((v): v is string => typeof v === "string");
    }
    if (typeof value === "string" && value.trim()) {
      return value.includes(ARRAY_SEP)
        ? value.split(ARRAY_SEP).filter(Boolean)
        : [value.trim()];
    }
    return base;
  }
  if (typeof base === "boolean") {
    if (typeof value === "boolean") return value;
    if (typeof value === "string") {
      const s = value.trim().toLowerCase();
      if (["1", "true", "yes", "да"].includes(s)) return true;
      if (["0", "false", "no", "нет"].includes(s)) return false;
    }
    return base;
  }
  if (typeof base === "number") {
    const n = typeof value === "number" ? value : Number(value);
    return Number.isFinite(n) ? n : base;
  }
  if (value == null) return base;
  return String(value);
}

/** Что можно восстановить из текущего адреса (без побочных эффектов). */
export function readFiltersFromUrl(initial: FilterValues): FilterValues {
  if (typeof window === "undefined") return {};
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
    /** nav.id экрана — подтянуть default_filters роли, если ключа нет в URL. */
    navId?: string;
  } = {},
): void {
  const { skip, onRestore, navId } = options;
  const restoredRef = useRef(false);
  const defaultsDoneRef = useRef(false);
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
    if (!navId || defaultsDoneRef.current) return;
    defaultsDoneRef.current = true;
    let cancelled = false;
    void fetchMyDefaultFilters(navId)
      .then((data) => {
        if (cancelled) return;
        const fromUrl = readFiltersFromUrl(initialRef.current);
        const patch: Partial<T> = {};
        const incoming = data.filters || {};
        for (const key of Object.keys(initialRef.current)) {
          if (key in fromUrl) continue;
          if (!(key in incoming)) continue;
          const coerced = coerceDefault(
            incoming[key],
            initialRef.current[key],
          );
          if (coerced === initialRef.current[key]) continue;
          (patch as FilterValues)[key] = coerced;
        }
        if (Object.keys(patch).length) {
          applyRef.current(patch);
          onRestoreRef.current?.(patch);
        }
      })
      .catch(() => {
        /* нет сессии / нет дефолтов — ок */
      });
    return () => {
      cancelled = true;
    };
  }, [navId]);

  useEffect(() => {
    if (!restoredRef.current) return;
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
    window.history.replaceState(window.history.state, "", next);
  }, [filters]);
}
