"use client";

import { useCallback, useEffect, useRef, useState } from "react";
import Image from "next/image";
import { useRouter } from "next/navigation";
import { Bot, Menu, MessageSquarePlus, RefreshCw, Send, Square, Trash2, X } from "lucide-react";
import ReactMarkdown from "react-markdown";
import remarkGfm from "remark-gfm";
import { AppShell } from "@/components/app-shell";
import {
  API_BASE,
  cancelAssistantMessage,
  createAssistantSession,
  deleteAssistantSession,
  fetchAssistantHealth,
  fetchAssistantMessages,
  fetchAssistantSessions,
  replyAssistantQuestion,
  sendAssistantMessage,
  type AssistantMessage,
  type AssistantQuestion,
  type AssistantSession,
} from "@/lib/api";
import { authHeaders, isAuthenticated, logout } from "@/lib/auth";

function ProtectedImage({ src }: { src: string }) {
  const [url, setUrl] = useState("");

  useEffect(() => {
    let active = true;
    let objectUrl = "";
    fetch(`${API_BASE}${src}`, { headers: authHeaders(), cache: "no-store" })
      .then((response) => {
        if (!response.ok) throw new Error("image");
        return response.blob();
      })
      .then((blob) => {
        objectUrl = URL.createObjectURL(blob);
        if (active) setUrl(objectUrl);
      })
      .catch(() => undefined);
    return () => {
      active = false;
      if (objectUrl) URL.revokeObjectURL(objectUrl);
    };
  }, [src]);

  if (!url) return null;
  return (
    <Image
      src={url}
      alt="График XCA AI"
      width={1200}
      height={720}
      unoptimized
      className="mt-3 h-auto max-h-[520px] w-full rounded-xl object-contain"
    />
  );
}

function Message({ message }: { message: AssistantMessage }) {
  return (
    <div className={`flex ${message.role === "user" ? "justify-end" : "justify-start"}`}>
      <div
        className={`max-w-[92%] overflow-hidden rounded-2xl px-4 py-3 text-sm leading-6 sm:max-w-[82%] ${
          message.role === "user"
            ? "rounded-br-md bg-sky-600 text-white"
            : "rounded-bl-md border border-slate-200 bg-white text-slate-800 shadow-sm dark:border-slate-700 dark:bg-slate-900 dark:text-slate-100"
        }`}
      >
        <div className="prose prose-sm max-w-none break-words prose-p:my-2 prose-pre:max-w-full prose-pre:overflow-x-auto prose-table:block prose-table:max-w-full prose-table:overflow-x-auto dark:prose-invert">
          <ReactMarkdown remarkPlugins={[remarkGfm]}>{message.text}</ReactMarkdown>
        </div>
        {message.images.map((src) => <ProtectedImage key={src} src={src} />)}
      </div>
    </div>
  );
}

function FullAiAssistantView() {
  const router = useRouter();
  const [sessions, setSessions] = useState<AssistantSession[]>([]);
  const [activeId, setActiveId] = useState("");
  const [messages, setMessages] = useState<AssistantMessage[]>([]);
  const [question, setQuestion] = useState<AssistantQuestion | null>(null);
  const [draft, setDraft] = useState("");
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(true);
  const [drawerOpen, setDrawerOpen] = useState(false);
  const [error, setError] = useState("");
  const [online, setOnline] = useState<boolean | null>(null);
  const [authReady, setAuthReady] = useState(false);
  const bottomRef = useRef<HTMLDivElement | null>(null);
  const activeIdRef = useRef("");
  const messagesRequestRef = useRef<AbortController | null>(null);
  const requestGenerationRef = useRef(0);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: busy ? "auto" : "smooth" });
  }, [messages, busy]);

  const loadMessages = useCallback(async (sessionId: string) => {
    const generation = requestGenerationRef.current;
    const controller = new AbortController();
    messagesRequestRef.current = controller;
    let payload;
    try {
      payload = await fetchAssistantMessages(sessionId, controller.signal);
    } catch (reason) {
      if (controller.signal.aborted) return true;
      throw reason;
    }
    if (
      controller.signal.aborted
      || activeIdRef.current !== sessionId
      || requestGenerationRef.current !== generation
    ) {
      return payload.busy;
    }
    setMessages(payload.items);
    setBusy(payload.busy);
    setQuestion(payload.question);
    setError(payload.error || "");
    return payload.busy;
  }, []);

  const refreshSessions = useCallback(async () => {
    const payload = await fetchAssistantSessions();
    setSessions(payload.items);
    return payload.items;
  }, []);

  const addSession = useCallback(async () => {
    setError("");
    const session = await createAssistantSession();
    setSessions((items) => [session, ...items]);
    setActiveId(session.id);
    setMessages([]);
    setQuestion(null);
    setBusy(false);
    setDrawerOpen(false);
  }, []);

  const reconnect = useCallback(async () => {
    setError("");
    const [health, payload] = await Promise.all([
      fetchAssistantHealth(),
      fetchAssistantSessions(),
    ]);
    setOnline(health.ok);
    let items = payload.items;
    if (health.ok && items.length === 0) {
      items = [await createAssistantSession()];
    }
    setSessions(items);
    if (!activeIdRef.current && items[0]) setActiveId(items[0].id);
    if (!health.ok) setError(health.error || "XCA AI временно недоступен");
  }, []);

  useEffect(() => {
    if (!isAuthenticated()) {
      logout();
      router.replace("/login");
      return;
    }
    setAuthReady(true);
  }, [router]);

  useEffect(() => {
    if (!authReady) return;
    let active = true;
    reconnect()
      .catch((reason) => {
        if (active) {
          setOnline(false);
          setError(reason instanceof Error ? reason.message : "Не удалось подключиться к XCA AI");
        }
      })
      .finally(() => active && setLoading(false));
    return () => {
      active = false;
      messagesRequestRef.current?.abort();
    };
  }, [authReady, reconnect]);

  useEffect(() => {
    if (online !== false) return;
    let cancelled = false;
    let timer: number | undefined;
    const retry = async () => {
      await reconnect().catch(() => undefined);
      if (!cancelled) timer = window.setTimeout(retry, 15_000);
    };
    timer = window.setTimeout(retry, 15_000);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
    };
  }, [online, reconnect]);

  useEffect(() => {
    requestGenerationRef.current += 1;
    activeIdRef.current = activeId;
    messagesRequestRef.current?.abort();
    if (!activeId) {
      setMessages([]);
      return;
    }
    setLoading(true);
    setError("");
    loadMessages(activeId)
      .catch((reason) => {
        if (!messagesRequestRef.current?.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Не удалось загрузить чат");
        }
      })
      .finally(() => setLoading(false));
  }, [activeId, loadMessages]);

  useEffect(() => {
    if (!activeId || !busy) return;
    let cancelled = false;
    let timer: number | undefined;
    const poll = async () => {
      try {
        const stillBusy = await loadMessages(activeId);
        if (!stillBusy) {
          await refreshSessions().catch(() => undefined);
          return;
        }
      } catch (reason) {
        if (!cancelled && !messagesRequestRef.current?.signal.aborted) {
          setError(reason instanceof Error ? reason.message : "Ошибка получения ответа");
        }
      }
      if (!cancelled) timer = window.setTimeout(poll, 1600);
    };
    timer = window.setTimeout(poll, 1600);
    return () => {
      cancelled = true;
      if (timer !== undefined) window.clearTimeout(timer);
      requestGenerationRef.current += 1;
      messagesRequestRef.current?.abort();
    };
  }, [activeId, busy, loadMessages, refreshSessions]);

  const send = async () => {
    const text = draft.trim();
    if (!text || !activeId || busy) return;
    setDraft("");
    setError("");
    setMessages((items) => [
      ...items,
      { id: `local-${Date.now()}`, role: "user", text, images: [] },
    ]);
    setBusy(true);
    try {
      await sendAssistantMessage(activeId, text);
      await refreshSessions();
    } catch (reason) {
      setBusy(false);
      setError(reason instanceof Error ? reason.message : "Не удалось отправить сообщение");
      await loadMessages(activeId).catch(() => undefined);
    }
  };

  const removeSession = async (sessionId: string) => {
    if (!window.confirm("Удалить этот чат?")) return;
    setError("");
    try {
      await deleteAssistantSession(sessionId);
      const items = sessions.filter((session) => session.id !== sessionId);
      setSessions(items);
      if (activeId === sessionId) {
        setActiveId(items[0]?.id || "");
        setMessages([]);
      }
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось удалить чат");
    }
  };

  const stop = async () => {
    if (!activeId) return;
    requestGenerationRef.current += 1;
    messagesRequestRef.current?.abort();
    try {
      await cancelAssistantMessage(activeId);
      setBusy(false);
      await loadMessages(activeId);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось остановить запрос");
    }
  };

  const answerQuestion = async (answer: string) => {
    if (!activeId || !question) return;
    try {
      await replyAssistantQuestion(activeId, question.id, answer);
      setQuestion(null);
      setBusy(true);
    } catch (reason) {
      setError(reason instanceof Error ? reason.message : "Не удалось отправить уточнение");
    }
  };

  const sessionList = (
    <div className="flex h-full min-h-0 flex-col">
      <div className="flex items-center justify-between border-b border-slate-200 p-3 dark:border-slate-700">
        <span className="font-semibold">Чаты</span>
        <button type="button" onClick={addSession} disabled={!online} className="inline-flex h-11 w-11 items-center justify-center rounded-xl text-sky-600 hover:bg-sky-50 disabled:opacity-40 dark:hover:bg-slate-800" aria-label="Новый чат">
          <MessageSquarePlus size={21} />
        </button>
      </div>
      <div className="min-h-0 flex-1 overflow-y-auto p-2">
        {sessions.map((session) => (
          <div key={session.id} className={`mb-1 flex items-center rounded-xl ${session.id === activeId ? "bg-sky-50 dark:bg-sky-950/40" : "hover:bg-slate-50 dark:hover:bg-slate-800"}`}>
            <button type="button" onClick={() => { setActiveId(session.id); setDrawerOpen(false); }} className="min-h-11 min-w-0 flex-1 px-3 py-2 text-left">
              <span className="block truncate text-sm font-medium">{session.title}</span>
              <span className="text-xs text-slate-500">{session.busy ? "XCA анализирует…" : "Открыть чат"}</span>
            </button>
            <button type="button" onClick={() => removeSession(session.id)} className="inline-flex h-11 w-11 shrink-0 items-center justify-center text-slate-400 hover:text-red-500" aria-label="Удалить чат">
              <Trash2 size={17} />
            </button>
          </div>
        ))}
      </div>
    </div>
  );

  return (
    <AppShell title="XCA AI" subtitle="Бизнес-ассистент по активным данным showcase">
      <div className="flex h-[calc(100dvh-132px)] min-h-[520px] overflow-hidden rounded-2xl border border-slate-200 bg-slate-50 shadow-sm dark:border-slate-700 dark:bg-slate-950 sm:h-[min(76vh,760px)]">
        <aside className="hidden w-72 shrink-0 border-r border-slate-200 bg-white dark:border-slate-700 dark:bg-slate-900 lg:block">
          {sessionList}
        </aside>

        {drawerOpen ? (
          <div className="fixed inset-0 z-[70] lg:hidden" role="dialog" aria-modal="true" aria-label="Список чатов">
            <button type="button" onClick={() => setDrawerOpen(false)} className="absolute inset-0 bg-black/40" aria-label="Закрыть список чатов" />
            <div className="bi-safe-area absolute inset-y-0 left-0 w-[min(88vw,340px)] bg-white shadow-2xl dark:bg-slate-900">
              <button type="button" onClick={() => setDrawerOpen(false)} className="absolute right-2 top-2 z-10 inline-flex h-11 w-11 items-center justify-center rounded-xl" aria-label="Закрыть">
                <X size={22} />
              </button>
              {sessionList}
            </div>
          </div>
        ) : null}

        <section className="flex min-w-0 flex-1 flex-col">
          <div className="flex min-h-14 shrink-0 items-center gap-2 border-b border-slate-200 bg-white px-3 dark:border-slate-700 dark:bg-slate-900">
            <button type="button" onClick={() => setDrawerOpen(true)} className="inline-flex h-11 w-11 items-center justify-center rounded-xl lg:hidden" aria-label="Открыть список чатов">
              <Menu size={21} />
            </button>
            <Bot size={22} className="text-sky-600" />
            <div className="min-w-0 flex-1">
              <div className="truncate text-sm font-semibold">{sessions.find((session) => session.id === activeId)?.title || "XCA AI"}</div>
              <div className={`text-xs ${online ? "text-emerald-600" : "text-amber-600"}`}>{online ? "Подключён к активной БД" : "Нет подключения"}</div>
            </div>
            {online === false ? (
              <button type="button" onClick={() => reconnect().catch(() => undefined)} className="inline-flex h-11 w-11 items-center justify-center rounded-xl text-amber-600" aria-label="Повторить подключение">
                <RefreshCw size={19} />
              </button>
            ) : null}
            <button type="button" onClick={addSession} disabled={!online} className="inline-flex h-11 w-11 items-center justify-center rounded-xl text-sky-600 disabled:opacity-40 lg:hidden" aria-label="Новый чат">
              <MessageSquarePlus size={21} />
            </button>
          </div>

          <div className="min-h-0 flex-1 space-y-4 overflow-y-auto overscroll-contain px-3 py-4 sm:px-5">
            {!messages.length && !loading ? (
              <div className="mx-auto mt-8 max-w-md text-center text-slate-500">
                <Bot className="mx-auto mb-3 text-sky-500" size={38} />
                <p className="font-semibold text-slate-700 dark:text-slate-200">Спросите XCA AI о проектах</p>
                <p className="mt-1 text-sm">Финансы, сроки, ресурсы, предписания и документация анализируются по активной showcase БД.</p>
              </div>
            ) : null}
            {messages.map((message) => <Message key={message.id || `${message.role}-${message.created_at}`} message={message} />)}
            {busy ? <div className="flex items-center gap-2 text-sm text-slate-500"><span className="h-2 w-2 animate-pulse rounded-full bg-sky-500" />XCA анализирует данные…</div> : null}
            <div ref={bottomRef} />
          </div>

          {question ? (
            <div className="shrink-0 border-t border-amber-200 bg-amber-50 px-3 py-3 dark:border-amber-900 dark:bg-amber-950/30">
              <p className="mb-2 text-sm font-medium">{question.text}</p>
              <div className="flex flex-wrap gap-2">
                {question.options.map((option) => (
                  <button key={option.value} type="button" onClick={() => answerQuestion(option.value)} className="min-h-11 rounded-xl border border-amber-300 bg-white px-3 text-sm dark:border-amber-800 dark:bg-slate-900">
                    {option.label}
                  </button>
                ))}
              </div>
            </div>
          ) : null}

          {error ? <div className="shrink-0 border-t border-red-200 bg-red-50 px-3 py-2 text-sm text-red-700 dark:border-red-900 dark:bg-red-950/30 dark:text-red-300">{error}</div> : null}

          <div className="shrink-0 border-t border-slate-200 bg-white p-2 pb-[max(0.5rem,env(safe-area-inset-bottom))] dark:border-slate-700 dark:bg-slate-900 sm:p-3">
            <div className="flex items-end gap-2">
              <textarea
                value={draft}
                onChange={(event) => setDraft(event.target.value)}
                onKeyDown={(event) => {
                  if (event.key === "Enter" && !event.shiftKey) {
                    event.preventDefault();
                    send();
                  }
                }}
                rows={1}
                disabled={!activeId || !online}
                placeholder={online ? "Спросите о данных…" : "XCA AI недоступен"}
                className="max-h-36 min-h-11 min-w-0 flex-1 resize-none rounded-xl border border-slate-300 bg-white px-3 py-2.5 text-base outline-none focus:border-sky-500 focus:ring-2 focus:ring-sky-200 disabled:opacity-60 dark:border-slate-600 dark:bg-slate-950 dark:focus:ring-sky-900 sm:text-sm"
              />
              {busy ? (
                <button type="button" onClick={stop} className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-slate-800 text-white" aria-label="Остановить">
                  <Square size={17} fill="currentColor" />
                </button>
              ) : (
                <button type="button" onClick={send} disabled={!draft.trim() || !activeId || !online} className="inline-flex h-11 w-11 shrink-0 items-center justify-center rounded-xl bg-sky-600 text-white disabled:opacity-40" aria-label="Отправить">
                  <Send size={19} />
                </button>
              )}
            </div>
            <p className="mt-1 hidden text-center text-[11px] text-slate-400 sm:block">Enter — отправить · Shift+Enter — новая строка</p>
          </div>
        </section>
      </div>
    </AppShell>
  );
}

type StubMessage = { role: "user" | "assistant"; text: string };

function stubReply(question: string): string {
  const value = question.trim().toLowerCase();
  if (value.includes("предписан")) {
    return "Предписания: меню → «Предписания по подрядчикам». Там доступны KPI, статусы и просрочки.";
  }
  if (value.includes("гдрс") || value.includes("ресурс") || value.includes("техник")) {
    return "ГДРС: разделы «Люди» и «Техника» показывают план/факт ресурсов.";
  }
  if (value.includes("бддс") || value.includes("бдр") || value.includes("бюджет") || value.includes("финанс")) {
    return "Финансовые отчёты находятся в разделе «Финансы»: БДДС, БДР, утверждённый бюджет и план/факт.";
  }
  if (value.includes("срок") || value.includes("график") || value.includes("отклон")) {
    return "Раздел «Сроки» содержит контрольные точки, график проекта и причины отклонений.";
  }
  if (value.includes("документ") || value.includes("пд") || value.includes("рд")) {
    return "Проектная, рабочая и исполнительная документация доступны отдельными пунктами меню.";
  }
  return "Это локальный демо-навигатор. Спросите про финансы, сроки, ГДРС, документацию или предписания.";
}

function StubAiAssistantView() {
  const [messages, setMessages] = useState<StubMessage[]>([
    {
      role: "assistant",
      text: "Локальный демо-навигатор по отчётам showcase. Полный XCA AI доступен на задеплоенном стенде.",
    },
  ]);
  const [draft, setDraft] = useState("");

  const send = () => {
    const text = draft.trim();
    if (!text) return;
    setMessages((items) => [
      ...items,
      { role: "user", text },
      { role: "assistant", text: stubReply(text) },
    ]);
    setDraft("");
  };

  return (
    <AppShell title="ИИ помощник" subtitle="Локальный демо-навигатор">
      <div className="mx-auto flex h-[min(72vh,680px)] max-w-3xl flex-col overflow-hidden rounded-2xl border border-slate-200 bg-white shadow-sm dark:border-slate-700 dark:bg-slate-900">
        <div className="border-b border-slate-200 px-4 py-3 text-sm text-slate-500 dark:border-slate-700">
          Демо-режим: навигация по разделам без подключения к данным и внешним AI-сервисам.
        </div>
        <div className="min-h-0 flex-1 space-y-3 overflow-y-auto p-4">
          {messages.map((message, index) => (
            <div
              key={`${message.role}-${index}`}
              className={`max-w-[90%] rounded-2xl px-4 py-3 text-sm ${
                message.role === "user"
                  ? "ml-auto rounded-br-md bg-sky-600 text-white"
                  : "rounded-bl-md bg-slate-100 text-slate-800 dark:bg-slate-800 dark:text-slate-100"
              }`}
            >
              {message.text}
            </div>
          ))}
        </div>
        <div className="flex gap-2 border-t border-slate-200 p-3 pb-[max(0.75rem,env(safe-area-inset-bottom))] dark:border-slate-700">
          <input
            value={draft}
            onChange={(event) => setDraft(event.target.value)}
            onKeyDown={(event) => {
              if (event.key === "Enter") send();
            }}
            placeholder="Например: где посмотреть финансы?"
            className="min-h-11 min-w-0 flex-1 rounded-xl border border-slate-300 bg-white px-3 text-base dark:border-slate-600 dark:bg-slate-950 sm:text-sm"
          />
          <button type="button" onClick={send} className="inline-flex h-11 w-11 items-center justify-center rounded-xl bg-sky-600 text-white" aria-label="Отправить">
            <Send size={19} />
          </button>
        </div>
      </div>
    </AppShell>
  );
}

export function AiAssistantView() {
  return process.env.NEXT_PUBLIC_AI_MODE === "full"
    ? <FullAiAssistantView />
    : <StubAiAssistantView />;
}
