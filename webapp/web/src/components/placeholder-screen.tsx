"use client";

import { AppShell } from "@/components/app-shell";
import { ComingSoonPage } from "@/components/coming-soon";

export function PlaceholderScreen({
  title,
  section,
}: {
  title: string;
  section?: string;
}) {
  return (
    <AppShell title={title} subtitle={section ? `Блок: ${section}` : undefined}>
      <ComingSoonPage title={title} section={section} />
    </AppShell>
  );
}
