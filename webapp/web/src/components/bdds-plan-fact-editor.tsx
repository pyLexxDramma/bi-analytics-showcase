"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import {
  applyBddsPlanFactEdits,
  fetchBddsPlanFactEditor,
  previewBddsPlanFact,
  type BddsPlanFactEditRow,
  type BddsPlanFactEditorPayload,
  type BddsPlanFactLotRecalc,
  type BddsPlanFactPayload,
  type BddsPlanFactQuery,
} from "@/lib/api";
import { getAuthSession } from "@/lib/auth";

type EditorFilters = Omit<BddsPlanFactQuery, "hide_zero"> & {
  hide_zero?: boolean | null;
};

type Props = {
  project: string;
  filters: EditorFilters;
  onDataChange: (data: BddsPlanFactPayload) => void;
  onPreviewError?: (message: string | null) => void;
};

const COL = {
  section: "Раздел",
  lot: "Лот",
  dist: "Условие распределения",
  ps: "План. начало",
  pe: "План. окончание",
  bp: "БДДС план (утверждённый), млн руб.",
  bf: "БДДС факт, млн руб.",
  a: "A, %",
  b: "B, %",
  c: "C, %",
} as const;

const inputSm =
  "w-full min-w-0 rounded border border-tremor-border bg-tremor-background px-1.5 py-1 text-xs dark:border-dark-tremor-border dark:bg-dark-tremor-background";
const inputDist =
  "w-full min-w-[9.5rem] rounded border border-tremor-border bg-tremor-background px-1.5 py-1 text-xs dark:border-dark-tremor-border dark:bg-dark-tremor-background";
const HEAD =
  "border border-[#cbd5e1] bg-[#e8f0fe] px-1.5 py-2 text-[11px] font-semibold uppercase text-[#111827] dark:border-[#7a9ec4] dark:bg-[#16283a] dark:text-[#f0f4f8] whitespace-nowrap";
const CELL = "border border-[#cbd5e1] bg-tremor-background px-1.5 py-1 text-xs dark:border-[#7a9ec4] dark:bg-dark-tremor-background";
const TABLE =
  "w-full min-w-[980px] border-collapse border-2 border-[#94a3b8] text-left dark:border-[#7a9ec4]";
const FIELD =
  "text-[10px] font-semibold uppercase tracking-wide text-[#64748b] dark:text-slate-400";
/** Правые A/B/C всегда видны при горизонтальном скролле. */
const STICKY_C =
  "sticky right-0 z-20 shadow-[-6px_0_8px_-6px_rgba(15,23,42,0.35)]";
const STICKY_B = "sticky right-[3.75rem] z-20";
const STICKY_A = "sticky right-[7.5rem] z-20";
const STICKY_LOT =
  "sticky left-0 z-10 max-w-[11rem] shadow-[6px_0_8px_-6px_rgba(15,23,42,0.25)]";

function rowUsesAbc(dist: string): boolean {
  return dist.includes("%");
}

function renderHelpMd(md: string): React.ReactNode {
  return md.split("\n").map((line, i) => {
    const parts = line.split(/(\*\*[^*]+\*\*)/g);
    return (
      <p key={i} className="mb-2 last:mb-0">
        {parts.map((part, j) =>
          part.startsWith("**") && part.endsWith("**") ? (
            <strong key={j}>{part.slice(2, -2)}</strong>
          ) : (
            <span key={j}>{part}</span>
          ),
        )}
      </p>
    );
  });
}

function deltaClass(value: number): string {
  if (Math.abs(value) < 0.05) return "";
  return value < 0
    ? "font-semibold text-[#15803d] dark:text-emerald-300"
    : "font-semibold text-[#b91c1c] dark:text-rose-300";
}

export function BddsPlanFactEditor({
  project,
  filters,
  onDataChange,
  onPreviewError,
}: Props) {
  const [editor, setEditor] = useState<BddsPlanFactEditorPayload | null>(null);
  const [rows, setRows] = useState<BddsPlanFactEditRow[]>([]);
  const [baseline, setBaseline] = useState<BddsPlanFactEditRow[]>([]);
  const [showStruct, setShowStruct] = useState(false);
  const [helpOpen, setHelpOpen] = useState(false);
  const [loading, setLoading] = useState(true);
  const [previewing, setPreviewing] = useState(false);
  const [applying, setApplying] = useState(false);
  const [applyFlash, setApplyFlash] = useState(false);
  const [lotRecalc, setLotRecalc] = useState<BddsPlanFactLotRecalc | null>(null);
  const [lotPeriod, setLotPeriod] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const previewSeq = useRef(0);

  const session = getAuthSession();
  const canEdit = editor?.can_edit ?? false;

  const loadEditor = useCallback(async () => {
    setLoading(true);
    setLocalError(null);
    try {
      const payload = await fetchBddsPlanFactEditor(project, showStruct);
      setEditor(payload);
      setRows(payload.rows);
      setBaseline(payload.baseline_rows);
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : String(cause));
      setEditor(null);
      setRows([]);
    } finally {
      setLoading(false);
    }
  }, [project, showStruct]);

  useEffect(() => {
    void loadEditor();
  }, [loadEditor]);

  const visibleIndices = useMemo(() => {
    if (!editor) return rows.map((_, i) => i);
    if (showStruct) return rows.map((_, i) => i);
    const score = rows.map(
      (r) =>
        Number(r[COL.bp] || 0) +
        Number(r[COL.bf] || 0),
    );
    const indices =
      editor.visible_indices.length && !showStruct
        ? [...editor.visible_indices]
        : rows.map((_, i) => i);
    return indices.sort(
      (a, b) =>
        -score[a] + score[b] ||
        String(rows[a]?.[COL.lot] || "").localeCompare(
          String(rows[b]?.[COL.lot] || ""),
          "ru",
        ),
    );
  }, [editor, rows, showStruct]);

  const runPreview = useCallback(
    async (nextRows: BddsPlanFactEditRow[], period: string) => {
      const seq = ++previewSeq.current;
      setPreviewing(true);
      onPreviewError?.(null);
      try {
        const payload = await previewBddsPlanFact(project, nextRows, {
          ...filters,
          hide_zero: filters.hide_zero ?? undefined,
          lot_recalc_period: period || undefined,
        });
        if (seq !== previewSeq.current) return;
        onDataChange(payload);
        setLotRecalc(payload.lot_recalc ?? null);
        const nextPeriod = payload.lot_recalc?.selected_period ?? "";
        if (nextPeriod) {
          setLotPeriod((prev) => (prev === nextPeriod ? prev : nextPeriod));
        }
        if (payload.validation_errors?.length) {
          onPreviewError?.(payload.validation_errors.join("; "));
        }
      } catch (cause) {
        if (seq !== previewSeq.current) return;
        onPreviewError?.(cause instanceof Error ? cause.message : String(cause));
      } finally {
        if (seq === previewSeq.current) setPreviewing(false);
      }
    },
    [project, filters, onDataChange, onPreviewError],
  );

  useEffect(() => {
    if (!rows.length || loading) return;
    const timer = window.setTimeout(() => {
      void runPreview(rows, lotPeriod);
    }, 450);
    return () => window.clearTimeout(timer);
  }, [rows, filters, lotPeriod, loading, runPreview]);

  const patchRow = (index: number, patch: Partial<BddsPlanFactEditRow>) => {
    setRows((prev) =>
      prev.map((row, i) => (i === index ? { ...row, ...patch } : row)),
    );
  };

  const resetToFile = () => {
    setRows(baseline.map((r) => ({ ...r })));
  };

  const setAllDist = (dist: string) => {
    const useAbc =
      dist.includes("%") || dist.toLowerCase().includes("распредел");
    setRows((prev) => prev.map((r) => ({ ...r, [COL.dist]: dist })));
    if (useAbc) {
      // Сброс «Весь срок» (Δ=0) → API без period выберет первый месяц.
      setLotPeriod("");
      setLotRecalc(null);
    }
  };

  const handleApply = async () => {
    if (!canEdit) return;
    setApplying(true);
    setLocalError(null);
    try {
      const payload = await applyBddsPlanFactEdits(project, rows, {
        ...filters,
        hide_zero: filters.hide_zero ?? undefined,
        lot_recalc_period: lotPeriod || undefined,
      });
      onDataChange(payload);
      setLotRecalc(payload.lot_recalc ?? null);
      setApplyFlash(true);
      window.setTimeout(() => setApplyFlash(false), 3000);
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setApplying(false);
    }
  };

  if (loading && !editor) {
    return (
      <Card className="mb-4 rounded-xl">
        <Text>Загрузка редактора лотов…</Text>
      </Card>
    );
  }

  if (localError && !editor) {
    return (
      <Card className="mb-4 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
        <Text className="text-rose-700 dark:text-rose-300">{localError}</Text>
      </Card>
    );
  }

  return (
    <div className="mb-6 space-y-4">
      <Card className="rounded-xl">
        <Title className="!text-base !text-tremor-content-strong dark:!text-dark-tremor-content-strong">
          {canEdit ? "Редактирование данных задач" : "Данные задач (только просмотр)"}
        </Title>
        {!canEdit ? (
          <Text className="mt-2 text-sm text-amber-800 dark:text-amber-200">
            Редактирование недоступно. Ваша роль:{" "}
            <b>{session?.role_label || session?.role || "не выполнен вход"}</b>.
            Правки: Администратор, Суперадминистратор, РП или Финансист.
          </Text>
        ) : (
          <Text className="mt-2 text-sm text-tremor-content dark:text-dark-tremor-content">
            Правки в полях сразу идут в график/таблицу. «Применить правки» — зафиксировать
            в сессии (до перезагрузки).
            {previewing ? " · пересчёт…" : null}
          </Text>
        )}

        <details
          className="mt-3 rounded-lg border border-tremor-border p-3 dark:border-dark-tremor-border"
          open={helpOpen}
          onToggle={(e) => setHelpOpen((e.target as HTMLDetailsElement).open)}
        >
          <summary className="cursor-pointer text-sm font-medium">
            Как редактировать таблицу лотов
          </summary>
          <div className="mt-2 text-sm text-tremor-content dark:text-dark-tremor-content">
            {editor?.help_md ? renderHelpMd(editor.help_md) : null}
          </div>
        </details>

        {canEdit ? (
          <div className="mt-3 flex flex-wrap gap-2">
            <button
              type="button"
              className="rounded-lg border border-tremor-border px-3 py-1.5 text-sm hover:bg-tremor-background-subtle dark:border-dark-tremor-border"
              onClick={resetToFile}
            >
              Сбросить таблицу к данным файла
            </button>
            <button
              type="button"
              className="rounded-lg border border-tremor-border px-3 py-1.5 text-sm hover:bg-tremor-background-subtle dark:border-dark-tremor-border"
              onClick={() => setAllDist("% Распределения")}
            >
              Всем лотам: % A/B/C
            </button>
            <button
              type="button"
              className="rounded-lg border border-tremor-border px-3 py-1.5 text-sm hover:bg-tremor-background-subtle dark:border-dark-tremor-border"
              onClick={() => setAllDist("Равномерно")}
            >
              Всем лотам: равномерно
            </button>
          </div>
        ) : null}

        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={showStruct}
            onChange={(e) => setShowStruct(e.target.checked)}
            disabled={!canEdit}
          />
          Показать строки без БДДС план/факт
        </label>

        {editor && editor.hidden_struct_rows > 0 && !showStruct ? (
          <Text className="mt-2 text-xs text-tremor-content dark:text-dark-tremor-content">
            В редакторе {editor.visible_rows} из {editor.total_rows} строк (скрыто{" "}
            {editor.hidden_struct_rows} служебных узлов MSP без сумм).
          </Text>
        ) : null}

        <Text className="mt-2 text-xs text-tremor-content dark:text-dark-tremor-content">
          Лотов {visibleIndices.length} в редакторе (всего в проекте {rows.length}).
          По умолчанию «Равномерно» — A%/B%/C% заблокированы. План/факт по месяцам всегда
          делятся равномерно.
        </Text>

        {/* Mobile: карточки */}
        <div className="mt-3 flex flex-col gap-3 lg:hidden">
          {visibleIndices.map((rowIndex) => {
            const row = rows[rowIndex];
            if (!row) return null;
            const abc = rowUsesAbc(String(row[COL.dist] || ""));
            return (
              <section
                key={rowIndex}
                className="min-w-0 rounded-lg border-2 border-[#94a3b8] p-3 dark:border-[#7a9ec4]"
              >
                <div className="mb-1 text-sm font-semibold leading-snug text-tremor-content-strong dark:text-dark-tremor-content-strong">
                  {row[COL.lot] || "—"}
                </div>
                {row[COL.section] ? (
                  <Text className="mb-2 break-words text-xs text-tremor-content dark:text-dark-tremor-content">
                    Раздел: {row[COL.section]}
                  </Text>
                ) : null}
                <div className="grid gap-2">
                  <label className="block min-w-0">
                    <span className={FIELD}>Условие</span>
                    <select
                      className={`${inputSm} mt-1`}
                      value={row[COL.dist]}
                      disabled={!canEdit}
                      onChange={(e) =>
                        patchRow(rowIndex, { [COL.dist]: e.target.value })
                      }
                    >
                      {(editor?.dist_options ?? ["Равномерно", "% Распределения"]).map(
                        (opt) => (
                          <option key={opt} value={opt}>
                            {opt}
                          </option>
                        ),
                      )}
                    </select>
                  </label>
                  <div className="grid grid-cols-2 gap-2">
                    <label className="block min-w-0">
                      <span className={FIELD}>Начало</span>
                      <input
                        className={`${inputSm} mt-1`}
                        value={row[COL.ps]}
                        disabled={!canEdit}
                        onChange={(e) =>
                          patchRow(rowIndex, { [COL.ps]: e.target.value })
                        }
                      />
                    </label>
                    <label className="block min-w-0">
                      <span className={FIELD}>Конец</span>
                      <input
                        className={`${inputSm} mt-1`}
                        value={row[COL.pe]}
                        disabled={!canEdit}
                        onChange={(e) =>
                          patchRow(rowIndex, { [COL.pe]: e.target.value })
                        }
                      />
                    </label>
                    <label className="block min-w-0">
                      <span className={FIELD}>План, млн</span>
                      <input
                        type="number"
                        step="0.0001"
                        className={`${inputSm} mt-1 tabular-nums`}
                        value={row[COL.bp]}
                        disabled={!canEdit}
                        onChange={(e) =>
                          patchRow(rowIndex, {
                            [COL.bp]: Number(e.target.value || 0),
                          })
                        }
                      />
                    </label>
                    <label className="block min-w-0">
                      <span className={FIELD}>Факт, млн</span>
                      <input
                        type="number"
                        step="0.0001"
                        className={`${inputSm} mt-1 tabular-nums`}
                        value={row[COL.bf]}
                        disabled={!canEdit}
                        onChange={(e) =>
                          patchRow(rowIndex, {
                            [COL.bf]: Number(e.target.value || 0),
                          })
                        }
                      />
                    </label>
                  </div>
                  <div className="grid grid-cols-3 gap-2">
                    {([COL.a, COL.b, COL.c] as const).map((key, i) => (
                      <label key={key} className="block min-w-0">
                        <span className={FIELD}>{["A%", "B%", "C%"][i]}</span>
                        <input
                          type="number"
                          step="0.01"
                          className={`${inputSm} mt-1 tabular-nums`}
                          value={row[key]}
                          disabled={!canEdit || !abc}
                          onChange={(e) =>
                            patchRow(rowIndex, {
                              [key]: Number(e.target.value || 0),
                            })
                          }
                        />
                      </label>
                    ))}
                  </div>
                </div>
              </section>
            );
          })}
        </div>

        {/* Desktop: таблица; A/B/C и Лот закреплены — правый край виден без «искать скролл» */}
        <div className="mt-3 hidden lg:block">
          <div className="overflow-x-auto overflow-y-visible rounded-md border border-[#94a3b8] dark:border-[#7a9ec4]">
            <table className={TABLE}>
              <thead>
                <tr>
                  <th className={HEAD}>Раздел</th>
                  <th className={`${HEAD} ${STICKY_LOT}`}>Лот</th>
                  <th className={`${HEAD} min-w-[10rem]`}>Условие</th>
                  <th className={HEAD}>Начало</th>
                  <th className={HEAD}>Конец</th>
                  <th className={HEAD}>БДДС план</th>
                  <th className={HEAD}>БДДС факт</th>
                  <th className={`${HEAD} ${STICKY_A} w-[3.75rem] min-w-[3.75rem]`}>A%</th>
                  <th className={`${HEAD} ${STICKY_B} w-[3.75rem] min-w-[3.75rem]`}>B%</th>
                  <th className={`${HEAD} ${STICKY_C} w-[3.75rem] min-w-[3.75rem]`}>C%</th>
                </tr>
              </thead>
              <tbody>
                {visibleIndices.map((rowIndex) => {
                  const row = rows[rowIndex];
                  if (!row) return null;
                  const abc = rowUsesAbc(String(row[COL.dist] || ""));
                  return (
                    <tr key={rowIndex}>
                      <td
                        className={`${CELL} max-w-[7rem] truncate`}
                        title={row[COL.section]}
                      >
                        {row[COL.section]}
                      </td>
                      <td
                        className={`${CELL} ${STICKY_LOT} truncate`}
                        title={row[COL.lot]}
                      >
                        {row[COL.lot]}
                      </td>
                      <td className={`${CELL} min-w-[10rem]`}>
                        <select
                          className={inputDist}
                          value={row[COL.dist]}
                          disabled={!canEdit}
                          onChange={(e) =>
                            patchRow(rowIndex, { [COL.dist]: e.target.value })
                          }
                        >
                          {(
                            editor?.dist_options ?? ["Равномерно", "% Распределения"]
                          ).map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className={CELL}>
                        <input
                          className={`${inputSm} w-[6.5rem]`}
                          value={row[COL.ps]}
                          disabled={!canEdit}
                          onChange={(e) =>
                            patchRow(rowIndex, { [COL.ps]: e.target.value })
                          }
                        />
                      </td>
                      <td className={CELL}>
                        <input
                          className={`${inputSm} w-[6.5rem]`}
                          value={row[COL.pe]}
                          disabled={!canEdit}
                          onChange={(e) =>
                            patchRow(rowIndex, { [COL.pe]: e.target.value })
                          }
                        />
                      </td>
                      <td className={CELL}>
                        <input
                          type="number"
                          step="0.0001"
                          className={`${inputSm} w-[5rem] tabular-nums`}
                          value={row[COL.bp]}
                          disabled={!canEdit}
                          onChange={(e) =>
                            patchRow(rowIndex, {
                              [COL.bp]: Number(e.target.value || 0),
                            })
                          }
                        />
                      </td>
                      <td className={CELL}>
                        <input
                          type="number"
                          step="0.0001"
                          className={`${inputSm} w-[5rem] tabular-nums`}
                          value={row[COL.bf]}
                          disabled={!canEdit}
                          onChange={(e) =>
                            patchRow(rowIndex, {
                              [COL.bf]: Number(e.target.value || 0),
                            })
                          }
                        />
                      </td>
                      <td className={`${CELL} ${STICKY_A} w-[3.75rem]`}>
                        <input
                          type="number"
                          step="0.01"
                          className={`${inputSm} tabular-nums`}
                          value={row[COL.a]}
                          disabled={!canEdit || !abc}
                          onChange={(e) =>
                            patchRow(rowIndex, {
                              [COL.a]: Number(e.target.value || 0),
                            })
                          }
                        />
                      </td>
                      <td className={`${CELL} ${STICKY_B} w-[3.75rem]`}>
                        <input
                          type="number"
                          step="0.01"
                          className={`${inputSm} tabular-nums`}
                          value={row[COL.b]}
                          disabled={!canEdit || !abc}
                          onChange={(e) =>
                            patchRow(rowIndex, {
                              [COL.b]: Number(e.target.value || 0),
                            })
                          }
                        />
                      </td>
                      <td className={`${CELL} ${STICKY_C} w-[3.75rem]`}>
                        <input
                          type="number"
                          step="0.01"
                          className={`${inputSm} tabular-nums`}
                          value={row[COL.c]}
                          disabled={!canEdit || !abc}
                          onChange={(e) =>
                            patchRow(rowIndex, {
                              [COL.c]: Number(e.target.value || 0),
                            })
                          }
                        />
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        </div>

        {canEdit ? (
          <div className="mt-4 flex flex-wrap items-center gap-3">
            <button
              type="button"
              className="rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50"
              disabled={applying || previewing}
              onClick={() => void handleApply()}
            >
              {applying ? "Применение…" : "Применить правки"}
            </button>
            {applyFlash ? (
              <Text className="text-sm text-emerald-700 dark:text-emerald-300">
                Правки зафиксированы в сессии.
              </Text>
            ) : null}
            {editor?.applied ? (
              <Text className="text-xs text-tremor-content dark:text-dark-tremor-content">
                Сохранённые правки загружены.
              </Text>
            ) : null}
          </div>
        ) : null}
      </Card>

      {lotRecalc && lotRecalc.rows.length > 0 ? (
        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-base !text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Пересчёт по лотам: было → стало
            </Title>
          </div>
          <div className="space-y-3 px-4 py-3">
            <label className="block text-sm">
              <Text>Прогноз за период</Text>
              <select
                className="mt-1 w-full max-w-md rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={lotPeriod || lotRecalc.selected_period}
                onChange={(e) => setLotPeriod(e.target.value)}
              >
                {lotRecalc.period_choices.map((p) => (
                  <option key={p} value={p}>
                    {p}
                  </option>
                ))}
              </select>
            </label>
            <Text className="text-xs text-tremor-content dark:text-dark-tremor-content">
              {lotRecalc.caption}
            </Text>
            <div className="flex flex-col gap-3 lg:hidden">
              {lotRecalc.rows.map((row) => (
                <section
                  key={row.lot}
                  className="min-w-0 rounded-lg border-2 border-[#94a3b8] p-3 text-xs dark:border-[#7a9ec4]"
                >
                  <div className="mb-2 break-words font-semibold leading-snug">
                    {row.lot}
                  </div>
                  <dl className="grid grid-cols-2 gap-x-2 gap-y-1">
                    <dt>План</dt>
                    <dd className="text-right tabular-nums">{row.plan_mln.toFixed(1)}</dd>
                    <dt>Факт</dt>
                    <dd className="text-right tabular-nums">{row.fact_mln.toFixed(1)}</dd>
                    <dt className="col-span-2 break-words text-[10px] text-[#64748b]">
                      {lotRecalc.forecast_uniform_column}
                    </dt>
                    <dd className="col-span-2 text-right tabular-nums">
                      {row.forecast_uniform_mln.toFixed(1)}
                    </dd>
                    <dt className="col-span-2 break-words text-[10px] text-[#64748b]">
                      {lotRecalc.forecast_cond_column}
                    </dt>
                    <dd className="col-span-2 text-right tabular-nums">
                      {row.forecast_cond_mln.toFixed(1)}
                    </dd>
                    <dt>Δ</dt>
                    <dd
                      className={`text-right tabular-nums ${deltaClass(row.delta_mln)}`}
                    >
                      {row.delta_mln.toFixed(1)}
                    </dd>
                  </dl>
                </section>
              ))}
            </div>
            <div className="hidden overflow-x-auto lg:block">
              <table className={TABLE}>
                <thead>
                  <tr>
                    <th className={HEAD}>Лот</th>
                    <th className={`${HEAD} text-right`}>БДДС план, млн</th>
                    <th className={`${HEAD} text-right`}>БДДС факт, млн</th>
                    <th className={`${HEAD} text-right`}>
                      {lotRecalc.forecast_uniform_column}
                    </th>
                    <th className={`${HEAD} text-right`}>
                      {lotRecalc.forecast_cond_column}
                    </th>
                    <th className={`${HEAD} text-right`}>{lotRecalc.delta_column}</th>
                  </tr>
                </thead>
                <tbody>
                  {lotRecalc.rows.map((row) => (
                    <tr key={row.lot}>
                      <td className={CELL}>{row.lot}</td>
                      <td className={`${CELL} text-right tabular-nums`}>
                        {row.plan_mln.toFixed(1)}
                      </td>
                      <td className={`${CELL} text-right tabular-nums`}>
                        {row.fact_mln.toFixed(1)}
                      </td>
                      <td className={`${CELL} text-right tabular-nums`}>
                        {row.forecast_uniform_mln.toFixed(1)}
                      </td>
                      <td className={`${CELL} text-right tabular-nums`}>
                        {row.forecast_cond_mln.toFixed(1)}
                      </td>
                      <td
                        className={`${CELL} text-right tabular-nums ${deltaClass(row.delta_mln)}`}
                      >
                        {row.delta_mln.toFixed(1)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </div>
        </Card>
      ) : null}
    </div>
  );
}
