"use client";

import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { CircleHelp, MoreHorizontal, Search, X } from "lucide-react";
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
import { useIsMobileViewport } from "@/lib/use-is-mobile";
import { BddsLotEditSheet } from "@/components/bdds-lot-edit-sheet";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";

type EditorFilters = Omit<BddsPlanFactQuery, "hide_zero"> & {
  hide_zero?: boolean | null;
};

type Props = {
  project: string;
  filters: EditorFilters;
  onDataChange: (data: BddsPlanFactPayload) => void;
  onPreviewError?: (message: string | null) => void;
  /** Mobile: переключить вкладку на график/таблицы после применения. */
  onGoToOverview?: () => void;
};

type LotFilter = "all" | "sums" | "abc";

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
  "sticky left-0 z-10 min-w-[10rem] max-w-[14rem] shadow-[6px_0_8px_-6px_rgba(15,23,42,0.25)]";

const ROW_H = 72;
const LIST_MAX_H = 420;
const TIPS_STORAGE_KEY = "bdds-pf-mobile-tips-v1";

const MOBILE_TIPS: { title: string; body: string }[] = [
  {
    title: "Как править",
    body: "Тап по лоту → форма. Меняйте даты, план/факт и условие. График пересчитывается сразу; «Применить» фиксирует в сессии.",
  },
  {
    title: "План и факт",
    body: "Сумма лота делится равномерно по месяцам между «Начало» и «Конец». Условие A/B/C на план и факт не влияет.",
  },
  {
    title: "Прогноз",
    body: "«Равномерно» — прогноз как план по месяцам. «% Распределения» — A% в месяц начала, C% в конец, B% поровну в середине.",
  },
  {
    title: "A + B + C = 100%",
    body: "При «% Распределения» поля A/B/C открываются. Сумма должна быть ровно 100%, иначе прогноз будет неверным.",
  },
  {
    title: "После правок",
    body: "«Применить» → смотрите «было → стало» или вкладку «Обзор» с графиком. Меню ⋯ — сброс и «всем лотам».",
  },
];

function FieldTip({ children }: { children: React.ReactNode }) {
  return (
    <p className="mt-1 text-[11px] leading-snug text-sky-800 dark:text-sky-200/90">
      {children}
    </p>
  );
}

function MobileTipsCoach({
  open,
  step,
  onStep,
  onClose,
}: {
  open: boolean;
  step: number;
  onStep: (n: number) => void;
  onClose: () => void;
}) {
  if (!open) return null;
  const tip = MOBILE_TIPS[step] ?? MOBILE_TIPS[0];
  const last = step >= MOBILE_TIPS.length - 1;
  return (
    <div
      className="mt-3 rounded-xl border border-sky-300 bg-sky-50 p-3 dark:border-sky-700 dark:bg-sky-950/40 lg:hidden"
      role="status"
    >
      <div className="flex items-start justify-between gap-2">
        <div className="min-w-0">
          <p className="text-[10px] font-semibold uppercase tracking-wide text-sky-700 dark:text-sky-300">
            Подсказка {step + 1}/{MOBILE_TIPS.length}
          </p>
          <p className="mt-1 text-sm font-semibold text-sky-950 dark:text-sky-50">
            {tip.title}
          </p>
          <p className="mt-1 text-sm leading-snug text-sky-900/90 dark:text-sky-100/90">
            {tip.body}
          </p>
        </div>
        <button
          type="button"
          className="inline-flex h-9 w-9 shrink-0 items-center justify-center rounded-lg text-sky-700 dark:text-sky-200"
          aria-label="Закрыть подсказки"
          onClick={onClose}
        >
          <X className="h-4 w-4" />
        </button>
      </div>
      <div className="mt-3 flex items-center gap-2">
        <div className="flex flex-1 gap-1">
          {MOBILE_TIPS.map((_, i) => (
            <span
              key={i}
              className={`h-1.5 flex-1 rounded-full ${
                i === step ? "bg-sky-600" : "bg-sky-200 dark:bg-sky-900"
              }`}
            />
          ))}
        </div>
        {!last ? (
          <button
            type="button"
            className="min-h-10 shrink-0 rounded-lg bg-sky-600 px-3 text-sm font-semibold text-white active:bg-sky-700"
            onClick={() => {
              tapFeedback();
              onStep(step + 1);
            }}
          >
            Далее
          </button>
        ) : (
          <button
            type="button"
            className="min-h-10 shrink-0 rounded-lg bg-sky-600 px-3 text-sm font-semibold text-white active:bg-sky-700"
            onClick={() => {
              confirmFeedback();
              onClose();
            }}
          >
            Понятно
          </button>
        )}
      </div>
    </div>
  );
}

function rowUsesAbc(dist: string): boolean {
  return dist.includes("%");
}

function toDateInputValue(raw: string): string {
  const s = String(raw || "").trim();
  if (/^\d{4}-\d{2}-\d{2}$/.test(s)) return s;
  const m = s.match(/^(\d{2})\.(\d{2})\.(\d{4})$/);
  if (m) return `${m[3]}-${m[2]}-${m[1]}`;
  return s;
}

function fmtMln(v: unknown): string {
  const n = Number(v || 0);
  return Number.isFinite(n) ? n.toFixed(1) : "0.0";
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

function LotEditForm({
  row,
  canEdit,
  distOptions,
  onPatch,
}: {
  row: BddsPlanFactEditRow;
  canEdit: boolean;
  distOptions: string[];
  onPatch: (patch: Partial<BddsPlanFactEditRow>) => void;
}) {
  const abc = rowUsesAbc(String(row[COL.dist] || ""));
  const abcSum =
    Number(row[COL.a] || 0) + Number(row[COL.b] || 0) + Number(row[COL.c] || 0);
  const abcOk = Math.abs(abcSum - 100) < 0.05;
  return (
    <div className="grid gap-3">
      <div className="rounded-lg border border-sky-200 bg-sky-50/80 px-3 py-2 text-[12px] leading-snug text-sky-950 dark:border-sky-800 dark:bg-sky-950/30 dark:text-sky-100">
        Правки сразу влияют на график. Для фиксации нажмите «Применить» внизу
        экрана после закрытия формы.
      </div>
      {row[COL.section] ? (
        <Text className="break-words text-xs text-tremor-content dark:text-dark-tremor-content">
          Раздел: {row[COL.section]}
        </Text>
      ) : null}
      <label className="block min-w-0">
        <span className={FIELD}>Условие</span>
        <select
          className={`${inputSm} mt-1 min-h-11 text-sm`}
          value={row[COL.dist]}
          disabled={!canEdit}
          onChange={(e) => onPatch({ [COL.dist]: e.target.value })}
        >
          {distOptions.map((opt) => (
            <option key={opt} value={opt}>
              {opt}
            </option>
          ))}
        </select>
        <FieldTip>
          {abc
            ? "Прогноз: A% — месяц начала, C% — окончания, B% — поровну в середине."
            : "Равномерно: прогноз = план, поровну по месяцам срока. Для A/B/C выберите «% Распределения»."}
        </FieldTip>
      </label>
      <div className="grid grid-cols-2 gap-2">
        <label className="block min-w-0">
          <span className={FIELD}>Начало</span>
          <input
            type="date"
            className={`${inputSm} mt-1 min-h-11 text-sm`}
            value={toDateInputValue(String(row[COL.ps] || ""))}
            disabled={!canEdit}
            onChange={(e) => onPatch({ [COL.ps]: e.target.value })}
          />
        </label>
        <label className="block min-w-0">
          <span className={FIELD}>Конец</span>
          <input
            type="date"
            className={`${inputSm} mt-1 min-h-11 text-sm`}
            value={toDateInputValue(String(row[COL.pe] || ""))}
            disabled={!canEdit}
            onChange={(e) => onPatch({ [COL.pe]: e.target.value })}
          />
        </label>
        <label className="block min-w-0">
          <span className={FIELD}>План, млн</span>
          <input
            type="number"
            step="0.0001"
            inputMode="decimal"
            className={`${inputSm} mt-1 min-h-11 text-sm tabular-nums`}
            value={row[COL.bp]}
            disabled={!canEdit}
            onChange={(e) =>
              onPatch({ [COL.bp]: Number(e.target.value || 0) })
            }
          />
        </label>
        <label className="block min-w-0">
          <span className={FIELD}>Факт, млн</span>
          <input
            type="number"
            step="0.0001"
            inputMode="decimal"
            className={`${inputSm} mt-1 min-h-11 text-sm tabular-nums`}
            value={row[COL.bf]}
            disabled={!canEdit}
            onChange={(e) =>
              onPatch({ [COL.bf]: Number(e.target.value || 0) })
            }
          />
        </label>
      </div>
      <FieldTip>
        План и факт всегда делятся равномерно по месяцам между началом и концом
        (A/B/C на них не влияет).
      </FieldTip>
      <div className="grid grid-cols-3 gap-2">
        {([COL.a, COL.b, COL.c] as const).map((key, i) => (
          <label key={key} className="block min-w-0">
            <span className={FIELD}>{["A%", "B%", "C%"][i]}</span>
            <input
              type="number"
              step="0.01"
              inputMode="decimal"
              className={`${inputSm} mt-1 min-h-11 text-sm tabular-nums`}
              value={row[key]}
              disabled={!canEdit || !abc}
              onChange={(e) =>
                onPatch({ [key]: Number(e.target.value || 0) })
              }
            />
          </label>
        ))}
      </div>
      {abc ? (
        <p
          className={`text-[11px] font-medium leading-snug ${
            abcOk
              ? "text-emerald-700 dark:text-emerald-300"
              : "text-rose-700 dark:text-rose-300"
          }`}
        >
          {abcOk
            ? `A+B+C = ${abcSum.toFixed(1)}% — ок`
            : `A+B+C = ${abcSum.toFixed(1)}% — нужно 100%`}
        </p>
      ) : (
        <FieldTip>A/B/C заблокированы, пока условие «Равномерно».</FieldTip>
      )}
    </div>
  );
}

/** Простой windowed-список без внешних зависимостей. */
function VirtualLotList({
  indices,
  rows,
  onOpen,
}: {
  indices: number[];
  rows: BddsPlanFactEditRow[];
  onOpen: (rowIndex: number) => void;
}) {
  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const [scrollTop, setScrollTop] = useState(0);
  const total = Math.max(ROW_H, indices.length * ROW_H);
  const height = Math.min(LIST_MAX_H, total);
  const start = Math.max(0, Math.floor(scrollTop / ROW_H) - 2);
  const visibleCount = Math.ceil(height / ROW_H) + 4;
  const end = Math.min(indices.length, start + visibleCount);
  const slice = indices.slice(start, end);

  return (
    <div
      ref={scrollerRef}
      className="overflow-y-auto overscroll-contain rounded-lg border border-[#94a3b8] dark:border-[#7a9ec4]"
      style={{ maxHeight: LIST_MAX_H, height: Math.min(height, LIST_MAX_H) }}
      onScroll={(e) => setScrollTop((e.target as HTMLDivElement).scrollTop)}
    >
      <div style={{ height: total, position: "relative" }}>
        {slice.map((rowIndex, i) => {
          const row = rows[rowIndex];
          if (!row) return null;
          const abc = rowUsesAbc(String(row[COL.dist] || ""));
          const top = (start + i) * ROW_H;
          return (
            <button
              key={rowIndex}
              type="button"
              style={{ top, height: ROW_H }}
              className="absolute inset-x-0 flex w-full items-center gap-2 border-b border-[#e2e8f0] px-3 text-left active:bg-slate-50 dark:border-[#334155] dark:active:bg-slate-800/60"
              onClick={() => {
                tapFeedback();
                onOpen(rowIndex);
              }}
            >
              <div className="min-w-0 flex-1">
                <div className="truncate text-sm font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong">
                  {row[COL.lot] || "—"}
                </div>
                <div className="mt-0.5 flex flex-wrap items-center gap-x-2 gap-y-0.5 text-[11px] text-tremor-content dark:text-dark-tremor-content">
                  <span className="tabular-nums">
                    П {fmtMln(row[COL.bp])} · Ф {fmtMln(row[COL.bf])}
                  </span>
                  <span
                    className={`rounded-full px-1.5 py-0.5 text-[10px] font-medium ${
                      abc
                        ? "bg-sky-100 text-sky-900 dark:bg-sky-950/50 dark:text-sky-200"
                        : "bg-slate-100 text-slate-700 dark:bg-slate-800 dark:text-slate-300"
                    }`}
                  >
                    {abc ? "% A/B/C" : "Равномерно"}
                  </span>
                </div>
              </div>
              <span className="shrink-0 text-lg text-slate-400" aria-hidden>
                ›
              </span>
            </button>
          );
        })}
      </div>
    </div>
  );
}

export function BddsPlanFactEditor({
  project,
  filters,
  onDataChange,
  onPreviewError,
  onGoToOverview,
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
  const [postApplyPrompt, setPostApplyPrompt] = useState(false);
  const [lotRecalc, setLotRecalc] = useState<BddsPlanFactLotRecalc | null>(null);
  const [lotPeriod, setLotPeriod] = useState("");
  const [localError, setLocalError] = useState<string | null>(null);
  const [applyBlinkOn, setApplyBlinkOn] = useState(false);
  const [lotQuery, setLotQuery] = useState("");
  const [lotFilter, setLotFilter] = useState<LotFilter>("all");
  const [editIndex, setEditIndex] = useState<number | null>(null);
  const [bulkOpen, setBulkOpen] = useState(false);
  const [tipsOpen, setTipsOpen] = useState(false);
  const [tipStep, setTipStep] = useState(0);
  const previewSeq = useRef(0);
  const mobile = useIsMobileViewport();
  const periodSelectRef = useRef<HTMLSelectElement | null>(null);
  const bulkMenuRef = useRef<HTMLDivElement | null>(null);
  const lotRecalcRef = useRef<HTMLDivElement | null>(null);

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

  useEffect(() => {
    if (!mobile || !canEdit) return;
    try {
      if (window.localStorage.getItem(TIPS_STORAGE_KEY) === "1") return;
    } catch {
      /* ignore */
    }
    setTipStep(0);
    setTipsOpen(true);
  }, [mobile, canEdit]);

  const closeTips = useCallback(() => {
    setTipsOpen(false);
    try {
      window.localStorage.setItem(TIPS_STORAGE_KEY, "1");
    } catch {
      /* ignore */
    }
  }, []);

  const reopenTips = useCallback(() => {
    setTipStep(0);
    setTipsOpen(true);
    setBulkOpen(false);
  }, []);

  useEffect(() => {
    if (!bulkOpen) return;
    const onDoc = (e: MouseEvent) => {
      if (!bulkMenuRef.current?.contains(e.target as Node)) setBulkOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    return () => document.removeEventListener("mousedown", onDoc);
  }, [bulkOpen]);

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

  const filteredIndices = useMemo(() => {
    const q = lotQuery.trim().toLowerCase();
    return visibleIndices.filter((i) => {
      const row = rows[i];
      if (!row) return false;
      const bp = Number(row[COL.bp] || 0);
      const bf = Number(row[COL.bf] || 0);
      const abc = rowUsesAbc(String(row[COL.dist] || ""));
      if (lotFilter === "sums" && bp === 0 && bf === 0) return false;
      if (lotFilter === "abc" && !abc) return false;
      if (!q) return true;
      const hay = `${row[COL.lot] || ""} ${row[COL.section] || ""}`.toLowerCase();
      return hay.includes(q);
    });
  }, [visibleIndices, rows, lotQuery, lotFilter]);

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
    setBulkOpen(false);
  };

  const setAllDist = (dist: string) => {
    setRows((prev) => prev.map((r) => ({ ...r, [COL.dist]: dist })));
    setBulkOpen(false);
  };

  const effectiveLotPeriod =
    lotPeriod || lotRecalc?.selected_period || "";
  const isFullTermPeriod = /весь срок/i.test(effectiveLotPeriod);
  const hasAbcRows = rows.some((r) =>
    rowUsesAbc(String(r[COL.dist] || "")),
  );
  /** На «весь срок» Δ=0 — нужно выбрать месяц. Desktop: мигание кнопки; mobile: баннер + 1 тап. */
  const nudgePickMonth =
    canEdit && hasAbcRows && isFullTermPeriod && Boolean(lotRecalc) && !applying;
  const firstMonthChoice =
    lotRecalc?.period_choices.find((p) => !/весь срок/i.test(p)) || "";
  const monthChoices = useMemo(
    () => (lotRecalc?.period_choices || []).filter((p) => !/весь срок/i.test(p)),
    [lotRecalc?.period_choices],
  );

  useEffect(() => {
    if (!nudgePickMonth || previewing || mobile) {
      setApplyBlinkOn(false);
      return;
    }
    const id = window.setInterval(() => {
      setApplyBlinkOn((v) => !v);
    }, 650);
    return () => window.clearInterval(id);
  }, [nudgePickMonth, previewing, mobile]);

  const applyButtonLabel = applying
    ? "Применение…"
    : previewing
      ? "Пересчет"
      : nudgePickMonth && !mobile
        ? applyBlinkOn
          ? "Пересчет"
          : "Применить правки"
        : "Применить правки";

  const pickFirstMonth = () => {
    if (!firstMonthChoice) return;
    setLotPeriod(firstMonthChoice);
    periodSelectRef.current?.scrollIntoView({
      behavior: "smooth",
      block: "center",
    });
  };

  const scrollToLotRecalc = useCallback(() => {
    setPostApplyPrompt(false);
    window.setTimeout(() => {
      lotRecalcRef.current?.scrollIntoView({
        behavior: "smooth",
        block: "start",
      });
    }, 50);
  }, []);

  const goOverviewAfterApply = useCallback(() => {
    setPostApplyPrompt(false);
    confirmFeedback();
    onGoToOverview?.();
  }, [onGoToOverview]);

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
      setEditIndex(null);
      setApplyFlash(true);
      window.setTimeout(() => setApplyFlash(false), 3000);
      if (mobile) {
        confirmFeedback();
        setPostApplyPrompt(true);
      }
    } catch (cause) {
      setLocalError(cause instanceof Error ? cause.message : String(cause));
    } finally {
      setApplying(false);
    }
  };

  const editRow = editIndex != null ? rows[editIndex] : null;
  const distOptions = editor?.dist_options ?? ["Равномерно", "% Распределения"];

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
      <Card
        className={`relative rounded-xl lg:pb-4 ${
          postApplyPrompt || (nudgePickMonth && !previewing) ? "pb-52" : "pb-20"
        }`}
      >
        <div className="flex items-start justify-between gap-2">
          <Title className="!text-base !text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            {canEdit ? "Редактирование данных задач" : "Данные задач (только просмотр)"}
          </Title>
          <div className="flex shrink-0 items-center gap-1.5 lg:hidden">
            <button
              type="button"
              className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-tremor-border dark:border-dark-tremor-border"
              aria-label="Подсказки по редактированию"
              onClick={() => {
                tapFeedback();
                reopenTips();
              }}
            >
              <CircleHelp className="h-5 w-5" />
            </button>
            {canEdit ? (
              <div className="relative" ref={bulkMenuRef}>
                <button
                  type="button"
                  className="inline-flex h-10 w-10 items-center justify-center rounded-lg border border-tremor-border dark:border-dark-tremor-border"
                  aria-label="Действия"
                  aria-expanded={bulkOpen}
                  onClick={() => setBulkOpen((v) => !v)}
                >
                  <MoreHorizontal className="h-5 w-5" />
                </button>
                {bulkOpen ? (
                  <div className="absolute right-0 z-30 mt-1 w-56 overflow-hidden rounded-xl border border-tremor-border bg-tremor-background shadow-lg dark:border-dark-tremor-border dark:bg-dark-tremor-background">
                    <button
                      type="button"
                      className="block w-full px-3 py-2.5 text-left text-sm hover:bg-tremor-background-subtle"
                      onClick={reopenTips}
                    >
                      Подсказки по редактированию
                    </button>
                    <button
                      type="button"
                      className="block w-full px-3 py-2.5 text-left text-sm hover:bg-tremor-background-subtle"
                      onClick={resetToFile}
                    >
                      Сбросить к данным файла
                    </button>
                    <button
                      type="button"
                      className="block w-full px-3 py-2.5 text-left text-sm hover:bg-tremor-background-subtle"
                      onClick={() => setAllDist("% Распределения")}
                    >
                      Всем лотам: % A/B/C
                    </button>
                    <button
                      type="button"
                      className="block w-full px-3 py-2.5 text-left text-sm hover:bg-tremor-background-subtle"
                      onClick={() => setAllDist("Равномерно")}
                    >
                      Всем лотам: равномерно
                    </button>
                  </div>
                ) : null}
              </div>
            ) : null}
          </div>
        </div>

        {!canEdit ? (
          <Text className="mt-2 text-sm text-amber-800 dark:text-amber-200">
            Редактирование недоступно. Ваша роль:{" "}
            <b>{session?.role_label || session?.role || "не выполнен вход"}</b>.
            Правки: Администратор, Суперадминистратор, РП или Финансист.
          </Text>
        ) : (
          <Text className="mt-2 hidden text-sm text-tremor-content dark:text-dark-tremor-content lg:block">
            Правки в полях сразу идут в график/таблицу. «Применить правки» — зафиксировать
            в сессии (до перезагрузки).
            {previewing ? " · пересчёт…" : null}
            {nudgePickMonth && !previewing
              ? " · на «весь срок» Δ=0 — выберите месяц в «Прогноз за период»"
              : null}
          </Text>
        )}

        <MobileTipsCoach
          open={tipsOpen && mobile}
          step={tipStep}
          onStep={setTipStep}
          onClose={closeTips}
        />

        {!tipsOpen && canEdit && mobile ? (
          <button
            type="button"
            className="mt-3 flex min-h-10 w-full items-center gap-2 rounded-xl border border-dashed border-sky-300 bg-sky-50/60 px-3 py-2 text-left text-xs text-sky-900 dark:border-sky-700 dark:bg-sky-950/30 dark:text-sky-100 lg:hidden"
            onClick={() => {
              tapFeedback();
              reopenTips();
            }}
          >
            <CircleHelp className="h-4 w-4 shrink-0" />
            <span>Тап по лоту → правка. Нужна помощь? Открыть подсказки.</span>
          </button>
        ) : null}

        <details
          className="mt-3 hidden rounded-lg border border-tremor-border p-3 dark:border-dark-tremor-border lg:block"
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

        {/* Desktop bulk actions */}
        {canEdit ? (
          <div className="mt-3 hidden flex-wrap gap-2 lg:flex">
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

        {/* Mobile: поиск + фильтр + компактный список → sheet */}
        <div className="mt-3 space-y-2 lg:hidden">
          <div className="relative">
            <Search className="pointer-events-none absolute left-3 top-1/2 h-4 w-4 -translate-y-1/2 text-slate-400" />
            <input
              type="search"
              value={lotQuery}
              onChange={(e) => setLotQuery(e.target.value)}
              placeholder="Поиск лота или раздела"
              className="min-h-11 w-full rounded-xl border border-tremor-border bg-tremor-background py-2 pl-9 pr-9 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            />
            {lotQuery ? (
              <button
                type="button"
                className="absolute right-2 top-1/2 inline-flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-lg text-slate-500"
                aria-label="Очистить поиск"
                onClick={() => setLotQuery("")}
              >
                <X className="h-4 w-4" />
              </button>
            ) : null}
          </div>
          <div className="flex gap-1.5 overflow-x-auto pb-0.5">
            {(
              [
                ["all", "Все"],
                ["sums", "С суммами"],
                ["abc", "Только %"],
              ] as const
            ).map(([id, label]) => (
              <button
                key={id}
                type="button"
                onClick={() => setLotFilter(id)}
                className={`min-h-9 shrink-0 rounded-full px-3 text-xs font-medium ${
                  lotFilter === id
                    ? "bg-sky-600 text-white"
                    : "border border-tremor-border text-tremor-content dark:border-dark-tremor-border dark:text-dark-tremor-content"
                }`}
              >
                {label}
              </button>
            ))}
          </div>
          <Text className="text-xs text-tremor-content dark:text-dark-tremor-content">
            Фильтр списка · показано {filteredIndices.length} из{" "}
            {visibleIndices.length}. Тап по лоту — правка.
          </Text>
          {filteredIndices.length ? (
            <VirtualLotList
              indices={filteredIndices}
              rows={rows}
              onOpen={setEditIndex}
            />
          ) : (
            <div className="rounded-lg border border-dashed border-slate-300 px-3 py-5 text-center dark:border-slate-600">
              <p className="text-sm text-slate-600 dark:text-slate-300">
                {lotFilter === "abc"
                  ? "Пока ни у одного лота нет условия «% Распределения» — фильтр пустой."
                  : lotFilter === "sums"
                    ? "Нет лотов с ненулевым планом/фактом."
                    : "Ничего не найдено"}
              </p>
              {lotFilter === "abc" && canEdit ? (
                <button
                  type="button"
                  className="mt-3 min-h-11 w-full rounded-xl bg-sky-600 px-3 text-sm font-semibold text-white active:bg-sky-700"
                  onClick={() => {
                    tapFeedback();
                    setAllDist("% Распределения");
                    setLotFilter("all");
                  }}
                >
                  Включить всем лотам % A/B/C
                </button>
              ) : (
                <button
                  type="button"
                  className="mt-3 min-h-10 text-sm text-sky-700 dark:text-sky-300"
                  onClick={() => {
                    setLotFilter("all");
                    setLotQuery("");
                  }}
                >
                  Сбросить фильтр
                </button>
              )}
            </div>
          )}
        </div>

        <BddsLotEditSheet
          open={editIndex != null && editRow != null}
          onClose={() => setEditIndex(null)}
          title={String(editRow?.[COL.lot] || "Лот")}
        >
          {editRow && editIndex != null ? (
            <LotEditForm
              row={editRow}
              canEdit={canEdit}
              distOptions={distOptions}
              onPatch={(patch) => patchRow(editIndex, patch)}
            />
          ) : null}
        </BddsLotEditSheet>

        {/* Desktop: таблица; A/B/C и Лот закреплены */}
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
                        className={`${CELL} min-w-[9rem] max-w-[14rem] whitespace-normal break-words align-top leading-snug`}
                        title={row[COL.section]}
                      >
                        {row[COL.section] || "—"}
                      </td>
                      <td
                        className={`${CELL} ${STICKY_LOT} whitespace-normal break-words align-top leading-snug`}
                        title={row[COL.lot]}
                      >
                        {row[COL.lot] || "—"}
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
                          {distOptions.map((opt) => (
                            <option key={opt} value={opt}>
                              {opt}
                            </option>
                          ))}
                        </select>
                      </td>
                      <td className={CELL}>
                        <input
                          type="date"
                          className={`${inputSm} w-[8.5rem]`}
                          value={toDateInputValue(String(row[COL.ps] || ""))}
                          disabled={!canEdit}
                          onChange={(e) =>
                            patchRow(rowIndex, { [COL.ps]: e.target.value })
                          }
                        />
                      </td>
                      <td className={CELL}>
                        <input
                          type="date"
                          className={`${inputSm} w-[8.5rem]`}
                          value={toDateInputValue(String(row[COL.pe] || ""))}
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

        {/* Desktop apply */}
        {canEdit ? (
          <div className="mt-4 hidden flex-wrap items-center gap-3 lg:flex">
            <button
              type="button"
              className={`rounded-lg bg-sky-600 px-4 py-2 text-sm font-medium text-white hover:bg-sky-700 disabled:opacity-50 ${
                nudgePickMonth && !previewing
                  ? applyBlinkOn
                    ? "opacity-100 ring-2 ring-sky-300"
                    : "opacity-70"
                  : ""
              }`}
              disabled={applying || previewing}
              onClick={() => void handleApply()}
            >
              {applyButtonLabel}
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

        {/* Mobile sticky: после Apply — предложить смотреть эффект; иначе Apply / nudge месяца */}
        {canEdit ? (
          <div className="fixed inset-x-0 bottom-0 z-40 border-t border-tremor-border bg-tremor-background/95 px-3 py-2 backdrop-blur supports-[padding:max(0px)]:pb-[max(0.5rem,env(safe-area-inset-bottom))] dark:border-dark-tremor-border dark:bg-dark-tremor-background/95 lg:hidden">
            {postApplyPrompt ? (
              <div className="mx-auto max-w-lg space-y-2">
                <p className="text-center text-sm font-medium text-emerald-800 dark:text-emerald-200">
                  Правки применены. Что дальше?
                </p>
                <div className="flex flex-col gap-2">
                  {lotRecalc && lotRecalc.rows.length > 0 ? (
                    <button
                      type="button"
                      className="min-h-11 w-full rounded-xl bg-sky-600 px-4 text-sm font-semibold text-white active:bg-sky-700"
                      onClick={() => {
                        tapFeedback();
                        scrollToLotRecalc();
                      }}
                    >
                      Смотреть было → стало
                    </button>
                  ) : null}
                  {onGoToOverview ? (
                    <button
                      type="button"
                      className="min-h-11 w-full rounded-xl border border-tremor-border bg-tremor-background px-4 text-sm font-semibold text-tremor-content-strong active:bg-tremor-background-subtle dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
                      onClick={goOverviewAfterApply}
                    >
                      К обзору (график)
                    </button>
                  ) : null}
                  <button
                    type="button"
                    className="min-h-10 w-full text-sm text-slate-500"
                    onClick={() => setPostApplyPrompt(false)}
                  >
                    Остаться в редакторе
                  </button>
                </div>
              </div>
            ) : nudgePickMonth && !previewing ? (
              <div className="mx-auto max-w-lg space-y-2">
                <p className="text-center text-xs leading-snug text-amber-900 dark:text-amber-100">
                  На «весь срок» Δ=0. Выберите месяц — как мигание «Применить» на
                  десктопе.
                </p>
                {firstMonthChoice ? (
                  <button
                    type="button"
                    className="min-h-11 w-full rounded-xl bg-amber-600 px-4 text-sm font-semibold text-white active:bg-amber-700"
                    onClick={() => {
                      tapFeedback();
                      pickFirstMonth();
                      scrollToLotRecalc();
                    }}
                  >
                    Показать Δ · {firstMonthChoice}
                  </button>
                ) : null}
                <button
                  type="button"
                  className="min-h-11 w-full rounded-xl bg-sky-600 px-4 text-sm font-semibold text-white active:bg-sky-700 disabled:opacity-50"
                  disabled={applying || previewing}
                  onClick={() => void handleApply()}
                >
                  {applyButtonLabel}
                </button>
              </div>
            ) : (
              <div className="mx-auto flex max-w-lg items-center gap-2">
                <button
                  type="button"
                  className="min-h-11 flex-1 rounded-xl bg-sky-600 px-4 text-sm font-semibold text-white active:bg-sky-700 disabled:opacity-50"
                  disabled={applying || previewing}
                  onClick={() => void handleApply()}
                >
                  {applyButtonLabel}
                </button>
                {previewing ? (
                  <span className="shrink-0 text-xs text-slate-500">пересчёт…</span>
                ) : null}
                {applyFlash ? (
                  <span className="shrink-0 text-xs font-medium text-emerald-700 dark:text-emerald-300">
                    OK
                  </span>
                ) : null}
              </div>
            )}
          </div>
        ) : null}
      </Card>

      {lotRecalc && lotRecalc.rows.length > 0 ? (
        <div ref={lotRecalcRef} className="scroll-mt-4">
        <Card className="overflow-hidden rounded-xl p-0">
          <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
            <Title className="!text-base !text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              Пересчёт по лотам: было → стало
            </Title>
          </div>
          <div className="space-y-3 px-4 py-3">
            {nudgePickMonth && !previewing ? (
              <div className="rounded-xl border border-amber-300 bg-amber-50 px-3 py-3 text-sm text-amber-950 dark:border-amber-700 dark:bg-amber-950/40 dark:text-amber-100 lg:hidden">
                <p className="leading-snug">
                  На <b>всём сроке</b> Δ = 0: A/B/C только перекладывает суммы по
                  месяцам. Чтобы увидеть эффект — выберите месяц.
                </p>
                {firstMonthChoice ? (
                  <button
                    type="button"
                    className="mt-3 min-h-11 w-full rounded-lg bg-amber-600 px-3 py-2.5 text-sm font-semibold text-white active:bg-amber-700"
                    onClick={pickFirstMonth}
                  >
                    Показать Δ · {firstMonthChoice}
                  </button>
                ) : null}
                {monthChoices.length > 1 ? (
                  <div className="-mx-1 mt-3 flex gap-2 overflow-x-auto px-1 pb-1">
                    {monthChoices.slice(0, 12).map((p) => (
                      <button
                        key={p}
                        type="button"
                        onClick={() => setLotPeriod(p)}
                        className="min-h-10 shrink-0 rounded-full border border-amber-400 bg-white px-3 py-1.5 text-xs font-medium text-amber-950 dark:border-amber-600 dark:bg-dark-tremor-background dark:text-amber-100"
                      >
                        {p}
                      </button>
                    ))}
                  </div>
                ) : null}
              </div>
            ) : null}
            <label className="block text-sm">
              <Text>Прогноз за период</Text>
              <select
                ref={periodSelectRef}
                className={`mt-1 w-full max-w-md rounded-tremor-default border bg-tremor-background px-3 py-2 text-sm dark:bg-dark-tremor-background ${
                  nudgePickMonth && !previewing
                    ? "border-amber-400 ring-2 ring-amber-200 dark:border-amber-500 dark:ring-amber-900"
                    : "border-tremor-border dark:border-dark-tremor-border"
                }`}
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
        </div>
      ) : null}
    </div>
  );
}
