"use client";

import { useEffect, useRef } from "react";

/**
 * Многоуровневая шапка таблицы: нижние ряды должны прилипать под верхними,
 * поэтому их высоты отдаются в CSS через переменные (см. `.bi-sticky-head`).
 *
 * `deps` — то, от чего меняется состав колонок: при пересборке шапки
 * наблюдение переустанавливается.
 */
export function useStickyHead(deps: readonly unknown[] = []) {
  const ref = useRef<HTMLTableElement | null>(null);

  useEffect(() => {
    const table = ref.current;
    if (!table) return;
    const rows = Array.from(table.querySelectorAll("thead tr"));
    if (rows.length < 2) return;

    const sync = () => {
      const first = Math.ceil(rows[0].getBoundingClientRect().height);
      table.style.setProperty("--bi-head-row-h", `${first}px`);
      if (rows[1]) {
        const second = Math.ceil(rows[1].getBoundingClientRect().height);
        table.style.setProperty("--bi-head-row2-h", `${first + second}px`);
      }
    };

    sync();
    const observer = new ResizeObserver(sync);
    rows.forEach((row) => observer.observe(row));
    return () => observer.disconnect();
    // eslint-disable-next-line react-hooks/exhaustive-deps -- состав колонок задаёт вызывающий
  }, deps);

  return ref;
}
