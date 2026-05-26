const BASE = import.meta.env.DEV ? "/api" : "http://127.0.0.1:8000";

function authHeaders(token) {
  return {
    "Content-Type": "application/json",
    ...(token ? { Authorization: `Bearer ${token}` } : {}),
  };
}

async function request(path, options = {}) {
  const res = await fetch(`${BASE}${path}`, options);
  const data = await res.json().catch(() => ({}));
  if (!res.ok) {
    const detail = data.detail;
    const msg = Array.isArray(detail)
      ? detail.map((d) => d.msg).join(", ")
      : detail || data.message || "Request failed";
    const err = new Error(typeof msg === "string" ? msg : "Request failed");
    if (res.status === 429) {
      err.retryAfter = res.headers.get("Retry-After");
    }
    throw err;
  }
  return data;
}

export function register(email, password) {
  return request("/auth/register", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ email, password }),
  });
}

export function login(email, password) {
  return request("/auth/login", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ email, password }),
  });
}

export function getHistory(token, sessionId) {
  const url = sessionId ? `/chat/history?session_id=${encodeURIComponent(sessionId)}` : "/chat/history";
  return request(url, { headers: authHeaders(token) });
}

export function sendMessage(token, message, sessionId) {
  return request("/chat", {
    method: "POST",
    headers: authHeaders(token),
    body: JSON.stringify({ message, session_id: sessionId }),
  });
}

export function getEscalations() {
  return request("/admin/dashboard");
}

export function resolveEscalation(escalationId, response) {
  return request("/admin/escalations", {
    method: "POST",
    headers: authHeaders(),
    body: JSON.stringify({ escalation_id: escalationId, response }),
  });
}
