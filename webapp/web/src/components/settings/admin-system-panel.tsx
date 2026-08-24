"use client";

import { useCallback, useEffect, useMemo, useState } from "react";
import { Card, Grid, Metric, Text, Title } from "@tremor/react";
import { DownloadTableButton } from "@/components/download-table-button";
import { EmeraldTabs } from "@/components/settings/emerald-tabs";
import { SETTINGS_TABLE } from "@/components/settings/form-bits";
import {
  deleteSettingsUser,
  fetchMspTaskOptions,
  fetchReportConfig,
  fetchSettingsLogs,
  fetchSettingsRoles,
  fetchSettingsStats,
  fetchSettingsUsers,
  fetchUserProjects,
  postSettingsChangeRole,
  postSettingsUser,
  putReportConfig,
  putUserProjects,
  type MspTaskOptions,
  type SettingsLogRow,
  type SettingsRole,
  type SettingsUser,
} from "@/lib/api";
import { getAuthSession } from "@/lib/auth";
import type { ExportTable } from "@/lib/table-export";
import { AdminRolesPanel } from "@/components/settings/admin-roles-panel";
import { MobileSearchField } from "@/components/mobile-ux";

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
  const [roles, setRoles] = useState<SettingsRole[]>([]);
  const [config, setConfig] = useState<Record<string, string>>({});
  const [configDesc, setConfigDesc] = useState<Record<string, string>>({});
  const [configDefaults, setConfigDefaults] = useState<Record<string, string>>({});
  const [taskOptions, setTaskOptions] = useState<MspTaskOptions | null>(null);
  const [usersQuery, setUsersQuery] = useState("");
  const [logsQuery, setLogsQuery] = useState("");

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
  const [userProjectsText, setUserProjectsText] = useState("");
  const [userProjectsUnrestricted, setUserProjectsUnrestricted] = useState(true);
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

  const loadUserProjects = useCallback(async (userId: number) => {
    if (!userId) return;
    try {
      const data = await fetchUserProjects(userId);
      setUserProjectsUnrestricted(data.unrestricted);
      setUserProjectsText((data.projects || []).join("\n"));
    } catch {
      setUserProjectsText("");
      setUserProjectsUnrestricted(true);
    }
  }, []);

  useEffect(() => {
    if (roleChange.user_id) void loadUserProjects(roleChange.user_id);
  }, [roleChange.user_id, loadUserProjects]);

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
    // Параллельно и одним рендером: иначе поле задачи сначала рисуется как
    // текстовый инпут и только через пару секунд превращается в select.
    const [data, options] = await Promise.all([
      fetchReportConfig(),
      fetchMspTaskOptions().catch((e: unknown) => ({
        options: [],
        level: null,
        task_column: null,
        current: "",
        hint: e instanceof Error ? e.message : String(e),
      })),
    ]);
    const defaults = data.defaults || {};
    setConfigDefaults(defaults);
    setConfig({
      ...data.values,
      control_points_milestones_json:
        data.values.control_points_milestones_json ||
        defaults.control_points_milestones_json ||
        "",
      developer_projects_matrix_json:
        data.values.developer_projects_matrix_json ||
        defaults.developer_projects_matrix_json ||
        "",
    });
    setConfigDesc(data.descriptions);
    setTaskOptions(options);
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
  const usersFiltered = useMemo(() => {
    const q = usersQuery.trim().toLowerCase();
    if (!q) return users;
    return users.filter((u) =>
      `${u.username} ${u.role_label} ${u.email ?? ""}`.toLowerCase().includes(q),
    );
  }, [users, usersQuery]);
  const logsFiltered = useMemo(() => {
    const q = logsQuery.trim().toLowerCase();
    if (!q) return logs;
    return logs.filter((l) =>
      `${l.username} ${l.action} ${l.details} ${l.ip_address}`.toLowerCase().includes(q),
    );
  }, [logs, logsQuery]);

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

  const taskValue = (config.baseline_plan_task_for_metrics || "ЗОС").trim();

  // Сохранённая задача может отсутствовать в текущей выгрузке MSP (сменился
  // снимок, переименовали задачу) — держим её в списке, чтобы select не сбросил
  // настройку на первый попавшийся вариант при простом открытии вкладки.
  const taskSelectItems = useMemo(() => {
    const items = (taskOptions?.options || []).map((o) => ({
      name: o.name,
      level: o.level as number | null,
    }));
    if (taskValue && !items.some((i) => i.name === taskValue)) {
      items.unshift({ name: taskValue, level: null });
    }
    return items;
  }, [taskOptions, taskValue]);

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
            <div className="mt-3 lg:hidden">
              <MobileSearchField
                value={usersQuery}
                onChange={setUsersQuery}
                placeholder="Поиск пользователя"
              />
            </div>
            <div className="mt-4 space-y-2 lg:hidden">
              {usersFiltered.length ? (
                usersFiltered.map((u) => (
                  <article
                    key={u.id}
                    className="rounded-xl border border-tremor-border bg-tremor-background p-3 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  >
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong">
                          {u.username}
                        </div>
                        <div className="text-xs text-tremor-content dark:text-dark-tremor-content">
                          {u.role_label} · id {u.id}
                        </div>
                      </div>
                      <span className="text-sm">{u.is_active ? "✅" : "❌"}</span>
                    </div>
                    <dl className="mt-2 grid grid-cols-2 gap-2 text-xs">
                      <div>
                        <dt className="opacity-70">Email</dt>
                        <dd>{u.email || "—"}</dd>
                      </div>
                      <div>
                        <dt className="opacity-70">Создан</dt>
                        <dd>{u.created_at_fmt}</dd>
                      </div>
                      <div className="col-span-2">
                        <dt className="opacity-70">Последний вход</dt>
                        <dd>{u.last_login_fmt}</dd>
                      </div>
                    </dl>
                  </article>
                ))
              ) : (
                <Text>Пользователи не найдены</Text>
              )}
            </div>
            <div className="mt-4 hidden overflow-x-auto lg:block">
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

          <Card className="rounded-xl">
            <Title className="!text-base">Проекты пользователя</Title>
            <Text className="mt-2 text-sm text-gray-600 dark:text-dark-tremor-content">
              Дополнительное ограничение поверх проектов роли. Пусто = без
              user-ограничения
              {userProjectsUnrestricted ? " (сейчас без ограничений)." : "."}
            </Text>
            {activeUsers.length ? (
              <div className="mt-4 flex max-w-lg flex-col gap-3">
                <select
                  className="w-full rounded-md border border-gray-200 px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={roleChange.user_id}
                  onChange={(e) => {
                    const id = Number(e.target.value);
                    const u = activeUsers.find((x) => x.id === id);
                    setRoleChange({
                      user_id: id,
                      new_role: u?.role || roleChange.new_role,
                    });
                  }}
                >
                  {activeUsers.map((u) => (
                    <option key={u.id} value={u.id}>
                      {u.username} ({u.role_label})
                    </option>
                  ))}
                </select>
                <textarea
                  className="min-h-[6rem] w-full rounded-md border border-gray-200 px-3 py-2 text-sm dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={userProjectsText}
                  onChange={(e) => setUserProjectsText(e.target.value)}
                  placeholder={"Проект А\nПроект Б"}
                />
                <button
                  type="button"
                  disabled={busy || !roleChange.user_id}
                  className="self-start rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60"
                  onClick={() =>
                    void run(async () => {
                      const projects = userProjectsText
                        .split(/\r?\n/)
                        .map((s) => s.trim())
                        .filter(Boolean);
                      await putUserProjects(roleChange.user_id, projects);
                      setMsg("Проекты пользователя сохранены.");
                      await loadUserProjects(roleChange.user_id);
                    })
                  }
                >
                  Сохранить проекты
                </button>
              </div>
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
          <div className="mt-3 lg:hidden">
            <MobileSearchField
              value={logsQuery}
              onChange={setLogsQuery}
              placeholder="Поиск в логах"
            />
          </div>
          <div className="mt-4 space-y-2 lg:hidden">
            {logsFiltered.length ? (
              logsFiltered.map((l) => (
                <article
                  key={l.id}
                  className="rounded-xl border border-tremor-border bg-tremor-background p-3 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                >
                  <div className="font-semibold text-tremor-content-strong dark:text-dark-tremor-content-strong">
                    {l.username} · {l.action}
                  </div>
                  <div className="mt-1 text-xs text-tremor-content dark:text-dark-tremor-content">
                    {l.created_at_fmt} · {l.ip_address || "—"}
                  </div>
                  <p className="mt-2 break-words text-sm">{l.details || "—"}</p>
                </article>
              ))
            ) : (
              <Text>Логи не найдены</Text>
            )}
          </div>
          <div className="mt-4 hidden overflow-x-auto lg:block">
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

      {subTab === "roles" ? <AdminRolesPanel /> : null}

      {subTab === "config" ? (
        <div className="space-y-6">
          <Card className="rounded-xl">
            <Title className="!text-base">Email администратора</Title>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
              <input
                className="w-full min-w-0 rounded-md border border-gray-200 px-3 py-2 sm:max-w-lg sm:flex-1 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                placeholder="например, admin@company.ru"
                value={config.admin_notification_email || ""}
                onChange={(e) =>
                  setConfig({ ...config, admin_notification_email: e.target.value })
                }
              />
              <button
                type="button"
                disabled={busy}
                className="w-full rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60 sm:w-auto sm:shrink-0"
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
            </div>
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-base">
              Отчёт «Отклонение от базового плана» — задача для KPI
            </Title>
            <Text className="mt-1 text-xs text-gray-500">
              {configDesc.baseline_plan_task_for_metrics}
            </Text>
            <div className="mt-3 flex flex-col gap-3 sm:flex-row sm:items-center">
              {taskOptions && taskOptions.options.length > 0 ? (
                <select
                  className="w-full min-w-0 rounded-md border border-gray-200 px-3 py-2 sm:max-w-lg sm:flex-1 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={taskValue}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      baseline_plan_task_for_metrics: e.target.value,
                    })
                  }
                >
                  {taskSelectItems.map((item) => (
                    <option key={item.name} value={item.name}>
                      {item.level != null
                        ? `Уровень ${item.level} — ${item.name}`
                        : item.name}
                    </option>
                  ))}
                </select>
              ) : (
                <input
                  className="w-full min-w-0 rounded-md border border-gray-200 px-3 py-2 sm:max-w-lg sm:flex-1 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                  value={taskValue}
                  onChange={(e) =>
                    setConfig({
                      ...config,
                      baseline_plan_task_for_metrics: e.target.value,
                    })
                  }
                />
              )}
              <button
                type="button"
                disabled={busy}
                className="w-full rounded-md bg-emerald-600 px-4 py-2 text-sm font-medium text-white disabled:opacity-60 sm:w-auto sm:shrink-0"
                onClick={() =>
                  void run(async () => {
                    await putReportConfig({
                      baseline_plan_task_for_metrics: taskValue,
                    });
                    setMsg("Сохранено.");
                  })
                }
              >
                Сохранить задачу для метрик
              </button>
            </div>
            {taskOptions?.hint ? (
              <Text className="mt-2 text-xs text-amber-600 dark:text-amber-400">
                {taskOptions.hint} Значение можно ввести вручную.
              </Text>
            ) : taskOptions && taskOptions.options.length > 0 ? (
              <Text className="mt-2 text-xs text-gray-500">
                Задач уровня {taskOptions.level} в текущей выгрузке MSP:{" "}
                {taskOptions.options.length}.
              </Text>
            ) : null}
          </Card>

          <Card className="rounded-xl">
            <Title className="!text-base">Контрольные точки — вехи (JSON)</Title>
            <Text className="mt-1 text-xs text-gray-500">
              {configDesc.control_points_milestones_json}
            </Text>
            <textarea
              rows={16}
              className="mt-3 w-full rounded-md border border-gray-200 px-3 py-2 font-mono text-xs placeholder:whitespace-pre-wrap placeholder:text-gray-400 dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:placeholder:text-gray-500"
              placeholder={configDefaults.control_points_milestones_json || ""}
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
              rows={16}
              className="mt-3 w-full rounded-md border border-gray-200 px-3 py-2 font-mono text-xs placeholder:whitespace-pre-wrap placeholder:text-gray-400 dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:placeholder:text-gray-500"
              placeholder={configDefaults.developer_projects_matrix_json || ""}
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
