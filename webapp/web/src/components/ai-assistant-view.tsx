"use client";

import { useEffect, useRef, useState } from "react";
import { Card, Text, Title } from "@tremor/react";
import { AppShell } from "@/components/app-shell";

type Msg = { role: "user" | "assistant"; text: string };

const STARTER: Msg = {
  role: "assistant",
  text:
    "Демо-помощник showcase. Полный OpenCode-агент — на Streamlit (ai.conall.ru). " +
    "Спросите, например: «какие отчёты есть» или «где предписания».",
};

function replyFor(q: string): string {
  const s = q.trim().toLowerCase();
  if (!s) return "Напишите вопрос про отчёты или данные.";
  if (s.includes("предписан")) {
    return "Предписания: меню → «Предписания по подрядчикам» (/prescriptions). KPI, статусы TESSA, просрочки.";
  }
  if (s.includes("исполнител") || s.includes(" ид") || s.endsWith("ид") || s.includes("комплект")) {
    return "Исполнительная документация: /executive-docs — статусы ИД, просрочки подрядчика/заказчика, динамика.";
  }
  if (s.includes("гдрс") || s.includes("ресурс") || s.includes("техник") || s.includes("люд")) {
    return "ГДРС: /gdrs/people и /gdrs/equipment — план/факт по людям и технике.";
  }
  if (s.includes("бддс") || s.includes("бдр") || s.includes("бюджет") || s.includes("финанс")) {
    return "Финансы: /finance/bdds, /finance/bdr, approved-budget, bdds-plan-fact.";
  }
  if (s.includes("срок") || s.includes("график") || s.includes("контрольн") || s.includes("отклон")) {
    return "Сроки: control-points, project-schedule, deviation-reasons, baseline-deviation в разделе «Сроки».";
  }
  if (s.includes("ftp") || s.includes("синхр") || s.includes("данн") || s.includes("admin")) {
    return "Данные: Админ-панель /settings/admin — статус web/ и POST FTP sync (нужен WEBAPP_ADMIN_TOKEN).";
  }
  if (s.includes("отчёт") || s.includes("меню") || s.includes("список") || s.includes("что есть")) {
    return (
      "Готовые отчёты: девелоперские проекты, финансы (4), сроки (4), ПД/РД, ГДРС (2), " +
      "предписания, ИД, дебиторка. Заглушек в отчётах больше нет."
    );
  }
  return (
    "Это демо-ответы без LLM. Для аналитики по цифрам используйте экраны в меню " +
    "или ИИ в Streamlit (OpenCode). Попробуйте: «финансы», «гдрс», «предписания»."
  );
}

export function AiAssistantView() {
  const [messages, setMessages] = useState<Msg[]>([STARTER]);
  const [draft, setDraft] = useState("");
  const bottomRef = useRef<HTMLDivElement | null>(null);

  useEffect(() => {
    bottomRef.current?.scrollIntoView({ behavior: "smooth" });
  }, [messages]);

  const send = () => {
    const text = draft.trim();
    if (!text) return;
    setDraft("");
    setMessages((m) => [
      ...m,
      { role: "user", text },
      { role: "assistant", text: replyFor(text) },
    ]);
  };

  return (
    <AppShell
      title="ИИ помощник"
      subtitle="Демо-навигатор по отчётам · без OpenCode в Next"
    >
      <Card className="mb-4 rounded-xl border-l-4 border-l-sky-500">
        <Text>
          Полноценный агент с доступом к БД — в Streamlit. Здесь — быстрые
          подсказки по разделам showcase.
        </Text>
      </Card>

      <Card className="flex h-[min(70vh,640px)] flex-col rounded-xl p-0 overflow-hidden">
        <div className="border-b border-tremor-border px-4 py-3 dark:border-dark-tremor-border">
          <Title className="!text-tremor-content-strong dark:!text-dark-tremor-content-strong">
            Чат
          </Title>
        </div>
        <div className="flex-1 space-y-3 overflow-y-auto px-4 py-4">
          {messages.map((m, i) => (
            <div
              key={`${m.role}-${i}`}
              className={`max-w-[90%] rounded-lg px-3 py-2 text-sm ${
                m.role === "user"
                  ? "ml-auto bg-sky-600 text-white"
                  : "bg-tremor-background-muted text-tremor-content-strong dark:bg-dark-tremor-background-muted dark:text-dark-tremor-content-strong"
              }`}
            >
              {m.text}
            </div>
          ))}
          <div ref={bottomRef} />
        </div>
        <div className="flex gap-2 border-t border-tremor-border p-3 dark:border-dark-tremor-border">
          <input
            className="w-full rounded-tremor-default border border-tremor-border bg-tremor-background px-3 py-2 text-tremor-default dark:border-dark-tremor-border dark:bg-dark-tremor-background"
            placeholder="Вопрос про отчёты…"
            value={draft}
            onChange={(e) => setDraft(e.target.value)}
            onKeyDown={(e) => {
              if (e.key === "Enter") send();
            }}
          />
          <button
            type="button"
            className="rounded-tremor-default bg-sky-600 px-4 py-2 font-medium text-white"
            onClick={send}
          >
            Отправить
          </button>
        </div>
      </Card>
    </AppShell>
  );
}
