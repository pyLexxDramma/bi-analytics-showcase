"use client";

import { useCallback, useEffect, useId, useState } from "react";
import { createPortal } from "react-dom";
import { usePathname } from "next/navigation";
import {
  buildBugReportUrl,
  resolveBugReportContext,
} from "@/lib/bug-report";
import { getAuthSession, type AuthUser } from "@/lib/auth";
import { tapFeedback } from "@/lib/haptics";

/**
 * Desktop-only: сначала инструкция, затем баг-форма с автозаполнением контекста.
 * На мобиле не рендерим (класс lg:flex).
 */
export function ReportBugButton({ pageTitle }: { pageTitle?: string }) {
  const pathname = usePathname();
  const titleId = useId();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [mounted, setMounted] = useState(false);
  const [open, setOpen] = useState(false);

  useEffect(() => setMounted(true), []);

  useEffect(() => {
    setUser(getAuthSession());
  }, [pathname]);

  useEffect(() => {
    if (!open) return;
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") setOpen(false);
    };
    document.addEventListener("keydown", onKey);
    return () => document.removeEventListener("keydown", onKey);
  }, [open]);

  const context = resolveBugReportContext(pathname, pageTitle);
  const available = context != null;

  const openForm = useCallback(() => {
    if (!context) return;
    tapFeedback();
    const url = buildBugReportUrl({
      context,
      user,
      pathname,
      search: typeof window !== "undefined" ? window.location.search : "",
    });
    setOpen(false);
    window.open(url, "_blank", "noopener,noreferrer");
  }, [context, user, pathname]);

  if (!available) return null;

  return (
    <div className="hidden lg:flex lg:flex-col lg:items-end lg:gap-1">
      <button
        type="button"
        onClick={() => {
          tapFeedback();
          setOpen(true);
        }}
        title="Сообщить об ошибке на этом экране"
        className="report-bug-btn inline-flex h-11 items-center gap-2 rounded-tremor-default px-4 text-tremor-default transition"
      >
        <span aria-hidden className="text-base leading-none">
          !
        </span>
        Сообщить об ошибке
      </button>

      {mounted &&
        open &&
        createPortal(
          <div
            className="fixed inset-0 z-[75] hidden items-start justify-center p-6 pt-[10vh] lg:flex"
            role="dialog"
            aria-modal="true"
            aria-labelledby={titleId}
          >
            <button
              type="button"
              aria-label="Закрыть инструкцию"
              onClick={() => setOpen(false)}
              className="absolute inset-0 cursor-default bg-slate-900/40 backdrop-blur-[2px]"
            />
            <div className="relative flex max-h-[80vh] w-full max-w-lg flex-col overflow-hidden rounded-xl border border-tremor-border bg-tremor-background shadow-2xl dark:border-dark-tremor-border dark:bg-dark-tremor-background">
              <div className="flex shrink-0 items-center justify-between border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
                <h2
                  id={titleId}
                  className="text-tremor-default font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong"
                >
                  Как заполнить сообщение об ошибке
                </h2>
                <kbd className="rounded border border-tremor-border px-1.5 py-0.5 text-xs text-tremor-content dark:border-dark-tremor-border dark:text-dark-tremor-content">
                  Esc
                </kbd>
              </div>

              <div className="min-h-0 flex-1 space-y-3 overflow-y-auto px-4 py-3 text-tremor-default text-tremor-content dark:text-dark-tremor-content">
                <p>
                  Часть полей уже подставится автоматически (раздел, отчёт, роль,
                  контур, браузер, фильтры). Обязательно укажите имя и фамилию,
                  опишите факт и ожидание, приложите скрин(ы) — можно перетащить
                  несколько файлов. Шаги воспроизведения необязательны.
                </p>
                <ol className="list-decimal space-y-2 pl-5">
                  <li>
                    <span className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      Тип и блок
                    </span>
                    {" — "}
                    выберите, что сломалось (интерфейс, данные, расчёт…) и где
                    именно (таблица, график, фильтр…).
                  </li>
                  <li>
                    <span className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      Фактически
                    </span>
                    {" — "}
                    что вы видите сейчас (цифры, текст ошибки, пустой экран).
                  </li>
                  <li>
                    <span className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      Ожидалось
                    </span>
                    {" — "}
                    как должно работать правильно.
                  </li>
                  <li>
                    <span className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      Шаги
                    </span>
                    {" — "}
                    по пунктам: какой экран → какие фильтры → что нажали.
                  </li>
                  <li>
                    <span className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                      Серьёзность
                    </span>
                    {" — "}
                    косметика / мешает работе / критично.
                  </li>
                </ol>
                <p className="rounded-lg border border-tremor-border bg-tremor-background-muted px-3 py-2 text-tremor-label dark:border-dark-tremor-border dark:bg-dark-tremor-background-muted">
                  Главное: по отчёту должно быть понятно,{" "}
                  <strong className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                    какая проблема
                  </strong>{" "}
                  и{" "}
                  <strong className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                    как должно работать
                  </strong>
                  . Скриншот — если помогает. Блок «Данные для сверки» появится
                  только при типе «Проблема с данными».
                </p>
              </div>

              <div className="flex shrink-0 items-center justify-end gap-2 border-t border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
                <button
                  type="button"
                  onClick={() => setOpen(false)}
                  className="inline-flex h-10 items-center rounded-tremor-default border border-tremor-border px-4 text-tremor-default text-tremor-content transition hover:bg-tremor-background-muted dark:border-dark-tremor-border dark:text-dark-tremor-content dark:hover:bg-dark-tremor-background-muted"
                >
                  Отмена
                </button>
                <button
                  type="button"
                  onClick={openForm}
                  className="report-bug-btn inline-flex h-10 items-center rounded-tremor-default px-4 text-tremor-default transition"
                >
                  Открыть форму
                </button>
              </div>
            </div>
          </div>,
          document.body,
        )}
    </div>
  );
}
