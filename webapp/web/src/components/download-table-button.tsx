"use client";

import { useEffect, useLayoutEffect, useRef, useState } from "react";
import { createPortal } from "react-dom";
import { CopyLinkButton } from "@/components/copy-link-button";
import { ShareTableButton } from "@/components/share-table-button";
import {
  downloadCsv,
  downloadXlsx,
  type ExportTable,
} from "@/lib/table-export";

/**
 * «Скачать таблицу» как в [main]: одна кнопка → выбор формата (CSV для Excel / .xlsx).
 * Меню через portal — не клипится overflow-hidden у Card.
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
  const [menuPos, setMenuPos] = useState<{
    top: number;
    left: number;
    openUp: boolean;
  } | null>(null);
  const btnRef = useRef<HTMLButtonElement | null>(null);
  const menuRef = useRef<HTMLDivElement | null>(null);

  useLayoutEffect(() => {
    if (!open || !btnRef.current) {
      setMenuPos(null);
      return;
    }
    const rect = btnRef.current.getBoundingClientRect();
    const menuWidth = 256;
    const spaceBelow = window.innerHeight - rect.bottom;
    const openUp = spaceBelow < 140 && rect.top > spaceBelow;
    const left = Math.min(
      Math.max(8, rect.right - menuWidth),
      window.innerWidth - menuWidth - 8,
    );
    setMenuPos({
      top: openUp ? rect.top - 8 : rect.bottom + 4,
      left,
      openUp,
    });
  }, [open]);

  useEffect(() => {
    if (!open) return;
    const onClickAway = (event: MouseEvent) => {
      const target = event.target as Node;
      if (btnRef.current?.contains(target)) return;
      if (menuRef.current?.contains(target)) return;
      setOpen(false);
    };
    const onEsc = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    const onReposition = () => setOpen(false);
    document.addEventListener("mousedown", onClickAway);
    document.addEventListener("keydown", onEsc);
    window.addEventListener("resize", onReposition);
    window.addEventListener("scroll", onReposition, true);
    return () => {
      document.removeEventListener("mousedown", onClickAway);
      document.removeEventListener("keydown", onEsc);
      window.removeEventListener("resize", onReposition);
      window.removeEventListener("scroll", onReposition, true);
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

  const menu =
    open && menuPos && typeof document !== "undefined"
      ? createPortal(
          <div
            ref={menuRef}
            className="fixed z-[200] w-64 rounded-lg border border-tremor-border bg-white p-1 shadow-lg dark:border-dark-tremor-border dark:bg-slate-900"
            style={{
              top: menuPos.openUp ? undefined : menuPos.top,
              bottom: menuPos.openUp
                ? window.innerHeight - menuPos.top
                : undefined,
              left: menuPos.left,
            }}
            role="menu"
          >
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
          </div>,
          document.body,
        )
      : null;

  return (
    <span className={`relative inline-flex flex-wrap items-center gap-2 ${className}`}>
      <button
        ref={btnRef}
        type="button"
        onClick={() => setOpen((state) => !state)}
        disabled={disabled || busy}
        aria-expanded={open}
        aria-haspopup="menu"
        className="rounded-md border border-tremor-border bg-white/90 px-2.5 py-1 text-sm shadow-sm disabled:opacity-40 dark:border-dark-tremor-border dark:bg-slate-900/90"
      >
        {busy ? "Выгрузка…" : label}
      </button>
      <ShareTableButton
        getTable={getTable}
        fileStem={fileStem}
        disabled={disabled}
      />
      <CopyLinkButton />
      {menu}
    </span>
  );
}
