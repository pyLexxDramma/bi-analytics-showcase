"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { Card, Text } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { AdminDataSyncSection } from "@/components/settings/admin-data-sync-section";
import { AdminFiltersPanel } from "@/components/settings/admin-filters-panel";
import { AdminSystemPanel } from "@/components/settings/admin-system-panel";
import { EmeraldTabs } from "@/components/settings/emerald-tabs";
import { fetchAuthMe } from "@/lib/api";
import {
  getAuthSession,
  hasAdminAccess,
  saveAuthSession,
  type AuthUser,
} from "@/lib/auth";

export function AdminView() {
  const [user, setUser] = useState<AuthUser | null>(null);
  const [primaryTab, setPrimaryTab] = useState("filters");
  const [accessDenied, setAccessDenied] = useState(false);

  useEffect(() => {
    const local = getAuthSession();
    setUser(local);
    if (local && !hasAdminAccess(local)) {
      setAccessDenied(true);
    }
    void fetchAuthMe()
      .then((r) => {
        setUser(r.user);
        saveAuthSession(r.user);
        setAccessDenied(!hasAdminAccess(r.user));
      })
      .catch(() => {
        if (local && !hasAdminAccess(local)) setAccessDenied(true);
      });
  }, []);

  if (accessDenied) {
    return (
      <AppShell title="Административная панель">
        <Card className="rounded-xl">
          <Text className="text-rose-700">
            У вас нет доступа к этой странице. Доступ имеют только администраторы
            и суперадминистраторы.
          </Text>
          <Link
            href="/developer-projects"
            className="mt-4 inline-block rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white"
          >
            Вернуться к отчетам
          </Link>
        </Card>
      </AppShell>
    );
  }

  return (
    <AppShell title="Административная панель">
      <p className="mb-4 text-sm text-tremor-content dark:text-dark-tremor-content">
        Управление фильтрами, пользователями и данными.
        {user?.username ? (
          <>
            {" "}
            Сессия:{" "}
            <span className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
              {user.username}
            </span>
            {user.role_label ? ` · ${user.role_label}` : ""}. Пароль и email — в{" "}
            <Link
              href="/settings/profile"
              className="text-emerald-700 underline dark:text-emerald-300"
            >
              профиле
            </Link>
            .
          </>
        ) : null}
      </p>

      <EmeraldTabs
        className="mb-6"
        active={primaryTab}
        onChange={setPrimaryTab}
        tabs={[
          { id: "filters", label: "Фильтры отчетов" },
          { id: "system", label: "Управление системой" },
        ]}
      />

      {primaryTab === "filters" ? <AdminFiltersPanel /> : null}
      {primaryTab === "system" ? (
        <>
          <AdminSystemPanel />
          <AdminDataSyncSection />
        </>
      ) : null}

      <div className="mt-8">
        <Link
          href="/developer-projects"
          className="inline-flex rounded-md border border-gray-200 bg-white px-4 py-2 text-sm font-medium hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
        >
          ← Вернуться к отчетам
        </Link>
      </div>
    </AppShell>
  );
}
