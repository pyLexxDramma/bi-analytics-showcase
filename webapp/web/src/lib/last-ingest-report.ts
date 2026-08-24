import type { AdminSyncResult } from "@/lib/api";

/**
 * Отчёт последней загрузки данных (FTP → web/ → БД).
 *
 * Кнопка в сайдбаре перезагружает страницу сразу после успеха, поэтому список
 * файлов негде показать «на месте» — складываем его сюда, а админка «Данные
 * (FTP / ingest)» показывает его как «Последняя загрузка».
 */
const STORAGE_KEY = "bi.last-ingest-report";

export type LastIngestReport = {
  at: number;
  result: AdminSyncResult;
};

export function saveLastIngestReport(result: AdminSyncResult): void {
  if (typeof window === "undefined") return;
  try {
    window.localStorage.setItem(
      STORAGE_KEY,
      JSON.stringify({ at: Date.now(), result } satisfies LastIngestReport),
    );
  } catch {
    // приватный режим / переполнение квоты — отчёт не критичен
  }
}

export function readLastIngestReport(): LastIngestReport | null {
  if (typeof window === "undefined") return null;
  try {
    const raw = window.localStorage.getItem(STORAGE_KEY);
    if (!raw) return null;
    const parsed = JSON.parse(raw) as LastIngestReport;
    if (!parsed || typeof parsed !== "object" || !parsed.result) return null;
    return parsed;
  } catch {
    return null;
  }
}
