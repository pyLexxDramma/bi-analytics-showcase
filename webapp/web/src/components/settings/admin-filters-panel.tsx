"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { EmeraldTabs } from "@/components/settings/emerald-tabs";
import { InfoBanner, SETTINGS_TABLE } from "@/components/settings/form-bits";
import {
  deleteSettingsFilter,
  fetchSettingsFilters,
  postSettingsCopyFilters,
  postSettingsFilter,
  type DefaultFilterRow,
} from "@/lib/api";
import {
  formatFilterValueDisplay,
  isGarbledReportName,
  reportDisplayName,
  sameReport,
} from "@/lib/settings-filters-display";

export function AdminFiltersPanel() {
  const [subTab, setSubTab] = useState("setup");
  const [meta, setMeta] = useState<{
    reports: string[];
    filter_types: Record<string, string>;
    roles: Record<string, string>;
  } | null>(null);
  const [items, setItems] = useState<DefaultFilterRow[]>([]);
  const [viewRole, setViewRole] = useState("Все");
  const [viewReport, setViewReport] = useState("Все");
  const [form, setForm] = useState({
    role: "analyst",
    report_name: "",
    filter_key: "",
    filter_type: "string",
    filter_value: "",
  });
  const [delForm, setDelForm] = useState({
    role: "analyst",
    report_name: "",
    filter_key: "",
  });
  const [copyForm, setCopyForm] = useState({
    source_role: "analyst",
    target_role: "manager",
    report_name: "Все",
  });
  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  const load = useCallback(async () => {
    try {
      const data = await fetchSettingsFilters({
        role: viewRole === "Все" ? undefined : viewRole,
        report_name: viewReport === "Все" ? undefined : viewReport,
      });
      setMeta({
        reports: data.reports,
        filter_types: data.filter_types,
        roles: data.roles,
      });
      setItems(data.items);
      if (!form.report_name && data.reports[0]) {
        setForm((f) => ({ ...f, report_name: data.reports[0] }));
        setDelForm((f) => ({ ...f, report_name: data.reports[0] }));
      }
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    }
  }, [viewRole, viewReport, form.report_name]);

  useEffect(() => {
    void load();
  }, [load]);

  useEffect(() => {
    const labels = [
      ...new Set(
        items
          .filter((i) => i.role === delForm.role)
          .map((i) => reportDisplayName(i.report_label || i.report_name)),
      ),
    ].filter(Boolean);
    if (!labels.length) return;
    setDelForm((f) => {
      if (labels.includes(f.report_name)) return f;
      return { ...f, report_name: labels[0], filter_key: "" };
    });
  }, [delForm.role, items]);

  const roleOptions = meta ? Object.entries(meta.roles) : [];
  const reports = meta?.reports || [];

  const saveFilter = async () => {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      await postSettingsFilter(form);
      setMsg("Фильтр успешно сохранен!");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const removeFilter = async () => {
    if (!delForm.filter_key) return;
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      await deleteSettingsFilter(delForm);
      setMsg("Фильтр успешно удален!");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const copyFilters = async () => {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      await postSettingsCopyFilters({
        source_role: copyForm.source_role,
        target_role: copyForm.target_role,
        report_name: copyForm.report_name === "Все" ? null : copyForm.report_name,
      });
      setMsg("Фильтры успешно скопированы!");
      await load();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  const extraTitles = [
    ...new Set(
      items
        .map((i) => reportDisplayName(i.report_label || i.report_name))
        .filter((t) => Boolean(t) && !isGarbledReportName(t)),
    ),
  ];

  const rowReportLabel = (row: DefaultFilterRow) =>
    reportDisplayName(row.report_label || row.report_name, extraTitles);

  const keysForDel = [
    ...new Set(
      items
        .filter(
          (i) =>
            i.role === delForm.role &&
            sameReport(
              i.report_label || i.report_name,
              delForm.report_name,
              extraTitles,
            ),
        )
        .map((i) => i.filter_key),
    ),
  ];

  const delReports = [
    ...new Set(
      items.filter((i) => i.role === delForm.role).map(rowReportLabel),
    ),
  ].filter(Boolean);

  const grouped = items.reduce<Record<string, DefaultFilterRow[]>>((acc, row) => {
    const key = `${row.role_label} — ${rowReportLabel(row)}`;
    (acc[key] ||= []).push(row);
    return acc;
  }, {});

  return (
    <div>
      <InfoBanner>
        Здесь вы можете настроить фильтры по умолчанию для всех ролей и отчетов.
        Фильтры определяют значения по умолчанию для различных параметров отчетов.
      </InfoBanner>

      <EmeraldTabs
        className="mb-6"
        active={subTab}
        onChange={setSubTab}
        tabs={[
          { id: "setup", label: "Настроить фильтры" },
          { id: "view", label: "Просмотр всех фильтров" },
          { id: "copy", label: "Копирование фильтров" },
        ]}
      />

      {msg ? <Text className="mb-3 text-emerald-700">{msg}</Text> : null}
      {err ? <Text className="mb-3 text-rose-600">{err}</Text> : null}

      {subTab === "setup" ? (
        <div className="space-y-6">
          <Card className="rounded-xl">
            <Title className="!text-base">Настройка фильтров</Title>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <label className="text-sm">
                Роль *
                <select
                  className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={form.role}
                  onChange={(e) => setForm({ ...form, role: e.target.value })}
                >
                  {roleOptions.map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm">
                Отчет *
                <select
                  className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={form.report_name}
                  onChange={(e) =>
                    setForm({ ...form, report_name: e.target.value })
                  }
                >
                  {!reports.length ? (
                    <option value="">Нет списка отчётов — обновите страницу</option>
                  ) : null}
                  {reports.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm">
                Ключ фильтра *
                <input
                  className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={form.filter_key}
                  onChange={(e) =>
                    setForm({ ...form, filter_key: e.target.value })
                  }
                  placeholder="например: project, year, contractor"
                />
                <span className="mt-1 block text-xs text-tremor-content dark:text-dark-tremor-content">
                  Не генерируется сам — укажите ключ фильтра дашборда (как в
                  Streamlit: project, year, org и т.п.).
                </span>
              </label>
              <label className="text-sm">
                Тип фильтра *
                <select
                  className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={form.filter_type}
                  onChange={(e) =>
                    setForm({ ...form, filter_type: e.target.value })
                  }
                >
                  {Object.entries(meta?.filter_types || {}).map(([k, v]) => (
                    <option key={k} value={k}>
                      {v}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <label className="mt-4 block text-sm">
              Значение фильтра
              <input
                className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={form.filter_value}
                onChange={(e) =>
                  setForm({ ...form, filter_value: e.target.value })
                }
              />
            </label>
            <button
              type="button"
              disabled={busy}
              className="mt-4 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={() => void saveFilter()}
            >
              Сохранить фильтр
            </button>
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-base">Текущие фильтры</Title>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <label className="text-sm">
                Роль для просмотра
                <select
                  className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={viewRole}
                  onChange={(e) => setViewRole(e.target.value)}
                >
                  <option value="Все">Все</option>
                  {roleOptions.map(([code, label]) => (
                    <option key={code} value={code}>
                      {label}
                    </option>
                  ))}
                </select>
              </label>
              <label className="text-sm">
                Отчет для просмотра
                <select
                  className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={viewReport}
                  onChange={(e) => setViewReport(e.target.value)}
                >
                  <option value="Все">Все</option>
                  {reports.map((r) => (
                    <option key={r} value={r}>
                      {r}
                    </option>
                  ))}
                </select>
              </label>
            </div>
            <div className="mt-4 overflow-x-auto">
              {items.length ? (
                <table className={SETTINGS_TABLE}>
                  <thead>
                    <tr>
                      {[
                        "Роль",
                        "Отчет",
                        "Ключ",
                        "Значение",
                        "Тип",
                        "Обновлено",
                        "Обновил",
                      ].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {items.map((row) => (
                      <tr key={`${row.role}-${row.report_name}-${row.filter_key}`}>
                        <td>{row.role_label}</td>
                        <td>{rowReportLabel(row)}</td>
                        <td>{row.filter_key}</td>
                        <td>{formatFilterValueDisplay(row.filter_value)}</td>
                        <td>{row.filter_type_label}</td>
                        <td>{row.updated_at || "-"}</td>
                        <td>{row.updated_by || "-"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Text>Фильтры не найдены</Text>
              )}
            </div>

            <Title className="mt-6 !text-base">Удаление фильтра</Title>
            <div className="mt-3 grid gap-4 md:grid-cols-3">
              <select
                className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={delForm.role}
                onChange={(e) =>
                  setDelForm({ ...delForm, role: e.target.value, filter_key: "" })
                }
              >
                {roleOptions.map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
              <select
                className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={delForm.report_name}
                onChange={(e) =>
                  setDelForm({ ...delForm, report_name: e.target.value, filter_key: "" })
                }
              >
                {(delReports.length ? delReports : reports).map((r) => (
                  <option key={r} value={r}>
                    {r}
                  </option>
                ))}
              </select>
              <select
                className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={delForm.filter_key}
                onChange={(e) =>
                  setDelForm({ ...delForm, filter_key: e.target.value })
                }
              >
                <option value="">— ключ —</option>
                {keysForDel.map((k) => (
                  <option key={k} value={k}>
                    {k}
                  </option>
                ))}
              </select>
            </div>
            <button
              type="button"
              disabled={busy || !delForm.filter_key}
              className="mt-3 rounded-md bg-rose-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={() => void removeFilter()}
            >
              Удалить фильтр
            </button>
          </Card>
        </div>
      ) : null}

      {subTab === "view" ? (
        <Card className="rounded-xl">
          <Title className="!text-base">Все фильтры по умолчанию</Title>
          {Object.keys(grouped).length === 0 ? (
            <Text className="mt-3">Фильтры не настроены</Text>
          ) : (
            <div className="mt-4 space-y-4">
              {Object.entries(grouped).map(([title, rows]) => (
                <details key={title} className="rounded-lg border border-gray-200 p-3 dark:border-dark-tremor-border">
                  <summary className="cursor-pointer font-medium">
                    {title} ({rows.length} фильтров)
                  </summary>
                  <div className="mt-3 overflow-x-auto">
                    <table className={SETTINGS_TABLE}>
                      <thead>
                        <tr>
                          {["Ключ", "Значение", "Тип", "Обновлено", "Обновил"].map(
                            (h) => (
                              <th key={h}>{h}</th>
                            ),
                          )}
                        </tr>
                      </thead>
                      <tbody>
                        {rows.map((row) => (
                          <tr key={row.filter_key}>
                            <td>{row.filter_key}</td>
                            <td>{formatFilterValueDisplay(row.filter_value)}</td>
                            <td>{row.filter_type_label}</td>
                            <td>{row.updated_at || "-"}</td>
                            <td>{row.updated_by || "-"}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                </details>
              ))}
            </div>
          )}
        </Card>
      ) : null}

      {subTab === "copy" ? (
        <Card className="rounded-xl">
          <Title className="!text-base">Копирование фильтров</Title>
          <InfoBanner>
            Скопируйте все фильтры из одной роли в другую. Можно для конкретного
            отчета или всех.
          </InfoBanner>
          <div className="grid gap-4 md:grid-cols-2">
            <label className="text-sm">
              Исходная роль
              <select
                className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={copyForm.source_role}
                onChange={(e) =>
                  setCopyForm({ ...copyForm, source_role: e.target.value })
                }
              >
                {roleOptions.map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
            <label className="text-sm">
              Целевая роль
              <select
                className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={copyForm.target_role}
                onChange={(e) =>
                  setCopyForm({ ...copyForm, target_role: e.target.value })
                }
              >
                {roleOptions.map(([code, label]) => (
                  <option key={code} value={code}>
                    {label}
                  </option>
                ))}
              </select>
            </label>
          </div>
          <label className="mt-4 block text-sm">
            Отчет (оставьте «Все» для копирования всех)
            <select
              className="mt-1 w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={copyForm.report_name}
              onChange={(e) =>
                setCopyForm({ ...copyForm, report_name: e.target.value })
              }
            >
              <option value="Все">Все</option>
              {reports.map((r) => (
                <option key={r} value={r}>
                  {r}
                </option>
              ))}
            </select>
          </label>
          <button
            type="button"
            disabled={busy}
            className="mt-4 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
            onClick={() => void copyFilters()}
          >
            Копировать фильтры
          </button>
        </Card>
      ) : null}
    </div>
  );
}
