"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";
import { FiltersSheet } from "@/components/filters-sheet";
import { confirmFeedback, tapFeedback } from "@/lib/haptics";
import { useIsMobileViewport } from "@/lib/use-is-mobile";

/** Shared select look — fixed height so all fields share one baseline. */
export const FILTER_SELECT_CLASS =
  "bi-filters-select w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 text-tremor-default text-tremor-content-strong outline-none focus:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong disabled:opacity-50";

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

function ChipSearch({
  value,
  onChange,
  count,
}: {
  value: string;
  onChange: (next: string) => void;
  count: number;
}) {
  return (
    <input
      type="search"
      inputMode="search"
      value={value}
      onChange={(e) => onChange(e.target.value)}
      placeholder={`Поиск · ${count}`}
      className="bi-filter-chip-search mb-2 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-sm text-tremor-content-strong outline-none focus:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
    />
  );
}

function useChipFilter<T extends { label: string }>(items: T[]) {
  const [query, setQuery] = useState("");
  const searchable = items.length > CHIP_SEARCH_AFTER;
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!searchable || !needle) return items;
    return items.filter((item) => item.label.toLowerCase().includes(needle));
  }, [items, query, searchable]);
  return { query, setQuery, searchable, visible };
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
  const normalized = options.map(normChipOption);
  const { query, setQuery, searchable, visible } = useChipFilter(normalized);
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
  const chips = (
    <div className={label != null ? "mt-2" : ""}>
      {searchable ? (
        <ChipSearch value={query} onChange={setQuery} count={normalized.length} />
      ) : null}
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
              }}
              className={on ? FILTER_CHIP_ON_CLASS : FILTER_CHIP_CLASS}
            >
              {lab}
            </button>
          );
        })}
      </ChipList>
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
  const rootRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    if (!open) return;
    const onPointerDown = (event: MouseEvent | TouchEvent) => {
      if (!rootRef.current?.contains(event.target as Node)) setOpen(false);
    };
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("mousedown", onPointerDown);
    document.addEventListener("keydown", onKey);
    return () => {
      document.removeEventListener("mousedown", onPointerDown);
      document.removeEventListener("keydown", onKey);
    };
  }, [open]);

  const searchable = options.length > CHIP_SEARCH_AFTER;
  const visible = useMemo(() => {
    const needle = query.trim().toLowerCase();
    if (!searchable || !needle) return options;
    return options.filter((name) => name.toLowerCase().includes(needle));
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

  return (
    <div ref={rootRef} className="relative">
      <button
        type="button"
        disabled={disabled}
        onClick={() => setOpen((v) => !v)}
        aria-expanded={open}
        aria-haspopup="listbox"
        className={`${FILTER_SELECT_CLASS} flex items-center justify-between gap-2 text-left`}
      >
        <span className="truncate">{summary}</span>
        <span aria-hidden className="shrink-0 text-xs opacity-60">
          ▾
        </span>
      </button>
      {open ? (
        <div
          role="listbox"
          aria-multiselectable
          className="absolute left-0 right-0 top-full z-30 mt-1 rounded-tremor-default border border-tremor-border bg-tremor-background p-2 shadow-tremor-dropdown dark:border-dark-tremor-border dark:bg-dark-tremor-background"
        >
          {searchable ? (
            <input
              type="search"
              value={query}
              onChange={(e) => setQuery(e.target.value)}
              placeholder={`Поиск · ${options.length}`}
              className="mb-2 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-2 py-1.5 text-tremor-default text-tremor-content-strong outline-none focus:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
            />
          ) : null}
          <div className="max-h-64 overflow-y-auto overscroll-contain">
            <label className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-tremor-default text-tremor-content-strong hover:bg-tremor-background-subtle dark:text-dark-tremor-content-strong dark:hover:bg-dark-tremor-background-subtle">
              <input
                type="checkbox"
                checked={values.length === 0}
                onChange={() => onChange([])}
              />
              {allLabel}
            </label>
            {visible.map((name) => (
              <label
                key={name}
                className="flex cursor-pointer items-center gap-2 rounded px-2 py-1.5 text-tremor-default text-tremor-content-strong hover:bg-tremor-background-subtle dark:text-dark-tremor-content-strong dark:hover:bg-dark-tremor-background-subtle"
              >
                <input
                  type="checkbox"
                  checked={values.includes(name)}
                  onChange={() => toggle(name)}
                />
                <span className="truncate">{name}</span>
              </label>
            ))}
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
  const opts = options.filter((o) => o && o !== allLabel);
  const allOn = values.length === 0;
  const {
    query,
    setQuery,
    searchable,
    visible: visibleOpts,
  } = useChipFilter(opts.map((name) => ({ label: name })));
  const desktop = (
    <MultiSelectDropdown
      values={values}
      options={opts}
      onChange={onChange}
      allLabel={allLabel}
      disabled={disabled}
    />
  );
  const chips = (
    <div className={label != null ? "mt-2" : ""}>
      {searchable ? (
        <ChipSearch value={query} onChange={setQuery} count={opts.length} />
      ) : null}
      <ChipList itemCount={visibleOpts.length + 1}>
        <button
          type="button"
          disabled={disabled}
          onClick={() => onChange([])}
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
  onReset,
  children,
}: {
  open: boolean;
  onToggle: () => void;
  title?: string;
  activeCount?: number;
  onReset?: () => void;
  children: ReactNode;
}) {
  const mobile = useIsMobileViewport();
  // Лист держим на собственном состоянии: экраны с `open=true` по умолчанию
  // (например «Дебиторка») иначе открывали бы его при загрузке страницы.
  const [sheetOpen, setSheetOpen] = useState(false);

  if (mobile) {
    return (
      <>
        <button
          type="button"
          onClick={() => {
            tapFeedback();
            setSheetOpen(true);
          }}
          aria-expanded={sheetOpen}
          className="bi-filters-trigger mb-4"
        >
          <span className="bi-filters-trigger-icon" aria-hidden>
            ⛭
          </span>
          <span className="flex-1 text-left">{title}</span>
          {activeCount ? (
            <span className="bi-filters-trigger-badge">{activeCount}</span>
          ) : null}
          <span aria-hidden>▾</span>
        </button>
        <FiltersSheet
          open={sheetOpen}
          onClose={() => setSheetOpen(false)}
          title={title}
          onReset={onReset}
        >
          <div className="bi-filters-body space-y-3">{children}</div>
        </FiltersSheet>
      </>
    );
  }

  return (
    <div className="bi-filters-panel mb-6 rounded-xl border border-tremor-border bg-tremor-background p-4 dark:border-dark-tremor-border dark:bg-dark-tremor-background">
      <button
        type="button"
        onClick={onToggle}
        aria-expanded={open}
        className="flex w-full items-center gap-2 text-left text-sm font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong"
      >
        <span className="text-xs">{open ? "▾" : "▸"}</span>
        {title}
      </button>
      {open ? <div className="bi-filters-body mt-3 space-y-3">{children}</div> : null}
    </div>
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
