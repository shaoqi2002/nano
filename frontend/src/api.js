const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || "/api";

async function request(path, options = {}) {
  const response = await fetch(`${API_BASE_URL}${path}`, {
    ...options,
    headers: {
      "Content-Type": "application/json",
      ...options.headers,
    },
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

export function sendMessage(conversationId, message, apiKey, tavilyApiKey) {
  const headers = {
    "X-DeepSeek-API-Key": apiKey,
  };
  if (tavilyApiKey) {
    headers["X-Tavily-API-Key"] = tavilyApiKey;
  }

  return request(`/conversations/${conversationId}/messages`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message }),
  });
}

export function deleteConversation(conversationId) {
  return request(`/conversations/${conversationId}`, { method: "DELETE" });
}
