"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Grid, Metric, Text, Title } from "@tremor/react";
import { DownloadTableButton } from "@/components/download-table-button";
import { EmeraldTabs } from "@/components/settings/emerald-tabs";
import { InfoBanner, SETTINGS_TABLE } from "@/components/settings/form-bits";
import {
  deleteSettingsUser,
  fetchReportConfig,
  fetchSettingsLogs,
  fetchSettingsRoles,
  fetchSettingsStats,
  fetchSettingsUsers,
  postSettingsChangeRole,
  postSettingsUser,
  putReportConfig,
  type SettingsLogRow,
  type SettingsUser,
} from "@/lib/api";
import { getAuthSession } from "@/lib/auth";
import type { ExportTable } from "@/lib/table-export";

export function AdminSystemPanel() {
  const [subTab, setSubTab] = useState("users");
  const session = getAuthSession();
  const isSuperadmin = session?.role === "superadmin";

  const [users, setUsers] = useState<SettingsUser[]>([]);
  const [stats, setStats] = useState<Awaited<ReturnType<typeof fetchSettingsStats>> | null>(null);
  const [logs, setLogs] = useState<SettingsLogRow[]>([]);
  const [logFilters, setLogFilters] = useState<{ usernames: string[]; actions: string[] }>({
    usernames: [],
    actions: [],
  });
  const [roles, setRoles] = useState<Array<{ code: string; label: string }>>([]);
  const [config, setConfig] = useState<Record<string, string>>({});
  const [configDesc, setConfigDesc] = useState<Record<string, string>>({});

  const [logQuery, setLogQuery] = useState({
    username: "Все",
    action: "Все",
    limit: 100,
    date_from: "",
    date_to: "",
  });

  const [newUser, setNewUser] = useState({
    username: "",
    password: "",
    role: "analyst",
    email: "",
  });
  const [roleChange, setRoleChange] = useState({ user_id: 0, new_role: "analyst" });
  const [deleteId, setDeleteId] = useState<number | "">("");
  const [deleteConfirm, setDeleteConfirm] = useState(false);

  const [msg, setMsg] = useState<string | null>(null);
  const [err, setErr] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);

  useEffect(() => {
    void fetchSettingsRoles()
      .then((data) => setRoles(data.items))
      .catch(() => {});
  }, []);

  const loadUsers = useCallback(async () => {
    const data = await fetchSettingsUsers();
    setUsers(data.items);
    if (data.items.length && !roleChange.user_id) {
      setRoleChange({ user_id: data.items[0].id, new_role: data.items[0].role });
    }
  }, [roleChange.user_id]);

  const loadStats = useCallback(async () => {
    setStats(await fetchSettingsStats());
  }, []);

  const loadLogs = useCallback(async () => {
    const data = await fetchSettingsLogs({
      username: logQuery.username,
      action: logQuery.action,
      limit: logQuery.limit,
      date_from: logQuery.date_from || undefined,
      date_to: logQuery.date_to || undefined,
    });
    setLogs(data.items);
    setLogFilters(data.filters);
  }, [logQuery]);

  const loadRoles = useCallback(async () => {
    const data = await fetchSettingsRoles();
    setRoles(data.items);
  }, []);

  const loadConfig = useCallback(async () => {
    const data = await fetchReportConfig();
    setConfig(data.values);
    setConfigDesc(data.descriptions);
  }, []);

  useEffect(() => {
    void (async () => {
      try {
        if (subTab === "users") await loadUsers();
        if (subTab === "stats") await loadStats();
        if (subTab === "logs") await loadLogs();
        if (subTab === "roles") await loadRoles();
        if (subTab === "config") await loadConfig();
      } catch (e) {
        setErr(e instanceof Error ? e.message : String(e));
      }
    })();
  }, [subTab, loadUsers, loadStats, loadLogs, loadRoles, loadConfig]);

  const activeUsers = users.filter((u) => u.is_active);
  const deletable = users.filter(
    (u) => u.username !== session?.username && u.role !== "superadmin",
  );

  const logsExport = useMemo<ExportTable | null>(() => {
    if (!logs.length) return null;
    return {
      header: [
        [
          "ID",
          "Пользователь",
          "Действие",
          "Детали",
          "IP адрес",
          "Дата и время",
        ],
      ],
      rows: logs.map((l) => [
        l.id,
        l.username,
        l.action,
        l.details,
        l.ip_address,
        l.created_at_fmt,
      ]),
    };
  }, [logs]);

  const run = async (fn: () => Promise<void>) => {
    setBusy(true);
    setMsg(null);
    setErr(null);
    try {
      await fn();
    } catch (e) {
      setErr(e instanceof Error ? e.message : String(e));
    } finally {
      setBusy(false);
    }
  };

  return (
    <div>
      <EmeraldTabs
        className="mb-6"
        active={subTab}
        onChange={setSubTab}
        tabs={[
          { id: "users", label: "Пользователи" },
          { id: "stats", label: "Статистика" },
          { id: "logs", label: "Логи" },
          { id: "roles", label: "Права доступа" },
          { id: "config", label: "Конфигурация настроек отчетов" },
        ]}
      />

      {msg ? <Text className="mb-3 text-emerald-700">{msg}</Text> : null}
      {err ? <Text className="mb-3 text-rose-600">{err}</Text> : null}

      {subTab === "users" ? (
        <div className="space-y-6">
          <Card className="rounded-xl">
            <Title className="!text-base">Список пользователей</Title>
            <div className="mt-4 overflow-x-auto">
              {users.length ? (
                <table className={SETTINGS_TABLE}>
                  <thead>
                    <tr>
                      {[
                        "ID",
                        "Имя",
                        "Роль",
                        "Email",
                        "Создан",
                        "Последний вход",
                        "Активен",
                      ].map((h) => (
                        <th key={h}>{h}</th>
                      ))}
                    </tr>
                  </thead>
                  <tbody>
                    {users.map((u) => (
                      <tr key={u.id}>
                        <td>{u.id}</td>
                        <td>{u.username}</td>
                        <td>{u.role_label}</td>
                        <td>{u.email || "-"}</td>
                        <td>{u.created_at_fmt}</td>
                        <td>{u.last_login_fmt}</td>
                        <td>{u.is_active ? "✅" : "❌"}</td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              ) : (
                <Text>Пользователи не найдены</Text>
              )}
            </div>
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-base">Добавить нового пользователя</Title>
            <div className="mt-4 grid gap-4 md:grid-cols-2">
              <input
                placeholder="Имя пользователя *"
                className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={newUser.username}
                onChange={(e) => setNewUser({ ...newUser, username: e.target.value })}
              />
              <input
                placeholder="Email"
                className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={newUser.email}
                onChange={(e) => setNewUser({ ...newUser, email: e.target.value })}
              />
              <input
                type="password"
                placeholder="Пароль *"
                className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={newUser.password}
                onChange={(e) => setNewUser({ ...newUser, password: e.target.value })}
              />
              <select
                className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                value={newUser.role}
                onChange={(e) => setNewUser({ ...newUser, role: e.target.value })}
              >
                {roles.length
                  ? roles.map((r) => (
                      <option key={r.code} value={r.code}>
                        {r.label}
                      </option>
                    ))
                  : null}
              </select>
            </div>
            <button
              type="button"
              disabled={busy}
              className="mt-4 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={() =>
                void run(async () => {
                  await postSettingsUser(newUser);
                  setMsg(`Пользователь ${newUser.username} успешно создан!`);
                  setNewUser({ username: "", password: "", role: "analyst", email: "" });
                  await loadUsers();
                })
              }
            >
              Добавить пользователя
            </button>
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-base">Изменить роль пользователя</Title>
            {activeUsers.length ? (
              <>
                <div className="mt-4 grid gap-4 md:grid-cols-2">
                  <select
                    className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                    value={roleChange.user_id}
                    onChange={(e) => {
                      const id = Number(e.target.value);
                      const u = activeUsers.find((x) => x.id === id);
                      setRoleChange({
                        user_id: id,
                        new_role: u?.role || "analyst",
                      });
                    }}
                  >
                    {activeUsers.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.username} ({u.role_label})
                      </option>
                    ))}
                  </select>
                  <select
                    className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                    value={roleChange.new_role}
                    onChange={(e) =>
                      setRoleChange({ ...roleChange, new_role: e.target.value })
                    }
                  >
                    {roles.map((r) => (
                      <option key={r.code} value={r.code}>
                        {r.label}
                      </option>
                    ))}
                  </select>
                </div>
                <button
                  type="button"
                  disabled={busy}
                  className="mt-4 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                  onClick={() =>
                    void run(async () => {
                      await postSettingsChangeRole(roleChange);
                      setMsg("Роль успешно изменена!");
                      await loadUsers();
                    })
                  }
                >
                  Изменить роль
                </button>
              </>
            ) : (
              <Text className="mt-3">Нет активных пользователей</Text>
            )}
          </Card>

          {isSuperadmin ? (
            <Card className="rounded-xl">
              <Title className="!text-base">Удалить пользователя</Title>
              {deletable.length ? (
                <>
                  <select
                    className="mt-4 w-full max-w-md rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                    value={deleteId}
                    onChange={(e) =>
                      setDeleteId(e.target.value ? Number(e.target.value) : "")
                    }
                  >
                    <option value="">Выберите пользователя</option>
                    {deletable.map((u) => (
                      <option key={u.id} value={u.id}>
                        {u.username} ({u.role_label})
                      </option>
                    ))}
                  </select>
                  <label className="mt-3 flex items-center gap-2 text-sm">
                    <input
                      type="checkbox"
                      checked={deleteConfirm}
                      onChange={(e) => setDeleteConfirm(e.target.checked)}
                    />
                    Подтверждаю удаление пользователя и всех его данных
                  </label>
                  <button
                    type="button"
                    disabled={busy || !deleteId || !deleteConfirm}
                    className="mt-3 rounded-md bg-rose-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                    onClick={() =>
                      void run(async () => {
                        const r = await deleteSettingsUser(Number(deleteId));
                        setMsg(r.message || "Пользователь удалён");
                        setDeleteId("");
                        setDeleteConfirm(false);
                        await loadUsers();
                      })
                    }
                  >
                    Удалить пользователя
                  </button>
                </>
              ) : (
                <Text className="mt-3">Нет пользователей, доступных для удаления</Text>
              )}
            </Card>
          ) : null}
        </div>
      ) : null}

      {subTab === "stats" && stats ? (
        <div>
          <Grid numItemsSm={2} numItemsLg={4} className="mb-6 gap-6">
            <Card className="rounded-xl">
              <Text>Всего пользователей</Text>
              <Metric className="mt-2">{stats.total_users}</Metric>
            </Card>
            <Card className="rounded-xl">
              <Text>Активных пользователей</Text>
              <Metric className="mt-2">{stats.active_users}</Metric>
            </Card>
            <Card className="rounded-xl">
              <Text>Пользователей с входом</Text>
              <Metric className="mt-2">{stats.users_with_login}</Metric>
            </Card>
            <Card className="rounded-xl">
              <Text>Всего действий в логах</Text>
              <Metric className="mt-2">{stats.total_logs}</Metric>
            </Card>
          </Grid>
          <Card className="rounded-xl">
            <Title className="!text-base">Распределение по ролям</Title>
            <div className="mt-4 overflow-x-auto">
              <table className={SETTINGS_TABLE}>
                <thead>
                  <tr>
                    <th>Роль</th>
                    <th>Количество</th>
                  </tr>
                </thead>
                <tbody>
                  {stats.roles.map((r) => (
                    <tr key={r.role}>
                      <td>{r.role_label}</td>
                      <td>{r.count}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          </Card>
        </div>
      ) : null}

      {subTab === "logs" ? (
        <Card className="rounded-xl">
          <Title className="!text-base">Логи действий пользователей</Title>
          <div className="mt-4 grid gap-3 md:grid-cols-3">
            <select
              className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={logQuery.username}
              onChange={(e) => setLogQuery({ ...logQuery, username: e.target.value })}
            >
              <option value="Все">Все</option>
              {logFilters.usernames.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </select>
            <select
              className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={logQuery.action}
              onChange={(e) => setLogQuery({ ...logQuery, action: e.target.value })}
            >
              <option value="Все">Все</option>
              {logFilters.actions.map((a) => (
                <option key={a} value={a}>
                  {a}
                </option>
              ))}
            </select>
            <input
              type="number"
              min={10}
              max={1000}
              step={10}
              className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={logQuery.limit}
              onChange={(e) =>
                setLogQuery({ ...logQuery, limit: Number(e.target.value) })
              }
            />
            <input
              type="date"
              className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={logQuery.date_from}
              onChange={(e) => setLogQuery({ ...logQuery, date_from: e.target.value })}
            />
            <input
              type="date"
              className="rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={logQuery.date_to}
              onChange={(e) => setLogQuery({ ...logQuery, date_to: e.target.value })}
            />
            <button
              type="button"
              className="rounded-md border border-gray-200 px-4 py-2 text-sm dark:border-dark-tremor-border"
              onClick={() => void loadLogs()}
            >
              Применить фильтры
            </button>
          </div>
          <div className="mt-4 flex items-center gap-3">
            <DownloadTableButton
              getTable={() => logsExport}
              fileStem={`logs_${new Date().toISOString().slice(0, 10)}`}
              disabled={!logs.length}
            />
          </div>
          <div className="mt-4 overflow-x-auto">
            {logs.length ? (
              <table className={SETTINGS_TABLE}>
                <thead>
                  <tr>
                    {[
                      "ID",
                      "Пользователь",
                      "Действие",
                      "Детали",
                      "IP адрес",
                      "Дата и время",
                    ].map((h) => (
                      <th key={h}>{h}</th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {logs.map((l) => (
                    <tr key={l.id}>
                      <td>{l.id}</td>
                      <td>{l.username}</td>
                      <td>{l.action}</td>
                      <td>{l.details}</td>
                      <td>{l.ip_address}</td>
                      <td>{l.created_at_fmt}</td>
                    </tr>
                  ))}
                </tbody>
              </table>
            ) : (
              <Text>Логи не найдены</Text>
            )}
          </div>
        </Card>
      ) : null}

      {subTab === "roles" ? (
        <Card className="rounded-xl">
          <Title className="!text-base">Права доступа</Title>
          <InfoBanner>
            Разрезка прав по отдельным проектам отключена. Доступ определяется
            только ролью пользователя.
          </InfoBanner>
          <div className="overflow-x-auto">
            <table className={SETTINGS_TABLE}>
              <thead>
                <tr>
                  <th>Код роли</th>
                  <th>Роль</th>
                </tr>
              </thead>
              <tbody>
                {roles.map((r) => (
                  <tr key={r.code}>
                    <td>{r.code}</td>
                    <td>{r.label}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>
      ) : null}

      {subTab === "config" ? (
        <div className="space-y-6">
          <Card className="rounded-xl">
            <Title className="!text-base">Email администратора</Title>
            <input
              className="mt-3 w-full max-w-lg rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              placeholder="например, admin@company.ru"
              value={config.admin_notification_email || ""}
              onChange={(e) =>
                setConfig({ ...config, admin_notification_email: e.target.value })
              }
            />
            <button
              type="button"
              disabled={busy}
              className="mt-3 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={() =>
                void run(async () => {
                  await putReportConfig({
                    admin_notification_email: config.admin_notification_email,
                  });
                  setMsg("Сохранено.");
                })
              }
            >
              Сохранить email администратора
            </button>
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-base">
              Отчёт «Отклонение от базового плана» — задача для KPI
            </Title>
            <Text className="mt-1 text-xs text-gray-500">
              {configDesc.baseline_plan_task_for_metrics}
            </Text>
            <input
              className="mt-3 w-full max-w-lg rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={config.baseline_plan_task_for_metrics || "ЗОС"}
              onChange={(e) =>
                setConfig({
                  ...config,
                  baseline_plan_task_for_metrics: e.target.value,
                })
              }
            />
            <button
              type="button"
              disabled={busy}
              className="mt-3 rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
              onClick={() =>
                void run(async () => {
                  await putReportConfig({
                    baseline_plan_task_for_metrics:
                      config.baseline_plan_task_for_metrics || "ЗОС",
                  });
                  setMsg("Сохранено.");
                })
              }
            >
              Сохранить задачу для метрик
            </button>
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-base">Контрольные точки — вехи (JSON)</Title>
            <Text className="mt-1 text-xs text-gray-500">
              {configDesc.control_points_milestones_json}
            </Text>
            <textarea
              rows={6}
              className="mt-3 w-full rounded-md border border-gray-200 px-3 py-2 font-mono text-xs dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={config.control_points_milestones_json || ""}
              onChange={(e) =>
                setConfig({
                  ...config,
                  control_points_milestones_json: e.target.value,
                })
              }
            />
            <button
              type="button"
              disabled={busy}
              className="mt-3 rounded-md border border-gray-200 px-4 py-2 text-sm dark:border-dark-tremor-border"
              onClick={() =>
                void run(async () => {
                  await putReportConfig({
                    control_points_milestones_json:
                      config.control_points_milestones_json,
                  });
                  setMsg("JSON сохранён.");
                })
              }
            >
              Сохранить JSON вех
            </button>
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-base">Девелоперские проекты — матрица (JSON)</Title>
            <Text className="mt-1 text-xs text-gray-500">
              {configDesc.developer_projects_matrix_json}
            </Text>
            <textarea
              rows={6}
              className="mt-3 w-full rounded-md border border-gray-200 px-3 py-2 font-mono text-xs dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              value={config.developer_projects_matrix_json || ""}
              onChange={(e) =>
                setConfig({
                  ...config,
                  developer_projects_matrix_json: e.target.value,
                })
              }
            />
            <button
              type="button"
              disabled={busy}
              className="mt-3 rounded-md border border-gray-200 px-4 py-2 text-sm dark:border-dark-tremor-border"
              onClick={() =>
                void run(async () => {
                  await putReportConfig({
                    developer_projects_matrix_json:
                      config.developer_projects_matrix_json,
                  });
                  setMsg("JSON сохранён.");
                })
              }
            >
              Сохранить JSON матрицы
            </button>
          </Card>
        </div>
      ) : null}
    </div>
  );
}
