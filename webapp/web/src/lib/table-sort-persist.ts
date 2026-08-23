"use client";

export type TableSortState = {
  key: string;
  dir: "asc" | "desc";
};

const PREFIX = "bi_table_sort_v1:";

export function readTableSort(navId: string): TableSortState | null {
  try {
    const raw = localStorage.getItem(`${PREFIX}${navId}`);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as TableSortState;
    if (!parsed?.key || (parsed.dir !== "asc" && parsed.dir !== "desc")) return null;
    return parsed;
  } catch {
    return null;
  }
}

export function writeTableSort(navId: string, state: TableSortState | null): void {
  try {
    const k = `${PREFIX}${navId}`;
    if (!state) {
      localStorage.removeItem(k);
      return;
    }
    localStorage.setItem(k, JSON.stringify(state));
  } catch {
    /* private mode */
  }
}
