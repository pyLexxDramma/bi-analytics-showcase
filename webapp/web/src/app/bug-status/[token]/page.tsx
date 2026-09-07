"use client";

import { API_BASE } from "@/lib/api";
import { useParams } from "next/navigation";
import { useEffect, useState } from "react";

type StatusPayload = {
  ok: boolean;
  bug_id: number;
  status: string;
  status_label: string;
  title: string;
  preview: string;
  created_at?: string;
  related_report_id?: number | null;
  report_tab?: string;
};

export default function BugStatusPage() {
  const params = useParams();
  const token = String(params?.token || "");
  const [data, setData] = useState<StatusPayload | null>(null);
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

  return (
    <main className="min-h-screen bg-[#f4f6f9] px-4 py-10 text-[#1c2430]">
      <div className="mx-auto w-full max-w-lg rounded-xl border border-[#d6dbe3] bg-white p-6 shadow-sm">
        <h1 className="text-xl font-semibold">Статус заявки</h1>
        <p className="mt-1 text-sm text-[#6b7280]">
          Без входа в Trello. Страница только для просмотра.
        </p>

        {loading && <p className="mt-6 text-sm text-[#6b7280]">Загрузка…</p>}
        {error && (
          <p className="mt-6 rounded-lg border border-[#eec0c0] bg-[#fdeeee] px-3 py-2 text-sm">
            {error}
          </p>
        )}
        {data && !error && (
          <div className="mt-6 space-y-4">
            <div className="rounded-lg bg-[#f0f5ff] px-3 py-2 text-sm">
              <div className="font-medium">Заявка №{data.bug_id}</div>
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
              этой (№{data.bug_id}).
            </p>
          </div>
        )}
      </div>
    </main>
  );
}
