"use client";

import { useCallback, useEffect, useState } from "react";
import { usePathname, useRouter } from "next/navigation";
import { postAskAiLink } from "@/lib/api";
import {
  canAccessReport,
  getAuthSession,
  isAuthenticated,
  type AuthUser,
} from "@/lib/auth";
import {
  ASK_AI_SCREENS,
  collectAskAiFiltersFromSearch,
  defaultAskAiCtx,
  defaultAskAiQuestion,
} from "@/lib/ask-ai-reports";
import { findNavItem } from "@/lib/nav";
import { tapFeedback } from "@/lib/haptics";

type AskAiVariant = "desktop" | "chip";

/** Shared action for desktop header, chip and mobile tab bar. */
export function useAskAiAction() {
  const pathname = usePathname();
  const router = useRouter();
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [session, setSession] = useState<AuthUser | null>(null);

  useEffect(() => {
    setSession(getAuthSession());
  }, [pathname]);

  const nav = findNavItem(pathname);
  const screen = nav ? ASK_AI_SCREENS[nav.id] : undefined;
  const available = Boolean(
    nav && screen && canAccessReport(nav.id, session),
  );

  const run = useCallback(async () => {
    if (!nav || !screen) return;
    tapFeedback();
    setError(null);
    if (!isAuthenticated()) {
      router.push("/login");
      return;
    }
    const popup = window.open("about:blank", "_blank");
    setBusy(true);
    try {
      // В момент клика — фактический адрес страницы (не React searchParams).
      const slice = collectAskAiFiltersFromSearch(window.location.search || "");
      const { url } = await postAskAiLink({
        nav_id: nav.id,
        report: screen.report,
        q: defaultAskAiQuestion(screen.title),
        ctx: defaultAskAiCtx(screen),
        project: slice.project,
        period: slice.period,
        filters: slice.filters,
        src: screen.src,
      });
      if (popup && !popup.closed) {
        popup.location.replace(url);
      } else {
        window.open(url, "_blank", "noopener,noreferrer");
      }
    } catch (err) {
      if (popup && !popup.closed) popup.close();
      setError(err instanceof Error ? err.message : "Не удалось открыть ИИ");
    } finally {
      setBusy(false);
    }
  }, [nav, screen, router]);

  return { available, busy, error, run };
}

function AskAiControl({ variant }: { variant: AskAiVariant }) {
  const { available, busy, error, run } = useAskAiAction();
  if (!available) return null;

  if (variant === "chip") {
    return (
      <div className="inline-flex max-w-full flex-col items-start gap-0.5 lg:hidden">
        <button
          type="button"
          onClick={() => void run()}
          disabled={busy}
          title="Спросить ИИ по этому дашборду"
          aria-label="Спросить ИИ по этому дашборду"
          className="ask-ai-btn inline-flex h-10 shrink-0 items-center gap-1.5 rounded-tremor-default px-3 text-sm font-bold transition disabled:cursor-wait"
        >
          <span aria-hidden className="text-sm leading-none">
            ✦
          </span>
          <span>{busy ? "…" : "Спросить ИИ"}</span>
        </button>
        {error ? (
          <p className="max-w-[10rem] text-left text-[10px] leading-tight text-red-600 dark:text-red-400">
            {error}
          </p>
        ) : null}
      </div>
    );
  }

  return (
    <div className="hidden lg:flex lg:flex-col lg:items-end lg:gap-1">
      <button
        type="button"
        onClick={() => void run()}
        disabled={busy}
        title="Спросить ИИ по этому дашборду"
        className="ask-ai-btn inline-flex h-11 items-center gap-2 rounded-tremor-default px-4 text-tremor-default transition disabled:cursor-wait"
      >
        <span aria-hidden className="text-base leading-none">
          ✦
        </span>
        {busy ? "Открываю…" : "Спросить ИИ"}
      </button>
      {error ? (
        <p className="max-w-[14rem] text-right text-xs text-red-600 dark:text-red-400">
          {error}
        </p>
      ) : null}
    </div>
  );
}

/** Desktop: полная кнопка в правой части шапки. */
export function AskAiButton() {
  return <AskAiControl variant="desktop" />;
}

/** Mobile: переливающаяся кнопка в правом верхнем углу шапки (как desktop). */
export function AskAiTitleChip() {
  return <AskAiControl variant="chip" />;
}
