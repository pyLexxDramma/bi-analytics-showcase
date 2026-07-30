"use client";

import { useEffect, useRef, useState } from "react";
import {
  downloadCsv,
  downloadXlsx,
  type ExportTable,
} from "@/lib/table-export";

/**
 * «Скачать таблицу» как в [main]: одна кнопка → выбор формата (CSV для Excel / .xlsx).
 * Таблица берётся из `getTable()` в момент клика, поэтому выгружается то, что видно
 * с учётом текущих фильтров.
 */
export function DownloadTableButton({
  getTable,
  fileStem,
  label = "Скачать таблицу",
  disabled = false,
  className = "",
}: {
  getTable: () => ExportTable | null;
  fileStem: string;
  label?: string;
  disabled?: boolean;
  className?: string;
}) {
  const [open, setOpen] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const boxRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onClickAway = (event: MouseEvent) => {
      if (!boxRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onClickAway);
    document.addEventListener("keydown", onEsc);
    return () => {
      document.removeEventListener("mousedown", onClickAway);
      document.removeEventListener("keydown", onEsc);
    };
  }, [open]);

  const run = async (format: "csv" | "xlsx") => {
    const table = getTable();
    if (!table || !table.rows.length) {
      setError("Нечего выгружать: таблица пуста");
      return;
    }
    setBusy(true);
    setError(null);
    try {
      if (format === "csv") downloadCsv(table, fileStem);
      else await downloadXlsx(table, fileStem);
      setOpen(false);
    } catch (cause) {
      setError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  const itemClass =
    "block w-full rounded-md px-3 py-2 text-left text-sm hover:bg-tremor-background-muted disabled:opacity-50 dark:hover:bg-dark-tremor-background-muted";

  return (
    <div ref={boxRef} className={`relative inline-block ${className}`}>
      <button
        type="button"
        onClick={() => setOpen((state) => !state)}
        disabled={disabled}
        className="rounded-md border border-tremor-border bg-white/90 px-2.5 py-1 text-sm shadow-sm disabled:opacity-40 dark:border-dark-tremor-border dark:bg-slate-900/90"
      >
        {label}
      </button>
      {open ? (
        <div className="absolute right-0 z-50 mt-1 w-64 rounded-lg border border-tremor-border bg-white p-1 shadow-lg dark:border-dark-tremor-border dark:bg-slate-900">
          <button
            type="button"
            className={itemClass}
            disabled={busy}
            onClick={() => void run("csv")}
          >
            Скачать CSV (для Excel)
          </button>
          <button
            type="button"
            className={itemClass}
            disabled={busy}
            onClick={() => void run("xlsx")}
          >
            Скачать Excel (.xlsx)
          </button>
          {error ? (
            <p className="px-3 py-2 text-xs text-rose-600 dark:text-rose-300">
              {error}
            </p>
          ) : null}
        </div>
      ) : null}
    </div>
  );
}
