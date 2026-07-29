const AUTH_KEY = "bi_showcase_auth";
const AUTH_USER_KEY = "bi_showcase_user";

export function isAuthenticated(): boolean {
  if (typeof window === "undefined") return false;
  try {
    return window.localStorage.getItem(AUTH_KEY) === "1";
  } catch {
    return false;
  }
}

export function getAuthUser(): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(AUTH_USER_KEY) || "";
  } catch {
    return "";
  }
}

export function login(username: string): void {
  window.localStorage.setItem(AUTH_KEY, "1");
  window.localStorage.setItem(AUTH_USER_KEY, username.trim() || "demo");
  document.cookie = `${AUTH_KEY}=1; path=/; max-age=${60 * 60 * 24 * 30}; SameSite=Lax`;
}

export function logout(): void {
  window.localStorage.removeItem(AUTH_KEY);
  window.localStorage.removeItem(AUTH_USER_KEY);
  document.cookie = `${AUTH_KEY}=; path=/; max-age=0; SameSite=Lax`;
}
