"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  REPORT_ACCORDIONS,
  REPORT_STANDALONE,
  REPORT_TOP_TAB,
  accordionIdForPath,
} from "@/lib/nav";
import { logout } from "@/lib/auth";

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-sm font-bold text-[#1f2937] dark:text-dark-tremor-content-strong">
      {children}
    </div>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <span
      className={`inline-block text-xs text-gray-500 transition-transform ${
        open ? "rotate-90" : ""
      }`}
      aria-hidden
    >
      ▸
    </span>
  );
}

export function AppSidebar() {
  const pathname = usePathname();
  const router = useRouter();
  const activeAccordion = accordionIdForPath(pathname);
  const [openId, setOpenId] = useState<string | null>(activeAccordion);

  useEffect(() => {
    if (activeAccordion) setOpenId(activeAccordion);
  }, [activeAccordion]);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);

  return (
    <aside className="flex w-full shrink-0 flex-col border-r border-gray-200 bg-[#f8f9fb] text-[13px] text-[#1f2937] dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong lg:h-screen lg:w-[280px]">
      <div className="flex-1 overflow-y-auto px-3 py-4">
        {/* Меню */}
        <section className="mb-5">
          <SectionTitle>Меню</SectionTitle>
          <Link
            href="/ai-assistant"
            className="flex items-center gap-2 rounded-md border border-sky-300 bg-white px-3 py-2 text-sky-700 hover:bg-sky-50 dark:border-sky-700 dark:bg-dark-tremor-background dark:text-sky-300"
          >
            <span aria-hidden>✨</span>
            <span>ИИ помощник</span>
          </Link>
        </section>

        {/* Отчёты */}
        <section className="mb-5">
          <SectionTitle>Отчёты</SectionTitle>
          <div className="flex flex-col gap-1.5">
            {/* Топ-вкладка */}
            <Link
              href={REPORT_TOP_TAB.href}
              className={`rounded-md px-3 py-2 font-medium transition ${
                isActive(REPORT_TOP_TAB.href)
                  ? "border border-emerald-300 bg-[#e8f5e9] text-emerald-900"
                  : "border border-transparent bg-white hover:bg-gray-100 dark:bg-dark-tremor-background-subtle"
              }`}
            >
              {REPORT_TOP_TAB.label}
            </Link>

            {/* Аккордеоны */}
            {REPORT_ACCORDIONS.map((acc) => {
              const open = openId === acc.id;
              const childActive = acc.items.some((i) => isActive(i.href));
              return (
                <div key={acc.id} className="flex flex-col gap-1">
                  <button
                    type="button"
                    onClick={() => setOpenId(open ? null : acc.id)}
                    className={`flex w-full items-center gap-2 rounded-md border px-3 py-2 text-left transition ${
                      childActive || open
                        ? "border-gray-300 bg-white dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle"
                        : "border-gray-200 bg-white hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                    }`}
                    aria-expanded={open}
                  >
                    <Chevron open={open} />
                    <span className="font-medium">{acc.label}</span>
                  </button>
                  {open ? (
                    <div className="ml-1 rounded-md border border-gray-200 bg-[#eef0f3] p-1.5 dark:border-dark-tremor-border dark:bg-dark-tremor-background-muted">
                      <div className="flex flex-col gap-1">
                        {acc.items.map((item) => (
                          <Link
                            key={item.id}
                            href={item.href}
                            className={`rounded-md border px-2.5 py-1.5 leading-snug transition ${
                              isActive(item.href)
                                ? "border-emerald-300 bg-[#e8f5e9] font-medium text-emerald-900"
                                : "border-gray-200 bg-white text-gray-800 hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
                            }`}
                          >
                            {item.label}
                            {!item.ready ? (
                              <span className="ml-1 text-[11px] text-gray-400">
                                · скоро
                              </span>
                            ) : null}
                          </Link>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}

            {/* Одиночные пункты */}
            {REPORT_STANDALONE.map((item) => (
              <Link
                key={item.id}
                href={item.href}
                className={`rounded-md border px-3 py-2 leading-snug transition ${
                  isActive(item.href)
                    ? "border-emerald-300 bg-[#e8f5e9] font-medium text-emerald-900"
                    : "border-gray-200 bg-white hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                }`}
              >
                {item.label}
                {item.ready ? (
                  <span className="ml-1 text-[11px] text-emerald-600">· готово</span>
                ) : (
                  <span className="ml-1 text-[11px] text-gray-400">· скоро</span>
                )}
              </Link>
            ))}
          </div>
        </section>

        {/* Настройки */}
        <section className="mb-5">
          <SectionTitle>Настройки</SectionTitle>
          <div className="flex flex-col gap-1.5">
            <Link
              href="/settings/profile"
              className="rounded-md border border-gray-200 bg-white px-3 py-2 hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            >
              Настройки профиля
            </Link>
            <Link
              href="/settings/admin"
              className="rounded-md border border-gray-200 bg-white px-3 py-2 hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            >
              Административная панель
            </Link>
          </div>
        </section>

        {/* Данные (заглушка UI как на Streamlit) */}
        <section className="mb-4">
          <SectionTitle>Данные</SectionTitle>
          <div className="space-y-2 rounded-md border border-gray-200 bg-white p-3 dark:border-dark-tremor-border dark:bg-dark-tremor-background">
            <label className="flex cursor-default items-center gap-2 text-gray-500">
              <input type="radio" disabled name="data-src" />
              Загрузить вручную
            </label>
            <label className="flex cursor-default items-center gap-2">
              <input type="radio" name="data-src" defaultChecked readOnly />
              Из папки web/
            </label>
            <label className="flex cursor-default items-center gap-2 text-gray-500">
              <input type="radio" disabled name="data-src" />
              FTP + web/
            </label>
            <button
              type="button"
              disabled
              className="mt-1 w-full rounded-md border border-gray-200 bg-gray-50 px-2 py-1.5 text-gray-400"
              title="Пока только в Streamlit / API sync"
            >
              Загрузить из web/
            </button>
            <button
              type="button"
              disabled
              className="w-full rounded-md bg-[#66bb6a] px-2 py-2 font-medium text-white opacity-70"
              title="Локально: POST /api/admin/sync"
            >
              FTP + перезагрузить БД
            </button>
            <p className="text-[11px] leading-snug text-gray-500">
              Выгрузка на FTP ежедневно в 07:00 МСК. Синк Next:{" "}
              <code className="text-[10px]">POST /api/admin/sync</code>
            </p>
          </div>
        </section>
      </div>

      <div className="shrink-0 border-t border-gray-200 p-3 dark:border-dark-tremor-border">
        <button
          type="button"
          className="w-full rounded-md bg-[#fdecea] px-3 py-2 font-medium text-[#c62828] transition hover:bg-[#f8d7d3]"
          onClick={() => {
            logout();
            router.push("/login");
          }}
        >
          Выйти
        </button>
      </div>
    </aside>
  );
}
