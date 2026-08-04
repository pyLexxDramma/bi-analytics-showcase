"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

/** Shared select look — fixed height so all fields share one baseline. */
export const FILTER_SELECT_CLASS =
  "bi-filters-select w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 text-tremor-default text-tremor-content-strong outline-none focus:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong disabled:opacity-50";

/** BDDS-style chip buttons for categorical filters. */
export const FILTER_CHIP_CLASS =
  "rounded-md border px-2.5 py-1 text-xs border-tremor-border bg-white text-tremor-content-strong disabled:cursor-not-allowed disabled:opacity-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong";
export const FILTER_CHIP_ON_CLASS =
  "rounded-md border px-2.5 py-1 text-xs border-emerald-600 bg-emerald-50 text-emerald-900 disabled:cursor-not-allowed disabled:opacity-50 dark:border-emerald-500 dark:bg-emerald-950/40 dark:text-emerald-200";

export type FilterChipOption = string | { value: string; label: string };

function normChipOption(opt: FilterChipOption): { value: string; label: string } {
  if (typeof opt === "string") return { value: opt, label: opt };
  return opt;
}

/** ~6 chip-rows visible; longer lists scroll (как старые MultiSelect max-h). */
const CHIP_LIST_BASE = "flex flex-wrap content-start gap-2";
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
    <ChipList
      itemCount={options.length}
      className={label != null ? "mt-2" : ""}
    >
      {normalized.map(({ value: v, label: lab }) => {
        const on = value === v;
        return (
          <button
            key={v}
            type="button"
            disabled={disabled}
            onClick={() => onChange(v)}
            className={on ? FILTER_CHIP_ON_CLASS : FILTER_CHIP_CLASS}
          >
            {lab}
          </button>
        );
      })}
    </ChipList>
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
 * Multi-select: empty `values` = «Все».
 * Desktop = native select (закрытый вид как main); mobile = chips.
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
  const desktopValue = values.length === 1 ? values[0]! : "";
  const desktop = (
    <select
      className={FILTER_SELECT_CLASS}
      value={desktopValue}
      disabled={disabled}
      onChange={(e) => {
        const next = e.target.value;
        onChange(next ? [next] : []);
      }}
    >
      <option value="">{allLabel}</option>
      {opts.map((name) => (
        <option key={name} value={name}>
          {name}
        </option>
      ))}
    </select>
  );
  const chips = (
    <ChipList
      itemCount={opts.length + 1}
      className={label != null ? "mt-2" : ""}
    >
      <button
        type="button"
        disabled={disabled}
        onClick={() => onChange([])}
        className={allOn ? FILTER_CHIP_ON_CLASS : FILTER_CHIP_CLASS}
      >
        {allLabel}
      </button>
      {opts.map((name) => {
        const on = values.includes(name);
        return (
          <button
            key={name}
            type="button"
            disabled={disabled}
            onClick={() =>
              onChange(on ? values.filter((p) => p !== name) : [...values, name])
            }
            className={on ? FILTER_CHIP_ON_CLASS : FILTER_CHIP_CLASS}
          >
            {name}
          </button>
        );
      })}
    </ChipList>
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
  children,
}: {
  open: boolean;
  onToggle: () => void;
  title?: string;
  children: ReactNode;
}) {
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
      onClick={onClick}
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
  ...input
}: InputHTMLAttributes<HTMLInputElement> & { label: ReactNode }) {
  return (
    <label
      className={`bi-filters-check flex items-start gap-2 text-sm text-tremor-content-strong dark:text-dark-tremor-content-strong ${
        input.disabled ? "opacity-50" : ""
      } ${className}`}
    >
      <input type="checkbox" className="bi-filters-check-input" {...input} />
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
