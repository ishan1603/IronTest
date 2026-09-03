// Thin API client. Every call carries the session token; a 401 clears it so
// the app falls back to the sign-in screen rather than looping on a dead
// session.

const BASE = (import.meta.env.VITE_API_BASE || "http://localhost:8000").replace(/\/$/, "");
export const API_BASE = BASE;
const TOKEN_KEY = "irontest.token";

export function getToken() {
  try {
    return localStorage.getItem(TOKEN_KEY) || "";
  } catch {
    // Private browsing and blocked site data both throw here.
    return "";
  }
}

export function setToken(token) {
  try {
    if (token) localStorage.setItem(TOKEN_KEY, token);
    else localStorage.removeItem(TOKEN_KEY);
  } catch {
    /* Nothing to do; the session simply will not persist across reloads. */
  }
}

export class ApiError extends Error {
  constructor(message, status, body) {
    super(message);
    this.status = status;
    this.body = body;
  }
}

async function request(path, { method = "GET", body, signal } = {}) {
  const token = getToken();
  const response = await fetch(`${BASE}${path}`, {
    method,
    signal,
    headers: {
      ...(body ? { "Content-Type": "application/json" } : {}),
      ...(token ? { Authorization: `Bearer ${token}` } : {}),
    },
    body: body ? JSON.stringify(body) : undefined,
  });

  if (response.status === 401) {
    setToken("");
    throw new ApiError("Your session has expired. Please sign in again.", 401);
  }

  if (response.status === 204) return null;

  const payload = await response.json().catch(() => null);
  if (!response.ok) {
    throw new ApiError(payload?.detail || `Request failed (${response.status})`, response.status, payload);
  }
  return payload;
}

export const api = {
  health: () => request("/health"),

  me: () => request("/api/auth/me"),
  logout: () => request("/api/auth/logout", { method: "POST" }),
  loginUrl: () => `${BASE}/api/auth/github/login`,

  availableRepos: () => request("/api/repos/available"),
  connectedRepos: () => request("/api/repos"),
  connectRepo: (fullName) => request("/api/repos", { method: "POST", body: { full_name: fullName } }),
  getRepo: (id) => request(`/api/repos/${id}`),
  rescanRepo: (id) => request(`/api/repos/${id}/rescan`, { method: "POST" }),
  repoBranches: (id) => request(`/api/repos/${id}/branches`),
  disconnectRepo: (id) => request(`/api/repos/${id}`, { method: "DELETE" }),

  analytics: () => request("/api/analytics"),
  analyticsRuns: (limit = 100) => request(`/api/analytics/runs?limit=${limit}`),
  analyticsRun: (runId) => request(`/api/analytics/runs/${runId}`),
  shareRun: (runId) => request(`/api/analytics/runs/${runId}/share`, { method: "POST" }),
  unshareRun: (runId) => request(`/api/analytics/runs/${runId}/share`, { method: "DELETE" }),
  publicReport: async (token) => {
    const res = await fetch(`${BASE}/api/reports/${encodeURIComponent(token)}`);
    if (!res.ok) throw new ApiError((await res.json().catch(() => null))?.detail || "Report not found", res.status);
    return res.json();
  },
  reportMarkdownUrl: (token) => `${BASE}/api/reports/${encodeURIComponent(token)}/export.md`,

  openPullRequest: (runId) => request(`/api/analytics/runs/${runId}/pull-request`, { method: "POST" }),
  getApiKey: () => request("/api/auth/api-key"),
  rotateApiKey: () => request("/api/auth/api-key", { method: "POST" }),
  revokeApiKey: () => request("/api/auth/api-key", { method: "DELETE" }),
  chats: () => request("/api/chats"),
  createChat: (repositoryId, title) =>
    request("/api/chats", { method: "POST", body: { repository_id: repositoryId, title } }),
  getChat: (id) => request(`/api/chats/${id}`),
  deleteChat: (id) => request(`/api/chats/${id}`, { method: "DELETE" }),
  startRun: (chatId, payload) => request(`/api/chats/${chatId}/runs`, { method: "POST", body: payload }),

  ingestJira: (payload) => request("/api/ingest/jira", { method: "POST", body: payload }),
  ingestAzure: (payload) => request("/api/ingest/azure-devops", { method: "POST", body: payload }),
};

// Server-Sent Events. EventSource cannot set headers, so the token rides in
// the query string and the server checks it against the session's owner.
export function openRunStream(sessionId, { onEvent, onError }) {
  const source = new EventSource(`${BASE}/api/stream/${sessionId}?token=${encodeURIComponent(getToken())}`);

  source.onmessage = (message) => {
    try {
      onEvent(JSON.parse(message.data));
    } catch {
      /* Keepalive comments arrive as non-JSON; ignore them. */
    }
  };
  source.onerror = () => {
    // The server holds the socket open after a run ends, so an error here is
    // a genuine transport failure rather than normal completion.
    onError?.();
    source.close();
  };

  return () => source.close();
}
