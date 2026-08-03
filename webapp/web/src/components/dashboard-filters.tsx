"use client";

import type { ButtonHTMLAttributes, InputHTMLAttributes, ReactNode } from "react";

/** Shared select look — fixed height so all fields share one baseline. */
export const FILTER_SELECT_CLASS =
  "bi-filters-select mt-1 w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 text-tremor-default text-tremor-content-strong outline-none focus:border-tremor-brand dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong disabled:opacity-50";

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
    <label className="bi-filters-field block text-sm">
      <span className="bi-filters-field-label text-tremor-content dark:text-dark-tremor-content">
        {label}
      </span>
      {children}
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
