/**
 * Выгрузка видимой таблицы — как «Скачать таблицу» в [main]:
 * CSV с разделителем «;» и UTF-8 BOM (региональные настройки RU) либо .xlsx.
 */

export type ExportCell = string | number | null | undefined;

export type ExportTable = {
  /** Заголовки; несколько строк — для таблиц со сгруппированными колонками. */
  header: ExportCell[][];
  rows: ExportCell[][];
  sheetName?: string;
};

function csvEscape(value: ExportCell): string {
  const text = value === null || value === undefined ? "" : String(value);
  return /[;"\n\r]/.test(text) ? `"${text.replace(/"/g, '""')}"` : text;
}

export function tableToCsv(table: ExportTable): string {
  const lines = [...table.header, ...table.rows].map((row) =>
    row.map(csvEscape).join(";"),
  );
  return `\uFEFF${lines.join("\r\n")}`;
}

function triggerDownload(filename: string, blob: Blob): void {
  const url = URL.createObjectURL(blob);
  const link = document.createElement("a");
  link.href = url;
  link.download = filename;
  link.click();
  URL.revokeObjectURL(url);
}

export function exportFileStem(name: string): string {
  const stem = String(name || "export")
    .trim()
    .replace(/\.(csv|xlsx|xls)$/i, "");
  return stem || "export";
}

export function downloadCsv(table: ExportTable, fileStem: string): void {
  triggerDownload(
    `${exportFileStem(fileStem)}.csv`,
    new Blob([tableToCsv(table)], { type: "text/csv;charset=utf-8" }),
  );
}

export async function downloadXlsx(
  table: ExportTable,
  fileStem: string,
): Promise<void> {
  // динамический импорт: писатель xlsx не нужен до клика по «Скачать»
  const writeXlsxFile = (await import("write-excel-file/browser")).default;
  const data = [
    ...table.header.map((row) =>
      row.map((value) => ({
        value: value === null || value === undefined ? "" : String(value),
        fontWeight: "bold" as const,
      })),
    ),
    ...table.rows.map((row) =>
      row.map((value) =>
        typeof value === "number"
          ? { type: Number, value }
          : { value: value === null || value === undefined ? "" : String(value) },
      ),
    ),
  ];
  await writeXlsxFile(data, { sheet: table.sheetName || "Данные" }).toFile(
    `${exportFileStem(fileStem)}.xlsx`,
  );
}
