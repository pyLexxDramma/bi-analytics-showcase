const ADMIN_TOKEN_KEY = "bi_showcase_admin_token";

export function getAdminToken(): string {
  if (typeof window === "undefined") return "";
  try {
    const stored = window.localStorage.getItem(ADMIN_TOKEN_KEY);
    if (stored) return stored;
  } catch {
    /* ignore */
  }
  return (process.env.NEXT_PUBLIC_WEBAPP_ADMIN_TOKEN || "").trim();
}

export function setAdminToken(token: string): void {
  window.localStorage.setItem(ADMIN_TOKEN_KEY, token.trim());
}

export function clearAdminToken(): void {
  window.localStorage.removeItem(ADMIN_TOKEN_KEY);
}
