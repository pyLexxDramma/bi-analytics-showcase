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
import { getAuthSession, isAdminRole, logout } from "@/lib/auth";
import { getAdminToken } from "@/lib/admin-token";
import {
  fetchAdminDataStatus,
  fetchAdminJob,
  fetchDataVersions,
  postActivateVersion,
  postAdminSync,
  type DataVersion,
} from "@/lib/api";

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
}: {
  /** Закрыть mobile-drawer после перехода по ссылке */
  onNavigate?: () => void;
  className?: string;
} = {}) {
  const pathname = usePathname();
  const router = useRouter();
  const activeAccordion = accordionIdForPath(pathname);
  const [openId, setOpenId] = useState<string | null>(activeAccordion);
  const [fileCount, setFileCount] = useState<number | null>(null);
  const [syncBusy, setSyncBusy] = useState(false);
  const [syncNote, setSyncNote] = useState<string | null>(null);
  const [versions, setVersions] = useState<DataVersion[]>([]);
  const [activeVersionId, setActiveVersionId] = useState<number | null>(null);
  const [versionBusy, setVersionBusy] = useState(false);
  const [versionNote, setVersionNote] = useState<string | null>(null);

  const navProps = onNavigate
    ? { onClick: () => onNavigate() }
    : {};

  useEffect(() => {
    if (activeAccordion) setOpenId(activeAccordion);
  }, [activeAccordion]);

  useEffect(() => {
    void fetchAdminDataStatus()
      .then((s) => setFileCount(s.files))
      .catch(() => setFileCount(null));
  }, [pathname]);

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
    void loadVersions();
  }, [pathname]);

  const isActive = (href: string) =>
    pathname === href || pathname.startsWith(`${href}/`);
  const externalAi = process.env.NEXT_PUBLIC_AI_MODE === "full";
  const aiHref = externalAi
    ? process.env.NEXT_PUBLIC_OPENCODE_URL
      || "https://opencode.conall.ru/L3dvcmtzcGFjZQ/session"
    : "/ai-assistant";

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
      const r = await postAdminSync(token || null, false);
      if (r.async && r.job_id) {
        setSyncNote(`job ${r.job_id}: queued`);
        const job = await waitAdminJob(token || null, r.job_id, (s) =>
          setSyncNote(`Синхронизация… ${s}`),
        );
        if (job.status !== "ok") {
          const detail =
            job.error ||
            (typeof job.result === "object" &&
            job.result &&
            Array.isArray((job.result as { errors?: string[] }).errors) &&
            (job.result as { errors: string[] }).errors[0]) ||
            "Ошибка FTP/БД";
          setSyncNote(String(detail));
          return;
        }
        const result =
          typeof job.result === "object" && job.result
            ? (job.result as Record<string, unknown>)
            : {};
        setSyncNote(
          `OK · файлов ${String(result.files ?? "—")} · активная версия обновлена`,
        );
      } else {
        setSyncNote(
          r.ok
            ? `OK · файлов ${r.files ?? "—"} · скачано ${r.downloaded ?? 0}`
            : `Ошибка: ${(r.errors || []).join("; ") || "см. админку"}`,
        );
      }
      const st = await fetchAdminDataStatus();
      setFileCount(st.files);
      await loadVersions();
      router.refresh();
    } catch (e) {
      setSyncNote(e instanceof Error ? e.message : String(e));
    } finally {
      setSyncBusy(false);
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

  return (
    <aside
      className={`flex w-full shrink-0 flex-col border-r border-gray-200 bg-[#f8f9fb] text-[13px] text-[#1f2937] dark:border-dark-tremor-border dark:bg-dark-tremor-background dark:text-dark-tremor-content-strong lg:sticky lg:top-0 lg:h-screen lg:w-[280px] lg:self-start ${className}`}
    >
      {/* прокрутка меню включается только под курсором — колесо над дашбордом не двигает сайдбар */}
      <div className="flex-1 overflow-y-auto px-3 py-4 lg:overflow-y-hidden lg:hover:overflow-y-auto">
        <section className="mb-5">
          <SectionTitle>Меню</SectionTitle>
          <Link
            href={aiHref}
            target={externalAi ? "_blank" : undefined}
            rel={externalAi ? "noopener noreferrer" : undefined}
            {...navProps}
            className={`flex min-h-11 items-center gap-2 rounded-md border px-3 py-2 ${
              isActive("/ai-assistant")
                ? "border-sky-400 bg-sky-50 text-sky-800 dark:border-sky-600 dark:bg-sky-950/40 dark:text-sky-200"
                : "border-sky-300 bg-white text-sky-700 hover:bg-sky-50 dark:border-sky-700 dark:bg-dark-tremor-background dark:text-sky-300"
            }`}
          >
            <span aria-hidden>✨</span>
            <span className="min-w-0 flex-1">
              <span className="block">ИИ помощник</span>
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
          </Link>
        </section>

        <section className="mb-5">
          <SectionTitle>Отчёты</SectionTitle>
          <div className="flex flex-col gap-1.5">
            <Link
              href={REPORT_TOP_TAB.href}
              {...navProps}
              className={`rounded-md px-3 py-2.5 font-medium transition ${
                isActive(REPORT_TOP_TAB.href)
                  ? "border border-emerald-300 bg-[#e8f5e9] text-emerald-900"
                  : "border border-transparent bg-white hover:bg-gray-100 dark:bg-dark-tremor-background-subtle"
              }`}
            >
              {REPORT_TOP_TAB.label}
            </Link>

            {REPORT_ACCORDIONS.map((acc) => {
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
                                ? "border-emerald-300 bg-[#e8f5e9] font-medium text-emerald-900"
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

            {REPORT_STANDALONE.map((item) => (
              <Link
                key={item.id}
                href={item.href}
                {...navProps}
                className={`rounded-md border px-3 py-2.5 leading-snug transition ${
                  isActive(item.href)
                    ? "border-emerald-300 bg-[#e8f5e9] font-medium text-emerald-900"
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
                  ? "border-emerald-300 bg-[#e8f5e9] font-medium text-emerald-900"
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
                  ? "border-emerald-300 bg-[#e8f5e9] font-medium text-emerald-900"
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
            <button
              type="button"
              disabled={syncBusy}
              onClick={() => void runFtpSync()}
              className="min-h-11 w-full rounded-md bg-[#66bb6a] px-2 py-2 font-medium text-white disabled:opacity-60"
            >
              {syncBusy ? "Синхронизация…" : "FTP + перезагрузить БД"}
            </button>
            {syncNote ? (
              <p className="text-[11px] leading-snug text-gray-600 dark:text-dark-tremor-content">
                {syncNote}
              </p>
            ) : (
              <p className="text-[11px] leading-snug text-gray-500">
                07:00 МСК — выгрузка 1С на FTP. Кнопка тянет файлы и создаёт
                новый снимок в списке ниже.
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
