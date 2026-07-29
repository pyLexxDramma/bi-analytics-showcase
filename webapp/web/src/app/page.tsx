"use client";

import Link from "next/link";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";

export default function HomePage() {
  return (
    <AppShell
      title="BI · Аналитика"
      subtitle="Showcase Next.js + FastAPI · внешний вид по data-spec (Tremor)"
    >
      <div className="grid gap-4">
        <Card className="rounded-xl">
          <div className="flex flex-wrap items-center justify-between gap-3">
            <div>
              <Title>Дебиторка подрядчиков</Title>
              <Text className="mt-1">Пилот · FTP-режим опционально (как ai.conall.ru)</Text>
            </div>
            <Link
              href="/debit-credit"
              className="rounded-tremor-default bg-tremor-brand px-4 py-2 text-tremor-default font-medium text-white"
            >
              Открыть
            </Link>
          </div>
        </Card>
        <Card className="rounded-xl opacity-70">
          <Title>Следующие экраны</Title>
          <Text className="mt-1">БДДС, БДР, ГДРС — по одному после приёмки пилота.</Text>
        </Card>
      </div>
    </AppShell>
  );
}
