"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import {
  REPORT_ACCORDIONS,
  REPORT_STANDALONE,
  REPORT_TOP_TAB,
  accordionIdForPath,
} from "@/lib/nav";
import { openCommandPalette } from "@/components/command-palette";
import {
  getAuthSession,
  isAdminRole,
  logout,
  canAccessReport,
  type AuthUser,
} from "@/lib/auth";
import { getAdminToken } from "@/lib/admin-token";
import { loadDataStatus } from "@/lib/data-status-store";
import {
  ApiError,
  downloadSnapshotExport,
  fetchAdminJob,
  fetchDataVersions,
  postActivateVersion,
  postAdminIngest,
  postAdminSync,
  postAskAiLink,
  postEnsureFresh,
  type AdminSyncResult,
  type DataFreshness,
  type DataVersion,
} from "@/lib/api";

const ENSURE_FRESH_SESSION_KEY = "bi_showcase_ensure_fresh_v1";
const COLLAPSED_KEY = "bi_showcase_sidebar_collapsed_v1";

function readSidebarCollapsed(): boolean {
  try {
    return localStorage.getItem(COLLAPSED_KEY) === "1";
  } catch {
    return false;
  }
}

function writeSidebarCollapsed(value: boolean): void {
  try {
    localStorage.setItem(COLLAPSED_KEY, value ? "1" : "0");
  } catch {
    /* приватный режим — состояние живёт до перезагрузки */
  }
}

function SectionTitle({ children }: { children: React.ReactNode }) {
  return (
    <div className="mb-2 text-sm font-bold text-[#1f2937] dark:text-dark-tremor-content-strong">
      {children}
    </div>
  );
}

function Chevron({ open }: { open: boolean }) {
  return (
    <span
      className={`inline-block text-xs text-gray-500 transition-transform ${
        open ? "rotate-90" : ""
      }`}
      aria-hidden
    >
      ▸
    </span>
  );
}

/** Как main `_fmt`: дата/время выгрузки + файлы/строки. */
function formatVersionStamp(raw: string): string {
  const s = (raw || "").trim();
  if (!s) return "—";
  // "2026-07-30 14:04:15" → "30.07.2026 14:04"
  const m = s.match(
    /^(\d{4})-(\d{2})-(\d{2})[ T](\d{2}):(\d{2})(?::\d{2})?/,
  );
  if (m) return `${m[3]}.${m[2]}.${m[1]} ${m[4]}:${m[5]}`;
  return s;
}

function versionCaption(v: DataVersion, activeId: number | null): string {
  const base = `${formatVersionStamp(v.created_at)} · файлов ${v.files_count}, строк ${v.rows_count}`;
  return v.id === activeId ? `${base} ✅` : base;
}

async function waitAdminJob(
  token: string | null,
  jobId: string,
  onTick?: (status: string) => void,
) {
  for (let i = 0; i < 180; i += 1) {
    const job = await fetchAdminJob(token, jobId);
    onTick?.(job.status);
    if (job.status === "ok" || job.status === "error") return job;
    await new Promise((r) => setTimeout(r, 2000));
  }
  throw new Error("Таймаут ожидания FTP/БД");
}

export function AppSidebar({
  onNavigate,
  className = "",
  collapsible = false,
}: {
  /** Закрыть mobile-drawer после перехода по ссылке */
  onNavigate?: () => void;
  className?: string;
  /** Сворачивание доступно только в десктопной колонке, не в mobile-drawer. */
  collapsible?: boolean;
} = {}) {
  const pathname = usePathname();
  const router = useRouter();
  const activeAccordion = accordionIdForPath(pathname);
  const [openId, setOpenId] = useState<string | null>(activeAccordion);
  const [fileCount, setFileCount] = useState<number | null>(null);
  const [freshness, setFreshness] = useState<DataFreshness | null>(null);
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncNote, setSyncNote] = useState<string | null>(null);
  const [snapshotBusy, setSnapshotBusy] = useState(false);
  const [versions, setVersions] = useState<DataVersion[]>([]);
  const [activeVersionId, setActiveVersionId] = useState<number | null>(null);
  const [versionBusy, setVersionBusy] = useState(false);
  const [versionNote, setVersionNote] = useState<string | null>(null);

  const [collapsed, setCollapsed] = useState(false);
  /** localStorage недоступен на SSR — иначе hydration mismatch и «1 Error» в DevTools. */
  const [session, setSession] = useState<AuthUser | null>(null);

  const navProps = onNavigate
    ? { onClick: () => onNavigate() }
    : {};

  useEffect(() => {
    if (activeAccordion) setOpenId(activeAccordion);
  }, [activeAccordion]);

  useEffect(() => {
    setSession(getAuthSession());
  }, [pathname]);

  useEffect(() => {
    if (!collapsible) return;
    setCollapsed(readSidebarCollapsed());
  }, [collapsible]);

  const toggleCollapsed = () => {
    setCollapsed((state) => {
      writeSidebarCollapsed(!state);
      return !state;
    });
  };

  const loadVersions = () =>
    fetchDataVersions()
      .then((v) => {
        setVersions(v.items || []);
        setActiveVersionId(v.active_version_id ?? null);
      })
      .catch(() => {
        setVersions([]);
        setActiveVersionId(null);
      });

  useEffect(() => {
    void loadDataStatus(true).then((s) => {
      setFileCount(s?.files ?? null);
      setFreshness(s?.freshness ?? null);
    });
    void loadVersions();
  }, [pathname]);

  // Один раз за сессию браузера: если данные устарели — тихо FTP→БД.
  useEffect(() => {
    if (typeof window === "undefined") return;
    if (sessionStorage.getItem(ENSURE_FRESH_SESSION_KEY)) return;
    const session = getAuthSession();
    if (!session) return;
    sessionStorage.setItem(ENSURE_FRESH_SESSION_KEY, "1");
    const token = getAdminToken();
    void postEnsureFresh(token || null, { force: false, background: true })
      .then(async (r) => {
        if (r.freshness) setFreshness(r.freshness);
        if (r.action === "fresh") return;
        if (r.action === "started" && r.job_id) {
          setSyncNote(r.message || "Авто-обновление данных…");
          setSyncBusy(true);
          try {
            const job = await waitAdminJob(token || null, r.job_id, (s) =>
              setSyncNote(`Авто-обновление… ${s}`),
            );
            if (job.status === "ok") {
              setSyncNote("Данные обновлены автоматически");
              const st = await loadDataStatus(true);
              setFileCount(st?.files ?? null);
              setFreshness(st?.freshness ?? null);
              await loadVersions();
              router.refresh();
            } else {
              setSyncNote(job.error || "Авто-обновление не удалось");
            }
          } finally {
            setSyncBusy(false);
          }
          return;
        }
        if (r.message && r.action !== "none") {
          setSyncNote(r.message);
        }
      })
      .catch(() => {
        /* тихо: индикатор свежести всё равно из data-status */
      });
  }, [router]);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);
  const visibleTop = canAccessReport(REPORT_TOP_TAB.id, session)
    ? REPORT_TOP_TAB
    : null;
  const visibleAccordions = REPORT_ACCORDIONS.map((acc) => ({
    ...acc,
    items: acc.items.filter((i) => canAccessReport(i.id, session)),
  })).filter((acc) => acc.items.length > 0);
  const visibleStandalone = REPORT_STANDALONE.filter((i) =>
    canAccessReport(i.id, session),
  );
  const externalAi = process.env.NEXT_PUBLIC_AI_MODE === "full";
  const [aiBusy, setAiBusy] = useState(false);
  const [aiError, setAiError] = useState<string | null>(null);

  const openFreeAskAi = async () => {
    if (!externalAi) {
      router.push("/ai-assistant");
      onNavigate?.();
      return;
    }
    setAiError(null);
    setAiBusy(true);
    const popup = window.open("about:blank", "_blank");
    try {
      const { url } = await postAskAiLink({
        mode: "free",
        report: "free",
        q: "",
        src: "sidebar",
      });
      if (popup && !popup.closed) {
        popup.location.replace(url);
      } else {
        window.open(url, "_blank", "noopener,noreferrer");
      }
      onNavigate?.();
    } catch (err) {
      if (popup && !popup.closed) popup.close();
      setAiError(err instanceof Error ? err.message : "Не удалось открыть ИИ");
    } finally {
      setAiBusy(false);
    }
  };

  const runFtpSync = async () => {
    const token = getAdminToken();
    const session = getAuthSession();
    const canFtp =
      Boolean(token) ||
      (session &&
        (isAdminRole(session.role) ||
          session.role.toLowerCase() === "analyst"));
    if (!canFtp) {
      setSyncNote("Войдите как admin/analyst или задайте токен в админке");
      router.push("/settings/admin");
      return;
    }
    setSyncBusy(true);
    setSyncNote(null);
    try {
      const status = await loadDataStatus(true);
      const mode = String(status?.data_mode || "").toLowerCase();
      // Ручной клик: всегда force FTP; в synthetic/local без FTP — ingest web/→БД.
      let r: AdminSyncResult;
      let viaIngest = false;
      if (mode && mode !== "ftp") {
        viaIngest = true;
        setSyncNote(`Режим ${mode}: пересборка БД из web/…`);
        r = await postAdminIngest(token || null);
      } else {
        try {
          // force=true — иначе FTP может «тихо» ничего не скачать и кажется, что кнопка мёртвая.
          r = await postAdminSync(token || null, true);
        } catch (e) {
          const msg = e instanceof Error ? e.message : String(e);
          const noFtp =
            e instanceof ApiError &&
            (e.status === 400 || /WEBAPP_DATA_MODE|не ftp|synthetic/i.test(msg));
          if (!noFtp) throw e;
          viaIngest = true;
          setSyncNote("FTP недоступен — пересборка БД из web/…");
          r = await postAdminIngest(token || null);
        }
      }

      if (r.async && r.job_id) {
        setSyncNote(`job ${r.job_id}: queued`);
        const job = await waitAdminJob(token || null, r.job_id, (s) =>
          setSyncNote(viaIngest ? `Пересборка БД… ${s}` : `Синхронизация… ${s}`),
        );
        if (job.status !== "ok") {
          const detail =
            job.error ||
            (typeof job.result === "object" &&
            job.result &&
            Array.isArray((job.result as { errors?: string[] }).errors) &&
            (job.result as { errors: string[] }).errors[0]) ||
            (viaIngest ? "Ошибка ingest" : "Ошибка FTP/БД");
          setSyncNote(String(detail));
          return;
        }
        const result =
          typeof job.result === "object" && job.result
            ? (job.result as Record<string, unknown>)
            : {};
        const vid =
          result.version_id ??
          result.active_version_id ??
          (result.db as { active_version_id?: unknown } | undefined)
            ?.active_version_id;
        setSyncNote(
          viaIngest
            ? `OK · БД пересобрана · версия ${String(vid ?? "—")}`
            : `OK · файлов ${String(result.files ?? "—")} · версия ${String(vid ?? "—")}`,
        );
      } else {
        setSyncNote(
          r.ok
            ? viaIngest
              ? `OK · БД пересобрана · версия ${String(r.version_id ?? r.active_version_id ?? "—")}`
              : `OK · файлов ${r.files ?? "—"} · скачано ${r.downloaded ?? 0}`
            : `Ошибка: ${(r.errors || []).join("; ") || r.detail || "см. админку"}`,
        );
        if (!r.ok) return;
      }
      const st = await loadDataStatus(true);
      setFileCount(st?.files ?? null);
      setFreshness(st?.freshness ?? null);
      await loadVersions();
      // Client-компоненты дашбордов держат state — refresh App Router мало; полный reload.
      window.setTimeout(() => {
        window.location.reload();
      }, 400);
    } catch (e) {
      setSyncNote(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncBusy(false);
    }
  };

  const downloadFreshSnapshot = async () => {
    const token = getAdminToken();
    const session = getAuthSession();
    const canFtp =
      Boolean(token) ||
      (session &&
        (isAdminRole(session.role) ||
          session.role.toLowerCase() === "analyst"));
    if (!canFtp) {
      setSyncNote("Скачивание слепка: войдите как admin/analyst");
      router.push("/login");
      return;
    }
    setSnapshotBusy(true);
    setSyncNote("Готовим архив свежего слепка…");
    try {
      const { filename, blob } = await downloadSnapshotExport(token || null);
      const href = URL.createObjectURL(blob);
      const a = document.createElement("a");
      a.href = href;
      a.download = filename;
      document.body.appendChild(a);
      a.click();
      a.remove();
      URL.revokeObjectURL(href);
      setSyncNote(`Скачан ${filename}`);
    } catch (e) {
      setSyncNote(e instanceof Error ? e.message : String(e));
    } finally {
      setSnapshotBusy(false);
    }
  };

  const applyVersion = async (versionId: number) => {
    if (versionId === activeVersionId) return;
    const token = getAdminToken();
    const session = getAuthSession();
    if (!token && !session) {
      setVersionNote("Войдите в систему или задайте токен в админке");
      router.push("/login");
      return;
    }
    setVersionBusy(true);
    setVersionNote(null);
    try {
      await postActivateVersion(token || null, versionId);
      await loadVersions();
      setVersionNote("Версия переключена — дашборд на свежих данных");
      router.refresh();
    } catch (e) {
      setVersionNote(e instanceof Error ? e.message : String(e));
    } finally {
      setVersionBusy(false);
    }
  };

  if (collapsible && collapsed) {
    return (
      <aside className="sticky top-0 flex h-screen w-12 shrink-0 flex-col items-center gap-2 border-r border-gray-200 bg-[#f8f9fb] py-4 dark:border-dark-tremor-border dark:bg-dark-tremor-background">
        <button
          type="button"
          onClick={toggleCollapsed}
          title="Развернуть меню"
          aria-label="Развернуть меню"
          aria-expanded={false}
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-gray-200 bg-white text-base text-[#1f2937] hover:bg-gray-100 dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content-strong"
        >
          »
        </button>
        <button
          type="button"
          onClick={openCommandPalette}
          title="Поиск по отчётам (Ctrl+K)"
          aria-label="Поиск по отчётам"
          className="inline-flex h-9 w-9 items-center justify-center rounded-md border border-gray-200 bg-white text-base hover:bg-gray-100 dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle"
        >
          🔎
        </button>
      </aside>
    );
  }

  return (
    <aside
      className={`flex w-full shrink-0 flex-col border-r border-gray-200 bg-[#f8f9fb] text-[13px] text-[#1f2937] dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong lg:sticky lg:top-0 lg:h-screen lg:w-[280px] lg:self-start ${className}`}
    >
      {/* overscroll-contain: докрутив меню до конца, колесо не начинает листать дашборд */}
      <div className="flex-1 overflow-y-auto overscroll-contain px-3 py-4">
        {collapsible ? (
          <div className="mb-3 flex justify-end">
            <button
              type="button"
              onClick={toggleCollapsed}
              title="Свернуть меню"
              aria-label="Свернуть меню"
              aria-expanded
              className="inline-flex h-8 w-8 items-center justify-center rounded-md border border-gray-200 bg-white text-base text-[#1f2937] hover:bg-gray-100 dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle dark:text-dark-tremor-content-strong"
            >
              «
            </button>
          </div>
        ) : null}
        <section className="mb-5">
          <SectionTitle>Меню</SectionTitle>
          <button
            type="button"
            onClick={() => void openFreeAskAi()}
            disabled={aiBusy}
            className={`flex min-h-11 w-full items-center gap-2 rounded-md border px-3 py-2 text-left ${
              isActive("/ai-assistant")
                ? "border-sky-400 bg-sky-50 text-sky-800 dark:border-sky-600 dark:bg-sky-950/40 dark:text-sky-200"
                : "border-sky-300 bg-white text-sky-700 hover:bg-sky-50 dark:border-sky-700 dark:bg-dark-tremor-background dark:text-sky-300"
            } disabled:opacity-60`}
          >
            <span aria-hidden>✨</span>
            <span className="min-w-0 flex-1">
              <span className="block">
                {aiBusy ? "Открываю ИИ…" : "ИИ помощник"}
              </span>
              {externalAi ? (
                <span className="mt-0.5 block text-[11px] font-normal leading-tight text-sky-600 dark:text-sky-400 lg:hidden">
                  ИИ откроется в отдельном окне
                </span>
              ) : null}
            </span>
            {externalAi ? (
              <span className="shrink-0 text-sm" aria-hidden>
                ↗
              </span>
            ) : null}
          </button>
          {aiError ? (
            <p className="mt-1 text-[11px] leading-snug text-red-600 dark:text-red-400">
              {aiError}
            </p>
          ) : null}
        </section>

        <section className="mb-5">
          <SectionTitle>Отчёты</SectionTitle>
          <div className="flex flex-col gap-1.5">
            {visibleTop ? (
              <Link
                href={visibleTop.href}
                {...navProps}
                className={`rounded-md px-3 py-2.5 font-medium transition ${
                  isActive(visibleTop.href)
                    ? "bi-nav-active border"
                    : "border border-transparent bg-white hover:bg-gray-100 dark:bg-dark-tremor-background-subtle"
                }`}
              >
                {visibleTop.label}
              </Link>
            ) : null}

            {visibleAccordions.map((acc) => {
              const open = openId === acc.id;
              const childActive = acc.items.some((i) => isActive(i.href));
              return (
                <div key={acc.id} className="flex flex-col gap-1">
                  <button
                    type="button"
                    onClick={() => setOpenId(open ? null : acc.id)}
                    className={`flex min-h-11 w-full items-center gap-2 rounded-md border px-3 py-2 text-left transition ${
                      childActive || open
                        ? "border-gray-300 bg-white dark:border-dark-tremor-border dark:bg-dark-tremor-background-subtle"
                        : "border-gray-200 bg-white hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                    }`}
                    aria-expanded={open}
                  >
                    <Chevron open={open} />
                    <span className="font-medium">{acc.label}</span>
                  </button>
                  {open ? (
                    <div className="ml-1 rounded-md border border-gray-200 bg-[#eef0f3] p-1.5 dark:border-dark-tremor-border dark:bg-dark-tremor-background-muted">
                      <div className="flex flex-col gap-1">
                        {acc.items.map((item) => (
                          <Link
                            key={item.id}
                            href={item.href}
                            {...navProps}
                            className={`rounded-md border px-2.5 py-2 leading-snug transition ${
                              isActive(item.href)
                                ? "bi-nav-active"
                                : "border-gray-200 bg-white text-gray-800 hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
                            }`}
                          >
                            {item.label}
                          </Link>
                        ))}
                      </div>
                    </div>
                  ) : null}
                </div>
              );
            })}

            {visibleStandalone.map((item) => (
              <Link
                key={item.id}
                href={item.href}
                {...navProps}
                className={`rounded-md border px-3 py-2.5 leading-snug transition ${
                  isActive(item.href)
                    ? "bi-nav-active"
                    : "border-gray-200 bg-white hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
                }`}
              >
                {item.label}
              </Link>
            ))}
          </div>
        </section>

        <section className="mb-5">
          <SectionTitle>Настройки</SectionTitle>
          <div className="flex flex-col gap-1.5">
            <Link
              href="/settings/profile"
              {...navProps}
              className={`rounded-md border px-3 py-2.5 ${
                isActive("/settings/profile")
                  ? "bi-nav-active"
                  : "border-gray-200 bg-white hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              }`}
            >
              Настройки профиля
            </Link>
            <Link
              href="/settings/admin"
              {...navProps}
              className={`rounded-md border px-3 py-2.5 ${
                isActive("/settings/admin")
                  ? "bi-nav-active"
                  : "border-gray-200 bg-white hover:bg-gray-50 dark:border-dark-tremor-border dark:bg-dark-tremor-background"
              }`}
            >
              Административная панель
            </Link>
          </div>
        </section>

        <section className="mb-4">
          <SectionTitle>Данные</SectionTitle>
          <div className="space-y-2 rounded-md border border-gray-200 bg-white p-3 dark:border-dark-tremor-border dark:bg-dark-tremor-background">
            <p className="text-[11px] leading-snug text-gray-600 dark:text-dark-tremor-content">
              Staging:{" "}
              <span className="font-medium text-gray-800 dark:text-dark-tremor-content-strong">
                web/
              </span>
              {fileCount != null ? ` · ${fileCount} файл.` : null}
            </p>
            {freshness ? (
              <p
                className={`rounded-md px-2 py-1.5 text-[11px] leading-snug ${
                  freshness.stale
                    ? "bg-amber-50 text-amber-950 dark:bg-amber-950/30 dark:text-amber-100"
                    : "bg-emerald-50 text-emerald-900 dark:bg-emerald-950/30 dark:text-emerald-100"
                }`}
                title={
                  freshness.active_version_created_at
                    ? `Снимок: ${freshness.active_version_created_at}`
                    : undefined
                }
              >
                {freshness.stale ? "⚠ " : "✓ "}
                Данные {freshness.label}
                {freshness.active_version_created_at
                  ? ` · снимок ${formatVersionStamp(freshness.active_version_created_at)}`
                  : null}
              </p>
            ) : null}
            <button
              type="button"
              disabled={syncBusy}
              onClick={() => void runFtpSync()}
              className="min-h-11 w-full rounded-md bg-[#66bb6a] px-2 py-2 font-medium text-white disabled:opacity-60"
            >
              {syncBusy ? "Синхронизация…" : "FTP + перезагрузить БД"}
            </button>
            <button
              type="button"
              disabled={snapshotBusy || syncBusy}
              onClick={() => void downloadFreshSnapshot()}
              className="hidden min-h-11 w-full rounded-md border border-gray-300 bg-white px-2 py-2 font-medium text-[#1f2937] disabled:opacity-60 lg:block dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong"
            >
              {snapshotBusy ? "Готовим архив…" : "Скачать свежий слепок FTP"}
            </button>
            {syncNote ? (
              <p className="text-[11px] leading-snug text-gray-600 dark:text-dark-tremor-content">
                {syncNote}
              </p>
            ) : (
              <p className="text-[11px] leading-snug text-gray-500">
                07:00 МСК — выгрузка на FTP; daily Action ~11:00. При входе
                дашборд сам проверяет свежесть
                <span className="hidden lg:inline">
                  . Кнопка «Скачать слепок» — файлы самой новой даты (всегда
                  актуальные после синка)
                </span>
                .
              </p>
            )}
          </div>
        </section>

        <section className="mb-4">
          <SectionTitle>Версия данных (в дашбордах)</SectionTitle>
          <div className="space-y-1.5 rounded-md border border-gray-200 bg-white p-2 dark:border-dark-tremor-border dark:bg-dark-tremor-background">
            {versions.length === 0 ? (
              <p className="px-1 py-1 text-[11px] leading-snug text-gray-500">
                Нет снимков в БД — нажмите «FTP + перезагрузить БД»
              </p>
            ) : (
              <>
                <ul className="max-h-52 space-y-1 overflow-y-auto">
                  {versions.map((v) => {
                    const active = v.id === activeVersionId;
                    return (
                      <li key={v.id}>
                        <button
                          type="button"
                          disabled={versionBusy}
                          onClick={() => void applyVersion(v.id)}
                          className={`w-full rounded-md border px-2 py-1.5 text-left text-[11px] leading-snug transition disabled:opacity-60 ${
                            active
                              ? "border-emerald-500 bg-emerald-50 font-semibold text-emerald-900 dark:border-emerald-600 dark:bg-emerald-950/40 dark:text-emerald-100"
                              : "border-amber-800/40 bg-amber-50/80 text-amber-950 hover:border-amber-800 dark:border-amber-700/50 dark:bg-amber-950/20 dark:text-amber-100"
                          }`}
                          title={
                            active
                              ? "Активная версия (загружена в дашборды)"
                              : "Предыдущая выгрузка — клик активирует"
                          }
                        >
                          <span className="block">
                            {versionCaption(v, activeVersionId)}
                          </span>
                          <span
                            className={`mt-0.5 block text-[10px] ${
                              active
                                ? "text-emerald-700 dark:text-emerald-300"
                                : "text-amber-800/80 dark:text-amber-200/80"
                            }`}
                          >
                            {active ? "активная" : `снимок #${v.id}`}
                          </span>
                        </button>
                      </li>
                    );
                  })}
                </ul>
                <p className="px-1 text-[11px] leading-snug text-gray-600 dark:text-dark-tremor-content">
                  {versionBusy
                    ? "Переключение…"
                    : versionNote ||
                      "Зелёная — текущая; коричневая — клик переключает"}
                </p>
              </>
            )}
          </div>
        </section>
      </div>

      <div className="shrink-0 border-t border-gray-200 p-3 dark:border-dark-tremor-border">
        <button
          type="button"
          className="min-h-11 w-full rounded-md bg-[#fdecea] px-3 py-2 font-medium text-[#c62828] transition hover:bg-[#f8d7d3]"
          onClick={() => {
            logout();
            onNavigate?.();
            router.push("/login");
          }}
        >
          Выйти
        </button>
      </div>
    </aside>
  );
}
