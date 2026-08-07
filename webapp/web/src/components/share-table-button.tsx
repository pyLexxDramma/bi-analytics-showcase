"use client";

import { useEffect, useState } from "react";
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
 * Данные те же, что в «Скачать таблицу» — файл собирается из того же `ExportTable`.
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
  const [busy, setBusy] = useState(false);
  const [note, setNote] = useState<string | null>(null);

  useEffect(() => {
    setSupported(
      typeof navigator !== "undefined" && typeof navigator.share === "function",
    );
  }, []);

  if (!supported) return null;

  const share = async () => {
    tapFeedback();
    const table = getTable();
    if (!table || !table.rows.length) {
      setNote("Нечем делиться: таблица пуста");
      return;
    }
    setBusy(true);
    setNote(null);
    const title = screenTitle();
    const url = typeof window !== "undefined" ? window.location.href : "";
    const stem = exportFileStem(fileStem);
    try {
      let file: File;
      try {
        file = new File([await tableToXlsxBlob(table)], `${stem}.xlsx`, {
          type: XLSX_MIME,
        });
      } catch {
        file = new File([tableToCsv(table)], `${stem}.csv`, {
          type: "text/csv;charset=utf-8",
        });
      }
      const canFiles =
        typeof navigator.canShare === "function" &&
        navigator.canShare({ files: [file] });
      if (canFiles) {
        await navigator.share({ files: [file], title, text: `${title}\n${url}` });
      } else {
        // Приложение не принимает файлы — отправляем ссылку с текущими фильтрами
        await navigator.share({ title, text: title, url });
      }
      confirmFeedback();
    } catch (cause) {
      if (cause instanceof DOMException && cause.name === "AbortError") return;
      setNote(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setBusy(false);
    }
  };

  return (
    <>
      <button
        type="button"
        onClick={() => void share()}
        disabled={disabled || busy}
        className="inline-flex items-center gap-1.5 rounded-md border border-tremor-border bg-white/90 px-2.5 py-1 text-sm shadow-sm disabled:opacity-40 lg:hidden dark:border-dark-tremor-border dark:bg-slate-900/90"
      >
        <span aria-hidden>⤴</span>
        {busy ? "Готовим файл…" : label}
      </button>
      {note ? (
        <span className="text-xs text-rose-600 lg:hidden dark:text-rose-300">
          {note}
        </span>
      ) : null}
    </>
  );
}
