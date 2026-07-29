"use client";

import Link from "next/link";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { NAV_SECTIONS } from "@/lib/nav";

export default function HomePage() {
  return (
    <AppShell
      title="BI · Аналитика"
      subtitle="Меню как на ai.conall.ru · пилот Next.js + FastAPI"
    >
      <div className="grid gap-4">
        {NAV_SECTIONS.map((section) => (
          <Card key={section.id} className="rounded-xl">
            <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
              {section.title}
            </Title>
            <ul className="mt-3 space-y-2">
              {section.items.map((item) => (
                <li key={item.id}>
                  <Link
                    href={item.href}
                    className="text-tremor-default text-tremor-brand hover:underline dark:text-dark-tremor-brand"
                  >
                    {item.label}
                    {item.ready ? (
                      <span className="ml-2 text-tremor-label text-emerald-600 dark:text-emerald-400">
                        готово
                      </span>
                    ) : (
                      <span className="ml-2 text-tremor-label text-tremor-content dark:text-dark-tremor-content">
                        скоро
                      </span>
                    )}
                  </Link>
                </li>
              ))}
            </ul>
          </Card>
        ))}
        <Text>
          Готовый экран с данными:{" "}
          <Link href="/debit-credit" className="font-medium text-tremor-brand">
            дебиторка / кредиторка
          </Link>
          .
        </Text>
      </div>
    </AppShell>
  );
}
