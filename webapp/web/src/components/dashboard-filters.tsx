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
  saveFilterPreset,
  type FilterPreset,
} from "@/lib/filter-presets";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";
import { useIsMobileViewport } from "@/lib/use-is-mobile";
import { usePathname, useRouter } from "next/navigation";

/** Shared select/date look — fixed height, non-OS chrome, focus-visible only. */
export const FILTER_SELECT_CLASS =
  "bi-filters-select w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 text-tremor-default text-tremor-content-strong outline-none focus-visible:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong disabled:opacity-50";

/** Date inputs: full visible date, same height as selects. */
export const FILTER_DATE_CLASS = `${FILTER_SELECT_CLASS} bi-filters-date`;

/** BDDS-style chip buttons for categorical filters. */
export const FILTER_CHIP_CLASS =
  "bi-filter-chip rounded-md border px-2.5 py-1 text-xs border-tremor-border bg-white text-tremor-content-strong disabled:cursor-not-allowed disabled:opacity-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong";
export const FILTER_CHIP_ON_CLASS =
  "bi-filter-chip rounded-md border px-2.5 py-1 text-xs border-emerald-600 bg-emerald-50 text-emerald-900 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-200";

export type FilterChipOption = string | { value: string; label: string };

function normChipOption(opt: FilterChipOption): { value: string; label: string } {
  if (typeof opt === "string") return { value: opt, label: opt };
  return opt;
}

/** ~6 chip-rows visible; longer lists scroll (как старые MultiSelect max-h). */
const CHIP_LIST_BASE = "bi-filter-chip-list flex flex-wrap content-start gap-2";
const CHIP_LIST_SCROLL = "max-h-52 overflow-y-auto overscroll-contain pr-0.5";
const CHIP_SCROLL_AFTER = 7;

function ChipList({
  children,
  itemCount,
  className = "",
}: {
  children: ReactNode;
  itemCount: number;
  className?: string;
}) {
  const scroll = itemCount > CHIP_SCROLL_AFTER;
  return (
    <div
      className={`${CHIP_LIST_BASE} ${scroll ? CHIP_LIST_SCROLL : ""} ${className}`}
    >
      {children}
    </div>
  );
}

/** Длинные списки (подрядчики, проекты) на телефоне без поиска непригодны. */
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

function ChipSearch({
  value,
  onChange,
  count,
  inputRef,
  onFocus,
}: {
  value: string;
  onChange: (next: string) => void;
  count: number;
  inputRef?: React.RefObject<HTMLInputElement | null>;
  onFocus?: () => void;
}) {
  return (
    <input
      ref={inputRef}
      type="text"
      inputMode="search"
      autoComplete="off"
      autoCorrect="off"
      spellCheck={false}
      value={value}
      onChange={(e) => onChange(e.target.value)}
      onFocus={onFocus}
      onKeyDown={(e) => e.stopPropagation()}
      onPointerDown={(e) => e.stopPropagation()}
      placeholder={`Поиск · ${count}`}
      className="bi-filter-chip-search mb-2 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-sm text-tremor-content-strong outline-none focus-visible:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
    />
  );
}

function useChipFilter<T extends { label: string; value?: string }>(
  items: T[],
  pinKey = "",
) {
  const [query, setQuery] = useState("");
  const searchable = items.length > CHIP_SEARCH_AFTER;
  const visible = useMemo(() => {
    const needle = filterSearchKey(query);
    if (!searchable || !needle) return items;
    const pinned = new Set(
      pinKey
        .split("\0")
        .map(filterSearchKey)
        .filter(Boolean),
    );
    const matched: T[] = [];
    const rest: T[] = [];
    for (const item of items) {
      const key = filterSearchKey(item.label);
      const isPinned =
        pinned.has(key) ||
        (item.value != null && pinned.has(filterSearchKey(item.value)));
      if (isPinned) {
        matched.push(item);
        continue;
      }
      if (key.includes(needle)) rest.push(item);
    }
    rest.sort((a, b) => {
      const ak = filterSearchKey(a.label);
      const bk = filterSearchKey(b.label);
      const aStart = ak.startsWith(needle) ? 0 : 1;
      const bStart = bk.startsWith(needle) ? 0 : 1;
      if (aStart !== bStart) return aStart - bStart;
      return ak.localeCompare(bk, "ru");
    });
    return [...matched, ...rest];
  }, [items, query, searchable, pinKey]);
  return { query, setQuery, searchable, visible, needle: filterSearchKey(query) };
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

/** Single-select: desktop = native `<select>` (как main), mobile = chips. */
export function FilterChipSelect({
  label,
  value,
  options,
  onChange,
  disabled,
}: {
  label?: ReactNode;
  value: string;
  options: FilterChipOption[];
  onChange: (next: string) => void;
  disabled?: boolean;
}) {
  const normalized = useMemo(() => options.map(normChipOption), [options]);
  const pinKey = useMemo(
    () => ["Все", "Все подрядчики", value].filter(Boolean).join("\0"),
    [value],
  );
  const { query, setQuery, searchable, visible, needle } = useChipFilter(
    normalized,
    pinKey,
  );
  const [suggestOpen, setSuggestOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const suggestMatches = useMemo(
    () =>
      matchSuggestOptions(
        normalized.map((o) => o.label).filter((lab) => lab !== "Все" && lab !== "Все подрядчики"),
        query,
      ),
    [normalized, query],
  );

  useEffect(() => {
    if (!suggestOpen) return;
    const onDoc = (event: MouseEvent | TouchEvent) => {
      const t = event.target as Node;
      if (searchRef.current?.contains(t) || listRef.current?.contains(t)) return;
      setSuggestOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("touchstart", onDoc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("touchstart", onDoc);
    };
  }, [suggestOpen]);

  const desktop = (
    <select
      className={`${FILTER_SELECT_CLASS}${label != null ? "" : ""}`}
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
  const plaqueOpen = suggestOpen && Boolean(needle) && suggestMatches.length > 0;
  const chips = (
    <div className={label != null ? "mt-2" : ""}>
      {searchable ? (
        <ChipSearch
          value={query}
          onChange={(next) => {
            setQuery(next);
            setSuggestOpen(true);
          }}
          onFocus={() => setSuggestOpen(true)}
          count={normalized.length}
          inputRef={searchRef}
        />
      ) : null}
      <FilterSuggestList
        open={plaqueOpen}
        matches={suggestMatches}
        anchorRef={searchRef}
        listRef={listRef}
        onSelect={(lab) => {
          const hit = normalized.find((o) => o.label === lab);
          onChange(hit?.value ?? lab);
          setQuery("");
          setSuggestOpen(false);
        }}
      />
      {/* Пока открыта плашка — скрываем длинный список чипов */}
      {!plaqueOpen ? (
        <ChipList itemCount={visible.length}>
          {visible.map(({ value: v, label: lab }) => {
            const on = value === v;
            return (
              <button
                key={v}
                type="button"
                disabled={disabled}
                onClick={() => {
                  tapFeedback();
                  onChange(v);
                  setQuery("");
                }}
                className={on ? FILTER_CHIP_ON_CLASS : FILTER_CHIP_CLASS}
              >
                {lab}
              </button>
            );
          })}
        </ChipList>
      ) : null}
      {searchable && needle && suggestMatches.length === 0 ? (
        <p className="mt-2 text-xs text-tremor-content dark:text-dark-tremor-content">
          Ничего не найдено
        </p>
      ) : null}
    </div>
  );
  const body = (
    <>
      <div className="bi-filters-field-control hidden lg:block">{desktop}</div>
      <div className="bi-filters-field-control lg:hidden">{chips}</div>
    </>
  );
  if (label == null) return body;
  return (
    <div className="bi-filters-field text-sm">
      <span className="bi-filters-field-label text-tremor-content dark:text-dark-tremor-content">
        {label}
      </span>
      {body}
    </div>
  );
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

  const summary =
    values.length === 0
      ? allLabel
      : values.length === 1
        ? values[0]!
        : `Выбрано: ${values.length}`;

  const toggle = (name: string) => {
    onChange(
      values.includes(name)
        ? values.filter((item) => item !== name)
        : [...values, name],
    );
  };

  /** Индекс 0 — строка «Все», дальше идут `visible`. */
  const rowCount = visible.length + 1;
  const commitActive = () => {
    if (active <= 0) {
      onChange([]);
      return;
    }
    const name = visible[active - 1];
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
    setActive((index) => (index >= rowCount ? 0 : index));
  }, [rowCount]);

  useEffect(() => {
    if (!open) return;
    listRef.current
      ?.querySelector<HTMLElement>(`[data-index="${active}"]`)
      ?.scrollIntoView({ block: "nearest" });
  }, [active, open]);

  const rowClass = (index: number, selected: boolean) =>
    `flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-tremor-default ${
      index === active
        ? "bg-tremor-background-subtle dark:bg-dark-tremor-background-subtle"
        : ""
    } ${
      selected
        ? "font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong"
        : "text-tremor-content-strong dark:text-dark-tremor-content-strong"
    } hover:bg-tremor-background-subtle dark:hover:bg-dark-tremor-background-subtle`;

  const allVisibleSelected =
    visible.length > 0 && visible.every((name) => values.includes(name));

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
        className={`${FILTER_SELECT_CLASS} flex items-center justify-between gap-2 text-left`}
      >
        <span className="truncate">{summary}</span>
        <span aria-hidden className="shrink-0 text-xs opacity-60">
          ▾
        </span>
      </button>
      {open ? (
        <div
          className="absolute left-0 right-0 top-full z-30 mt-1 rounded-tremor-default border border-tremor-border bg-tremor-background p-2 shadow-tremor-dropdown dark:border-dark-tremor-border dark:bg-dark-tremor-background"
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
              aria-activedescendant={`${listId}-${active}`}
              className="mb-2 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-2 py-1.5 text-tremor-default text-tremor-content-strong outline-none focus-visible:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
            />
          ) : null}
          <div className="mb-2 flex items-center gap-2 text-xs">
            <button
              type="button"
              disabled={allVisibleSelected || visible.length === 0}
              onClick={() =>
                onChange([
                  ...values,
                  ...visible.filter((name) => !values.includes(name)),
                ])
              }
              className="rounded border border-tremor-border px-2 py-1 text-tremor-content-emphasis hover:bg-tremor-background-subtle disabled:opacity-40 dark:border-dark-tremor-border dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
            >
              Выбрать все{query ? " найденные" : ""}
            </button>
            <button
              type="button"
              disabled={values.length === 0}
              onClick={() => onChange([])}
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
            aria-activedescendant={`${listId}-${active}`}
            className="max-h-64 overflow-y-auto overscroll-contain outline-none"
          >
            <label
              id={`${listId}-0`}
              data-index={0}
              role="option"
              aria-selected={values.length === 0}
              onMouseEnter={() => setActive(0)}
              className={rowClass(0, values.length === 0)}
            >
              <input
                type="checkbox"
                tabIndex={-1}
                checked={values.length === 0}
                onChange={() => onChange([])}
              />
              {allLabel}
            </label>
            {visible.map((name, index) => {
              const selected = values.includes(name);
              return (
                <label
                  key={name}
                  id={`${listId}-${index + 1}`}
                  data-index={index + 1}
                  role="option"
                  aria-selected={selected}
                  onMouseEnter={() => setActive(index + 1)}
                  className={rowClass(index + 1, selected)}
                >
                  <input
                    type="checkbox"
                    tabIndex={-1}
                    checked={selected}
                    onChange={() => toggle(name)}
                  />
                  <span className="truncate">{name}</span>
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
 * Desktop = выпадающий список с чекбоксами; mobile = chips.
 */
export function FilterChipMulti({
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
  const opts = useMemo(
    () => options.filter((o) => o && o !== allLabel),
    [options, allLabel],
  );
  const chipItems = useMemo(
    () => opts.map((name) => ({ label: name, value: name })),
    [opts],
  );
  const allOn = values.length === 0;
  const pinKey = useMemo(() => values.join("\0"), [values]);
  const {
    query,
    setQuery,
    searchable,
    visible: visibleOpts,
    needle,
  } = useChipFilter(chipItems, pinKey);
  const [suggestOpen, setSuggestOpen] = useState(false);
  const searchRef = useRef<HTMLInputElement>(null);
  const listRef = useRef<HTMLUListElement>(null);
  const suggestMatches = useMemo(
    () => matchSuggestOptions(opts, query),
    [opts, query],
  );

  useEffect(() => {
    if (!suggestOpen) return;
    const onDoc = (event: MouseEvent | TouchEvent) => {
      const t = event.target as Node;
      if (searchRef.current?.contains(t) || listRef.current?.contains(t)) return;
      setSuggestOpen(false);
    };
    document.addEventListener("mousedown", onDoc);
    document.addEventListener("touchstart", onDoc);
    return () => {
      document.removeEventListener("mousedown", onDoc);
      document.removeEventListener("touchstart", onDoc);
    };
  }, [suggestOpen]);

  const desktop = (
    <MultiSelectDropdown
      values={values}
      options={opts}
      onChange={onChange}
      allLabel={allLabel}
      disabled={disabled}
    />
  );
  const plaqueOpen = suggestOpen && Boolean(needle) && suggestMatches.length > 0;
  const chips = (
    <div className={label != null ? "mt-2" : ""}>
      {searchable ? (
        <ChipSearch
          value={query}
          onChange={(next) => {
            setQuery(next);
            setSuggestOpen(true);
          }}
          onFocus={() => setSuggestOpen(true)}
          count={opts.length}
          inputRef={searchRef}
        />
      ) : null}
      <FilterSuggestList
        open={plaqueOpen}
        matches={suggestMatches}
        anchorRef={searchRef}
        listRef={listRef}
        onSelect={(name) => {
          onChange(values.includes(name) ? values : [...values, name]);
          setQuery("");
          setSuggestOpen(false);
        }}
      />
      {!plaqueOpen ? (
        <ChipList itemCount={visibleOpts.length + 1}>
          <button
            type="button"
            disabled={disabled}
            onClick={() => {
              tapFeedback();
              onChange([]);
              setQuery("");
            }}
            className={allOn ? FILTER_CHIP_ON_CLASS : FILTER_CHIP_CLASS}
          >
            {allLabel}
          </button>
          {visibleOpts.map(({ label: name }) => {
            const on = values.includes(name);
            return (
              <button
                key={name}
                type="button"
                disabled={disabled}
                onClick={() => {
                  tapFeedback();
                  onChange(on ? values.filter((p) => p !== name) : [...values, name]);
                }}
                className={on ? FILTER_CHIP_ON_CLASS : FILTER_CHIP_CLASS}
              >
                {name}
              </button>
            );
          })}
        </ChipList>
      ) : null}
      {searchable && needle && suggestMatches.length === 0 ? (
        <p className="mt-2 text-xs text-tremor-content dark:text-dark-tremor-content">
          Ничего не найдено
        </p>
      ) : null}
    </div>
  );
  const body = (
    <>
      <div className="bi-filters-field-control hidden lg:block">{desktop}</div>
      <div className="bi-filters-field-control lg:hidden">{chips}</div>
    </>
  );
  if (label == null) return body;
  return (
    <div className="bi-filters-field text-sm">
      <span className="bi-filters-field-label text-tremor-content dark:text-dark-tremor-content">
        {label}
      </span>
      {body}
    </div>
  );
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

  const savePresetBtn =
    navId && onApply ? (
      <button
        type="button"
        className="text-xs text-sky-700 underline-offset-2 hover:underline dark:text-sky-300"
        onClick={() => {
          const name = window.prompt("Название среза фильтров:", "Мой срез");
          if (!name) return;
          saveFilterPreset(navId, name, window.location.search.replace(/^\?/, ""));
          setPresets(listFilterPresets(navId));
          confirmFeedback();
        }}
      >
        Сохранить срез
      </button>
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
          {savePresetBtn ? <div className="mb-2">{savePresetBtn}</div> : null}
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
        {!open && savePresetBtn ? <div className="mt-2">{savePresetBtn}</div> : null}
        {open ? <div className="bi-filters-body mt-3 space-y-3">{children}</div> : null}
        {open && chips.length ? <div className="mt-3">{chipsRow}</div> : null}
        {open ? presetsRow : null}
        {open && savePresetBtn ? <div className="mt-2">{savePresetBtn}</div> : null}
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
}: {
  label: ReactNode;
  children: ReactNode;
}) {
  return (
    <label className="bi-filters-field text-sm">
      <span className="bi-filters-field-label text-tremor-content dark:text-dark-tremor-content">
        {label}
      </span>
      <div className="bi-filters-field-control">{children}</div>
    </label>
  );
}

export function FilterCheck({
  label,
  className = "",
  onChange,
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
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
