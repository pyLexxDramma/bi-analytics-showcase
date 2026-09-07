"use client";

import Link from "next/link";
import { useEffect, useState } from "react";
import { AppShell } from "@/components/app-shell";
import { API_BASE } from "@/lib/api";
import { authHeaders, getAuthSession } from "@/lib/auth";

type Ticket = {
  bug_id: number;
  created_at?: string;
  title: string;
  status: string;
  status_label: string;
  report_tab?: string;
  status_url?: string;
  public_token?: string;
};

export default function MyTicketsPage() {
  const [items, setItems] = useState<Ticket[]>([]);
  const [error, setError] = useState("");
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const session = getAuthSession();
    if (!session) {
      setError("Войдите в систему, чтобы увидеть свои заявки.");
      setLoading(false);
      return;
    }
    let cancelled = false;
    (async () => {
      try {
        const path = `/api/bugform/mine`;
        const url = API_BASE ? `${API_BASE}${path}` : path;
        const resp = await fetch(url, {
          headers: { ...authHeaders() },
        });
        const json = await resp.json().catch(() => ({}));
        if (!resp.ok) {
          throw new Error(json.detail || json.error || `Ошибка ${resp.status}`);
        }
        if (!cancelled) setItems((json.items || []) as Ticket[]);
      } catch (err) {
        if (!cancelled) setError(err instanceof Error ? err.message : String(err));
      } finally {
        if (!cancelled) setLoading(false);
      }
    })();
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <AppShell title="Мои заявки">
      <div className="mx-auto max-w-4xl space-y-4 px-1 py-2">
        <p className="text-tremor-default text-tremor-content dark:text-dark-tremor-content">
          Реестр ваших баг-репортов со статусами. Trello не нужен — открывайте
          персональную страницу статуса.
        </p>
        {loading && <p className="text-sm text-tremor-content">Загрузка…</p>}
        {error && (
          <p className="rounded-lg border border-red-200 bg-red-50 px-3 py-2 text-sm text-red-800 dark:border-red-900 dark:bg-red-950/40 dark:text-red-200">
            {error}
          </p>
        )}
        {!loading && !error && items.length === 0 && (
          <p className="text-sm text-tremor-content">Заявок пока нет.</p>
        )}
        {items.length > 0 && (
          <div className="overflow-x-auto rounded-xl border border-tremor-border dark:border-dark-tremor-border">
            <table className="min-w-full text-left text-sm">
              <thead className="bg-tremor-background-muted dark:bg-dark-tremor-background-muted">
                <tr>
                  <th className="px-3 py-2 font-medium">№</th>
                  <th className="px-3 py-2 font-medium">Дата</th>
                  <th className="px-3 py-2 font-medium">Тема</th>
                  <th className="px-3 py-2 font-medium">Статус</th>
                  <th className="px-3 py-2 font-medium">Ссылка</th>
                </tr>
              </thead>
              <tbody>
                {items.map((row) => {
                  const href =
                    row.status_url ||
                    (row.public_token ? `/bug-status/${row.public_token}` : "");
                  return (
                    <tr
                      key={row.bug_id}
                      className="border-t border-tremor-border dark:border-dark-tremor-border"
                    >
                      <td className="px-3 py-2 whitespace-nowrap">{row.bug_id}</td>
                      <td className="px-3 py-2 whitespace-nowrap text-tremor-content">
                        {row.created_at || "—"}
                      </td>
                      <td className="px-3 py-2">
                        <div className="font-medium text-tremor-content-strong dark:text-dark-tremor-content-strong">
                          {row.title}
                        </div>
                        {row.report_tab ? (
                          <div className="text-xs text-tremor-content">{row.report_tab}</div>
                        ) : null}
                      </td>
                      <td className="px-3 py-2 whitespace-nowrap">{row.status_label}</td>
                      <td className="px-3 py-2">
                        {href ? (
                          <Link
                            href={href.startsWith("http") ? href : href}
                            className="text-[#2a6fdb] underline-offset-2 hover:underline"
                            target={href.startsWith("http") ? "_blank" : undefined}
                            rel={href.startsWith("http") ? "noopener noreferrer" : undefined}
                          >
                            Открыть
                          </Link>
                        ) : (
                          "—"
                        )}
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </AppShell>
  );
}
