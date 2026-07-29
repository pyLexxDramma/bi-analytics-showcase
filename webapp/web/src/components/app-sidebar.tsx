"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";

type NavItem = {
  href: string;
  label: string;
  icon: string;
  hint: string;
  ready?: boolean;
};

const items: NavItem[] = [
  {
    href: "/debit-credit",
    label: "Дебиторка подрядчиков",
    icon: "🏗",
    hint: "Авансы vs КС-2",
    ready: true,
  },
  {
    href: "/#bdds",
    label: "Бюджет проектов",
    icon: "📊",
    hint: "БДДС · скоро",
  },
  {
    href: "/#bdr",
    label: "БДР",
    icon: "📈",
    hint: "Доходы и расходы · скоро",
  },
  {
    href: "/#gdrs",
    label: "Ресурсы: ГДРС",
    icon: "👥",
    hint: "Люди / техника · скоро",
  },
];

export function AppSidebar() {
  const pathname = usePathname();

  return (
    <aside className="flex w-full shrink-0 flex-col gap-1 border-tremor-border bg-tremor-background p-4 dark:border-dark-tremor-border dark:bg-dark-tremor-background lg:h-screen lg:w-64 lg:border-r">
      <Link href="/" className="mb-6 px-2 pt-2">
        <div className="text-tremor-title font-bold text-tremor-content-strong dark:text-dark-tremor-content-strong">
          BI · Аналитика
        </div>
        <div className="text-tremor-label text-tremor-content dark:text-dark-tremor-content">
          Showcase Next · строительные проекты
        </div>
      </Link>

      <nav className="flex flex-col gap-1">
        {items.map((item) => {
          const isActive =
            item.href === pathname ||
            (item.href !== "/" && pathname.startsWith(item.href));
          const className = `flex items-start gap-3 rounded-tremor-default px-3 py-2.5 text-left transition ${
            isActive
              ? "bg-tremor-brand-faint text-tremor-brand-emphasis dark:bg-dark-tremor-brand-faint dark:text-dark-tremor-brand-emphasis"
              : "text-tremor-content-emphasis hover:bg-tremor-background-subtle dark:text-dark-tremor-content-emphasis dark:hover:bg-dark-tremor-background-subtle"
          } ${item.ready ? "" : "opacity-55"}`;

          if (!item.ready) {
            return (
              <div key={item.href} className={className} title="В очереди миграции">
                <span className="text-lg leading-none">{item.icon}</span>
                <span className="flex flex-col">
                  <span className="text-tremor-default font-medium">{item.label}</span>
                  <span className="text-tremor-label text-tremor-content dark:text-dark-tremor-content">
                    {item.hint}
                  </span>
                </span>
              </div>
            );
          }

          return (
            <Link key={item.href} href={item.href} className={className}>
              <span className="text-lg leading-none">{item.icon}</span>
              <span className="flex flex-col">
                <span className="text-tremor-default font-medium">{item.label}</span>
                <span className="text-tremor-label text-tremor-content dark:text-dark-tremor-content">
                  {item.hint}
                </span>
              </span>
            </Link>
          );
        })}
      </nav>
    </aside>
  );
}
