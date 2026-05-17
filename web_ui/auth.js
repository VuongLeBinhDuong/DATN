const AUTH_STORAGE_KEY = "datn_auth_token";
const AUTH_USER_KEY = "datn_auth_user";

function authDefaultApiBase() {
  try {
    const { protocol, host } = window.location;
    if (host && (protocol === "http:" || protocol === "https:")) {
      return `${protocol}//${host}`;
    }
  } catch {
    /* ignore */
  }
  return "http://127.0.0.1:8000";
}

function getAuthToken() {
  return localStorage.getItem(AUTH_STORAGE_KEY) || "";
}

function getAuthUser() {
  return localStorage.getItem(AUTH_USER_KEY) || "";
}

function setAuthSession(token, username) {
  localStorage.setItem(AUTH_STORAGE_KEY, token);
  localStorage.setItem(AUTH_USER_KEY, username || "");
}

function clearAuthSession() {
  localStorage.removeItem(AUTH_STORAGE_KEY);
  localStorage.removeItem(AUTH_USER_KEY);
}

async function authApiFetch(path, options = {}) {
  const base = authDefaultApiBase().replace(/\/$/, "");
  const headers = new Headers(options.headers || {});
  const token = getAuthToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);
  const response = await fetch(`${base}${path}`, { ...options, headers });
  if (response.status === 401) {
    clearAuthSession();
  }
  return response;
}

async function verifySession() {
  const token = getAuthToken();
  if (!token) return false;
  try {
    const response = await authApiFetch("/api/auth/me", { method: "GET" });
    if (!response.ok) return false;
    const data = await response.json().catch(() => ({}));
    if (data?.username) localStorage.setItem(AUTH_USER_KEY, data.username);
    return true;
  } catch {
    return false;
  }
}

async function login(username, password) {
  const response = await authApiFetch("/api/auth/login", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.detail || "Đăng nhập thất bại.");
  }
  if (!data?.access_token) {
    throw new Error("API đăng nhập không trả về token.");
  }
  setAuthSession(data.access_token, data.username || username);
  return data;
}

async function logout() {
  try {
    await authApiFetch("/api/auth/logout", { method: "POST" });
  } catch {
    /* ignore */
  } finally {
    clearAuthSession();
  }
}

async function ensureProtectedPage() {
  const ok = await verifySession();
  if (!ok) {
    const next = encodeURIComponent(window.location.pathname);
    window.location.href = `/ui/login.html?next=${next}`;
  }
}

function bindAuthUi() {
  const loginLink = document.getElementById("loginLink");
  const logoutBtn = document.getElementById("logoutBtn");
  const authLabel = document.getElementById("authUserLabel");
  const token = getAuthToken();
  const username = getAuthUser();
  if (authLabel) {
    authLabel.textContent = token ? `Xin chào, ${username || "user"}` : "";
  }
  if (loginLink) loginLink.classList.toggle("hidden", Boolean(token));
  if (logoutBtn) logoutBtn.classList.toggle("hidden", !token);
  if (logoutBtn) {
    logoutBtn.addEventListener("click", async () => {
      await logout();
      window.location.href = "/ui/login.html";
    });
  }
}

window.DATNAuth = {
  authApiFetch,
  bindAuthUi,
  clearAuthSession,
  ensureProtectedPage,
  getAuthToken,
  login,
  logout,
  verifySession,
};
