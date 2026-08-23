"use client";

import { useCallback, useState } from "react";
import { readTableSort, writeTableSort } from "@/lib/table-sort-persist";

export type PersistedSortState = { key: string; asc: boolean } | null;

/** Сортировка таблицы с запоминанием в localStorage (`scopeId` = `navId:table`). */
export function usePersistedTableSort(scopeId: string): [
  PersistedSortState,
  (key: string) => void,
] {
  const [sort, setSort] = useState<PersistedSortState>(() => {
    const saved = readTableSort(scopeId);
    if (!saved) return null;
    return { key: saved.key, asc: saved.dir === "asc" };
  });

  const toggleSort = useCallback(
    (key: string) => {
      setSort((prev) => {
        let next: PersistedSortState;
        if (!prev || prev.key !== key) {
          next = { key, asc: true };
        } else if (prev.asc) {
          next = { key, asc: false };
        } else {
          next = null;
        }
        if (next) {
          writeTableSort(scopeId, {
            key: next.key,
            dir: next.asc ? "asc" : "desc",
          });
        } else {
          writeTableSort(scopeId, null);
        }
        return next;
      });
    },
    [scopeId],
  );

  return [sort, toggleSort];
}
