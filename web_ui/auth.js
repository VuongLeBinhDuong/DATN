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

async function registerGuest(username = "") {
  const base = authDefaultApiBase().replace(/\/$/, "");
  const response = await fetch(`${base}/api/auth/register-guest`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.detail || "Đăng ký phiên khách thất bại.");
  }
  setAuthSession(data.access_token, data.username);
  return data;
}

async function register(username, password) {
  const base = authDefaultApiBase().replace(/\/$/, "");
  const response = await fetch(`${base}/api/auth/register`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ username, password }),
  });
  const data = await response.json().catch(() => ({}));
  if (!response.ok) {
    throw new Error(data?.detail || "Đăng ký tài khoản thất bại.");
  }
  setAuthSession(data.access_token, data.username || username);
  return data;
}

async function ensureProtectedPage() {
  // Bỏ chuyển hướng cưỡng bức, cho phép Khách sử dụng mọi trang
  return true;
}

function bindAuthUi() {
  const loginLink = document.getElementById("loginLink");
  const logoutBtn = document.getElementById("logoutBtn");
  const authLabel = document.getElementById("authUserLabel");
  const token = getAuthToken();
  const username = getAuthUser();

  const isGuest = !token || !username || (typeof username === "string" && username.startsWith("Khách_"));



  if (authLabel) {
    authLabel.textContent = isGuest ? "Xin chào, Khách" : `Xin chào, ${username}`;
    authLabel.style.marginRight = "10px";
  }

  // Handle registerLink dynamically
  let registerLink = document.getElementById("registerLink");

  if (isGuest) {
    // Show Sign In button
    if (loginLink) {
      loginLink.textContent = "Đăng nhập";
      loginLink.setAttribute("href", "/ui/login.html?tab=login");
      loginLink.classList.remove("hidden");
      loginLink.onclick = null;
    }
    // Show Sign Up button next to it
    if (loginLink && !registerLink) {
      registerLink = document.createElement("a");
      registerLink.id = "registerLink";
      registerLink.className = "btn primary btn-auth";
      registerLink.textContent = "Đăng ký";
      registerLink.setAttribute("href", "/ui/login.html?tab=register");
      registerLink.style.marginLeft = "8px";
      loginLink.parentNode.insertBefore(registerLink, loginLink.nextSibling);
    }
    if (registerLink) {
      registerLink.classList.remove("hidden");
    }
    // Hide Logout button
    if (logoutBtn) {
      logoutBtn.classList.add("hidden");
    }
  } else {
    // Registered user
    if (loginLink) {
      loginLink.classList.add("hidden");
    }
    if (registerLink) {
      registerLink.classList.add("hidden");
    }
    if (logoutBtn) {
      logoutBtn.classList.remove("hidden");
      logoutBtn.onclick = async () => {
        await logout();
        window.location.href = "/ui/";
      };
    }
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
  registerGuest,
  register,
};

// Check and verify session on load
(async () => {
  const token = getAuthToken();
  const username = getAuthUser();

  // Tự động dọn dẹp các phiên khách ngẫu nhiên cũ để đồng bộ trạng thái mới
  if (username && username.startsWith("Khách_")) {
    clearAuthSession();
  } else if (token) {
    await verifySession().catch(() => {});
  }
  bindAuthUi();
})();




