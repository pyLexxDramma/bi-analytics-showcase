"use client";

import { useEffect, useRef, useState } from "react";
import {
  exportFileStem,
  tableToCsv,
  tableToXlsxBlob,
  type ExportTable,
} from "@/lib/table-export";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";

const XLSX_MIME =
  "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet";

/** Заголовок экрана — им подписываем сообщение в мессенджере. */
function screenTitle(): string {
  if (typeof document === "undefined") return "Строительная аналитика";
  const h1 = document.querySelector("h1")?.textContent?.trim();
  return h1 || document.title || "Строительная аналитика";
}

/**
 * «Поделиться» через системную шторку телефона (Telegram, MAX, почта и т. д.).
 * Только мобильный вьюпорт: `lg:hidden` + проверка `navigator.share`.
 *
 * `navigator.share()` требует «свежего» жеста пользователя: любой `await` перед
 * вызовом гасит активацию и телефон отвечает `NotAllowedError`. Поэтому xlsx
 * готовится заранее, на нажатии пальца, а по клику шторка открывается синхронно —
 * с готовым xlsx либо с CSV, который собирается без промисов.
 */
export function ShareTableButton({
  getTable,
  fileStem,
  label = "Поделиться",
  disabled = false,
}: {
  getTable: () => ExportTable | null;
  fileStem: string;
  label?: string;
  disabled?: boolean;
}) {
  const [supported, setSupported] = useState(false);
  const [note, setNote] = useState<string | null>(null);
  const xlsxRef = useRef<File | null>(null);

  useEffect(() => {
    setSupported(
      typeof navigator !== "undefined" && typeof navigator.share === "function",
    );
  }, []);

  if (!supported) return null;

  const prewarmXlsx = () => {
    const table = getTable();
    if (!table || !table.rows.length) return;
    const name = `${exportFileStem(fileStem)}.xlsx`;
    tableToXlsxBlob(table)
      .then((blob) => {
        xlsxRef.current = new File([blob], name, { type: XLSX_MIME });
      })
      .catch(() => {
        xlsxRef.current = null;
      });
  };

  const share = () => {
    tapFeedback();
    const table = getTable();
    if (!table || !table.rows.length) {
      setNote("Нечем делиться: таблица пуста");
      return;
    }
    setNote(null);
    const title = screenTitle();
    const url = window.location.href;
    const file =
      xlsxRef.current ??
      new File(
        [tableToCsv(table)],
        `${exportFileStem(fileStem)}.csv`,
        { type: "text/csv;charset=utf-8" },
      );
    const canFiles =
      typeof navigator.canShare === "function" &&
      navigator.canShare({ files: [file] });
    const payload: ShareData = canFiles
      ? { files: [file], title, text: `${title}\n${url}` }
      : { title, text: title, url };

    navigator
      .share(payload)
      .then(() => confirmFeedback())
      .catch((cause: unknown) => {
        if (cause instanceof DOMException) {
          if (cause.name === "AbortError") return;
          if (cause.name === "NotAllowedError") {
            setNote("Телефон не открыл шторку — нажмите ещё раз");
            return;
          }
        }
        setNote(cause instanceof Error ? cause.message : String(cause));
      });
  };

  return (
    <>
      <button
        type="button"
        onPointerDown={prewarmXlsx}
        onClick={share}
        disabled={disabled}
        className="inline-flex items-center gap-1.5 rounded-md border border-tremor-border bg-white/90 px-2.5 py-1 text-sm shadow-sm disabled:opacity-40 lg:hidden dark:border-dark-tremor-border dark:bg-slate-900/90"
      >
        <span aria-hidden>⤴</span>
        {label}
      </button>
      {note ? (
        <span className="text-xs text-rose-600 lg:hidden dark:text-rose-300">
          {note}
        </span>
      ) : null}
    </>
  );
}
