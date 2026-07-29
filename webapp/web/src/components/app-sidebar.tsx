"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { NAV_SECTIONS } from "@/lib/nav";

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-full shrink-0 flex-col border-tremor-border bg-tremor-background dark:border-dark-tremor-border dark:bg-dark-tremor-background lg:h-screen lg:w-72 lg:border-r">
      <Link href="/" className="shrink-0 px-4 pb-3 pt-5">
        <div className="text-tremor-title font-bold text-tremor-content-strong dark:text-dark-tremor-content-strong">
          BI · Аналитика
        </div>
        <div className="text-tremor-label text-tremor-content dark:text-dark-tremor-content">
          Как на ai.conall.ru · Next.js
        </div>
      </Link>

      <nav className="flex-1 space-y-4 overflow-y-auto px-3 pb-6">
        {NAV_SECTIONS.map((section) => (
          <div key={section.id}>
            <div className="mb-1 px-2 text-[11px] font-semibold uppercase tracking-wide text-tremor-content dark:text-dark-tremor-content">
              {section.title}
            </div>
            <div className="flex flex-col gap-0.5">
              {section.items.map((item) => {
                const isActive =
                  pathname === item.href ||
                  pathname.startsWith(`${item.href}/`);
                const className = `rounded-tremor-default px-2.5 py-2 text-left text-tremor-default transition ${
                  isActive
                    ? "bg-tremor-brand-faint font-medium text-tremor-brand-emphasis dark:bg-dark-tremor-brand-faint dark:text-dark-tremor-brand-emphasis"
                    : "text-tremor-content-emphasis hover:bg-tremor-background-subtle dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
                } ${item.ready ? "" : "opacity-60"}`;

                if (!item.ready) {
                  return (
                    <Link
                      key={item.id}
                      href={item.href}
                      className={className}
                      title="Страница-заглушка · в очереди миграции"
                    >
                      <span className="leading-snug">{item.label}</span>
                      <span className="mt-0.5 block text-tremor-label text-tremor-content dark:text-dark-tremor-content">
                        скоро
                      </span>
                    </Link>
                  );
                }

                return (
                  <Link key={item.id} href={item.href} className={className}>
                    <span className="leading-snug">{item.label}</span>
                  </Link>
                );
              })}
            </div>
          </div>
        ))}
      </nav>
    </aside>
  );
}
