const AUTH_KEY = "bi_showcase_auth";
const AUTH_USER_KEY = "bi_showcase_user";
const AUTH_ROLE_KEY = "bi_showcase_role";
const AUTH_ROLE_LABEL_KEY = "bi_showcase_role_label";
const AUTH_EMAIL_KEY = "bi_showcase_email";
const AUTH_TOKEN_KEY = "bi_showcase_token";
const AUTH_ALLOWED_REPORTS_KEY = "bi_showcase_allowed_reports";
const AUTH_CAN_ADMIN_KEY = "bi_showcase_can_admin";

export type AuthUser = {
  username: string;
  role: string;
  role_label: string;
  email?: string | null;
  allowed_reports?: string[];
  can_admin?: boolean;
};

function readStorage(key: string): string {
  if (typeof window === "undefined") return "";
  try {
    return window.localStorage.getItem(key) || "";
  } catch {
    return "";
  }
}

export function isAuthenticated(): boolean {
  return (
    readStorage(AUTH_KEY) === "1" &&
    !!readStorage(AUTH_USER_KEY) &&
    !!readStorage(AUTH_TOKEN_KEY)
  );
}

export function getAuthUser(): string {
  return getAuthSession()?.username || "";
}

function readAllowedReports(): string[] | undefined {
  const raw = readStorage(AUTH_ALLOWED_REPORTS_KEY);
  if (!raw) return undefined;
  try {
    const parsed = JSON.parse(raw);
    if (Array.isArray(parsed)) {
      return parsed.map((x) => String(x));
    }
  } catch {
    /* ignore */
  }
  return undefined;
}

export function getAuthSession(): AuthUser | null {
  if (typeof window === "undefined") return null;
  if (readStorage(AUTH_KEY) !== "1") return null;
  const username = readStorage(AUTH_USER_KEY);
  if (!username) return null;
  const role = readStorage(AUTH_ROLE_KEY) || "";
  const canAdminRaw = readStorage(AUTH_CAN_ADMIN_KEY);
  return {
    username,
    role: role || "analyst",
    role_label: readStorage(AUTH_ROLE_LABEL_KEY) || role || "Аналитик",
    email: readStorage(AUTH_EMAIL_KEY) || null,
    allowed_reports: readAllowedReports(),
    can_admin:
      canAdminRaw === "1"
        ? true
        : canAdminRaw === "0"
          ? false
          : undefined,
  };
}

export function saveAuthSession(user: AuthUser, token?: string): void {
  window.localStorage.setItem(AUTH_KEY, "1");
  window.localStorage.setItem(AUTH_USER_KEY, user.username);
  window.localStorage.setItem(AUTH_ROLE_KEY, user.role);
  window.localStorage.setItem(AUTH_ROLE_LABEL_KEY, user.role_label);
  if (user.email) {
    window.localStorage.setItem(AUTH_EMAIL_KEY, user.email);
  } else {
    window.localStorage.removeItem(AUTH_EMAIL_KEY);
  }
  if (user.allowed_reports) {
    window.localStorage.setItem(
      AUTH_ALLOWED_REPORTS_KEY,
      JSON.stringify(user.allowed_reports),
    );
  } else {
    window.localStorage.removeItem(AUTH_ALLOWED_REPORTS_KEY);
  }
  if (user.can_admin !== undefined) {
    window.localStorage.setItem(AUTH_CAN_ADMIN_KEY, user.can_admin ? "1" : "0");
  } else {
    window.localStorage.removeItem(AUTH_CAN_ADMIN_KEY);
  }
  if (token !== undefined) {
    if (token) {
      window.localStorage.setItem(AUTH_TOKEN_KEY, token);
    } else {
      window.localStorage.removeItem(AUTH_TOKEN_KEY);
    }
  }
  document.cookie = `${AUTH_KEY}=1; path=/; max-age=${60 * 60 * 24 * 30}; SameSite=Lax`;
}

export function logout(): void {
  window.localStorage.removeItem(AUTH_KEY);
  window.localStorage.removeItem(AUTH_USER_KEY);
  window.localStorage.removeItem(AUTH_ROLE_KEY);
  window.localStorage.removeItem(AUTH_ROLE_LABEL_KEY);
  window.localStorage.removeItem(AUTH_EMAIL_KEY);
  window.localStorage.removeItem(AUTH_TOKEN_KEY);
  window.localStorage.removeItem(AUTH_ALLOWED_REPORTS_KEY);
  window.localStorage.removeItem(AUTH_CAN_ADMIN_KEY);
  document.cookie = `${AUTH_KEY}=; path=/; max-age=0; SameSite=Lax`;
}

export function authHeaders(): Record<string, string> {
  const token = readStorage(AUTH_TOKEN_KEY);
  return token ? { Authorization: `Bearer ${token}` } : {};
}

export function isAdminRole(role: string | undefined): boolean {
  const r = (role || "").toLowerCase();
  return r === "admin" || r === "superadmin";
}

export function hasAdminAccess(user?: AuthUser | null): boolean {
  const session = user ?? getAuthSession();
  if (!session) return false;
  if (isAdminRole(session.role)) return true;
  return Boolean(session.can_admin);
}

export function canAccessReport(
  reportId: string | undefined | null,
  user?: AuthUser | null,
): boolean {
  if (!reportId) return true;
  const session = user ?? getAuthSession();
  if (!session) return false;
  if (hasAdminAccess(session)) return true;
  const allowed = session.allowed_reports;
  if (!allowed) return true; // пока каталог не подтянут — не прячем всё
  return allowed.includes(reportId);
}
