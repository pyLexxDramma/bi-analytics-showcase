"use client";

import { Card, Text, Title } from "@tremor/react";
import Link from "next/link";

export function ComingSoonPage({
  title,
  section,
}: {
  title: string;
  section?: string;
}) {
  return (
    <Card className="rounded-xl">
      <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
        {title}
      </Title>
      {section ? (
        <Text className="mt-1">Раздел «{section}» · как на ai.conall.ru</Text>
      ) : null}
      <Text className="mt-4">
        Страница в очереди миграции со Streamlit. Меню уже совпадает с
        основным дашбордом; контент добавим постепенно.
      </Text>
      <div className="mt-6">
        <Link
          href="/debit-credit"
          className="text-tremor-default font-medium text-tremor-brand hover:underline dark:text-dark-tremor-brand"
        >
          Открыть готовый пилот — дебиторка →
        </Link>
      </div>
    </Card>
  );
}
