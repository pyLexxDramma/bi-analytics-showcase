"use client";

import { useEffect, useState } from "react";
import { Card, Grid, Metric, Text, Title } from "@tremor/react";
import { getAuthUser, login } from "@/lib/auth";
import { AppShell } from "@/components/app-shell";

export function ProfileView() {
  const [user, setUser] = useState("");
  const [draftName, setDraftName] = useState("");
  const [msg, setMsg] = useState<string | null>(null);

  useEffect(() => {
    const u = getAuthUser() || "demo";
    setUser(u);
    setDraftName(u);
  }, []);

  const saveName = () => {
    const next = draftName.trim() || "demo";
    login(next);
    setUser(next);
    setMsg("Имя сохранено локально (демо-вход).");
  };

  return (
    <AppShell
      title="Настройки профиля"
      subtitle="Демо-сессия Next.js · без серверных пользователей"
    >
      <Grid numItemsSm={2} numItemsLg={3} className="mb-6 gap-6">
        <Card className="rounded-xl">
          <Text>Пользователь</Text>
          <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
            {user || "—"}
          </Metric>
        </Card>
        <Card className="rounded-xl">
          <Text>Роль</Text>
          <Metric className="mt-2 text-blue-600 dark:text-blue-400">
            demo
          </Metric>
        </Card>
        <Card className="rounded-xl">
          <Text>Сессия</Text>
          <Metric className="mt-2 text-emerald-600 dark:text-emerald-400">
            localStorage
          </Metric>
        </Card>
      </Grid>

      <Card className="mb-6 rounded-xl">
        <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
          Отображаемое имя
        </Title>
        <Text className="mt-1">
          Меняет только локальный демо-логин в браузере.
        </Text>
        <div className="mt-4 flex max-w-md flex-col gap-2 sm:flex-row">
          <input
            className="w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            value={draftName}
            onChange={(e) => setDraftName(e.target.value)}
          />
          <button
            type="button"
            className="rounded-tremor-default bg-tremor-brand px-4 py-2 font-medium text-white"
            onClick={saveName}
          >
            Сохранить
          </button>
        </div>
        {msg ? <Text className="mt-3 text-emerald-700 dark:text-emerald-300">{msg}</Text> : null}
      </Card>

      <Card className="rounded-xl">
        <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
          Смена пароля / email
        </Title>
        <Text className="mt-2">
          В showcase нет серверных учёток. Полный профиль и админ-права — в
          Streamlit на ai.conall.ru.
        </Text>
      </Card>
    </AppShell>
  );
}
