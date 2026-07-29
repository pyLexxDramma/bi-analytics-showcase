"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, Grid, Metric, Text, Title } from "@tremor/react";
import {
  fetchAdminDataStatus,
  fetchHealth,
  postAdminSync,
  type AdminDataStatus,
  type AdminSyncResult,
} from "@/lib/api";
import { getAdminToken, setAdminToken } from "@/lib/admin-token";
import { AppShell } from "@/components/app-shell";

function formatMtime(ts: number | null | undefined): string {
  if (ts == null || !Number.isFinite(ts)) return "—";
  try {
    return new Date(ts * 1000).toLocaleString("ru-RU");
  } catch {
    return "—";
  }
}

export function AdminView() {
  const [status, setStatus] = useState<AdminDataStatus | null>(null);
  const [health, setHealth] = useState<{
    version?: string;
    data_mode?: string;
    files?: number;
  } | null>(null);
  const [token, setToken] = useState("");
  const [force, setForce] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<AdminSyncResult | null>(null);

  const refresh = useCallback(async () => {
    setLoading(true);
    setError(null);
    try {
      const [st, h] = await Promise.all([
        fetchAdminDataStatus(),
        fetchHealth().catch(() => null),
      ]);
      setStatus(st);
      setHealth(h);
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
      setStatus(null);
    } finally {
      setLoading(false);
    }
  }, []);

  useEffect(() => {
    setToken(getAdminToken());
    void refresh();
  }, [refresh]);

  const onSync = async () => {
    setSyncing(true);
    setError(null);
    setSyncResult(null);
    try {
      setAdminToken(token);
      const result = await postAdminSync(token.trim(), force);
      setSyncResult(result);
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(false);
    }
  };

  return (
    <AppShell
      title="Административная панель"
      subtitle="Статус данных FTP / web и ручная синхронизация"
    >
      <Grid numItemsSm={2} numItemsLg={4} className="mb-6 gap-6">
        <Card className="rounded-xl">
          <Text>Режим данных</Text>
          <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
            {status?.data_mode || health?.data_mode || "…"}
          </Metric>
        </Card>
        <Card className="rounded-xl">
          <Text>Файлов в web/</Text>
          <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
            {loading ? "…" : String(status?.files ?? "—")}
          </Metric>
        </Card>
        <Card className="rounded-xl">
          <Text>FTP настроен</Text>
          <Metric
            className={`mt-2 ${
              status?.ftp_configured
                ? "text-emerald-600 dark:text-emerald-400"
                : "text-amber-600 dark:text-amber-400"
            }`}
          >
            {status == null ? "…" : status.ftp_configured ? "Да" : "Нет"}
          </Metric>
        </Card>
        <Card className="rounded-xl">
          <Text>API версия</Text>
          <Metric className="mt-2 text-tremor-content-strong dark:text-dark-tremor-content-strong">
            {health?.version || "—"}
          </Metric>
        </Card>
      </Grid>

      <Card className="mb-6 rounded-xl">
        <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
          Каталог данных
        </Title>
        <Text className="mt-2 break-all">
          {status?.web_dir || "—"}
        </Text>
        <Text className="mt-2">
          Последнее изменение файла:{" "}
          <b>{formatMtime(status?.latest_mtime)}</b>
        </Text>
        <button
          type="button"
          className="mt-4 rounded-tremor-default border border-tremor-border px-4 py-2 text-tremor-default hover:bg-tremor-background-muted dark:border-dark-tremor-border"
          onClick={() => void refresh()}
          disabled={loading}
        >
          Обновить статус
        </button>
      </Card>

      <Card className="mb-6 rounded-xl">
        <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
          FTP → web/
        </Title>
        <Text className="mt-1">
          Как ежедневный ingest на VPS. Нужен токен{" "}
          <code className="text-xs">WEBAPP_ADMIN_TOKEN</code>.
        </Text>
        <label className="mt-4 block text-sm">
          <Text>Admin token</Text>
          <input
            type="password"
            className="mt-1 w-full max-w-md rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            placeholder="X-Admin-Token"
            autoComplete="off"
          />
        </label>
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input
            type="checkbox"
            checked={force}
            onChange={(e) => setForce(e.target.checked)}
          />
          <Text>Force (перекачать даже при том же размере)</Text>
        </label>
        <button
          type="button"
          className="mt-4 rounded-tremor-default bg-emerald-600 px-4 py-2 font-medium text-white disabled:opacity-60"
          onClick={() => void onSync()}
          disabled={syncing || !token.trim()}
        >
          {syncing ? "Синхронизация…" : "FTP + обновить данные"}
        </button>
      </Card>

      {error ? (
        <Card className="mb-6 rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">{error}</Text>
        </Card>
      ) : null}

      {syncResult ? (
        <Card className="rounded-xl border-l-4 border-l-emerald-500">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            Результат sync
          </Title>
          <pre className="mt-3 overflow-x-auto rounded-md bg-tremor-background-muted p-3 text-xs dark:bg-dark-tremor-background-muted">
            {JSON.stringify(syncResult, null, 2)}
          </pre>
        </Card>
      ) : null}
    </AppShell>
  );
}
