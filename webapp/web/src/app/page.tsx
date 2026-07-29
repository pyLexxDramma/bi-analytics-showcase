"use client";

import Link from "next/link";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import {
  REPORT_ACCORDIONS,
  REPORT_STANDALONE,
  REPORT_TOP_TAB,
} from "@/lib/nav";

export default function HomePage() {
  return (
    <AppShell
      title="BI · Аналитика"
      subtitle="Сайдбар как на ai.conall.ru — вкладки раскрывают дашборды"
    >
      <div className="grid gap-4">
        <Card className="rounded-xl">
          <Title>Отчёты</Title>
          <Text className="mt-1">
            Слева: аккордеоны Финансы / Сроки / Проектные работы / ГДРС.
          </Text>
          <ul className="mt-3 list-disc space-y-1 pl-5 text-tremor-default">
            <li>
              <Link className="text-tremor-brand hover:underline" href={REPORT_TOP_TAB.href}>
                {REPORT_TOP_TAB.label}
              </Link>
            </li>
            {REPORT_ACCORDIONS.map((a) => (
              <li key={a.id}>
                <span className="font-medium">{a.label}</span>
                <ul className="ml-4 list-disc text-tremor-content">
                  {a.items.map((i) => (
                    <li key={i.id}>
                      <Link href={i.href} className="text-tremor-brand hover:underline">
                        {i.label}
                      </Link>
                    </li>
                  ))}
                </ul>
              </li>
            ))}
            {REPORT_STANDALONE.map((i) => (
              <li key={i.id}>
                <Link href={i.href} className="text-tremor-brand hover:underline">
                  {i.label}
                  {i.ready ? " · готово" : ""}
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      </div>
    </AppShell>
  );
}
