// Shared API layer: token storage, fetch wrapper, typed-error handling.
// The UI is served same-origin under /app/, so API calls are plain relative
// paths and there is no CORS involved.

const TOKEN_KEY = "lf_token";
const USER_KEY = "lf_user";

export const auth = {
  get token() {
    return localStorage.getItem(TOKEN_KEY);
  },
  get user() {
    try {
      return JSON.parse(localStorage.getItem(USER_KEY) || "null");
    } catch {
      return null;
    }
  },
  get isLoggedIn() {
    return Boolean(this.token);
  },
  save(token, user) {
    localStorage.setItem(TOKEN_KEY, token);
    localStorage.setItem(USER_KEY, JSON.stringify(user));
  },
  clear() {
    localStorage.removeItem(TOKEN_KEY);
    localStorage.removeItem(USER_KEY);
  },
};

/**
 * Error carrying the API's typed response.
 * `fieldErrors` maps a field name to a message when the API returned a
 * Pydantic 422 (detail is an array of {loc, msg}); `message` is always a
 * human-readable string.
 */
export class ApiError extends Error {
  constructor(status, detail) {
    const fieldErrors = {};
    let message;

    if (Array.isArray(detail)) {
      // Pydantic validation: [{loc: ["body","password"], msg: "...", ...}]
      for (const d of detail) {
        const field = Array.isArray(d.loc) ? d.loc[d.loc.length - 1] : "_";
        if (!fieldErrors[field]) fieldErrors[field] = d.msg;
      }
      message = detail.map((d) => `${d.loc?.slice(1).join(".") || ""}: ${d.msg}`).join("\n");
    } else if (typeof detail === "string") {
      message = detail;
    } else {
      message = `Request failed (HTTP ${status}).`;
    }

    super(message);
    this.status = status;
    this.detail = detail;
    this.fieldErrors = fieldErrors;
  }
}

function redirectToLogin() {
  const here = window.location.pathname + window.location.search;
  if (window.location.pathname.endsWith("/login.html")) return;
  window.location.href = `/app/login.html?next=${encodeURIComponent(here)}`;
}

/**
 * Core fetch wrapper.
 * - attaches Authorization: Bearer <token> when logged in
 * - parses the API's JSON error envelope into an ApiError
 * - on 401 for an authenticated call, clears the session and redirects
 */
export async function request(path, { method = "GET", body, params, auth: needsAuth = false } = {}) {
  const url = new URL(path, window.location.origin);
  if (params) {
    for (const [k, v] of Object.entries(params)) {
      if (v !== undefined && v !== null && v !== "") url.searchParams.set(k, v);
    }
  }

  const headers = {};
  if (body !== undefined) headers["Content-Type"] = "application/json";
  if (auth.token) headers["Authorization"] = `Bearer ${auth.token}`;

  let response;
  try {
    response = await fetch(url, {
      method,
      headers,
      body: body === undefined ? undefined : JSON.stringify(body),
    });
  } catch (networkError) {
    throw new ApiError(0, `Could not reach the server: ${networkError.message}`);
  }

  if (response.status === 401 && (needsAuth || auth.token)) {
    auth.clear();
    redirectToLogin();
    throw new ApiError(401, "Your session has expired. Please log in again.");
  }

  const text = await response.text();
  const payload = text ? JSON.parse(text) : null;

  if (!response.ok) {
    throw new ApiError(response.status, payload?.detail ?? null);
  }
  return payload;
}

// --- endpoint bindings: names and shapes taken from /openapi.json -----------

export const api = {
  // auth
  register: (b) => request("/auth/register", { method: "POST", body: b }),
  verifyRegistration: (b) => request("/auth/verify-registration", { method: "POST", body: b }),
  login: (b) => request("/auth/login", { method: "POST", body: b }),
  passwordResetRequest: (b) =>
    request("/auth/password-reset/request", { method: "POST", body: b }),
  passwordResetConfirm: (b) =>
    request("/auth/password-reset/confirm", { method: "POST", body: b }),
  me: () => request("/auth/me", { auth: true }),

  // items
  searchItems: (params) => request("/items", { params }),
  getItem: (id) => request(`/items/${id}`),
  itemSuggestions: (id) => request(`/items/${id}/suggestions`),
  createItem: (b) => request("/items", { method: "POST", body: b, auth: true }),
  updateItem: (id, b) => request(`/items/${id}`, { method: "PATCH", body: b, auth: true }),
  transitionStatus: (id, b) =>
    request(`/items/${id}/status`, { method: "POST", body: b, auth: true }),
  deleteItem: (id) => request(`/items/${id}`, { method: "DELETE", auth: true }),

  // claims
  fileClaim: (itemId, b) =>
    request(`/items/${itemId}/claims`, { method: "POST", body: b, auth: true }),
  listClaims: (params) => request("/claims", { params, auth: true }),
  decideClaim: (claimId, b) =>
    request(`/claims/${claimId}/decision`, { method: "POST", body: b, auth: true }),

  // reference data
  listCategories: () => request("/categories"),
  listLocations: () => request("/locations"),
  createLocation: (b) => request("/locations", { method: "POST", body: b, auth: true }),
  createCategory: (b) => request("/categories", { method: "POST", body: b, auth: true }),

  // admin (403 for everyone else)
  adminStats: () => request("/admin/stats", { auth: true }),
  adminUsers: (params) => request("/admin/users", { params, auth: true }),
  adminSetRole: (id, b) =>
    request(`/admin/users/${id}/role`, { method: "POST", body: b, auth: true }),
  adminDeleteUser: (id) => request(`/admin/users/${id}`, { method: "DELETE", auth: true }),
  adminDeleteItem: (id) => request(`/admin/items/${id}`, { method: "DELETE", auth: true }),
  adminBulkDeleteItems: (itemIds) =>
    request("/admin/items/bulk-delete", { method: "POST", body: { item_ids: itemIds }, auth: true }),
  adminDeleteLocation: (id) =>
    request(`/admin/locations/${id}`, { method: "DELETE", auth: true }),
  adminDeleteCategory: (id) =>
    request(`/admin/categories/${id}`, { method: "DELETE", auth: true }),

  // misc
  notifications: () => request("/notifications", { auth: true }),
  health: () => request("/health"),
};

// --- small DOM helpers shared by the pages ---------------------------------

export function showError(err, formEl) {
  if (formEl) {
    formEl.querySelectorAll("[data-field-error]").forEach((n) => (n.textContent = ""));
    formEl.querySelectorAll(".invalid").forEach((n) => n.classList.remove("invalid"));
  }
  const banner = document.querySelector("[data-error-banner]");

  if (err instanceof ApiError && Object.keys(err.fieldErrors).length && formEl) {
    let unmatched = [];
    for (const [field, msg] of Object.entries(err.fieldErrors)) {
      const slot = formEl.querySelector(`[data-field-error="${field}"]`);
      const input = formEl.querySelector(`[name="${field}"]`);
      if (slot) slot.textContent = msg;
      else unmatched.push(`${field}: ${msg}`);
      if (input) input.classList.add("invalid");
    }
    if (banner) {
      banner.textContent = unmatched.join(" · ");
      banner.hidden = unmatched.length === 0;
    }
    return;
  }
  if (banner) {
    banner.textContent = err.message;
    banner.hidden = false;
  } else {
    alert(err.message);
  }
}

export function clearError(formEl) {
  const banner = document.querySelector("[data-error-banner]");
  if (banner) {
    banner.textContent = "";
    banner.hidden = true;
  }
  if (formEl) {
    formEl.querySelectorAll("[data-field-error]").forEach((n) => (n.textContent = ""));
    formEl.querySelectorAll(".invalid").forEach((n) => n.classList.remove("invalid"));
  }
}

export function showNotice(message, kind = "ok") {
  const el = document.querySelector("[data-notice]");
  if (!el) return;
  el.textContent = message;
  el.className = `notice notice-${kind}`;
  el.hidden = false;
}

export function formData(form) {
  const out = {};
  for (const [k, v] of new FormData(form).entries()) {
    out[k] = typeof v === "string" ? v.trim() : v;
  }
  return out;
}

export function requireLogin() {
  if (!auth.isLoggedIn) {
    redirectToLogin();
    return false;
  }
  return true;
}

export function qs(name) {
  return new URLSearchParams(window.location.search).get(name);
}
