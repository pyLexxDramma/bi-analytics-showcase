const AUTH_KEY = "bi_showcase_auth";
const AUTH_USER_KEY = "bi_showcase_user";
const AUTH_ROLE_KEY = "bi_showcase_role";
const AUTH_ROLE_LABEL_KEY = "bi_showcase_role_label";
const AUTH_EMAIL_KEY = "bi_showcase_email";

/** Стендовый суперадмин (как на скринах main / seed users.db). */
export const STAND_ADMIN: AuthUser = {
  username: "admin",
  role: "superadmin",
  role_label: "Суперадминистратор",
  email: "admin@example.com",
};

export type AuthUser = {
  username: string;
  role: string;
  role_label: string;
  email?: string | null;
};

function readStorage(key: string): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

function isLegacyDemoSession(username: string, role: string): boolean {
  const u = username.trim().toLowerCase();
  const r = role.trim().toLowerCase();
  return u === "demo" || u === "" || r === "demo" || r === "analyst" && u === "demo";
}

export function isAuthenticated(): boolean {
  return readStorage(AUTH_KEY) === "1" && !!readStorage(AUTH_USER_KEY);
}

export function getAuthUser(): string {
  return getAuthSession()?.username || "";
}

export function getAuthSession(): AuthUser | null {
  if (typeof window === "undefined") return null;
  if (readStorage(AUTH_KEY) !== "1") return null;
  const username = readStorage(AUTH_USER_KEY);
  if (!username) return null;
  const role = readStorage(AUTH_ROLE_KEY) || "";
  if (isLegacyDemoSession(username, role)) {
    saveAuthSession(STAND_ADMIN);
    return { ...STAND_ADMIN };
  }
  return {
    username,
    role: role || "analyst",
    role_label: readStorage(AUTH_ROLE_LABEL_KEY) || role || "Аналитик",
    email: readStorage(AUTH_EMAIL_KEY) || null,
  };
}

export function saveAuthSession(user: AuthUser): void {
  window.localStorage.setItem(AUTH_KEY, "1");
  window.localStorage.setItem(AUTH_USER_KEY, user.username);
  window.localStorage.setItem(AUTH_ROLE_KEY, user.role);
  window.localStorage.setItem(AUTH_ROLE_LABEL_KEY, user.role_label);
  if (user.email) {
    window.localStorage.setItem(AUTH_EMAIL_KEY, user.email);
  } else {
    window.localStorage.removeItem(AUTH_EMAIL_KEY);
  }
  document.cookie = `${AUTH_KEY}=1; path=/; max-age=${60 * 60 * 24 * 30}; SameSite=Lax`;
}

export function loginDemo(username: string): AuthUser {
  const name = username.trim().toLowerCase();
  // Пустой/demo/любой «гостевой» вход на стенде → admin / суперадмин
  if (!name || name === "demo" || name === "admin") {
    saveAuthSession(STAND_ADMIN);
    return { ...STAND_ADMIN };
  }
  const user: AuthUser = {
    username: username.trim(),
    role: "analyst",
    role_label: "Аналитик",
    email: null,
  };
  saveAuthSession(user);
  return user;
}

/** @deprecated use saveAuthSession */
export function login(username: string): void {
  loginDemo(username);
}

export function logout(): void {
  window.localStorage.removeItem(AUTH_KEY);
  window.localStorage.removeItem(AUTH_USER_KEY);
  window.localStorage.removeItem(AUTH_ROLE_KEY);
  window.localStorage.removeItem(AUTH_ROLE_LABEL_KEY);
  window.localStorage.removeItem(AUTH_EMAIL_KEY);
  document.cookie = `${AUTH_KEY}=; path=/; max-age=0; SameSite=Lax`;
}

export function authHeaders(): Record<string, string> {
  const user = getAuthSession()?.username;
  return user ? { "X-Auth-User": user } : {};
}

export function isAdminRole(role: string | undefined): boolean {
  const r = (role || "").toLowerCase();
  return r === "admin" || r === "superadmin";
}
