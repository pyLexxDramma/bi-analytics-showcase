"use client";

import {
  useCallback,
  useEffect,
  useId,
  useLayoutEffect,
  useMemo,
  useRef,
  useState,
} from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { createPortal } from "react-dom";
import { FiltersSheet } from "@/components/filters-sheet";
import { FilterStickyBar } from "@/components/filter-sticky-bar";
import type { ActiveFilter } from "@/lib/filters-summary";
import {
  deleteFilterPreset,
  listFilterPresets,
  type FilterPreset,
} from "@/lib/filter-presets";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";
import { useIsMobileViewport } from "@/lib/use-is-mobile";
import { AclFilterGate } from "@/lib/use-report-ui-acl";
import { usePathname, useRouter } from "next/navigation";

/** Shared select/date look — fixed height, non-OS chrome, focus-visible only. */
export const FILTER_SELECT_CLASS =
  "bi-filters-select w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 text-tremor-default text-tremor-content-strong outline-none focus-visible:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong disabled:opacity-50";

/** Date inputs: full visible date, same height as selects. */
export const FILTER_DATE_CLASS = `${FILTER_SELECT_CLASS} bi-filters-date`;

export type FilterChipOption = string | { value: string; label: string };

function normChipOption(opt: FilterChipOption): { value: string; label: string } {
  if (typeof opt === "string") return { value: opt, label: opt };
  return opt;
}

/** Длинные списки (подрядчики, проекты) — поиск в combobox. */
const CHIP_SEARCH_AFTER = 12;

function filterSearchKey(value: string): string {
  return value.trim().toLocaleLowerCase("ru-RU").replace(/\u00a0/g, " ");
}

function matchSuggestOptions(options: string[], query: string, limit = 20): string[] {
  const needle = filterSearchKey(query);
  if (!needle) return [];
  const seen = new Set<string>();
  const starts: string[] = [];
  const mid: string[] = [];
  for (const option of options) {
    const key = filterSearchKey(option);
    if (!key || seen.has(key)) continue;
    if (!key.includes(needle)) continue;
    seen.add(key);
    if (key.startsWith(needle)) starts.push(option);
    else mid.push(option);
  }
  return [...starts, ...mid].slice(0, limit);
}

type SuggestRect = { top: number; left: number; width: number; maxHeight: number };

/**
 * Плашка подсказок через portal — не режется overflow у FiltersSheet.
 * z-index выше листа (70).
 */
function FilterSuggestList({
  open,
  matches,
  anchorRef,
  listRef,
  onSelect,
}: {
  open: boolean;
  matches: string[];
  anchorRef: React.RefObject<HTMLElement | null>;
  listRef: React.RefObject<HTMLUListElement | null>;
  onSelect: (value: string) => void;
}) {
  const [rect, setRect] = useState<SuggestRect | null>(null);
  const [mounted, setMounted] = useState(false);

  useEffect(() => setMounted(true), []);

  const sync = useCallback(() => {
    const el = anchorRef.current;
    if (!el || !open || !matches.length) {
      setRect(null);
      return;
    }
    const r = el.getBoundingClientRect();
    const gap = 4;
    const spaceBelow = window.innerHeight - r.bottom - gap - 12;
    const spaceAbove = r.top - gap - 12;
    const placeAbove = spaceBelow < 160 && spaceAbove > spaceBelow;
    const maxHeight = Math.min(224, Math.max(120, placeAbove ? spaceAbove : spaceBelow));
    setRect({
      top: placeAbove ? r.top - gap - maxHeight : r.bottom + gap,
      left: r.left,
      width: r.width,
      maxHeight,
    });
  }, [anchorRef, open, matches.length]);

  useLayoutEffect(() => {
    sync();
  }, [sync, matches]);

  useEffect(() => {
    if (!open || !matches.length) return;
    const onScroll = () => sync();
    window.addEventListener("resize", onScroll);
    window.addEventListener("scroll", onScroll, true);
    return () => {
      window.removeEventListener("resize", onScroll);
      window.removeEventListener("scroll", onScroll, true);
    };
  }, [open, matches.length, sync]);

  if (!mounted || !open || !matches.length || !rect) return null;

  return createPortal(
    <ul
      ref={listRef}
      role="listbox"
      className="bi-filter-suggest fixed overflow-y-auto overscroll-contain rounded-lg border border-tremor-border bg-tremor-background py-1 text-sm text-tremor-content-strong shadow-xl dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
      style={{
        top: rect.top,
        left: rect.left,
        width: rect.width,
        maxHeight: rect.maxHeight,
        zIndex: 90,
      }}
    >
      {matches.map((option) => (
        <li key={option} role="option">
          <button
            type="button"
            className="block min-h-11 w-full truncate px-3 py-2 text-left hover:bg-tremor-background-subtle dark:hover:bg-dark-tremor-background-subtle"
            onMouseDown={(e) => e.preventDefault()}
            onClick={() => {
              tapFeedback();
              onSelect(option);
            }}
          >
            {option}
          </button>
        </li>
      ))}
    </ul>,
    document.body,
  );
}

/**
 * Частичный поиск № договора с выпадающими вариантами (как datalist в main).
 */
export function ContractNoSuggest({
  value,
  options,
  onChange,
  placeholder = "Частичный поиск",
}: {
  value: string;
  options: string[];
  onChange: (next: string) => void;
  placeholder?: string;
}) {
  const [open, setOpen] = useState(false);
  const inputRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const matches = useMemo(
    () => matchSuggestOptions(options, value),
    [options, value],
  );

  useEffect(() => {
    if (!open) return;
    const onDoc = (event: MouseEvent | TouchEvent) => {
      const t = event.target as Node;
      if (inputRef.current?.contains(t) || listRef.current?.contains(t)) return;
      setOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("touchstart", onDoc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("touchstart", onDoc);
    };
  }, [open]);

  return (
    <div className="relative">
      <input
        ref={inputRef}
        value={value}
        onChange={(e) => {
          onChange(e.target.value);
          setOpen(true);
        }}
        onFocus={() => setOpen(true)}
        onKeyDown={(e) => e.stopPropagation()}
        onPointerDown={(e) => e.stopPropagation()}
        className={FILTER_SELECT_CLASS}
        placeholder={placeholder}
        autoComplete="off"
        autoCorrect="off"
        spellCheck={false}
        role="combobox"
        aria-expanded={open && matches.length > 0}
        aria-autocomplete="list"
      />
      <FilterSuggestList
        open={open}
        matches={matches}
        anchorRef={inputRef}
        listRef={listRef}
        onSelect={(option) => {
          onChange(option);
          setOpen(false);
        }}
      />
    </div>
  );
}

/** Single-select: native `<select>` на всех ширинах (в т.ч. FiltersSheet на телефоне). */
export function FilterChipSelect({
  label,
  value,
  options,
  onChange,
  disabled,
  filterKey,
}: {
  label?: ReactNode;
  value: string;
  options: FilterChipOption[];
  onChange: (next: string) => void;
  disabled?: boolean;
  /** Ключ UI ACL (report-ui-catalog); без ключа — всегда виден. */
  filterKey?: string;
}) {
  const normalized = useMemo(() => options.map(normChipOption), [options]);

  const control = (
    <select
      className={FILTER_SELECT_CLASS}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      {normalized.map(({ value: v, label: lab }) => (
        <option key={v} value={v}>
          {lab}
        </option>
      ))}
    </select>
  );
  const field =
    label == null ? (
      <div className="bi-filters-field-control">{control}</div>
    ) : (
      <div className="bi-filters-field text-sm">
        <span className="bi-filters-field-label text-tremor-content dark:text-dark-tremor-content">
          {label}
        </span>
        <div className="bi-filters-field-control">{control}</div>
      </div>
    );
  return <AclFilterGate filterKey={filterKey}>{field}</AclFilterGate>;
}

/**
 * Desktop-мультивыбор: нативный `<select multiple>` неудобен (Ctrl+клик, растянутый
 * список), поэтому — кнопка со сводкой и выпадающий список чекбоксов, как в main.
 */
function MultiSelectDropdown({
  values,
  options,
  onChange,
  allLabel,
  disabled,
}: {
  values: string[];
  options: string[];
  onChange: (next: string[]) => void;
  allLabel: string;
  disabled?: boolean;
}) {
  const [open, setOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [active, setActive] = useState(0);
  const rootRef = useRef<HTMLDivElement | null>(null);
  const triggerRef = useRef<HTMLButtonElement | null>(null);
  const searchRef = useRef<HTMLInputElement | null>(null);
  const listRef = useRef<HTMLDivElement | null>(null);
  const listId = useId();

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    return () => document.removeEventListener("mousedown", onPointerDown);
  }, [open]);

  useEffect(() => {
    if (!open) {
      setQuery("");
      setActive(0);
      return;
    }
    const timer = window.setTimeout(() => {
      (searchRef.current ?? listRef.current)?.focus();
    }, 0);
    return () => window.clearTimeout(timer);
  }, [open]);

  const searchable = options.length > CHIP_SEARCH_AFTER;
  const visible = useMemo(() => {
    const needle = filterSearchKey(query);
    if (!searchable || !needle) return options;
    return options
      .filter((name) => filterSearchKey(name).includes(needle))
      .sort((a, b) => {
        const ak = filterSearchKey(a);
        const bk = filterSearchKey(b);
        const aStart = ak.startsWith(needle) ? 0 : 1;
        const bStart = bk.startsWith(needle) ? 0 : 1;
        if (aStart !== bStart) return aStart - bStart;
        return ak.localeCompare(bk, "ru");
      });
  }, [options, query, searchable]);

  /**
   * Пустой `values` = «Все» (без ограничения). В UI это все галочки.
   * После «Снять все» при «Все» — локально показываем пустой выбор, чтобы
   * можно было отметить нужные; пока ничего не выбрано, снаружи всё ещё [].
   */
  const isAll = values.length === 0;
  const [clearedFromAll, setClearedFromAll] = useState(false);
  useEffect(() => {
    setClearedFromAll(false);
  }, [values]);
  useEffect(() => {
    if (!open) setClearedFromAll(false);
  }, [open]);

  const showAsAllSelected = isAll && !clearedFromAll;

  const summary =
    isAll
      ? allLabel
      : values.length === 1
        ? values[0]!
        : `Выбрано: ${values.length}`;

  const isChecked = (name: string) =>
    showAsAllSelected || values.includes(name);

  const toggle = (name: string) => {
    if (showAsAllSelected) {
      setClearedFromAll(false);
      onChange(options.filter((item) => item !== name));
      return;
    }
    if (clearedFromAll && isAll) {
      setClearedFromAll(false);
      onChange([name]);
      return;
    }
    if (values.includes(name)) {
      const next = values.filter((item) => item !== name);
      onChange(next);
      return;
    }
    const next = [...values, name];
    onChange(next.length >= options.length ? [] : next);
  };

  /** Индексы строк = позиции в `visible`. */
  const rowCount = visible.length;
  const commitActive = () => {
    const name = visible[active];
    if (name) toggle(name);
  };

  const closeToTrigger = () => {
    setOpen(false);
    triggerRef.current?.focus();
  };

  const onPopupKeyDown = (event: React.KeyboardEvent) => {
    if (event.key === "Escape" || event.key === "Tab") {
      event.preventDefault();
      closeToTrigger();
      return;
    }
    if (rowCount === 0) return;
    if (event.key === "ArrowDown") {
      event.preventDefault();
      setActive((index) => (index + 1) % rowCount);
      return;
    }
    if (event.key === "ArrowUp") {
      event.preventDefault();
      setActive((index) => (index - 1 + rowCount) % rowCount);
      return;
    }
    if (event.key === "Home") {
      event.preventDefault();
      setActive(0);
      return;
    }
    if (event.key === "End") {
      event.preventDefault();
      setActive(rowCount - 1);
      return;
    }
    if (event.key === "Enter" || (event.key === " " && event.target !== searchRef.current)) {
      event.preventDefault();
      commitActive();
    }
  };

  useEffect(() => {
    setActive((index) => (rowCount === 0 ? 0 : Math.min(index, rowCount - 1)));
  }, [rowCount]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const rowClass = (index: number, selected: boolean) =>
    `flex cursor-pointer items-start gap-2 rounded px-2 py-2 text-tremor-default ${
      index === active
        ? "bg-tremor-background-subtle dark:bg-dark-tremor-background-subtle"
        : ""
    } ${
      selected
        ? "font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong"
        : "text-tremor-content-strong dark:text-dark-tremor-content-strong"
    } hover:bg-tremor-background-subtle dark:hover:bg-dark-tremor-background-subtle`;

  const allVisibleSelected =
    visible.length > 0 && visible.every((name) => isChecked(name));
  const canClear = showAsAllSelected || values.length > 0;

  return (
    <div ref={rootRef} className="relative">
      <button
        ref={triggerRef}
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        onKeyDown={(event) => {
          if (event.key === "ArrowDown" && !open) {
            event.preventDefault();
            setOpen(true);
          }
        }}
        aria-expanded={open}
        aria-haspopup="listbox"
        aria-controls={open ? listId : undefined}
        className={`${FILTER_SELECT_CLASS} bi-filters-select-wrap flex items-center justify-between gap-2 text-left`}
      >
        <span className="min-w-0 flex-1 whitespace-normal break-words leading-snug line-clamp-2">
          {summary}
        </span>
        <span aria-hidden className="shrink-0 text-xs opacity-60">
          ▾
        </span>
      </button>
      {open ? (
        <div
          className="relative z-30 mt-1 rounded-tremor-default border border-tremor-border bg-tremor-background p-2 shadow-tremor-dropdown dark:border-dark-tremor-border dark:bg-dark-tremor-background"
          onKeyDown={onPopupKeyDown}
        >
          {searchable ? (
            <input
              ref={searchRef}
              type="text"
              inputMode="search"
              autoComplete="off"
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setActive(0);
              }}
              placeholder={`Поиск · ${options.length}`}
              aria-controls={listId}
              aria-activedescendant={
                rowCount > 0 ? `${listId}-${active}` : undefined
              }
              className="mb-2 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-2 py-1.5 text-tremor-default text-tremor-content-strong outline-none focus-visible:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
            />
          ) : null}
          <div className="mb-2 flex flex-wrap items-center gap-2 text-xs">
            <button
              type="button"
              disabled={allVisibleSelected || visible.length === 0}
              onClick={() => {
                setClearedFromAll(false);
                if (!query.trim()) {
                  onChange([]);
                  return;
                }
                const merged = [
                  ...values,
                  ...visible.filter((name) => !values.includes(name)),
                ];
                onChange(merged.length >= options.length ? [] : merged);
              }}
              className="rounded border border-tremor-border px-2 py-1 text-tremor-content-emphasis hover:bg-tremor-background-subtle disabled:opacity-40 dark:border-dark-tremor-border dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
            >
              Выбрать все{query ? " найденные" : ""}
            </button>
            <button
              type="button"
              disabled={!canClear}
              onClick={() => {
                if (showAsAllSelected) {
                  setClearedFromAll(true);
                  return;
                }
                setClearedFromAll(false);
                onChange([]);
              }}
              className="rounded border border-tremor-border px-2 py-1 text-tremor-content-emphasis hover:bg-tremor-background-subtle disabled:opacity-40 dark:border-dark-tremor-border dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
            >
              Снять все
            </button>
          </div>
          <div
            ref={listRef}
            id={listId}
            role="listbox"
            aria-multiselectable
            aria-label={allLabel}
            tabIndex={searchable ? -1 : 0}
            aria-activedescendant={
              rowCount > 0 ? `${listId}-${active}` : undefined
            }
            className="max-h-64 overflow-y-auto overscroll-contain outline-none sm:max-h-72"
          >
            {visible.map((name, index) => {
              const selected = isChecked(name);
              return (
                <label
                  key={name}
                  id={`${listId}-${index}`}
                  data-index={index}
                  role="option"
                  aria-selected={selected}
                  onMouseEnter={() => setActive(index)}
                  className={rowClass(index, selected)}
                >
                  <input
                    type="checkbox"
                    tabIndex={-1}
                    className="mt-0.5 shrink-0"
                    checked={selected}
                    onChange={() => toggle(name)}
                  />
                  <span className="min-w-0 whitespace-normal break-words leading-snug">
                    {name}
                  </span>
                </label>
              );
            })}
            {visible.length === 0 ? (
              <div className="px-2 py-2 text-tremor-default text-tremor-content dark:text-dark-tremor-content">
                Ничего не найдено
              </div>
            ) : null}
          </div>
        </div>
      ) : null}
    </div>
  );
}

/**
 * Multi-select: empty `values` = «Все».
 * Combobox с чекбоксами на всех ширинах (в т.ч. FiltersSheet на телефоне).
 */
export function FilterChipMulti({
  label,
  values,
  options,
  onChange,
  allLabel = "Все",
  disabled,
  filterKey,
}: {
  label?: ReactNode;
  values: string[];
  options: string[];
  onChange: (next: string[]) => void;
  allLabel?: string;
  disabled?: boolean;
  filterKey?: string;
}) {
  const opts = useMemo(
    () => options.filter((o) => o && o !== allLabel),
    [options, allLabel],
  );

  const control = (
    <MultiSelectDropdown
      values={values}
      options={opts}
      onChange={onChange}
      allLabel={allLabel}
      disabled={disabled}
    />
  );
  const field =
    label == null ? (
      <div className="bi-filters-field-control">{control}</div>
    ) : (
      <div className="bi-filters-field text-sm">
        <span className="bi-filters-field-label text-tremor-content dark:text-dark-tremor-content">
          {label}
        </span>
        <div className="bi-filters-field-control">{control}</div>
      </div>
    );
  return <AclFilterGate filterKey={filterKey}>{field}</AclFilterGate>;
}

type Cols = 2 | 3 | 4 | 5;

function colsClass(cols: Cols): string {
  if (cols === 2) return "bi-filters-grid bi-filters-cols-2";
  if (cols === 3) return "bi-filters-grid bi-filters-cols-3";
  if (cols === 4) return "bi-filters-grid bi-filters-cols-4";
  return "bi-filters-grid bi-filters-cols-5";
}

export function FiltersCard({
  open,
  onToggle,
  title = "Фильтры",
  activeCount,
  activeFilters,
  onReset,
  onApply,
  applyDisabled,
  resetDisabled,
  /** Для сохранённых срезов (localStorage) */
  navId,
  /** Плавающая «Применить» при скролле */
  stickyPending,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  title?: string;
  activeCount?: number;
  /** Чипы выбранных значений — mobile всегда; desktop — под заголовком панели. */
  activeFilters?: ActiveFilter[];
  onReset?: () => void;
  /** BUG-010: зафиксировать черновик в URL/запрос. */
  onApply?: () => void;
  applyDisabled?: boolean;
  resetDisabled?: boolean;
  navId?: string;
  stickyPending?: boolean;
  children: ReactNode;
}) {
  const mobile = useIsMobileViewport();
  const router = useRouter();
  const pathname = usePathname();
  const panelRef = useRef<HTMLDivElement | null>(null);
  // Лист держим на собственном состоянии: экраны с `open=true` по умолчанию
  // (например «Дебиторка») иначе открывали бы его при загрузке страницы.
  const [sheetOpen, setSheetOpen] = useState(false);
  const [presets, setPresets] = useState<FilterPreset[]>([]);

  useEffect(() => {
    if (!navId) return;
    setPresets(listFilterPresets(navId));
  }, [navId, sheetOpen, open]);

  const presetsRow =
    navId && presets.length ? (
      <div className="bi-filter-presets mt-2 flex flex-wrap items-center gap-2">
        <span className="text-xs text-tremor-content dark:text-dark-tremor-content">
          Срезы:
        </span>
        {presets.map((p) => (
          <span key={p.id} className="inline-flex items-center gap-0.5">
            <button
              type="button"
              className="bi-active-chip text-xs"
              onClick={() => {
                tapFeedback();
                const q = p.query ? `?${p.query}` : "";
                router.push(`${pathname}${q}`);
              }}
              title={`Загрузить срез «${p.name}»`}
            >
              {p.name}
            </button>
            <button
              type="button"
              className="rounded px-1 text-xs text-tremor-content hover:text-rose-600 dark:text-dark-tremor-content"
              aria-label={`Удалить срез ${p.name}`}
              onClick={() => {
                deleteFilterPreset(navId, p.id);
                setPresets(listFilterPresets(navId));
              }}
            >
              ✕
            </button>
          </span>
        ))}
      </div>
    ) : null;

  const chips = activeFilters ?? [];
  const chipsRow =
    chips.length > 0 ? (
      <div
        className={`bi-active-filters ${mobile ? "mb-4" : "mt-3"}`}
        aria-label="Выбраны фильтры"
      >
        <span className="bi-active-filters-label">Выбраны фильтры:</span>
        <div className="bi-active-chips">
          {chips.map((chip) =>
            chip.onClear ? (
              <button
                key={chip.key}
                type="button"
                className="bi-active-chip"
                onClick={() => {
                  tapFeedback();
                  chip.onClear?.();
                }}
                title={`Снять фильтр: ${chip.label}`}
              >
                <span className="bi-active-chip-text">{chip.label}</span>
                <span className="bi-active-chip-x" aria-hidden>
                  ✕
                </span>
              </button>
            ) : (
              <span key={chip.key} className="bi-active-chip">
                <span className="bi-active-chip-text">{chip.label}</span>
              </span>
            ),
          )}
          {onReset && chips.length > 1 ? (
            <button
              type="button"
              className="bi-active-chip bi-active-chip-reset"
              onClick={() => {
                confirmFeedback();
                onReset();
              }}
            >
              Сбросить всё
            </button>
          ) : null}
        </div>
      </div>
    ) : null;

  if (mobile) {
    const count = activeCount ?? chips.length;
    return (
      <>
        <div ref={panelRef}>
          <button
            type="button"
            onClick={() => {
              tapFeedback();
              setSheetOpen(true);
            }}
            aria-expanded={sheetOpen}
            className={`bi-filters-trigger ${chips.length ? "mb-2" : "mb-4"}`}
          >
            <span className="bi-filters-trigger-icon" aria-hidden>
              ⛭
            </span>
            <span className="flex-1 text-left">{title}</span>
            {count ? (
              <span className="bi-filters-trigger-badge">{count}</span>
            ) : null}
            <span aria-hidden>▾</span>
          </button>
          {chipsRow}
          {presetsRow}
        </div>
        <FiltersSheet
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          title={title}
          onReset={onReset}
          onApply={onApply}
          applyDisabled={applyDisabled}
          resetDisabled={resetDisabled}
        >
          <div className="bi-filters-body space-y-3">{children}</div>
        </FiltersSheet>
        {stickyPending && onApply ? (
          <FilterStickyBar
            anchorRef={panelRef}
            pending={!applyDisabled}
            onApply={onApply}
            applyDisabled={applyDisabled}
          />
        ) : null}
      </>
    );
  }

  const actions =
    onApply || onReset ? (
      <div className="mt-3 flex flex-wrap gap-2">
        {onApply ? (
          <FiltersApply disabled={applyDisabled} onClick={onApply} />
        ) : null}
        {onReset ? (
          <FiltersReset disabled={resetDisabled} onClick={onReset} />
        ) : null}
      </div>
    ) : null;

  return (
    <>
      <div
        ref={panelRef}
        className="bi-filters-panel mb-6 rounded-xl border border-tremor-border bg-tremor-background p-4 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
      >
        <button
          type="button"
          onClick={onToggle}
          aria-expanded={open}
          className="flex w-full items-center gap-2 text-left text-sm font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong"
        >
          <span className="text-xs">{open ? "▾" : "▸"}</span>
          {title}
          {!open && chips.length ? (
            <span className="ml-auto rounded-full bg-emerald-100 px-2 py-0.5 text-[11px] font-semibold text-emerald-800 dark:bg-emerald-950/50 dark:text-emerald-200">
              {chips.length}
            </span>
          ) : null}
        </button>
        {!open ? chipsRow : null}
        {!open ? presetsRow : null}
        {open ? <div className="bi-filters-body mt-3 space-y-3">{children}</div> : null}
        {open && chips.length ? <div className="mt-3">{chipsRow}</div> : null}
        {open ? presetsRow : null}
        {open ? actions : null}
      </div>
      {stickyPending && onApply ? (
        <FilterStickyBar
          anchorRef={panelRef}
          pending={!applyDisabled}
          onApply={onApply}
          applyDisabled={applyDisabled}
        />
      ) : null}
    </>
  );
}

export function FiltersApply({
  disabled,
  onClick,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={(event) => {
        confirmFeedback();
        onClick?.(event);
      }}
      className="rounded-tremor-default bg-emerald-600 px-3 py-1.5 text-sm font-medium text-white disabled:opacity-40"
      {...rest}
    >
      Применить
    </button>
  );
}

export function FiltersReset({
  disabled,
  onClick,
  ...rest
}: ButtonHTMLAttributes<HTMLButtonElement>) {
  return (
    <button
      type="button"
      disabled={disabled}
      onClick={(event) => {
        confirmFeedback();
        onClick?.(event);
      }}
      className="rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-1.5 text-sm text-tremor-content-strong disabled:opacity-40 dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
      {...rest}
    >
      Сбросить
    </button>
  );
}

/**
 * Desktop native `<select>` (паритет main Streamlit select/multiselect в закрытом виде).
 * Пустое value = «Все» / без фильтра.
 */
export function FilterNativeSelect({
  label,
  value,
  options,
  onChange,
  allLabel = "Все",
  disabled,
}: {
  label?: ReactNode;
  value: string;
  options: string[];
  onChange: (next: string) => void;
  allLabel?: string;
  disabled?: boolean;
}) {
  const field = (
    <select
      className={FILTER_SELECT_CLASS}
      value={value}
      disabled={disabled}
      onChange={(e) => onChange(e.target.value)}
    >
      <option value="">{allLabel}</option>
      {options.map((opt) => (
        <option key={opt} value={opt}>
          {opt}
        </option>
      ))}
    </select>
  );
  if (label == null) return field;
  return (
    <label className="bi-filters-field text-sm">
      <span className="bi-filters-field-label text-tremor-content dark:text-dark-tremor-content">
        {label}
      </span>
      <div className="bi-filters-field-control">{field}</div>
    </label>
  );
}

/**
 * Multi через native select: пустой массив = все; одно значение = фильтр.
 * Для UI как main (placeholder «Все …» в одной строке).
 */
export function FilterNativeMultiAsSelect({
  label,
  values,
  options,
  onChange,
  allLabel = "Все",
  disabled,
}: {
  label?: ReactNode;
  values: string[];
  options: string[];
  onChange: (next: string[]) => void;
  allLabel?: string;
  disabled?: boolean;
}) {
  const current = values.length === 1 ? values[0]! : "";
  return (
    <FilterNativeSelect
      label={label}
      value={current}
      options={options}
      allLabel={allLabel}
      disabled={disabled}
      onChange={(next) => onChange(next ? [next] : [])}
    />
  );
}

/** Row of selects — same column tracks as FilterChecksRow (main `st.columns(5)`). */
export function FilterFieldsRow({
  cols = 5,
  children,
}: {
  cols?: Cols;
  children: ReactNode;
}) {
  return <div className={colsClass(cols)}>{children}</div>;
}

/** Row of checkboxes — identical grid so icons sit under selects. */
export function FilterChecksRow({
  cols = 5,
  children,
}: {
  cols?: Cols;
  children: ReactNode;
}) {
  return <div className={`${colsClass(cols)} bi-filters-checks`}>{children}</div>;
}

export function FilterField({
  label,
  children,
  filterKey,
}: {
  label: ReactNode;
  children: ReactNode;
  filterKey?: string;
}) {
  return (
    <AclFilterGate filterKey={filterKey}>
      <label className="bi-filters-field text-sm">
        <span className="bi-filters-field-label text-tremor-content dark:text-dark-tremor-content">
          {label}
        </span>
        <div className="bi-filters-field-control">{children}</div>
      </label>
    </AclFilterGate>
  );
}

/**
 * Дата в фильтрах: кнопка + скрытый native input.
 *
 * Почему не голый input[type=date]:
 * 1) `.bi-filters-field { height:100% }` у соседнего селекта в той же ячейке
 *    сетки растягивается поверх date-поля — кликабельна только верхняя кромка.
 * 2) В WebKit клик по цифрам уходит во внутренние сегменты и не открывает picker.
 *
 * Кнопка принимает клик по всей площади; календарь открывает скрытый input
 * через showPicker().
 */
export function FilterDateInput({
  className = "",
  value,
  onChange,
  min,
  max,
  disabled,
  id,
  name,
  "aria-label": ariaLabel,
  ...rest
}: InputHTMLAttributes<HTMLInputElement>) {
  const inputRef = useRef<HTMLInputElement>(null);
  const raw = typeof value === "string" ? value : "";
  const display = (() => {
    const m = /^(\d{4})-(\d{2})-(\d{2})$/.exec(raw.trim());
    return m ? `${m[3]}.${m[2]}.${m[1]}` : raw || "дд.мм.гггг";
  })();

  const openPicker = () => {
    const el = inputRef.current;
    if (!el || disabled) return;
    try {
      if (typeof el.showPicker === "function") {
        el.showPicker();
        return;
      }
    } catch {
      // fall through to click()
    }
    el.click();
  };

  return (
    <div className={`bi-filters-date-wrap relative ${className}`.trim()}>
      <button
        type="button"
        className={`${FILTER_DATE_CLASS} bi-filters-date-trigger flex w-full items-center justify-between gap-2 text-left`}
        onClick={openPicker}
        disabled={disabled}
        aria-label={ariaLabel}
      >
        <span className={raw ? undefined : "text-tremor-content dark:text-dark-tremor-content"}>
          {display}
        </span>
        <svg
          aria-hidden
          viewBox="0 0 16 16"
          width="14"
          height="14"
          className="shrink-0 text-tremor-content dark:text-dark-tremor-content"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.4"
        >
          <rect x="2" y="3.5" width="12" height="10.5" rx="1.5" />
          <path d="M2 6.5h12M5.5 2v3M10.5 2v3" strokeLinecap="round" />
        </svg>
      </button>
      <input
        {...rest}
        ref={inputRef}
        type="date"
        id={id}
        name={name}
        min={min}
        max={max}
        value={raw}
        disabled={disabled}
        tabIndex={-1}
        aria-hidden
        className="bi-filters-date-native"
        onChange={onChange}
      />
    </div>
  );
}

/**
 * Пара дат «с/по» занимает 2 колонки сетки фильтров (BUG-001/002/006):
 * иначе min-width у type=date (~10.75rem×2) вылезает в соседнее поле.
 */
export function FilterDateRange({
  label = "Период",
  from,
  to,
  min,
  max,
  onFromChange,
  onToChange,
  fromAriaLabel = "Период с",
  toAriaLabel = "Период по",
  filterKey,
}: {
  label?: ReactNode;
  from: string;
  to: string;
  min?: string;
  max?: string;
  onFromChange: (value: string) => void;
  onToChange: (value: string) => void;
  fromAriaLabel?: string;
  toAriaLabel?: string;
  filterKey?: string;
}) {
  return (
    <div className="bi-filters-date-range">
      <FilterField label={label} filterKey={filterKey}>
        <div className="bi-filters-date-range-inputs">
          <FilterDateInput
            min={min}
            max={to || max}
            value={from}
            onChange={(event) => onFromChange(event.target.value)}
            aria-label={fromAriaLabel}
          />
          <FilterDateInput
            min={from || min}
            max={max}
            value={to}
            onChange={(event) => onToChange(event.target.value)}
            aria-label={toAriaLabel}
          />
        </div>
      </FilterField>
    </div>
  );
}

export function FilterCheck({
  label,
  className = "",
  onChange,
  filterKey,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & {
  label: ReactNode;
  filterKey?: string;
}) {
  return (
    <AclFilterGate filterKey={filterKey}>
      <label
        className={`bi-filters-check flex items-start gap-2 text-sm text-tremor-content-strong dark:text-dark-tremor-content-strong ${
          input.disabled ? "opacity-50" : ""
        } ${className}`}
      >
        <input
          type="checkbox"
          className="bi-filters-check-input"
          onChange={(event) => {
            tapFeedback();
            onChange?.(event);
          }}
          {...input}
        />
        <span className="bi-filters-check-label leading-snug">{label}</span>
      </label>
    </AclFilterGate>
  );
}

export function FilterRadios({
  label,
  children,
}: {
  label: ReactNode;
  children: ReactNode;
}) {
  return (
    <fieldset className="bi-filters-radios text-sm">
      <legend className="mb-2 text-tremor-content dark:text-dark-tremor-content">{label}</legend>
      <div className="flex flex-nowrap gap-6 overflow-x-auto">{children}</div>
    </fieldset>
  );
}

export function FilterRadio({
  label,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label className="inline-flex shrink-0 items-center gap-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
      <input type="radio" className="bi-filters-radio-input" {...input} />
      <span>{label}</span>
    </label>
  );
}
