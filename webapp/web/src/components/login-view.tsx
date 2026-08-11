"use client";

import { FormEvent, useEffect, useState } from "react";
import { useRouter } from "next/navigation";
import { ConstructionAnalyticsScene } from "@/components/construction-analytics-scene";
import { fetchAuthMe, fetchAuthStatus, postAuthLogin } from "@/lib/api";
import { isAuthenticated, logout, saveAuthSession } from "@/lib/auth";

export function LoginView() {
  const router = useRouter();
  const [username, setUsername] = useState("");
  const [password, setPassword] = useState("");
  const [showPassword, setShowPassword] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [hint, setHint] = useState<string | null>(null);
  const [busy, setBusy] = useState(false);
  const [initialized, setInitialized] = useState<boolean | null>(null);
  const [checkingSession, setCheckingSession] = useState(true);

  useEffect(() => {
    let cancelled = false;
    void (async () => {
      try {
        const status = await fetchAuthStatus();
        if (!cancelled) setInitialized(status.initialized);
      } catch {
        if (!cancelled) setInitialized(null);
      }

      if (!isAuthenticated()) {
        if (!cancelled) setCheckingSession(false);
        return;
      }

      // Не доверяем только флагу в localStorage — сверяем токен с API.
      try {
        await fetchAuthMe();
        if (!cancelled) router.replace("/developer-projects");
      } catch {
        logout();
        if (!cancelled) {
          setError("Сессия истекла или недействительна. Войдите снова.");
          setCheckingSession(false);
        }
      }
    })();
    return () => {
      cancelled = true;
    };
  }, [router]);

  const onSubmit = async (event: FormEvent) => {
    event.preventDefault();
    setError(null);
    setHint(null);
    if (!username.trim() || !password) {
      setError("Введите имя пользователя и пароль");
      return;
    }
    setBusy(true);
    try {
      const result = await postAuthLogin(username.trim(), password);
      saveAuthSession(result.user, result.token);
      router.replace("/developer-projects");
    } catch {
      setError("Неверное имя пользователя или пароль");
    } finally {
      setBusy(false);
    }
  };

  if (checkingSession) {
    return (
      <div className="login-page relative flex min-h-full items-center justify-center overflow-hidden px-4 py-10">
        <ConstructionAnalyticsScene />
        <p className="relative z-10 text-sm text-slate-600">Проверка сессии…</p>
      </div>
    );
  }

  return (
    <div className="login-page relative flex min-h-full items-center justify-center overflow-hidden px-4 py-10">
      <ConstructionAnalyticsScene />

      <div className="relative z-10 w-full max-w-[380px]">
        <div className="login-card rounded-2xl border border-white/60 bg-white/90 p-8 shadow-[0_24px_60px_rgba(15,40,70,0.18)] backdrop-blur-md">
          <h1 className="login-brand text-center text-[28px] font-extrabold tracking-tight text-[#0f2744]">
            BI Analytics
          </h1>
          <p className="mt-2 text-center text-sm text-slate-500">
            {initialized === false
              ? "Система ещё не инициализирована"
              : "Строительная аналитика"}
          </p>

          <form className="mt-8 space-y-3" onSubmit={(e) => void onSubmit(e)}>
            <label className="block">
              <span className="sr-only">Имя пользователя</span>
              <input
                className="login-input w-full rounded-xl border border-slate-200 bg-white px-4 py-3 text-[15px] text-[#0f2744] outline-none transition placeholder:text-slate-400 focus:border-teal-400 focus:ring-2 focus:ring-teal-200"
                placeholder="Имя пользователя"
                autoComplete="username"
                value={username}
                onChange={(e) => setUsername(e.target.value)}
              />
            </label>

            <label className="relative block">
              <span className="sr-only">Пароль</span>
              <input
                className="login-input w-full rounded-xl border border-slate-200 bg-white px-4 py-3 pr-12 text-[15px] text-[#0f2744] outline-none transition placeholder:text-slate-400 focus:border-teal-400 focus:ring-2 focus:ring-teal-200"
                placeholder="Пароль"
                type={showPassword ? "text" : "password"}
                autoComplete="current-password"
                value={password}
                onChange={(e) => setPassword(e.target.value)}
              />
              <button
                type="button"
                className="absolute right-2 top-1/2 flex h-8 w-8 -translate-y-1/2 items-center justify-center rounded-md bg-[#0f2744] text-white"
                aria-label={showPassword ? "Скрыть пароль" : "Показать пароль"}
                onClick={() => setShowPassword((v) => !v)}
              >
                {showPassword ? "🙈" : "👁"}
              </button>
            </label>

            {error ? (
              <p className="text-sm font-medium text-rose-600">{error}</p>
            ) : null}
            {hint ? (
              <p className="text-sm font-medium text-teal-700">{hint}</p>
            ) : null}

            <button
              type="submit"
              disabled={busy}
              className="login-btn-primary relative mt-2 flex w-full items-center justify-center overflow-hidden rounded-xl bg-gradient-to-r from-[#b7f0c5] to-[#9be6b0] px-4 py-3 text-[15px] font-bold text-[#0f2744] transition hover:brightness-105 disabled:opacity-70"
            >
              <span className="absolute left-0 top-0 h-full w-1.5 bg-[#2e7d4f]" />
              {busy ? "Вход…" : "Войти"}
            </button>

            <button
              type="button"
              className="login-btn-secondary w-full rounded-xl bg-[#e8f7ec] px-4 py-3 text-[15px] font-bold text-[#0f2744] transition hover:bg-[#dcf3e3]"
              onClick={() =>
                setHint("Для восстановления доступа обратитесь к администратору.")
              }
            >
              Забыли пароль?
            </button>
          </form>
        </div>
      </div>
    </div>
  );
}
