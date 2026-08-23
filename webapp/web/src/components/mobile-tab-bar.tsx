"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useEffect, useState } from "react";
import { findNavItem } from "@/lib/nav";
import { tapFeedback } from "@/lib/haptics";

/** Ниже этого скролла «Вверх» бесполезна — гасим её, но место в панели держим. */
const SCROLL_TOP_AFTER_PX = 280;

function IconMenu() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M4 6.5h16M4 12h16M4 17.5h16" strokeLinecap="round" />
    </svg>
  );
}

function IconArrowUp() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M12 19.5V5" strokeLinecap="round" />
      <path d="M5.5 11.5L12 5l6.5 6.5" strokeLinecap="round" strokeLinejoin="round" />
    </svg>
  );
}

function IconSearch() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path d="M4 6h11M4 12h7M4 18h5" strokeLinecap="round" />
      <circle cx="17" cy="15" r="4" />
      <path d="M20 18l2.5 2.5" strokeLinecap="round" />
    </svg>
  );
}

function IconAi() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <path
        d="M12 3l1.7 4.6L18.5 9l-4.8 1.4L12 15l-1.7-4.6L5.5 9l4.8-1.4L12 3z"
        strokeLinejoin="round"
      />
      <path d="M18.5 15.5l.8 2.2 2.2.8-2.2.8-.8 2.2-.8-2.2-2.2-.8 2.2-.8.8-2.2z" strokeLinejoin="round" />
    </svg>
  );
}

function IconProfile() {
  return (
    <svg viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.8" aria-hidden>
      <circle cx="12" cy="8.5" r="3.5" />
      <path d="M4.5 20c1.4-3.4 4.1-5 7.5-5s6.1 1.6 7.5 5" strokeLinecap="round" />
    </svg>
  );
}

/**
 * Нижняя навигация — только мобильный вьюпорт (`lg:hidden`, стили в
 * `@media (max-width: 1023px)`). Desktop-раскладка не меняется.
 */
export function MobileTabBar({
  onOpenMenu,
  menuOpen = false,
  onOpenSearch,
}: {
  onOpenMenu: () => void;
  menuOpen?: boolean;
  onOpenSearch: () => void;
}) {
  const pathname = usePathname();
  const [canScrollUp, setCanScrollUp] = useState(false);

  useEffect(() => {
    const sync = () => {
      const y =
        window.scrollY ||
        document.documentElement.scrollTop ||
        document.body.scrollTop ||
        0;
      setCanScrollUp(y > SCROLL_TOP_AFTER_PX);
    };
    sync();
    window.addEventListener("scroll", sync, { passive: true });
    return () => window.removeEventListener("scroll", sync);
  }, []);

  const searchActive = Boolean(findNavItem(pathname)) && !menuOpen;
  const aiActive = pathname.startsWith("/ai-assistant");
  const profileActive = pathname.startsWith("/settings");

  const externalAi = process.env.NEXT_PUBLIC_AI_MODE === "full";
  const aiHref = externalAi
    ? process.env.NEXT_PUBLIC_OPENCODE_URL ||
      "https://opencode.conall.ru/L3dvcmtzcGFjZQ/session"
    : "/ai-assistant";

  const itemClass = (on: boolean) =>
    `bi-tabbar-item${on ? " bi-tabbar-item-on" : ""}`;

  return (
    <nav className="bi-tabbar lg:hidden" aria-label="Основная навигация">
      <button
        type="button"
        onClick={() => {
          tapFeedback();
          onOpenMenu();
        }}
        className={itemClass(menuOpen)}
        aria-expanded={menuOpen}
      >
        <span className="bi-tabbar-icon">
          <IconMenu />
        </span>
        <span className="bi-tabbar-label">Меню</span>
      </button>

      <button
        type="button"
        onClick={() => {
          tapFeedback();
          onOpenSearch();
        }}
        className={itemClass(searchActive)}
      >
        <span className="bi-tabbar-icon">
          <IconSearch />
        </span>
        <span className="bi-tabbar-label">Поиск</span>
      </button>

      <Link
        href={aiHref}
        target={externalAi ? "_blank" : undefined}
        rel={externalAi ? "noopener noreferrer" : undefined}
        onClick={() => tapFeedback()}
        className={itemClass(aiActive)}
        aria-current={aiActive ? "page" : undefined}
      >
        <span className="bi-tabbar-icon">
          <IconAi />
          {externalAi ? (
            <span className="bi-tabbar-ext" aria-hidden>
              ↗
            </span>
          ) : null}
        </span>
        <span className="bi-tabbar-label">
          ИИ
          {externalAi ? (
            <span className="sr-only"> (откроется в новой вкладке)</span>
          ) : null}
        </span>
      </Link>

      <Link
        href="/settings/profile"
        onClick={() => tapFeedback()}
        className={itemClass(profileActive)}
        aria-current={profileActive ? "page" : undefined}
      >
        <span className="bi-tabbar-icon">
          <IconProfile />
        </span>
        <span className="bi-tabbar-label">Профиль</span>
      </Link>

      <button
        type="button"
        disabled={!canScrollUp}
        onClick={() => {
          tapFeedback();
          window.scrollTo({ top: 0, behavior: "smooth" });
        }}
        className={`bi-tabbar-item${canScrollUp ? "" : " bi-tabbar-item-mute"}`}
        aria-label="Наверх страницы"
      >
        <span className="bi-tabbar-icon">
          <IconArrowUp />
        </span>
        <span className="bi-tabbar-label">Вверх</span>
      </button>
    </nav>
  );
}
