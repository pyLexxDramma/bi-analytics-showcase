"use client";

import { useCallback, useEffect, useState } from "react";
import { Card, Grid, Metric, Text, Title } from "@tremor/react";
import {
  fetchAdminDataStatus,
  fetchAdminJob,
  fetchHealth,
  postAdminIngest,
  postAdminSync,
  type AdminDataStatus,
  type AdminSyncResult,
} from "@/lib/api";
import { getAdminToken, setAdminToken } from "@/lib/admin-token";

function formatMtime(ts: number | null | undefined): string {
  if (ts == null || !Number.isFinite(ts)) return "—";
  try {
    return new Date(ts * 1000).toLocaleString("ru-RU");
  } catch {
    return "—";
  }
}

async function waitJob(token: string, jobId: string, onTick?: (s: string) => void) {
  for (let i = 0; i < 180; i += 1) {
    const job = await fetchAdminJob(token, jobId);
    onTick?.(job.status);
    if (job.status === "ok" || job.status === "error") return job;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error("Таймаут ожидания job");
}

export function AdminDataSyncSection() {
  const [status, setStatus] = useState<AdminDataStatus | null>(null);
  const [health, setHealth] = useState<{
    version?: string;
    data_mode?: string;
    files?: number;
    active_version_id?: number | null;
  } | null>(null);
  const [token, setToken] = useState("");
  const [force, setForce] = useState(false);
  const [loading, setLoading] = useState(true);
  const [syncing, setSyncing] = useState(false);
  const [ingesting, setIngesting] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [syncResult, setSyncResult] = useState<AdminSyncResult | null>(null);
  const [jobHint, setJobHint] = useState<string | null>(null);

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
    if (
      !window.confirm(
        force
          ? "Запустить FTP → web/ → БД с force? Операция может занять несколько минут и перезапишет данные."
          : "Запустить синхронизацию FTP → web/ → БД? Операция может занять несколько минут.",
      )
    ) {
      return;
    }
    setSyncing(true);
    setError(null);
    setSyncResult(null);
    setJobHint(null);
    try {
      setAdminToken(token);
      const result = await postAdminSync(token.trim(), force);
      if (result.async && result.job_id) {
        setJobHint(`job ${result.job_id}: queued`);
        const job = await waitJob(token.trim(), result.job_id, (s) =>
          setJobHint(`job ${result.job_id}: ${s}`),
        );
        setSyncResult({
          ok: job.status === "ok",
          job_id: job.id,
          ...(typeof job.result === "object" && job.result ? (job.result as object) : {}),
          error: job.error,
        } as AdminSyncResult);
      } else {
        setSyncResult(result);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncing(false);
      setJobHint(null);
    }
  };

  const onIngest = async () => {
    if (
      !window.confirm(
        "Пересобрать БД только из web/ (без FTP)? Текущая активная версия будет заменена новым снимком.",
      )
    ) {
      return;
    }
    setIngesting(true);
    setError(null);
    setSyncResult(null);
    setJobHint(null);
    try {
      setAdminToken(token);
      const result = await postAdminIngest(token.trim());
      if (result.async && result.job_id) {
        setJobHint(`job ${result.job_id}: queued`);
        const job = await waitJob(token.trim(), result.job_id, (s) =>
          setJobHint(`job ${result.job_id}: ${s}`),
        );
        setSyncResult({
          ok: job.status === "ok",
          job_id: job.id,
          ...(typeof job.result === "object" && job.result ? (job.result as object) : {}),
          error: job.error,
        } as AdminSyncResult);
      } else {
        setSyncResult(result);
      }
      await refresh();
    } catch (e) {
      setError(e instanceof Error ? e.message : String(e));
    } finally {
      setIngesting(false);
      setJobHint(null);
    }
  };

  const db = status?.db;
  const versionLabel =
    db?.active_version_id != null
      ? String(db.active_version_id)
      : health?.active_version_id != null
        ? String(health.active_version_id)
        : "—";

  return (
    <div className="mt-8 space-y-6 border-t border-gray-200 pt-8 dark:border-dark-tremor-border">
      <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
        Данные (FTP / ingest)
      </Title>
      <Text>
        Синхронизация web/ и web_data.db — как в [main]. Токен{" "}
        <code className="text-xs">WEBAPP_ADMIN_TOKEN</code>.
      </Text>

      <Grid numItemsSm={2} numItemsLg={4} className="gap-6">
        <Card className="rounded-xl">
          <Text>Режим данных</Text>
          <Metric className="mt-2">{status?.data_mode || health?.data_mode || "…"}</Metric>
        </Card>
        <Card className="rounded-xl">
          <Text>Файлов в web/</Text>
          <Metric className="mt-2">{loading ? "…" : String(status?.files ?? "—")}</Metric>
        </Card>
        <Card className="rounded-xl">
          <Text>web_data.db version</Text>
          <Metric className="mt-2">{loading ? "…" : versionLabel}</Metric>
        </Card>
        <Card className="rounded-xl">
          <Text>API версия</Text>
          <Metric className="mt-2">{health?.version || "—"}</Metric>
        </Card>
      </Grid>

      <Card className="rounded-xl">
        <Text className="break-all">web/: {status?.web_dir || "—"}</Text>
        <Text className="mt-2 break-all">
          БД: {db?.web_db_path || "—"}{" "}
          {db?.exists ? `(${Math.round((db.size_bytes || 0) / 1024)} KB)` : "(нет файла)"}
        </Text>
        <Text className="mt-2">
          Последнее изменение web/: <b>{formatMtime(status?.latest_mtime)}</b>
        </Text>
        {status?.freshness ? (
          <Text className="mt-2">
            Свежесть:{" "}
            <b className={status.freshness.stale ? "text-amber-700" : "text-emerald-700"}>
              {status.freshness.label}
            </b>
            {status.freshness.active_version_created_at
              ? ` · снимок ${status.freshness.active_version_created_at}`
              : null}
            {" · "}порог {status.freshness.stale_after_hours ?? 26} ч
          </Text>
        ) : null}
        <button
          type="button"
          className="mt-4 rounded-tremor-default border border-tremor-border px-4 py-2 text-sm hover:bg-tremor-background-muted dark:border-dark-tremor-border"
          onClick={() => void refresh()}
          disabled={loading}
        >
          Обновить статус
        </button>
      </Card>

      <Card className="rounded-xl">
        <label className="block text-sm">
          <Text>Admin token</Text>
          <input
            type="password"
            className="mt-1 w-full max-w-md rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            value={token}
            onChange={(e) => setToken(e.target.value)}
            autoComplete="off"
          />
        </label>
        <label className="mt-3 flex items-center gap-2 text-sm">
          <input type="checkbox" checked={force} onChange={(e) => setForce(e.target.checked)} />
          <Text>Force FTP</Text>
        </label>
        <div className="mt-4 flex flex-wrap gap-3">
          <button
            type="button"
            className="rounded-tremor-default bg-emerald-600 px-4 py-2 font-medium text-white disabled:opacity-60"
            onClick={() => void onSync()}
            disabled={syncing || ingesting || !token.trim()}
          >
            {syncing ? "FTP+БД…" : "FTP → web → БД"}
          </button>
          <button
            type="button"
            className="rounded-tremor-default border border-tremor-border px-4 py-2 font-medium disabled:opacity-60 dark:border-dark-tremor-border"
            onClick={() => void onIngest()}
            disabled={syncing || ingesting || !token.trim()}
          >
            {ingesting ? "Ingest…" : "Только web → БД"}
          </button>
        </div>
        {jobHint ? (
          <Text className="mt-3 text-amber-700 dark:text-amber-300">{jobHint}</Text>
        ) : null}
      </Card>

      {error ? (
        <Card className="rounded-xl border-rose-300 bg-rose-50 dark:bg-rose-950/30">
          <Text className="text-rose-700 dark:text-rose-300">{error}</Text>
        </Card>
      ) : null}

      {syncResult ? (
        <Card className="rounded-xl border-l-4 border-l-emerald-500">
          <pre className="overflow-x-auto rounded-md bg-tremor-background-muted p-3 text-xs dark:bg-dark-tremor-background-muted">
            {JSON.stringify(syncResult, null, 2)}
          </pre>
        </Card>
      ) : null}
    </div>
  );
}
