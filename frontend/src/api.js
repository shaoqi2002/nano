const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL || "/api";

async function request(path, options = {}) {
  const headers = { ...options.headers };
  if (options.body && !(options.body instanceof FormData)) {
    headers["Content-Type"] = "application/json";
  }
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers,
  });

  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `请求失败（${response.status}）`);
  }

  if (response.status === 204) return null;
  return response.json();
}

export function createConversation() {
  return request("/conversations", { method: "POST" });
}

export function listConversations() {
  return request("/conversations");
}

export function getMessages(conversationId) {
  return request(`/conversations/${conversationId}/messages`);
}

export function sendMessage(conversationId, message, apiKey, tavilyApiKey, useRag = true) {
  const headers = {
    "X-DeepSeek-API-Key": apiKey,
  };
  if (tavilyApiKey) {
    headers["X-Tavily-API-Key"] = tavilyApiKey;
  }

  return request(`/conversations/${conversationId}/messages`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, use_rag: useRag }),
  });
}

export function deleteConversation(conversationId) {
  return request(`/conversations/${conversationId}`, { method: "DELETE" });
}

export function listDocuments() {
  return request("/documents");
}

export function uploadDocument(file) {
  const body = new FormData();
  body.append("file", file);
  return request("/documents", { method: "POST", body });
}

export function deleteDocument(documentId) {
  return request(`/documents/${documentId}`, { method: "DELETE" });
}

export function reindexDocument(documentId) {
  return request(`/documents/${documentId}/reindex`, { method: "POST" });
}

export function documentContentUrl(documentId, download = false) {
  const suffix = download ? "?download=true" : "";
  return `${API_BASE_URL}/documents/${documentId}/content${suffix}`;
}

export async function getDocumentText(documentId) {
  const response = await fetch(`${API_BASE_URL}/documents/${documentId}/text`);
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `请求失败（${response.status}）`);
  }
  return response.text();
}
