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

export function getDeepSeekBalance(apiKey) {
  return request("/account/deepseek/balance", {
    headers: { "X-DeepSeek-API-Key": apiKey },
  });
}

export function listConversations() {
  return request("/conversations");
}

export function getMessages(conversationId) {
  return request(`/conversations/${conversationId}/messages`);
}

export function sendMessage(conversationId, message, apiKey, tavilyApiKey, useRag = true, mode = "auto") {
  const headers = {
    "X-DeepSeek-API-Key": apiKey,
  };
  if (tavilyApiKey) {
    headers["X-Tavily-API-Key"] = tavilyApiKey;
  }

  return request(`/conversations/${conversationId}/messages`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, use_rag: useRag, mode }),
  });
}

export async function consumeEventStream(response, onEvent) {
  if (!response.body) throw new Error("浏览器不支持流式响应");
  const reader = response.body.getReader();
  const decoder = new TextDecoder();
  let buffer = "";

  function dispatch(block) {
    if (!block || block.startsWith(":")) return;
    let event = "message";
    const data = [];
    for (const line of block.split("\n")) {
      if (line.startsWith("event:")) event = line.slice(6).trim();
      if (line.startsWith("data:")) data.push(line.slice(5).trimStart());
    }
    if (!data.length) return;
    const payload = JSON.parse(data.join("\n"));
    onEvent({ type: event, ...payload });
  }

  while (true) {
    const { done, value } = await reader.read();
    buffer += decoder.decode(value || new Uint8Array(), { stream: !done });
    buffer = buffer.replaceAll("\r\n", "\n");
    let boundary;
    while ((boundary = buffer.indexOf("\n\n")) >= 0) {
      dispatch(buffer.slice(0, boundary));
      buffer = buffer.slice(boundary + 2);
    }
    if (done) break;
  }
  dispatch(buffer.trim());
}

export async function sendMessageStream(
  conversationId,
  message,
  apiKey,
  tavilyApiKey,
  useRag,
  mode,
  onEvent,
  signal,
) {
  const headers = {
    "Content-Type": "application/json",
    "X-DeepSeek-API-Key": apiKey,
  };
  if (tavilyApiKey) headers["X-Tavily-API-Key"] = tavilyApiKey;

  const response = await fetch(`${API_BASE_URL}/conversations/${conversationId}/messages/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({ message, use_rag: useRag, mode }),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `请求失败（${response.status}）`);
  }
  await consumeEventStream(response, onEvent);
}

export function getAgentRun(runId) {
  return request(`/agent-runs/${runId}`);
}

export function getAgentRunEvents(runId) {
  return request(`/agent-runs/${runId}/events`);
}

export function getEvalDataset() {
  return request("/evals/dataset");
}

function customEvalCasePath(caseId) {
  return String(caseId).replace(/^custom:/, "");
}

export function createEvalCase(definition) {
  return request("/evals/cases", {
    method: "POST",
    body: JSON.stringify(definition),
  });
}

export function updateEvalCase(caseId, definition) {
  return request(`/evals/cases/${customEvalCasePath(caseId)}`, {
    method: "PUT",
    body: JSON.stringify(definition),
  });
}

export function deleteEvalCase(caseId) {
  return request(`/evals/cases/${customEvalCasePath(caseId)}`, {
    method: "DELETE",
  });
}

export function restorePresetEvalCases() {
  return request("/evals/cases/presets/restore", { method: "POST" });
}

export function listEvalRuns() {
  return request("/evals/runs");
}

export function getEvalRun(runId) {
  return request(`/evals/runs/${runId}`);
}

export async function runEvalStream(
  caseIds,
  apiKey,
  tavilyApiKey,
  judgeEnabled,
  judgeWeight,
  baselineRunId,
  onEvent,
  signal,
) {
  const headers = {
    "Content-Type": "application/json",
    "X-DeepSeek-API-Key": apiKey,
  };
  if (tavilyApiKey) headers["X-Tavily-API-Key"] = tavilyApiKey;
  const response = await fetch(`${API_BASE_URL}/evals/runs/stream`, {
    method: "POST",
    headers,
    body: JSON.stringify({
      case_ids: caseIds,
      judge_enabled: judgeEnabled,
      judge_weight: judgeWeight,
      baseline_run_id: baselineRunId || null,
    }),
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `请求失败（${response.status}）`);
  }
  await consumeEventStream(response, onEvent);
}

export async function resumeAgentRunStream(runId, apiKey, tavilyApiKey, onEvent, signal) {
  const headers = { "X-DeepSeek-API-Key": apiKey };
  if (tavilyApiKey) headers["X-Tavily-API-Key"] = tavilyApiKey;
  const response = await fetch(`${API_BASE_URL}/agent-runs/${runId}/resume/stream`, {
    method: "POST",
    headers,
    signal,
  });
  if (!response.ok) {
    const body = await response.json().catch(() => null);
    throw new Error(body?.detail || `请求失败（${response.status}）`);
  }
  await consumeEventStream(response, onEvent);
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
