"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { InfoBanner, SETTINGS_TABLE } from "@/components/settings/form-bits";
import {
  deleteSettingsRole,
  fetchReportCatalog,
  fetchSettingsRoles,
  patchSettingsRole,
  postSettingsRole,
  type SettingsRole,
} from "@/lib/api";

export function AdminRolesPanel() {
  const [roles, setRoles] = useState<SettingsRole[]>([]);
  const [catalog, setCatalog] = useState<
    Array<{ id: string; title: string; path: string }>
  >([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [reports, setReports] = useState<string[]>([]);
  const [projectsText, setProjectsText] = useState("");
  const [newCode, setNewCode] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [rolesData, catalogData] = await Promise.all([
      fetchSettingsRoles(),
      fetchReportCatalog(),
    ]);
    setRoles(rolesData.items);
    setCatalog(catalogData.items);
  }, []);

  useEffect(() => {
    void load().catch((e) =>
      setErr(e instanceof Error ? e.message : "Не удалось загрузить роли"),
    );
  }, [load]);

  const current = useMemo(
    () => roles.find((r) => r.code === selected) || null,
    [roles, selected],
  );

  useEffect(() => {
    if (!current) return;
    setLabel(current.label);
    setReports([...(current.reports || [])]);
    setProjectsText((current.projects || []).join("\n"));
  }, [current]);

  const lockedReports =
    current?.code === "admin" || current?.code === "superadmin";
  const lockedProjects = lockedReports;

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(e instanceof Error ? e.message : "Ошибка");
    } finally {
      setBusy(false);
    }
  };

  const toggleReport = (id: string) => {
    if (lockedReports) return;
    setReports((prev) =>
      prev.includes(id) ? prev.filter((x) => x !== id) : [...prev, id],
    );
  };

  return (
    <div className="space-y-6">
      <Card className="rounded-xl">
        <Title className="!text-base">Роли и доступ к дашбордам</Title>
        <InfoBanner>
          Системные роли создаются автоматически. Кастомную роль можно удалить,
          только если на неё не назначены пользователи. У admin/superadmin список
          отчётов не сокращается.
        </InfoBanner>
        {msg ? <Text className="mt-2 text-emerald-700">{msg}</Text> : null}
        {err ? <Text className="mt-2 text-red-600">{err}</Text> : null}

        <div className="mt-4 overflow-x-auto">
          <table className={SETTINGS_TABLE}>
            <thead>
              <tr>
                <th>Код</th>
                <th>Название</th>
                <th>Тип</th>
                <th>Отчётов</th>
              </tr>
            </thead>
            <tbody>
              {roles.map((r) => (
                <tr
                  key={r.code}
                  className={
                    selected === r.code
                      ? "bg-emerald-50 dark:bg-emerald-950/30"
                      : "cursor-pointer"
                  }
                  onClick={() => setSelected(r.code)}
                >
                  <td>{r.code}</td>
                  <td>{r.label}</td>
                  <td>{r.is_system ? "системная" : "кастомная"}</td>
                  <td>{(r.reports || []).length}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </Card>

      <Card className="rounded-xl">
        <Title className="!text-base">Новая роль</Title>
        <div className="mt-3 flex flex-wrap gap-3">
          <input
            className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            placeholder="код (rd_only)"
            value={newCode}
            onChange={(e) => setNewCode(e.target.value)}
          />
          <input
            className="min-w-[12rem] flex-1 rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            placeholder="Название"
            value={newLabel}
            onChange={(e) => setNewLabel(e.target.value)}
          />
          <button
            type="button"
            disabled={busy || !newCode.trim() || !newLabel.trim()}
            className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            onClick={() =>
              void run(async () => {
                const res = await postSettingsRole({
                  code: newCode.trim(),
                  label: newLabel.trim(),
                  reports: [],
                });
                setNewCode("");
                setNewLabel("");
                await load();
                setSelected(res.item.code);
                setMsg("Роль создана.");
              })
            }
          >
            Создать
          </button>
        </div>
      </Card>

      {current ? (
        <Card className="rounded-xl">
          <Title className="!text-base">
            Редактирование: {current.code}
          </Title>
          <label className="mt-3 block text-sm text-gray-600 dark:text-dark-tremor-content">
            Название
            <input
              className="mt-1 w-full max-w-lg rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={label}
              onChange={(e) => setLabel(e.target.value)}
            />
          </label>

          <div className="mt-4">
            <Text className="font-medium">Дашборды</Text>
            {lockedReports ? (
              <InfoBanner>Список отчётов для admin/superadmin фиксирован.</InfoBanner>
            ) : null}
            <div className="mt-2 grid max-h-80 gap-2 overflow-y-auto sm:grid-cols-2">
              {catalog.map((item) => {
                const checked = reports.includes(item.id);
                return (
                  <label
                    key={item.id}
                    className="flex cursor-pointer items-start gap-2 rounded-md border border-gray-100 px-2 py-1.5 text-sm dark:border-dark-tremor-border"
                  >
                    <input
                      type="checkbox"
                      className="mt-1"
                      checked={checked}
                      disabled={lockedReports || busy}
                      onChange={() => toggleReport(item.id)}
                    />
                    <span>
                      <span className="font-medium">{item.title}</span>
                      <span className="block text-xs text-gray-500">{item.id}</span>
                    </span>
                  </label>
                );
              })}
            </div>
          </div>

          <div className="mt-4">
            <Text className="font-medium">Проекты (пусто = все)</Text>
            {lockedProjects ? (
              <InfoBanner>У admin/superadmin проекты не ограничиваются.</InfoBanner>
            ) : (
              <InfoBanner>
                По одному названию проекта на строку. Ограничение роли действует
                на данные API и Ask AI catalog.
              </InfoBanner>
            )}
            <textarea
              className="mt-2 min-h-[6rem] w-full max-w-lg rounded-md border border-gray-200 px-3 py-2 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              disabled={lockedProjects || busy}
              value={projectsText}
              onChange={(e) => setProjectsText(e.target.value)}
              placeholder={"Проект А\nПроект Б"}
            />
          </div>

          <div className="mt-4 flex flex-wrap gap-3">
            <button
              type="button"
              disabled={busy}
              className="rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={() =>
                void run(async () => {
                  const projects = projectsText
                    .split(/\r?\n/)
                    .map((s) => s.trim())
                    .filter(Boolean);
                  await patchSettingsRole(current.code, {
                    label: label.trim(),
                    reports: lockedReports ? undefined : reports,
                    projects: lockedProjects ? undefined : projects,
                  });
                  await load();
                  setMsg("Сохранено.");
                })
              }
            >
              Сохранить
            </button>
            {!current.is_system ? (
              <button
                type="button"
                disabled={busy}
                className="rounded-md border border-red-300 px-4 py-2 text-sm font-medium text-red-700 disabled:opacity-60"
                onClick={() =>
                  void run(async () => {
                    if (!window.confirm(`Удалить роль «${current.code}»?`)) return;
                    await deleteSettingsRole(current.code);
                    setSelected(null);
                    await load();
                    setMsg("Роль удалена.");
                  })
                }
              >
                Удалить
              </button>
            ) : null}
          </div>
        </Card>
      ) : null}
    </div>
  );
}
