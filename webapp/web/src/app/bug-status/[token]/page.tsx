"use client";

import Link from "next/link";
import { API_BASE } from "@/lib/api";
import { authHeaders, getAuthSession, isAdminRole } from "@/lib/auth";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type StatusPayload = {
  ok: boolean;
  bug_id: number;
  user_seq?: number;
  username?: string;
  status: string;
  status_label: string;
  title: string;
  preview: string;
  created_at?: string;
  related_report_id?: number | null;
  report_tab?: string;
};

type MineItem = {
  bug_id: number;
  status_label: string;
  title: string;
  public_token?: string;
  status_url?: string;
  created_at?: string;
};

export default function BugStatusPage() {
  const params = useParams();
  const token = String(params?.token || "");
  const [data, setData] = useState<StatusPayload | null>(null);
  const [mine, setMine] = useState<MineItem[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    if (!token) {
      setError("Нет токена заявки");
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const path = `/api/bugform/status/${encodeURIComponent(token)}`;
        const url = API_BASE ? `${API_BASE}${path}` : path;
        const resp = await fetch(url);
        const json = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(json.detail || json.error || `Ошибка ${resp.status}`);
        }
        if (!cancelled) setData(json as StatusPayload);

        const session = getAuthSession();
        const ticketUser = String(json.username || "").trim();
        if (
          session &&
          isAdminRole(session.role) &&
          ticketUser &&
          session.username === ticketUser
        ) {
          const minePath = `/api/bugform/mine`;
          const mineUrl = API_BASE ? `${API_BASE}${minePath}` : minePath;
          const mineResp = await fetch(mineUrl, { headers: { ...authHeaders() } });
          const mineJson = await mineResp.json().catch(() => ({}));
          if (mineResp.ok && !cancelled) {
            setMine((mineJson.items || []) as MineItem[]);
          }
        }
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [token]);

  const ticketNo = data?.user_seq || data?.bug_id;

  return (
    <main className="min-h-screen bg-[#f4f6f9] px-4 py-10 text-[#1c2430]">
      <div className="mx-auto w-full max-w-lg space-y-4">
        <div className="rounded-xl border border-[#d6dbe3] bg-white p-6 shadow-sm">
          <h1 className="text-xl font-semibold">Статус заявки</h1>

          {loading && <p className="mt-6 text-sm text-[#6b7280]">Загрузка…</p>}
          {error && (
            <p className="mt-6 rounded-lg border border-[#eec0c0] bg-[#fdeeee] px-3 py-2 text-sm">
              {error}
            </p>
          )}
          {data && !error && (
            <div className="mt-6 space-y-4">
              <div className="rounded-lg bg-[#f0f5ff] px-3 py-2 text-sm">
                <div className="font-medium">Заявка №{ticketNo}</div>
                <div className="mt-1 text-base font-semibold text-[#2a6fdb]">
                  {data.status_label}
                </div>
              </div>
              {data.title ? (
                <div>
                  <div className="text-xs font-medium uppercase tracking-wide text-[#6b7280]">
                    Кратко
                  </div>
                  <p className="mt-1 text-sm">{data.title}</p>
                </div>
              ) : null}
              {data.preview ? (
                <div>
                  <div className="text-xs font-medium uppercase tracking-wide text-[#6b7280]">
                    Описание
                  </div>
                  <p className="mt-1 whitespace-pre-wrap text-sm leading-relaxed">
                    {data.preview}
                  </p>
                </div>
              ) : null}
              {data.report_tab ? (
                <p className="text-sm text-[#6b7280]">Раздел: {data.report_tab}</p>
              ) : null}
              {data.related_report_id ? (
                <p className="text-sm text-[#6b7280]">
                  Связана с заявкой №{data.related_report_id}
                </p>
              ) : null}
              {data.created_at ? (
                <p className="text-xs text-[#6b7280]">Создана: {data.created_at}</p>
              ) : null}
              <p className="rounded-lg border border-[#d6dbe3] bg-[#fafbfc] px-3 py-2 text-sm text-[#6b7280]">
                Если статус «Готово к проверке», а проблема осталась — оформите{" "}
                <strong className="text-[#1c2430]">новую заявку</strong> и укажите номер
                этой (№{ticketNo}).
              </p>
            </div>
          )}
        </div>

        {mine.length > 0 ? (
          <div className="rounded-xl border border-[#d6dbe3] bg-white p-6 shadow-sm">
            <div className="flex items-center justify-between gap-2">
              <h2 className="text-base font-semibold">Мои заявки</h2>
              <Link
                href="/settings/my-tickets"
                className="text-sm font-medium text-[#2a6fdb] hover:underline"
              >
                Весь список →
              </Link>
            </div>
            <ul className="mt-3 divide-y divide-[#e5e7eb]">
              {mine.slice(0, 8).map((item) => {
                const href =
                  item.status_url ||
                  (item.public_token ? `/bug-status/${item.public_token}` : "");
                return (
                  <li key={`${item.bug_id}-${item.public_token || ""}`} className="py-2 text-sm">
                    <div className="flex items-start justify-between gap-2">
                      <div>
                        <div className="font-medium">
                          №{item.bug_id} — {item.status_label}
                        </div>
                        <div className="text-[#6b7280]">{item.title}</div>
                      </div>
                      {href ? (
                        <Link href={href} className="shrink-0 text-[#2a6fdb] hover:underline">
                          открыть
                        </Link>
                      ) : null}
                    </div>
                  </li>
                );
              })}
            </ul>
          </div>
        ) : null}
      </div>
    </main>
  );
}
