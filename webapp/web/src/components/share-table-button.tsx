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

/** Запасной путь: положить ссылку в буфер. execCommand — для http-стенда. */
function copyLink(url: string): boolean {
  try {
    if (navigator.clipboard?.writeText) {
      void navigator.clipboard.writeText(url);
      return true;
    }
  } catch {
    /* ниже execCommand */
  }
  try {
    const area = document.createElement("textarea");
    area.value = url;
    area.setAttribute("readonly", "");
    area.style.position = "fixed";
    area.style.opacity = "0";
    document.body.appendChild(area);
    area.select();
    const ok = document.execCommand("copy");
    area.remove();
    return ok;
  } catch {
    return false;
  }
}

function isAbort(cause: unknown): boolean {
  return cause instanceof DOMException && cause.name === "AbortError";
}

function causeName(cause: unknown): string {
  if (cause instanceof DOMException) return cause.name;
  return cause instanceof Error ? cause.message : String(cause);
}

/**
 * «Поделиться» через системную шторку телефона (Telegram, MAX, почта и т. д.).
 * Только мобильный вьюпорт: `lg:hidden` + проверка `navigator.share`.
 *
 * Лестница попыток, потому что шторка отказывает по-разному: часть браузеров
 * не берёт файлы, часть блокирует Web Share вне https. Сначала файл, затем
 * ссылка, затем буфер обмена. Все вызовы `share()` синхронны по клику — любой
 * `await` перед ними гасит пользовательский жест и даёт `NotAllowedError`.
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
  const [done, setDone] = useState(false);
  const xlsxRef = useRef<File | null>(null);

  useEffect(() => {
    setSupported(
      typeof navigator !== "undefined" &&
        (typeof navigator.share === "function" ||
          typeof navigator.clipboard?.writeText === "function"),
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
    setDone(false);

    const title = screenTitle();
    const url = window.location.href;
    const canShare = typeof navigator.share === "function";

    const succeeded = () => {
      confirmFeedback();
      setNote(null);
    };

    const toClipboard = (reason: string) => {
      if (copyLink(url)) {
        confirmFeedback();
        setDone(true);
        setNote(null);
        return;
      }
      setNote(`Не удалось поделиться (${reason})`);
    };

    const shareLink = (reason: string) => {
      if (!canShare) {
        toClipboard(reason);
        return;
      }
      navigator
        .share({ title, text: title, url })
        .then(succeeded)
        .catch((cause: unknown) => {
          if (isAbort(cause)) return;
          toClipboard(causeName(cause));
        });
    };

    if (!canShare) {
      toClipboard("нет системной шторки");
      return;
    }

    const file =
      xlsxRef.current ??
      new File([tableToCsv(table)], `${exportFileStem(fileStem)}.csv`, {
        type: "text/csv;charset=utf-8",
      });
    const canFiles =
      typeof navigator.canShare === "function" &&
      navigator.canShare({ files: [file] });

    if (!canFiles) {
      shareLink("файлы не поддерживаются");
      return;
    }

    navigator
      .share({ files: [file], title, text: `${title}\n${url}` })
      .then(succeeded)
      .catch((cause: unknown) => {
        if (isAbort(cause)) return;
        // Телефон не принял файл — пробуем отдать хотя бы ссылку
        shareLink(causeName(cause));
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
      {done ? (
        <span className="text-xs text-emerald-600 lg:hidden dark:text-emerald-300">
          Ссылка скопирована — вставьте в чат
        </span>
      ) : null}
      {note ? (
        <span className="text-xs text-rose-600 lg:hidden dark:text-rose-300">
          {note}
        </span>
      ) : null}
    </>
  );
}
