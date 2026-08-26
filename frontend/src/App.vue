<script setup>
import { computed, nextTick, onMounted, reactive, ref } from "vue";

import {
  createWorkspace,
  createConversation,
  deleteWorkspace,
  deleteConversation as deleteConversationRequest,
  getAgentRun,
  getAgentRunEvents,
  getDeepSeekBalance,
  getEmbeddingStatus,
  getMessages,
  getTavilyUsage,
  listConversations,
  listWorkspaces,
  resolveWorkspace,
  resumeAgentRunStream,
  sendMessageStream,
  setActiveWorkspaceId,
} from "./api";
import DocumentsView from "./DocumentsView.vue";
import EvaluationsView from "./EvaluationsView.vue";
import JobApplicationsView from "./JobApplicationsView.vue";
import { renderMarkdown } from "./markdown";
import {
  CHAT_ATTACHMENT_ACCEPT,
  MAX_CHAT_ATTACHMENT_BYTES,
  MAX_CHAT_ATTACHMENTS,
  attachmentPayload,
  attachmentPreviewUrl,
  attachmentTypeLabel,
  fileToChatAttachment,
} from "./chatAttachments";


const ACTIVE_KEY = "nano-agent-active-conversation";
const API_KEY_STORAGE_KEY = "nano-deepseek-api-key";
const TAVILY_API_KEY_STORAGE_KEY = "nano-tavily-api-key";
const EMBEDDING_API_KEY_STORAGE_KEY = "nano-embedding-api-key";
const EMBEDDING_BASE_URL_STORAGE_KEY = "nano-embedding-base-url";
const DEFAULT_EMBEDDING_BASE_URL = "https://dashscope.aliyuncs.com/compatible-mode/v1";
const RAG_STORAGE_KEY = "nano-rag-enabled";
const AGENT_MODE_STORAGE_KEY = "nano-agent-mode";
const ACTIVE_RUN_STORAGE_KEY = "nano-agent-active-run";
const KNOWN_WORKSPACES_STORAGE_KEY = "nano-known-workspaces";

const workspaces = ref([]);
const activeWorkspace = ref(null);
const workspaceEntry = ref("");
const newWorkspaceName = ref("");
const workspaceLoading = ref(true);
const workspaceSubmitting = ref(false);
const workspaceDeleting = ref(false);
const workspaceError = ref("");
const conversations = ref([]);
const activeView = ref("chat");
const activeConversationId = ref(null);
const messages = ref([]);
const draft = ref("");
const isLoading = ref(false);
const isSending = ref(false);
const errorMessage = ref("");
const sidebarOpen = ref(false);
const messageList = ref(null);
const composer = ref(null);
const chatFileInput = ref(null);
const pendingAttachments = ref([]);
const composerDragging = ref(false);
const apiKey = ref(localStorage.getItem(API_KEY_STORAGE_KEY) || "");
const apiKeyDraft = ref("");
const tavilyApiKey = ref(localStorage.getItem(TAVILY_API_KEY_STORAGE_KEY) || "");
const tavilyApiKeyDraft = ref("");
const embeddingApiKey = ref(localStorage.getItem(EMBEDDING_API_KEY_STORAGE_KEY) || "");
const embeddingApiKeyDraft = ref("");
const embeddingBaseUrl = ref(
  localStorage.getItem(EMBEDDING_BASE_URL_STORAGE_KEY) || DEFAULT_EMBEDDING_BASE_URL,
);
const embeddingBaseUrlDraft = ref(embeddingBaseUrl.value);
const apiKeyDialogOpen = ref(false);
const apiBalance = ref(null);
const apiBalanceLoading = ref(false);
const apiBalanceError = ref("");
let apiBalanceRequestId = 0;
const tavilyUsage = ref(null);
const tavilyUsageLoading = ref(false);
const tavilyUsageError = ref("");
let tavilyUsageRequestId = 0;
const embeddingStatus = ref(null);
const embeddingStatusLoading = ref(false);
const embeddingStatusError = ref("");
let embeddingStatusRequestId = 0;
const deletingConversationId = ref(null);
const useRag = ref(localStorage.getItem(RAG_STORAGE_KEY) !== "false");
const agentMode = ref(localStorage.getItem(AGENT_MODE_STORAGE_KEY) || "auto");
const documentTarget = ref({ id: null, page: null });
const streamController = ref(null);
const resumableRun = ref(null);
const traceDialogOpen = ref(false);
const traceLoading = ref(false);
const traceRun = ref(null);
const traceEvents = ref([]);

const activeConversation = computed(() =>
  conversations.value.find((item) => item.id === activeConversationId.value),
);

const canSend = computed(
  () => (draft.value.trim().length > 0 || pendingAttachments.value.length > 0)
    && !isSending.value && activeConversationId.value,
);
const hasCh4Features = computed(() => activeWorkspace.value?.slug === "ch4");

function workspaceStorageKey(key) {
  return `${key}:${activeWorkspace.value?.id || "none"}`;
}

function knownWorkspaceIds() {
  try {
    const value = JSON.parse(localStorage.getItem(KNOWN_WORKSPACES_STORAGE_KEY) || "[]");
    return Array.isArray(value) ? value.filter((item) => typeof item === "string") : [];
  } catch {
    return [];
  }
}

function rememberWorkspace(workspaceId) {
  const ids = [...new Set([...knownWorkspaceIds(), workspaceId])];
  localStorage.setItem(KNOWN_WORKSPACES_STORAGE_KEY, JSON.stringify(ids));
}

function forgetWorkspace(workspaceId) {
  const ids = knownWorkspaceIds().filter((id) => id !== workspaceId);
  localStorage.setItem(KNOWN_WORKSPACES_STORAGE_KEY, JSON.stringify(ids));
}

async function addChatFiles(fileList) {
  const files = [...(fileList || [])];
  if (!files.length) return;
  const available = MAX_CHAT_ATTACHMENTS - pendingAttachments.value.length;
  if (files.length > available) {
    errorMessage.value = `每条消息最多添加 ${MAX_CHAT_ATTACHMENTS} 个附件`;
  }
  for (const file of files.slice(0, Math.max(0, available))) {
    try {
      const currentBytes = pendingAttachments.value.reduce(
        (total, attachment) => total + (attachment.byteSize || 0), 0,
      );
      if (currentBytes + file.size > MAX_CHAT_ATTACHMENT_BYTES) {
        throw new Error("每条消息的附件总大小不能超过 15 MB");
      }
      pendingAttachments.value.push(await fileToChatAttachment(file));
      errorMessage.value = "";
    } catch (error) {
      errorMessage.value = error.message;
      break;
    }
  }
  if (chatFileInput.value) chatFileInput.value.value = "";
}

function removeChatAttachment(index) {
  pendingAttachments.value.splice(index, 1);
}

function handleComposerPaste(event) {
  const files = [...(event.clipboardData?.files || [])];
  if (!files.length) return;
  event.preventDefault();
  void addChatFiles(files);
}

function handleComposerDrop(event) {
  composerDragging.value = false;
  void addChatFiles(event.dataTransfer?.files);
}

const apiKeyStatusLabel = computed(() => {
  const count = [apiKey.value, tavilyApiKey.value, embeddingApiKey.value]
    .filter(Boolean).length;
  if (!count) return "设置 API Key";
  if (count === 1 && apiKey.value) return "DeepSeek 已配置";
  return `${count} 个 API Keys 已配置`;
});

function rememberActiveConversation(id) {
  activeConversationId.value = id;
  localStorage.setItem(workspaceStorageKey(ACTIVE_KEY), id);
}

function openApiKeyDialog() {
  apiKeyDraft.value = apiKey.value;
  tavilyApiKeyDraft.value = tavilyApiKey.value;
  embeddingApiKeyDraft.value = embeddingApiKey.value;
  embeddingBaseUrlDraft.value = embeddingBaseUrl.value;
  apiKeyDialogOpen.value = true;
  sidebarOpen.value = false;
  if (apiKey.value) void refreshApiBalance(apiKey.value);
  if (tavilyApiKey.value) void refreshTavilyUsage(tavilyApiKey.value);
}

function formatBalance(value, currency) {
  const amount = Number(value);
  if (!Number.isFinite(amount)) return `${value} ${currency}`;
  try {
    return new Intl.NumberFormat("zh-CN", {
      style: "currency",
      currency,
      currencyDisplay: "narrowSymbol",
      minimumFractionDigits: 2,
    }).format(amount);
  } catch {
    return `${amount.toFixed(2)} ${currency}`;
  }
}

async function refreshApiBalance(key = apiKey.value) {
  const value = key.trim();
  if (!value) return;
  const requestId = ++apiBalanceRequestId;
  apiBalanceLoading.value = true;
  apiBalanceError.value = "";
  try {
    const balance = await getDeepSeekBalance(value);
    if (requestId === apiBalanceRequestId) apiBalance.value = balance;
  } catch (error) {
    if (requestId === apiBalanceRequestId) {
      apiBalance.value = null;
      apiBalanceError.value = error.message;
    }
  } finally {
    if (requestId === apiBalanceRequestId) apiBalanceLoading.value = false;
  }
}

function handleApiKeyDraftInput() {
  if (apiKeyDraft.value.trim() === apiKey.value) return;
  apiBalanceRequestId += 1;
  apiBalanceLoading.value = false;
  apiBalance.value = null;
  apiBalanceError.value = "";
}

async function refreshTavilyUsage(key = tavilyApiKey.value) {
  const value = key.trim();
  if (!value) return;
  const requestId = ++tavilyUsageRequestId;
  tavilyUsageLoading.value = true;
  tavilyUsageError.value = "";
  try {
    const usage = await getTavilyUsage(value);
    if (requestId === tavilyUsageRequestId) tavilyUsage.value = usage;
  } catch (error) {
    if (requestId === tavilyUsageRequestId) {
      tavilyUsage.value = null;
      tavilyUsageError.value = error.message;
    }
  } finally {
    if (requestId === tavilyUsageRequestId) tavilyUsageLoading.value = false;
  }
}

function handleTavilyKeyDraftInput() {
  if (tavilyApiKeyDraft.value.trim() === tavilyApiKey.value) return;
  tavilyUsageRequestId += 1;
  tavilyUsageLoading.value = false;
  tavilyUsage.value = null;
  tavilyUsageError.value = "";
}

function usagePercent(usage, limit) {
  if (!limit) return 0;
  return Math.min(100, Math.max(0, (usage / limit) * 100));
}

async function verifyEmbeddingKey(
  key = embeddingApiKey.value,
  baseUrl = embeddingBaseUrl.value,
) {
  const value = key.trim();
  const url = baseUrl.trim();
  if (!value || !url) return;
  const requestId = ++embeddingStatusRequestId;
  embeddingStatusLoading.value = true;
  embeddingStatusError.value = "";
  try {
    const status = await getEmbeddingStatus(value, url);
    if (requestId === embeddingStatusRequestId) embeddingStatus.value = status;
  } catch (error) {
    if (requestId === embeddingStatusRequestId) {
      embeddingStatus.value = null;
      embeddingStatusError.value = error.message;
    }
  } finally {
    if (requestId === embeddingStatusRequestId) embeddingStatusLoading.value = false;
  }
}

function handleEmbeddingKeyDraftInput() {
  if (
    embeddingApiKeyDraft.value.trim() === embeddingApiKey.value
    && embeddingBaseUrlDraft.value.trim() === embeddingBaseUrl.value
  ) return;
  embeddingStatusRequestId += 1;
  embeddingStatusLoading.value = false;
  embeddingStatus.value = null;
  embeddingStatusError.value = "";
}

function saveApiKey() {
  const value = apiKeyDraft.value.trim();
  if (!value) return;

  apiKey.value = value;
  localStorage.setItem(API_KEY_STORAGE_KEY, value);
  tavilyApiKey.value = tavilyApiKeyDraft.value.trim();
  if (tavilyApiKey.value) {
    localStorage.setItem(TAVILY_API_KEY_STORAGE_KEY, tavilyApiKey.value);
  } else {
    localStorage.removeItem(TAVILY_API_KEY_STORAGE_KEY);
  }
  embeddingApiKey.value = embeddingApiKeyDraft.value.trim();
  embeddingBaseUrl.value = embeddingBaseUrlDraft.value.trim() || DEFAULT_EMBEDDING_BASE_URL;
  if (embeddingApiKey.value) {
    localStorage.setItem(EMBEDDING_API_KEY_STORAGE_KEY, embeddingApiKey.value);
  } else {
    localStorage.removeItem(EMBEDDING_API_KEY_STORAGE_KEY);
  }
  localStorage.setItem(EMBEDDING_BASE_URL_STORAGE_KEY, embeddingBaseUrl.value);
  apiKeyDialogOpen.value = false;
  errorMessage.value = "";
}

function clearApiKey() {
  apiBalanceRequestId += 1;
  tavilyUsageRequestId += 1;
  embeddingStatusRequestId += 1;
  apiKey.value = "";
  apiKeyDraft.value = "";
  tavilyApiKey.value = "";
  tavilyApiKeyDraft.value = "";
  embeddingApiKey.value = "";
  embeddingApiKeyDraft.value = "";
  embeddingBaseUrl.value = DEFAULT_EMBEDDING_BASE_URL;
  embeddingBaseUrlDraft.value = DEFAULT_EMBEDDING_BASE_URL;
  localStorage.removeItem(API_KEY_STORAGE_KEY);
  localStorage.removeItem(TAVILY_API_KEY_STORAGE_KEY);
  localStorage.removeItem(EMBEDDING_API_KEY_STORAGE_KEY);
  localStorage.removeItem(EMBEDDING_BASE_URL_STORAGE_KEY);
  apiKeyDialogOpen.value = false;
  apiBalance.value = null;
  apiBalanceError.value = "";
  tavilyUsage.value = null;
  tavilyUsageError.value = "";
  embeddingStatus.value = null;
  embeddingStatusError.value = "";
}

function formatDate(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

async function scrollToBottom() {
  await nextTick();
  messageList.value?.scrollTo({
    top: messageList.value.scrollHeight,
    behavior: "smooth",
  });
}

async function startNewConversation() {
  if (isLoading.value || isSending.value) return;
  if (activeConversationId.value && messages.value.length === 0) return;

  activeView.value = "chat";
  errorMessage.value = "";
  isLoading.value = true;

  try {
    const conversation = await createConversation();
    conversations.value.unshift({
      id: conversation.id,
      title: "新对话",
      createdAt: conversation.created_at,
    });
    rememberActiveConversation(conversation.id);
    messages.value = [];
    sidebarOpen.value = false;
    await nextTick();
    composer.value?.focus();
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isLoading.value = false;
  }
}

async function openConversation(id) {
  if (isSending.value) return;

  activeView.value = "chat";
  if (id === activeConversationId.value && messages.value.length) {
    sidebarOpen.value = false;
    return;
  }

  errorMessage.value = "";
  isLoading.value = true;
  rememberActiveConversation(id);

  try {
    const result = await getMessages(id);
    messages.value = result.messages.map((message) => ({
      ...message,
      runId: message.run_id || null,
    }));
    sidebarOpen.value = false;
    await scrollToBottom();
  } catch (error) {
    if (error.message.includes("not found")) {
      conversations.value = conversations.value.filter((item) => item.id !== id);
      isLoading.value = false;
      await startNewConversation();
      return;
    }
    errorMessage.value = error.message;
  } finally {
    isLoading.value = false;
  }
}

function openDocuments() {
  documentTarget.value = { id: null, page: null };
  activeView.value = "documents";
  sidebarOpen.value = false;
}

function openEvaluations() {
  activeView.value = "evaluations";
  sidebarOpen.value = false;
}

function openSource(source) {
  documentTarget.value = {
    id: source.document_id,
    page: source.page_number || null,
  };
  activeView.value = "documents";
}

function toggleRag() {
  useRag.value = !useRag.value;
  localStorage.setItem(RAG_STORAGE_KEY, String(useRag.value));
}

function setAgentMode(mode) {
  agentMode.value = mode;
  localStorage.setItem(AGENT_MODE_STORAGE_KEY, mode);
}

function openJobApplications() {
  activeView.value = "job-applications";
  sidebarOpen.value = false;
}

function messageModeLabel(mode) {
  return ({ auto: "自动", chat: "快速回答", research: "深度研究" })[mode] || mode;
}

async function removeConversation(id) {
  const conversation = conversations.value.find((item) => item.id === id);
  if (!window.confirm(`删除“${conversation?.title || "该对话"}”及其全部消息？`)) return;

  deletingConversationId.value = id;
  errorMessage.value = "";

  try {
    await deleteConversationRequest(id);
    conversations.value = conversations.value.filter((item) => item.id !== id);

    if (activeConversationId.value === id) {
      localStorage.removeItem(workspaceStorageKey(ACTIVE_KEY));
      activeConversationId.value = null;
      messages.value = [];

      if (conversations.value.length) {
        await openConversation(conversations.value[0].id);
      } else {
        await startNewConversation();
      }
    }
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    deletingConversationId.value = null;
  }
}

function updateConversationTitle(content) {
  const conversation = activeConversation.value;
  if (!conversation || conversation.title !== "新对话") return;

  conversation.title = content.length > 28 ? `${content.slice(0, 28)}…` : content;
}

function toolLabel(name) {
  return {
    document_search: "检索文档库",
    web_search: "搜索网页",
    web_extract: "读取网页",
    deep_research: "深度研究",
    word_create_document: "生成 Word",
    word_edit_document: "编辑 Word",
    word_convert_to_pdf: "转换 PDF",
  }[name] || name;
}

function formatFileSize(bytes) {
  const value = Number(bytes || 0);
  if (value < 1024) return `${value} B`;
  if (value < 1024 * 1024) return `${(value / 1024).toFixed(1)} KB`;
  return `${(value / (1024 * 1024)).toFixed(1)} MB`;
}

function formatArtifactExpiry(seconds) {
  const hours = Math.max(1, Math.round(Number(seconds || 86400) / 3600));
  if (hours < 24) return `${hours} 小时内可下载`;
  const days = Math.max(1, Math.round(hours / 24));
  return `${days} 天内可下载`;
}

function agentLabel(agent) {
  return {
    supervisor: "Supervisor",
    web_researcher: "Web Researcher",
    document_analyst: "Document Analyst",
    general_researcher: "General Researcher",
    writer: "Writer",
    reviewer: "Reviewer",
  }[agent] || agent;
}

function handleStreamEvent(message, event) {
  if (event.type === "message.started") {
    message.runId = event.run_id;
    message.mode = event.mode;
    resumableRun.value = {
      runId: event.run_id,
      conversationId: activeConversationId.value,
      mode: event.mode,
    };
    localStorage.setItem(
      workspaceStorageKey(ACTIVE_RUN_STORAGE_KEY),
      JSON.stringify(resumableRun.value),
    );
  } else if (event.type === "message.delta") {
    message.content += event.delta || "";
  } else if (event.type === "message.reset") {
    message.content = "";
  } else if (event.type === "sources.ready") {
    message.sources = event.sources || [];
  } else if (event.type === "tool.started") {
    message.steps.push({
      callId: event.call_id,
      name: event.name,
      label: toolLabel(event.name),
      status: "running",
    });
  } else if (event.type === "node.started") {
    const callId = `node-${event.node}`;
    const existing = message.steps.find((item) => item.callId === callId);
    if (existing) {
      Object.assign(existing, {
        label: event.label || event.node,
        agent: event.agent,
        status: "running",
      });
    } else {
      message.steps.push({
        callId,
        name: event.node,
        label: event.label || event.node,
        agent: event.agent,
        status: "running",
      });
    }
  } else if (["node.completed", "node.failed"].includes(event.type)) {
    const callId = `node-${event.node}`;
    const step = message.steps.find((item) => item.callId === callId);
    if (step) step.status = event.type === "node.failed" ? "failed" : "completed";
  } else if (event.type === "plan.ready") {
    message.plan = event.plan;
  } else if (event.type === "agent.retrying") {
    const step = message.steps.find((item) => item.callId === `node-${event.task_id}`);
    if (step) {
      step.retryAttempt = event.attempt;
      step.message = event.message;
    }
  } else if (["tool.completed", "tool.failed"].includes(event.type)) {
    const step = message.steps.find((item) => item.callId === event.call_id);
    if (step) {
      step.status = event.type === "tool.failed" ? "failed" : "completed";
      step.durationMs = event.duration_ms;
      step.resultCount = event.result_count;
      step.message = event.message;
    }
    if (event.type === "tool.completed" && event.artifacts?.length) {
      message.artifacts ||= [];
      for (const artifact of event.artifacts) {
        if (!message.artifacts.some((item) => item.artifact_id === artifact.artifact_id)) {
          message.artifacts.push(artifact);
        }
      }
    }
  } else if (event.type === "message.completed") {
    Object.assign(message, event.message, {
      steps: message.steps,
      status: "completed",
    });
    resumableRun.value = null;
    localStorage.removeItem(workspaceStorageKey(ACTIVE_RUN_STORAGE_KEY));
  } else if (event.type === "message.failed") {
    throw new Error(event.message || "生成回答失败");
  }
  nextTick(() => {
    if (!messageList.value) return;
    messageList.value.scrollTop = messageList.value.scrollHeight;
  });
}

function stopGeneration() {
  streamController.value?.abort();
}

async function submitMessage() {
  const content = draft.value.trim();
  if (!canSend.value) return;

  if (!apiKey.value) {
    errorMessage.value = "请先在左下角设置 DeepSeek API Key";
    openApiKeyDialog();
    return;
  }

  const conversationId = activeConversationId.value;
  const attachments = pendingAttachments.value.map(attachmentPayload);
  const optimisticMessage = {
    id: `local-${Date.now()}`,
    role: "user",
    content,
    attachments: pendingAttachments.value.slice(),
    created_at: new Date().toISOString(),
    options: {
      mode: agentMode.value,
      use_rag: useRag.value,
    },
  };
  const streamingMessage = reactive({
    id: `stream-${Date.now()}`,
    role: "assistant",
    content: "",
    sources: [],
    artifacts: [],
    steps: [],
    plan: null,
    runId: null,
    status: "streaming",
    created_at: new Date().toISOString(),
  });

  messages.value.push(optimisticMessage, streamingMessage);
  updateConversationTitle(content || attachments[0]?.name || "附件");
  draft.value = "";
  pendingAttachments.value = [];
  errorMessage.value = "";
  isSending.value = true;
  streamController.value = new AbortController();
  resizeComposer();
  await scrollToBottom();

  try {
    await sendMessageStream(
      conversationId,
      content,
      apiKey.value,
      tavilyApiKey.value,
      useRag.value,
      agentMode.value,
      embeddingApiKey.value,
      embeddingBaseUrl.value,
      attachments,
      (event) => handleStreamEvent(streamingMessage, event),
      streamController.value.signal,
    );
    if (streamingMessage.status === "streaming") {
      throw new Error("流式响应意外中断，请重试");
    }
  } catch (error) {
    if (error.name === "AbortError") {
      streamingMessage.status = "stopped";
      if (!streamingMessage.content) {
        messages.value = messages.value.filter((item) => item !== streamingMessage);
      }
    } else {
      streamingMessage.status = "failed";
      errorMessage.value = error.message;
    }
  } finally {
    streamController.value = null;
    isSending.value = false;
  }
}

async function resumeGeneration(message) {
  if (!message.runId || isSending.value || !apiKey.value) return;
  message.status = "streaming";
  errorMessage.value = "";
  isSending.value = true;
  streamController.value = new AbortController();
  try {
    await resumeAgentRunStream(
      message.runId,
      apiKey.value,
      tavilyApiKey.value,
      (event) => handleStreamEvent(message, event),
      streamController.value.signal,
    );
  } catch (error) {
    if (error.name === "AbortError") {
      message.status = "stopped";
    } else {
      message.status = "failed";
      errorMessage.value = error.message;
    }
  } finally {
    streamController.value = null;
    isSending.value = false;
  }
}

function handleComposerKeydown(event) {
  if (event.key === "Enter" && !event.shiftKey) {
    event.preventDefault();
    submitMessage();
  }
}

function resizeComposer() {
  if (!composer.value) return;
  composer.value.style.height = "auto";
  composer.value.style.height = `${Math.min(composer.value.scrollHeight, 180)}px`;
}

async function copyMessage(content) {
  await navigator.clipboard.writeText(content);
}

function traceEventLabel(event) {
  return {
    "run.started": "任务开始",
    "run.paused": "任务暂停",
    "run.cancelled": "任务取消",
    "run.failed": "任务失败",
    "node.started": "节点开始",
    "node.completed": "节点完成",
    "node.failed": "节点失败",
    "tool.started": "工具调用",
    "tool.completed": "工具完成",
    "tool.failed": "工具失败",
    "plan.ready": "研究计划",
    "review.completed": "报告审核",
    "agent.delegated": "Agent 任务交接",
    "agent.retrying": "Agent 自动重试",
    "agent.completed": "Agent 完成任务",
    "agent.failed": "Agent 任务失败",
    "message.completed": "回答完成",
  }[event.event_type] || event.event_type;
}

function traceEventActor(event) {
  const payload = event.payload || {};
  if (event.event_type === "agent.delegated") {
    return `${agentLabel(payload.from_agent)} → ${agentLabel(payload.to_agent)}`;
  }
  return agentLabel(payload.agent) || event.node || event.tool_name || "Agent";
}

function formatDurationMs(value) {
  if (value === null || value === undefined) return "—";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(2)} s`;
}

async function openTrace(message) {
  if (!message.runId) return;
  traceDialogOpen.value = true;
  traceLoading.value = true;
  traceRun.value = null;
  traceEvents.value = [];
  try {
    [traceRun.value, traceEvents.value] = await Promise.all([
      getAgentRun(message.runId),
      getAgentRunEvents(message.runId),
    ]);
  } catch (error) {
    errorMessage.value = error.message;
    traceDialogOpen.value = false;
  } finally {
    traceLoading.value = false;
  }
}

async function loadWorkspaceData() {
  isLoading.value = true;
  try {
    conversations.value = (await listConversations()).map((conversation) => ({
      id: conversation.id,
      title: conversation.title === "New conversation" ? "新对话" : conversation.title,
      createdAt: conversation.created_at,
    }));
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isLoading.value = false;
  }

  const activeExists = conversations.value.some(
    (conversation) => conversation.id === activeConversationId.value,
  );

  if (activeExists) {
    await openConversation(activeConversationId.value);
  } else if (conversations.value.length) {
    await openConversation(conversations.value[0].id);
  } else {
    await startNewConversation();
  }


  if (resumableRun.value?.conversationId === activeConversationId.value) {
    try {
      const run = await getAgentRun(resumableRun.value.runId);
      if (["pending", "running", "paused", "failed"].includes(run.status)) {
        messages.value.push(reactive({
          id: `run-${run.id}`,
          role: "assistant",
          content: "",
          sources: [],
          steps: (run.progress || []).map((step) => ({
            ...step,
            callId: `node-${step.node}`,
            name: step.node,
          })),
          plan: run.plan?.length ? { objective: run.query, tasks: run.plan } : null,
          runId: run.id,
          mode: run.mode,
          status: "stopped",
          created_at: run.created_at,
        }));
      } else {
        resumableRun.value = null;
        localStorage.removeItem(workspaceStorageKey(ACTIVE_RUN_STORAGE_KEY));
      }
    } catch {
      resumableRun.value = null;
      localStorage.removeItem(workspaceStorageKey(ACTIVE_RUN_STORAGE_KEY));
    }
  }
}

async function enterWorkspace(workspace) {
  if (!workspace) return;
  errorMessage.value = "";
  activeWorkspace.value = workspace;
  activeView.value = "chat";
  setActiveWorkspaceId(workspace.id);
  rememberWorkspace(workspace.id);
  const scopedConversationKey = workspaceStorageKey(ACTIVE_KEY);
  const legacyConversationId = workspace.slug === "ch4" ? localStorage.getItem(ACTIVE_KEY) : null;
  activeConversationId.value = localStorage.getItem(scopedConversationKey) || legacyConversationId;
  if (activeConversationId.value) {
    localStorage.setItem(scopedConversationKey, activeConversationId.value);
  }
  const storedRun = localStorage.getItem(workspaceStorageKey(ACTIVE_RUN_STORAGE_KEY));
  const legacyRun = workspace.slug === "ch4" ? localStorage.getItem(ACTIVE_RUN_STORAGE_KEY) : null;
  try {
    resumableRun.value = JSON.parse(storedRun || legacyRun || "null");
  } catch {
    resumableRun.value = null;
  }
  workspaceError.value = "";
  await loadWorkspaceData();
}

async function enterSelectedOrExistingWorkspace() {
  const name = workspaceEntry.value.trim();
  if (!name) {
    workspaceError.value = "请输入 workspace 名称";
    return;
  }
  workspaceSubmitting.value = true;
  workspaceError.value = "";
  try {
    const knownWorkspace = workspaces.value.find(
      (item) => item.name.toLocaleLowerCase() === name.toLocaleLowerCase(),
    );
    const workspace = knownWorkspace || await resolveWorkspace(name);
    if (!workspaces.value.some((item) => item.id === workspace.id)) {
      workspaces.value.push(workspace);
    }
    workspaceEntry.value = workspace.name;
    await enterWorkspace(workspace);
  } catch (error) {
    workspaceError.value = error.message;
  } finally {
    workspaceSubmitting.value = false;
  }
}

async function createAndEnterWorkspace() {
  const name = newWorkspaceName.value.trim();
  if (!name) {
    workspaceError.value = "请输入新 workspace 名称";
    return;
  }
  workspaceSubmitting.value = true;
  workspaceError.value = "";
  try {
    const workspace = await createWorkspace(name);
    workspaces.value.push(workspace);
    workspaceEntry.value = workspace.name;
    newWorkspaceName.value = "";
    await enterWorkspace(workspace);
  } catch (error) {
    workspaceError.value = error.message;
  } finally {
    workspaceSubmitting.value = false;
  }
}

function leaveWorkspace() {
  streamController.value?.abort();
  setActiveWorkspaceId("");
  activeWorkspace.value = null;
  activeConversationId.value = null;
  conversations.value = [];
  messages.value = [];
  activeView.value = "chat";
  sidebarOpen.value = false;
  resumableRun.value = null;
}

async function removeActiveWorkspace() {
  const workspace = activeWorkspace.value;
  if (!workspace || workspace.slug === "ch4") return;
  if (!window.confirm(`永久删除 workspace“${workspace.name}”及其中全部对话和文档？此操作无法撤销。`)) {
    return;
  }
  workspaceDeleting.value = true;
  errorMessage.value = "";
  try {
    await deleteWorkspace(workspace.id);
    localStorage.removeItem(workspaceStorageKey(ACTIVE_KEY));
    localStorage.removeItem(workspaceStorageKey(ACTIVE_RUN_STORAGE_KEY));
    forgetWorkspace(workspace.id);
    workspaces.value = workspaces.value.filter((item) => item.id !== workspace.id);
    workspaceEntry.value = workspaces.value[0]?.name || "";
    leaveWorkspace();
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    workspaceDeleting.value = false;
  }
}

onMounted(async () => {
  workspaceLoading.value = true;
  try {
    const knownIds = knownWorkspaceIds();
    workspaces.value = await listWorkspaces(knownIds);
    localStorage.setItem(
      KNOWN_WORKSPACES_STORAGE_KEY,
      JSON.stringify(workspaces.value.map((workspace) => workspace.id)),
    );
    if (workspaces.value.length) {
      workspaceEntry.value = workspaces.value[0].name;
    }
  } catch (error) {
    workspaceError.value = error.message;
  } finally {
    workspaceLoading.value = false;
  }
});
</script>

<template>
  <main v-if="!activeWorkspace" class="workspace-gate">
    <section class="workspace-gate__card">
      <div class="workspace-gate__brand"><span>N</span> Nano</div>
      <div>
        <p class="workspace-gate__eyebrow">WORKSPACE</p>
        <h1>进入你的工作区</h1>
        <p>对话、文档和使用记录会按 workspace 完全隔离。</p>
      </div>

      <div v-if="workspaceLoading" class="workspace-gate__loading">
        <span class="loader" /> 正在载入 workspace
      </div>
      <template v-else>
        <form class="workspace-gate__form" @submit.prevent="enterSelectedOrExistingWorkspace">
          <label>
            <span>选择或输入 workspace</span>
            <input
              v-model="workspaceEntry"
              list="known-workspaces"
              maxlength="80"
              placeholder="输入准确的 workspace 名称"
              autocomplete="off"
              :disabled="workspaceSubmitting"
            />
            <datalist id="known-workspaces">
              <option v-for="workspace in workspaces" :key="workspace.id" :value="workspace.name" />
            </datalist>
          </label>
          <button type="submit" :disabled="workspaceSubmitting || !workspaceEntry.trim()">进入 Nano</button>
        </form>

        <div class="workspace-gate__divider"><span>或创建新的 workspace</span></div>

        <form class="workspace-gate__form workspace-gate__create" @submit.prevent="createAndEnterWorkspace">
          <label>
            <span>Workspace 名称</span>
            <input
              v-model="newWorkspaceName"
              maxlength="80"
              placeholder="例如：personal"
              :disabled="workspaceSubmitting"
            />
          </label>
          <button type="submit" :disabled="workspaceSubmitting || !newWorkspaceName.trim()">创建并进入</button>
        </form>
      </template>
      <p v-if="workspaceError" class="workspace-gate__error" role="alert">{{ workspaceError }}</p>
    </section>
  </main>

  <div v-else class="app-shell">
    <div
      v-if="sidebarOpen"
      class="sidebar-backdrop"
      aria-hidden="true"
      @click="sidebarOpen = false"
    />

    <aside class="sidebar" :class="{ 'sidebar--open': sidebarOpen }">
      <div class="sidebar__top">
        <div class="brand">
          <span class="brand__mark">N</span>
          <span>Nano</span>
        </div>
        <button class="icon-button sidebar__close" aria-label="关闭侧栏" @click="sidebarOpen = false">
          ×
        </button>
      </div>

      <div class="workspace-switcher">
        <div>
          <span>当前工作区</span>
          <strong>{{ activeWorkspace.name }}</strong>
        </div>
        <div class="workspace-switcher__actions">
          <button
            v-if="activeWorkspace.slug !== 'ch4'"
            type="button"
            class="workspace-switcher__delete"
            :disabled="isSending || workspaceDeleting"
            title="永久删除当前工作区"
            @click="removeActiveWorkspace"
          >删除</button>
          <button
            type="button"
            class="workspace-switcher__exit"
            :disabled="isSending || workspaceDeleting"
            @click="leaveWorkspace"
          >退出</button>
        </div>
      </div>

      <button
        class="new-chat-button"
        :disabled="isLoading || isSending"
        @click="startNewConversation"
      >
        <span class="new-chat-button__icon">＋</span>
        新对话
      </button>

      <button
        class="new-chat-button documents-button"
        :class="{ 'documents-button--active': activeView === 'documents' }"
        @click="openDocuments"
      >
        <span class="new-chat-button__icon">▤</span>
        文档库
      </button>

      <button
        v-if="hasCh4Features"
        class="new-chat-button documents-button"
        :class="{ 'documents-button--active': activeView === 'evaluations' }"
        @click="openEvaluations"
      >
        <span class="new-chat-button__icon">✓</span>
        Agent Eval
      </button>

      <button
        v-if="hasCh4Features"
        class="new-chat-button documents-button"
        :class="{ 'documents-button--active': activeView === 'job-applications' }"
        @click="openJobApplications"
      >
        <span class="new-chat-button__icon">▦</span>
        求职投递
      </button>

      <div class="history-label">最近对话</div>
      <nav class="conversation-list" aria-label="历史对话">
        <div
          v-for="conversation in conversations"
          :key="conversation.id"
          class="conversation-row"
          :class="{ 'conversation-row--active': conversation.id === activeConversationId }"
        >
          <button
            class="conversation-item"
            :disabled="isSending || deletingConversationId === conversation.id"
            @click="openConversation(conversation.id)"
          >
            <span class="conversation-item__title">{{ conversation.title }}</span>
          </button>
          <button
            class="conversation-delete"
            :disabled="isSending || deletingConversationId === conversation.id"
            :aria-label="`删除对话：${conversation.title}`"
            @click="removeConversation(conversation.id)"
          >
            ×
          </button>
        </div>
      </nav>

      <button class="sidebar__footer" @click="openApiKeyDialog">
        <span class="status-dot" :class="{ 'status-dot--configured': apiKey }" />
        <span>{{ apiKeyStatusLabel }}</span>
      </button>
    </aside>

    <main v-if="activeView === 'chat'" class="chat-panel">
      <header class="topbar">
        <button class="icon-button menu-button" aria-label="打开侧栏" @click="sidebarOpen = true">
          ☰
        </button>
        <div>
          <div class="topbar__title">{{ activeConversation?.title || "Nano" }}</div>
          <div class="topbar__subtitle">DeepSeek</div>
        </div>
      </header>

      <section ref="messageList" class="message-list" aria-live="polite">
        <div v-if="isLoading" class="state-card">
          <span class="loader" />
          正在载入对话
        </div>

        <div v-else-if="messages.length === 0" class="welcome">
          <div class="welcome__mark">N</div>
          <h1>有什么可以帮忙的？</h1>
        </div>

        <div v-else class="message-stream">
          <article
            v-for="message in messages"
            :key="message.id"
            class="message"
            :class="`message--${message.role}`"
          >
            <div v-if="message.role === 'assistant'" class="assistant-avatar">N</div>
            <div class="message__body">
              <div v-if="message.role === 'assistant' && message.plan?.tasks?.length" class="research-plan">
                <strong>{{ message.plan.objective || "研究计划" }}</strong>
                <ol>
                  <li v-for="task in message.plan.tasks" :key="task.id">
                    <span v-if="task.agent" class="agent-role-badge">{{ agentLabel(task.agent) }}</span>
                    {{ task.question }}
                  </li>
                </ol>
              </div>
              <div v-if="message.role === 'assistant' && message.steps?.length" class="agent-steps">
                <div
                  v-for="step in message.steps"
                  :key="step.callId"
                  class="agent-step"
                  :class="`agent-step--${step.status}`"
                >
                  <span class="agent-step__status" />
                  <span v-if="step.agent" class="agent-role-badge">{{ agentLabel(step.agent) }}</span>
                  <span>{{ step.label }}</span>
                  <span v-if="step.retryAttempt" class="agent-step__detail">
                    第 {{ step.retryAttempt }} 次尝试
                  </span>
                  <span v-if="step.resultCount !== undefined" class="agent-step__detail">
                    {{ step.resultCount }} 条结果
                  </span>
                  <span v-else-if="step.durationMs" class="agent-step__detail">
                    {{ (step.durationMs / 1000).toFixed(1) }}s
                  </span>
                  <span v-if="step.message" class="agent-step__detail" :title="step.message">失败</span>
                </div>
              </div>
              <div
                v-if="message.role === 'assistant' && !message.content && message.status === 'streaming'"
                class="typing-indicator"
                aria-label="正在生成回答"
              >
                <span />
                <span />
                <span />
              </div>
              <div
                v-else-if="message.role === 'assistant'"
                class="message__content markdown-body"
                v-html="renderMarkdown(message.content)"
              />
              <div v-if="message.role === 'user' && message.attachments?.length" class="message-attachments">
                <figure
                  v-for="(attachment, index) in message.attachments"
                  :key="`${attachment.name}-${index}`"
                  class="message-attachment"
                  :class="`message-attachment--${attachment.kind}`"
                >
                  <img
                    v-if="attachment.kind === 'image'"
                    :src="attachmentPreviewUrl(attachment)"
                    :alt="attachment.name"
                  />
                  <span v-else class="message-attachment__icon">{{ attachmentTypeLabel(attachment) }}</span>
                  <figcaption>{{ attachment.name }}</figcaption>
                </figure>
              </div>
              <div v-if="message.role === 'user' && message.content" class="message__content">{{ message.content }}</div>
              <div
                v-if="message.role === 'user' && message.options?.mode"
                class="message-options"
              >
                <span>{{ messageModeLabel(message.options.mode) }}</span>
                <span v-if="message.options.use_rag">文档 RAG</span>
              </div>
              <div v-if="message.role === 'assistant' && message.sources?.length" class="message-sources">
                <button
                  v-for="source in message.sources"
                  :key="source.chunk_id"
                  type="button"
                  @click="openSource(source)"
                >
                  {{ source.document_name }}<span v-if="source.page_number"> · 第 {{ source.page_number }} 页</span>
                </button>
              </div>
              <div class="message__meta">
                <span>{{ formatDate(message.created_at) }}</span>
                <span v-if="message.status === 'stopped'">已停止</span>
                <span v-if="message.status === 'failed'">生成失败</span>
                <button
                  v-if="message.runId && ['stopped', 'failed'].includes(message.status)"
                  class="copy-button"
                  :disabled="isSending"
                  @click="resumeGeneration(message)"
                >继续任务</button>
                <button
                  v-if="message.role === 'assistant' && message.content"
                  class="copy-button"
                  aria-label="复制回答"
                  @click="copyMessage(message.content)"
                >
                  复制
                </button>
                <button
                  v-if="message.role === 'assistant' && message.runId"
                  class="copy-button"
                  @click="openTrace(message)"
                >运行详情</button>
              </div>
            </div>
          </article>

        </div>
      </section>

      <footer class="composer-area">
        <div v-if="errorMessage" class="error-banner" role="alert">
          {{ errorMessage }}
        </div>
        <div
          class="composer-box"
          :class="{ 'composer-box--dragging': composerDragging }"
          @dragenter.prevent="composerDragging = true"
          @dragover.prevent="composerDragging = true"
          @dragleave.self="composerDragging = false"
          @drop.prevent="handleComposerDrop"
        >
          <div v-if="pendingAttachments.length" class="pending-attachments">
            <div
              v-for="(attachment, index) in pendingAttachments"
              :key="`${attachment.name}-${index}`"
              class="pending-attachment"
            >
              <img
                v-if="attachment.kind === 'image'"
                :src="attachmentPreviewUrl(attachment)"
                :alt="attachment.name"
              />
              <span v-else class="pending-attachment__icon">{{ attachmentTypeLabel(attachment) }}</span>
              <span class="pending-attachment__name" :title="attachment.name">{{ attachment.name }}</span>
              <button
                type="button"
                class="pending-attachment__remove"
                aria-label="移除附件"
                title="移除附件"
                @click="removeChatAttachment(index)"
              >
                <svg viewBox="0 0 16 16" aria-hidden="true">
                  <path d="M4 4l8 8M12 4l-8 8" />
                </svg>
              </button>
            </div>
          </div>
          <div class="composer-input-row">
          <input
            ref="chatFileInput"
            class="visually-hidden"
            type="file"
            multiple
            :accept="CHAT_ATTACHMENT_ACCEPT"
            @change="addChatFiles($event.target.files)"
          />
          <button
            type="button"
            class="attach-button"
            :disabled="isSending || pendingAttachments.length >= MAX_CHAT_ATTACHMENTS"
            aria-label="添加文本或图片附件"
            title="添加文本或图片"
            @click="chatFileInput?.click()"
          >
            <svg viewBox="0 0 16 16" aria-hidden="true">
              <path d="M8 3v10M3 8h10" />
            </svg>
          </button>
          <textarea
            ref="composer"
            v-model="draft"
            rows="1"
            maxlength="10000"
            placeholder="给 Nano 发消息"
            aria-label="消息内容"
            @input="resizeComposer"
            @paste="handleComposerPaste"
            @keydown="handleComposerKeydown"
          />
          <button
            v-if="isSending"
            class="send-button stop-button"
            aria-label="停止生成"
            @click="stopGeneration"
          >
            ■
          </button>
          <button
            v-else
            class="send-button"
            :disabled="!canSend"
            aria-label="发送消息"
            @click="submitMessage"
          >
            ↑
          </button>
          </div>
        </div>
        <div class="composer-options">
          <div class="mode-selector" aria-label="Agent 模式">
            <button
              v-for="option in [
                { value: 'auto', label: '自动' },
                { value: 'chat', label: '快速回答' },
                { value: 'research', label: '深度研究' },
              ]"
              :key="option.value"
              type="button"
              :class="{ 'mode-selector__button--active': agentMode === option.value }"
              @click="setAgentMode(option.value)"
            >{{ option.label }}</button>
          </div>
          <button
            type="button"
            class="rag-toggle"
            :class="{ 'rag-toggle--active': useRag }"
            :aria-pressed="useRag"
            @click="toggleRag"
          >文档 RAG {{ useRag ? "已开启" : "已关闭" }}</button>
          <p class="composer-hint">Enter 发送 · Shift + Enter 换行</p>
        </div>
      </footer>
    </main>

    <DocumentsView
      v-else-if="activeView === 'documents'"
      :initial-document-id="documentTarget.id"
      :initial-page="documentTarget.page"
      :embedding-api-key="embeddingApiKey"
      :embedding-base-url="embeddingBaseUrl"
      @back="activeView = 'chat'"
    />

    <EvaluationsView
      v-else-if="activeView === 'evaluations'"
      :api-key="apiKey"
      :tavily-api-key="tavilyApiKey"
      @back="activeView = 'chat'"
      @configure-keys="openApiKeyDialog"
    />

    <JobApplicationsView
      v-else
      :api-key="apiKey"
      :tavily-api-key="tavilyApiKey"
      @back="activeView = 'chat'"
      @configure-keys="openApiKeyDialog"
    />

    <div v-if="apiKeyDialogOpen" class="dialog-backdrop" @click.self="apiKeyDialogOpen = false">
      <form class="api-key-dialog" @submit.prevent="saveApiKey">
        <div class="api-key-dialog__header">
          <div>
            <h2>API Keys</h2>
            <p>密钥只保存在当前浏览器中，并随消息请求发送到 Nano 后端。</p>
          </div>
          <button type="button" class="dialog-close" aria-label="关闭" @click="apiKeyDialogOpen = false">
            ×
          </button>
        </div>
        <div class="api-provider-grid">
          <section class="api-provider-panel">
        <label class="api-key-field">
          <span>DeepSeek API Key</span>
          <input
            v-model="apiKeyDraft"
            type="password"
            autocomplete="off"
            placeholder="sk-..."
            aria-label="DeepSeek API Key"
            autofocus
            @input="handleApiKeyDraftInput"
          />
        </label>
        <section v-if="apiKeyDraft.trim()" class="api-balance-card">
          <header>
            <div>
              <strong>DeepSeek 账户余额</strong>
              <small>该 API Key 所属账户</small>
            </div>
            <button
              type="button"
              class="balance-refresh"
              :disabled="apiBalanceLoading"
              @click="refreshApiBalance(apiKeyDraft)"
            >{{ apiBalanceLoading ? "查询中…" : "刷新" }}</button>
          </header>
          <p v-if="apiBalanceError" class="api-balance-error">{{ apiBalanceError }}</p>
          <div v-else-if="apiBalance?.balance_infos?.length" class="api-balance-list">
            <article v-for="info in apiBalance.balance_infos" :key="info.currency">
              <span>{{ info.currency }}</span>
              <strong>{{ formatBalance(info.total_balance, info.currency) }}</strong>
              <small>
                充值 {{ formatBalance(info.topped_up_balance, info.currency) }}
                · 赠金 {{ formatBalance(info.granted_balance, info.currency) }}
              </small>
            </article>
            <span
              class="api-balance-status"
              :class="{ 'api-balance-status--unavailable': !apiBalance.is_available }"
            >{{ apiBalance.is_available ? "可正常调用" : "余额不足" }}</span>
          </div>
          <p v-else-if="!apiBalanceLoading" class="api-balance-placeholder">
            点击刷新验证 Key 并查询余额。
          </p>
        </section>
          </section>
          <section class="api-provider-panel">
        <label class="api-key-field">
          <span>Tavily API Key（可选）</span>
          <input
            v-model="tavilyApiKeyDraft"
            type="password"
            autocomplete="off"
            placeholder="tvly-..."
            aria-label="Tavily API Key"
            @input="handleTavilyKeyDraftInput"
          />
        </label>
        <section v-if="tavilyApiKeyDraft.trim()" class="api-balance-card tavily-usage-card">
          <header>
            <div>
              <strong>Tavily Credits</strong>
              <small v-if="tavilyUsage">{{ tavilyUsage.account.current_plan }} 套餐</small>
              <small v-else>API Key 与账户用量</small>
            </div>
            <button
              type="button"
              class="balance-refresh"
              :disabled="tavilyUsageLoading"
              @click="refreshTavilyUsage(tavilyApiKeyDraft)"
            >{{ tavilyUsageLoading ? "查询中…" : "查询余量" }}</button>
          </header>
          <p v-if="tavilyUsageError" class="api-balance-error">{{ tavilyUsageError }}</p>
          <div v-else-if="tavilyUsage" class="tavily-usage-list">
            <article>
              <div>
                <span>当前 Key</span>
                <strong>{{ Math.max(0, tavilyUsage.key.limit - tavilyUsage.key.usage) }} credits 剩余</strong>
                <small>{{ tavilyUsage.key.usage }} / {{ tavilyUsage.key.limit }} 已用</small>
              </div>
              <div v-if="message.role === 'assistant' && message.artifacts?.length" class="message-artifacts">
                <a
                  v-for="artifact in message.artifacts"
                  :key="artifact.artifact_id"
                  class="message-artifact-download"
                  :href="artifact.download_url"
                  :download="artifact.filename"
                >
                  <span class="message-artifact-download__icon">
                    {{ artifact.kind === "pdf" ? "PDF" : "DOCX" }}
                  </span>
                  <span class="message-artifact-download__body">
                    <strong>{{ artifact.filename }}</strong>
                    <small>{{ formatFileSize(artifact.size_bytes) }} · {{ formatArtifactExpiry(artifact.expires_in_seconds) }}</small>
                  </span>
                  <svg viewBox="0 0 16 16" aria-hidden="true">
                    <path d="M8 2v8m0 0l-3-3m3 3l3-3M3 13h10" />
                  </svg>
                </a>
              </div>
              <div class="usage-track">
                <span :style="{ width: `${usagePercent(tavilyUsage.key.usage, tavilyUsage.key.limit)}%` }" />
              </div>
            </article>
            <article>
              <div>
                <span>账户套餐</span>
                <strong>{{ Math.max(0, tavilyUsage.account.plan_limit - tavilyUsage.account.plan_usage) }} credits 剩余</strong>
                <small>{{ tavilyUsage.account.plan_usage }} / {{ tavilyUsage.account.plan_limit }} 已用</small>
              </div>
              <div class="usage-track">
                <span :style="{ width: `${usagePercent(tavilyUsage.account.plan_usage, tavilyUsage.account.plan_limit)}%` }" />
              </div>
            </article>
            <div class="tavily-usage-breakdown">
              <span>Search {{ tavilyUsage.key.search_usage }}</span>
              <span>Extract {{ tavilyUsage.key.extract_usage }}</span>
              <span>Research {{ tavilyUsage.key.research_usage }}</span>
              <span v-if="tavilyUsage.account.paygo_limit">
                PayGo {{ tavilyUsage.account.paygo_usage }}/{{ tavilyUsage.account.paygo_limit }}
              </span>
            </div>
          </div>
          <p v-else-if="!tavilyUsageLoading" class="api-balance-placeholder">
            点击查询余量验证 Tavily Key。
          </p>
        </section>
          </section>
          <section class="api-provider-panel">
        <label class="api-key-field">
          <span>阿里云百炼 Embedding API Key（可选）</span>
          <input
            v-model="embeddingApiKeyDraft"
            type="password"
            autocomplete="off"
            placeholder="sk-..."
            aria-label="阿里云百炼 Embedding API Key"
            @input="handleEmbeddingKeyDraftInput"
          />
        </label>
        <label class="api-key-field">
          <span>Base URL</span>
          <input
            v-model="embeddingBaseUrlDraft"
            type="url"
            autocomplete="off"
            placeholder="https://dashscope.aliyuncs.com/compatible-mode/v1"
            aria-label="阿里云百炼 Embedding Base URL"
            @input="handleEmbeddingKeyDraftInput"
          />
          <small class="api-key-field__hint">API Key 与 Base URL 必须属于同一地域和服务方案</small>
        </label>
        <section v-if="embeddingApiKeyDraft.trim()" class="api-balance-card embedding-status-card">
          <header>
            <div>
              <strong>百炼 Embedding</strong>
              <small>用于文档索引与 RAG 查询向量化</small>
            </div>
            <button
              type="button"
              class="balance-refresh"
              :disabled="embeddingStatusLoading"
              @click="verifyEmbeddingKey(embeddingApiKeyDraft, embeddingBaseUrlDraft)"
            >{{ embeddingStatusLoading ? "验证中…" : "验证配置" }}</button>
          </header>
          <p v-if="embeddingStatusError" class="api-balance-error">{{ embeddingStatusError }}</p>
          <div v-else-if="embeddingStatus" class="embedding-status-result">
            <span class="api-balance-status">配置可用</span>
            <strong>{{ embeddingStatus.model }}</strong>
            <small>{{ embeddingStatus.dimensions }} 维 · 验证会产生一次极小的 Embedding 调用</small>
          </div>
          <p v-else-if="!embeddingStatusLoading" class="api-balance-placeholder">
            Key 仅保存在当前浏览器；服务器环境变量仍可作为后备配置。
          </p>
        </section>
          </section>
        </div>
        <div class="api-key-dialog__actions">
          <button v-if="apiKey" type="button" class="danger-button" @click="clearApiKey">
            清除全部
          </button>
          <span v-else />
          <button type="submit" class="primary-button" :disabled="!apiKeyDraft.trim()">
            保存
          </button>
        </div>
      </form>
    </div>

    <div v-if="traceDialogOpen" class="dialog-backdrop" @click.self="traceDialogOpen = false">
      <section class="trace-dialog" aria-label="Agent 运行详情">
        <header class="trace-dialog__header">
          <div>
            <h2>Agent 运行详情</h2>
            <p v-if="traceRun">{{ traceRun.mode }} · {{ traceRun.status }}</p>
          </div>
          <button class="dialog-close" aria-label="关闭" @click="traceDialogOpen = false">×</button>
        </header>
        <div v-if="traceLoading" class="trace-loading">正在加载 Trace…</div>
        <template v-else-if="traceRun">
          <div class="trace-metrics">
            <div><span>总耗时</span><strong>{{ formatDurationMs(traceRun.duration_ms) }}</strong></div>
            <div><span>工具调用</span><strong>{{ traceRun.tool_call_count }}</strong></div>
            <div><span>工具失败</span><strong>{{ traceRun.tool_failure_count }}</strong></div>
            <div><span>当前节点</span><strong>{{ traceRun.current_node || "—" }}</strong></div>
          </div>
          <div class="trace-timeline">
            <article v-for="event in traceEvents" :key="event.id" class="trace-event">
              <span class="trace-event__dot" :class="{ 'trace-event__dot--failed': event.event_type.endsWith('failed') }" />
              <div>
                <strong>{{ traceEventLabel(event) }}</strong>
                <span>{{ traceEventActor(event) }} · {{ formatDate(event.created_at) }}</span>
                <span v-if="event.duration_ms !== null">耗时 {{ formatDurationMs(event.duration_ms) }}</span>
                <details v-if="Object.keys(event.payload || {}).length">
                  <summary>查看事件数据</summary>
                  <pre>{{ JSON.stringify(event.payload, null, 2) }}</pre>
                </details>
              </div>
            </article>
          </div>
        </template>
      </section>
    </div>
  </div>
</template>
