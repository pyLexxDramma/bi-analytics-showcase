"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { InfoBanner, SETTINGS_TABLE } from "@/components/settings/form-bits";
import {
  deleteSettingsRole,
  fetchReportCatalog,
  fetchSettingsRoles,
  fetchUiCatalog,
  patchSettingsRole,
  postSettingsRole,
  type ReportUiCatalogScreen,
  type RoleUiAclEntry,
  type SettingsRole,
} from "@/lib/api";

type UiAclMap = Record<string, RoleUiAclEntry>;

function cloneUiAcl(src: UiAclMap | undefined): UiAclMap {
  if (!src) return {};
  const out: UiAclMap = {};
  for (const [rid, entry] of Object.entries(src)) {
    out[rid] = {
      filters: entry.filters == null ? null : [...entry.filters],
      widgets: entry.widgets == null ? null : [...entry.widgets],
    };
  }
  return out;
}

function isKeyChecked(
  entry: RoleUiAclEntry | undefined,
  dim: "filters" | "widgets",
  key: string,
): boolean {
  const list = entry?.[dim];
  if (list == null) return true;
  return list.includes(key);
}

function toggleKeyInList(
  current: string[] | null,
  catalogIds: string[],
  key: string,
  checked: boolean,
): string[] | null {
  const base = current == null ? [...catalogIds] : [...current];
  const next = checked
    ? base.includes(key)
      ? base
      : [...base, key]
    : base.filter((k) => k !== key);
  if (next.length === catalogIds.length && catalogIds.every((id) => next.includes(id))) {
    return null;
  }
  return next;
}

export function AdminRolesPanel() {
  const [roles, setRoles] = useState<SettingsRole[]>([]);
  const [catalog, setCatalog] = useState<
    Array<{ id: string; title: string; path: string }>
  >([]);
  const [uiCatalog, setUiCatalog] = useState<ReportUiCatalogScreen[]>([]);
  const [selected, setSelected] = useState<string | null>(null);
  const [label, setLabel] = useState("");
  const [reports, setReports] = useState<string[]>([]);
  const [projectsText, setProjectsText] = useState("");
  const [uiAcl, setUiAcl] = useState<UiAclMap>({});
  const [expandedReport, setExpandedReport] = useState<string | null>(null);
  const [newCode, setNewCode] = useState("");
  const [newLabel, setNewLabel] = useState("");
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    const [rolesData, catalogData, uiCat] = await Promise.all([
      fetchSettingsRoles(),
      fetchReportCatalog(),
      fetchUiCatalog(),
    ]);
    setRoles(rolesData.items);
    setCatalog(catalogData.items);
    setUiCatalog(uiCat.items);
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
    setUiAcl(cloneUiAcl(current.ui_acl));
    setExpandedReport(null);
  }, [current]);

  const uiByNav = useMemo(() => {
    const m = new Map<string, ReportUiCatalogScreen>();
    for (const row of uiCatalog) m.set(row.nav_id, row);
    return m;
  }, [uiCatalog]);

  const lockedReports =
    current?.code === "admin" || current?.code === "superadmin";
  const lockedProjects = lockedReports;
  const lockedUiAcl = lockedReports;

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
    setReports((prev) => {
      if (prev.includes(id)) {
        setUiAcl((acl) => {
          const next = { ...acl };
          delete next[id];
          return next;
        });
        if (expandedReport === id) setExpandedReport(null);
        return prev.filter((x) => x !== id);
      }
      return [...prev, id];
    });
  };

  const toggleUiKey = (
    reportId: string,
    dim: "filters" | "widgets",
    key: string,
    checked: boolean,
  ) => {
    if (lockedUiAcl) return;
    const screen = uiByNav.get(reportId);
    if (!screen) return;
    const catalogIds = (dim === "filters" ? screen.filters : screen.widgets).map(
      (x) => x.id,
    );
    setUiAcl((prev) => {
      const entry = prev[reportId] || { filters: null, widgets: null };
      const nextList = toggleKeyInList(entry[dim], catalogIds, key, checked);
      return {
        ...prev,
        [reportId]: { ...entry, [dim]: nextList },
      };
    });
  };

  const buildUiAclPayload = (): UiAclMap => {
    const out: UiAclMap = {};
    for (const rid of reports) {
      const entry = uiAcl[rid];
      if (!entry) continue;
      if (entry.filters == null && entry.widgets == null) continue;
      out[rid] = {
        filters: entry.filters,
        widgets: entry.widgets,
      };
    }
    // Clear ACL for unchecked reports / unrestricted
    for (const rid of Object.keys(uiAcl)) {
      if (!reports.includes(rid)) {
        out[rid] = { filters: null, widgets: null };
      }
    }
    // Ensure every report with prior ACL that is now unrestricted is cleared
    for (const rid of reports) {
      const entry = uiAcl[rid];
      if (!entry) {
        if (current?.ui_acl?.[rid]) {
          out[rid] = { filters: null, widgets: null };
        }
        continue;
      }
      out[rid] = {
        filters: entry.filters,
        widgets: entry.widgets,
      };
    }
    return out;
  };

  return (
    <div className="space-y-6">
      <Card className="rounded-xl">
        <Title className="!text-base">Роли и доступ к дашбордам</Title>
        <InfoBanner>
          Системные роли создаются автоматически. Кастомную роль можно удалить,
          только если на неё не назначены пользователи. У admin/superadmin список
          отчётов не сокращается. Фильтры/виджеты: пустой allowlist = все видны.
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
            <div className="mt-2 space-y-2">
              {catalog.map((item) => {
                const checked = reports.includes(item.id);
                const screen = uiByNav.get(item.id);
                const open = expandedReport === item.id && checked;
                return (
                  <div
                    key={item.id}
                    className="rounded-md border border-gray-100 dark:border-dark-tremor-border"
                  >
                    <div className="flex items-start gap-2 px-2 py-1.5 text-sm">
                      <input
                        type="checkbox"
                        className="mt-1"
                        checked={checked}
                        disabled={lockedReports || busy}
                        onChange={() => toggleReport(item.id)}
                      />
                      <button
                        type="button"
                        className="min-w-0 flex-1 text-left"
                        disabled={!checked || !screen}
                        onClick={() =>
                          setExpandedReport((cur) =>
                            cur === item.id ? null : item.id,
                          )
                        }
                      >
                        <span className="font-medium">{item.title}</span>
                        <span className="block text-xs text-gray-500">
                          {item.id}
                          {screen ? " · фильтры/виджеты" : ""}
                        </span>
                      </button>
                    </div>
                    {open && screen ? (
                      <div className="border-t border-gray-100 px-3 py-2 dark:border-dark-tremor-border">
                        {lockedUiAcl ? (
                          <Text className="text-xs text-gray-500">
                            UI ACL для admin/superadmin не ограничивается.
                          </Text>
                        ) : (
                          <div className="grid gap-4 sm:grid-cols-2">
                            <div>
                              <Text className="mb-1 text-xs font-medium">
                                Фильтры (все = без ограничений)
                              </Text>
                              <div className="max-h-40 space-y-1 overflow-y-auto">
                                {screen.filters.map((f) => (
                                  <label
                                    key={f.id}
                                    className="flex items-center gap-2 text-xs"
                                  >
                                    <input
                                      type="checkbox"
                                      disabled={busy}
                                      checked={isKeyChecked(
                                        uiAcl[item.id],
                                        "filters",
                                        f.id,
                                      )}
                                      onChange={(e) =>
                                        toggleUiKey(
                                          item.id,
                                          "filters",
                                          f.id,
                                          e.target.checked,
                                        )
                                      }
                                    />
                                    {f.label}
                                  </label>
                                ))}
                              </div>
                            </div>
                            <div>
                              <Text className="mb-1 text-xs font-medium">
                                Виджеты / графики
                              </Text>
                              <div className="max-h-40 space-y-1 overflow-y-auto">
                                {screen.widgets.map((w) => (
                                  <label
                                    key={w.id}
                                    className="flex items-center gap-2 text-xs"
                                  >
                                    <input
                                      type="checkbox"
                                      disabled={busy}
                                      checked={isKeyChecked(
                                        uiAcl[item.id],
                                        "widgets",
                                        w.id,
                                      )}
                                      onChange={(e) =>
                                        toggleUiKey(
                                          item.id,
                                          "widgets",
                                          w.id,
                                          e.target.checked,
                                        )
                                      }
                                    />
                                    {w.label}
                                  </label>
                                ))}
                              </div>
                            </div>
                          </div>
                        )}
                      </div>
                    ) : null}
                  </div>
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
                    ui_acl: lockedUiAcl ? undefined : buildUiAclPayload(),
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
