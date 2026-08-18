"use client";

import { useState } from "react";

export function PasswordField({
  label,
  value,
  onChange,
  placeholder,
}: {
  label: string;
  value: string;
  onChange: (v: string) => void;
  placeholder?: string;
}) {
  const [show, setShow] = useState(false);
  return (
    <label className="block text-sm">
      <span className="mb-1 block font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
        {label}
      </span>
      <div className="relative">
        <input
          type={show ? "text" : "password"}
          className="w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 pr-10 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
          value={value}
          onChange={(e) => onChange(e.target.value)}
          placeholder={placeholder}
          autoComplete="off"
        />
        <button
          type="button"
          className="absolute right-2 top-1/2 -translate-y-1/2 rounded px-1.5 py-0.5 text-xs text-gray-600 hover:bg-gray-100 dark:text-dark-tremor-content"
          onClick={() => setShow((v) => !v)}
          aria-label={show ? "Скрыть" : "Показать"}
        >
          {show ? "🙈" : "👁"}
        </button>
      </div>
    </label>
  );
}

export function InfoBanner({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-4 rounded-lg border border-sky-200 bg-sky-50 px-4 py-3 text-sm text-sky-900 dark:border-sky-800 dark:bg-sky-950/40 dark:text-sky-100">
      {children}
    </div>
  );
}

export const SETTINGS_TABLE =
  "min-w-full border-collapse text-sm [&_th]:border-b [&_th]:border-gray-200 [&_th]:bg-gray-50 [&_th]:px-3 [&_th]:py-2 [&_th]:text-center [&_th]:font-semibold [&_td]:border-b [&_td]:border-gray-100 [&_td]:px-3 [&_td]:py-2 dark:[&_th]:border-dark-tremor-border dark:[&_th]:bg-dark-tremor-background-subtle dark:[&_td]:border-dark-tremor-border";
