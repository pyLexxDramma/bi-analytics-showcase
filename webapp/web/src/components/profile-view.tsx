"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";
import { EmeraldTabs } from "@/components/settings/emerald-tabs";
import {
  InfoBanner,
  PasswordField,
} from "@/components/settings/form-bits";
import { UserMetrics } from "@/components/settings/user-metrics";
import { fetchAuthMe, postProfileEmail, postProfilePassword } from "@/lib/api";
import {
  getAuthSession,
  logout,
  saveAuthSession,
  type AuthUser,
} from "@/lib/auth";

export function ProfileView() {
  const router = useRouter();
  const [user, setUser] = useState<AuthUser | null>(null);
  const [tab, setTab] = useState("password");
  const [oldPassword, setOldPassword] = useState("");
  const [newPassword, setNewPassword] = useState("");
  const [confirmPassword, setConfirmPassword] = useState("");
  const [newEmail, setNewEmail] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    // migrate legacy demo → admin/superadmin, then refresh from users.db
    const local = getAuthSession();
    setUser(local);
    setNewEmail(local?.email || "");
    void fetchAuthMe()
      .then((r) => {
        setUser(r.user);
        saveAuthSession(r.user);
        setNewEmail(r.user.email || "");
      })
      .catch(() => {
        if (local) {
          setUser(local);
          setNewEmail(local.email || "");
        }
      });
  }, []);

  const onPassword = async () => {
    setMsg(null);
    setErr(null);
    if (!oldPassword) {
      setErr("Введите текущий пароль");
      return;
    }
    if (!newPassword) {
      setErr("Введите новый пароль");
      return;
    }
    if (newPassword.length < 6) {
      setErr("Новый пароль должен содержать минимум 6 символов");
      return;
    }
    if (newPassword !== confirmPassword) {
      setErr("Новый пароль и подтверждение не совпадают");
      return;
    }
    setBusy(true);
    try {
      const r = await postProfilePassword(oldPassword, newPassword);
      setMsg(r.message);
      setOldPassword("");
      setNewPassword("");
      setConfirmPassword("");
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const onEmail = async () => {
    setMsg(null);
    setErr(null);
    const emailValue = newEmail.trim() || null;
    if (emailValue && !emailValue.includes("@")) {
      setErr("Введите корректный email адрес");
      return;
    }
    setBusy(true);
    try {
      const r = await postProfileEmail(emailValue);
      setMsg(r.message);
      if (user) {
        const next = { ...user, email: r.email ?? emailValue };
        setUser(next);
        saveAuthSession(next);
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const currentEmail = user?.email || "Не указан";

  return (
    <AppShell title="Настройки профиля">
      <UserMetrics
        username={user?.username || "—"}
        roleLabel={user?.role_label || "—"}
      />

      <EmeraldTabs
        className="mb-6"
        active={tab}
        onChange={setTab}
        tabs={[
          { id: "password", label: "Изменить пароль" },
          { id: "email", label: "Изменить email" },
        ]}
      />

      {msg ? <Text className="mb-3 text-emerald-700">{msg}</Text> : null}
      {err ? <Text className="mb-3 text-rose-600">{err}</Text> : null}

      {tab === "password" ? (
        <Card className="rounded-xl">
          <Title className="!text-base">Изменение пароля</Title>
          <InfoBanner>
            Для изменения пароля необходимо ввести текущий пароль и новый пароль.
          </InfoBanner>
          <div className="max-w-md space-y-4">
            <PasswordField
              label="Текущий пароль"
              value={oldPassword}
              onChange={setOldPassword}
            />
            <PasswordField
              label="Новый пароль"
              value={newPassword}
              onChange={setNewPassword}
            />
            <PasswordField
              label="Подтвердите новый пароль"
              value={confirmPassword}
              onChange={setConfirmPassword}
            />
            <button
              type="button"
              disabled={busy}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={() => void onPassword()}
            >
              Изменить пароль
            </button>
          </div>
        </Card>
      ) : null}

      {tab === "email" ? (
        <Card className="rounded-xl">
          <Title className="!text-base">Изменение email</Title>
          <InfoBanner>
            Вы можете изменить или добавить email адрес для вашего профиля.
          </InfoBanner>
          <Text className="mb-4">
            <b>Текущий email:</b> {currentEmail}
          </Text>
          <label className="block max-w-md text-sm">
            Новый email
            <input
              type="email"
              className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={newEmail}
              onChange={(e) => setNewEmail(e.target.value)}
            />
          </label>
          <button
            type="button"
            disabled={busy}
            className="mt-4 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            onClick={() => void onEmail()}
          >
            Изменить email
          </button>
        </Card>
      ) : null}

      <Card className="mt-6 rounded-xl">
        <InfoBanner>
          Для возврата к отчетам используйте меню в боковой панели. Для выхода из
          системы нажмите «Выйти» внизу боковой панели.
        </InfoBanner>
        <div className="flex flex-wrap gap-3">
          <Link
            href="/developer-projects"
            className="rounded-md border border-emerald-300 bg-emerald-50 px-4 py-2 text-sm font-medium text-emerald-900"
          >
            К отчётам
          </Link>
          <button
            type="button"
            className="rounded-md bg-[#fdecea] px-4 py-2 text-sm font-medium text-[#c62828]"
            onClick={() => {
              logout();
              router.push("/login");
            }}
          >
            Выйти
          </button>
        </div>
      </Card>
    </AppShell>
  );
}
