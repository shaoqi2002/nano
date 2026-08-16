<script setup>
import { computed, nextTick, onMounted, reactive, ref } from "vue";

import {
  createConversation,
  deleteConversation as deleteConversationRequest,
  getAgentRun,
  getAgentRunEvents,
  getDeepSeekBalance,
  getMessages,
  listConversations,
  resumeAgentRunStream,
  sendMessageStream,
} from "./api";
import DocumentsView from "./DocumentsView.vue";
import EvaluationsView from "./EvaluationsView.vue";
import { renderMarkdown } from "./markdown";


const ACTIVE_KEY = "nano-agent-active-conversation";
const API_KEY_STORAGE_KEY = "nano-deepseek-api-key";
const TAVILY_API_KEY_STORAGE_KEY = "nano-tavily-api-key";
const RAG_STORAGE_KEY = "nano-rag-enabled";
const AGENT_MODE_STORAGE_KEY = "nano-agent-mode";
const ACTIVE_RUN_STORAGE_KEY = "nano-agent-active-run";

const conversations = ref([]);
const activeView = ref("chat");
const activeConversationId = ref(localStorage.getItem(ACTIVE_KEY));
const messages = ref([]);
const draft = ref("");
const isLoading = ref(false);
const isSending = ref(false);
const errorMessage = ref("");
const sidebarOpen = ref(false);
const messageList = ref(null);
const composer = ref(null);
const apiKey = ref(localStorage.getItem(API_KEY_STORAGE_KEY) || "");
const apiKeyDraft = ref("");
const tavilyApiKey = ref(localStorage.getItem(TAVILY_API_KEY_STORAGE_KEY) || "");
const tavilyApiKeyDraft = ref("");
const apiKeyDialogOpen = ref(false);
const apiBalance = ref(null);
const apiBalanceLoading = ref(false);
const apiBalanceError = ref("");
let apiBalanceRequestId = 0;
const deletingConversationId = ref(null);
const useRag = ref(localStorage.getItem(RAG_STORAGE_KEY) !== "false");
const agentMode = ref(localStorage.getItem(AGENT_MODE_STORAGE_KEY) || "auto");
const documentTarget = ref({ id: null, page: null });
const streamController = ref(null);
const resumableRun = ref(JSON.parse(localStorage.getItem(ACTIVE_RUN_STORAGE_KEY) || "null"));
const traceDialogOpen = ref(false);
const traceLoading = ref(false);
const traceRun = ref(null);
const traceEvents = ref([]);

const activeConversation = computed(() =>
  conversations.value.find((item) => item.id === activeConversationId.value),
);

const canSend = computed(
  () => draft.value.trim().length > 0 && !isSending.value && activeConversationId.value,
);

const apiBalanceSummary = computed(() => {
  const infos = apiBalance.value?.balance_infos || [];
  return infos.map((info) => formatBalance(info.total_balance, info.currency)).join(" / ");
});

function rememberActiveConversation(id) {
  activeConversationId.value = id;
  localStorage.setItem(ACTIVE_KEY, id);
}

function openApiKeyDialog() {
  apiKeyDraft.value = apiKey.value;
  tavilyApiKeyDraft.value = tavilyApiKey.value;
  apiKeyDialogOpen.value = true;
  sidebarOpen.value = false;
  if (apiKey.value) void refreshApiBalance(apiKey.value);
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
  apiKeyDialogOpen.value = false;
  errorMessage.value = "";
  void refreshApiBalance(value);
}

function clearApiKey() {
  apiBalanceRequestId += 1;
  apiKey.value = "";
  apiKeyDraft.value = "";
  tavilyApiKey.value = "";
  tavilyApiKeyDraft.value = "";
  localStorage.removeItem(API_KEY_STORAGE_KEY);
  localStorage.removeItem(TAVILY_API_KEY_STORAGE_KEY);
  apiKeyDialogOpen.value = false;
  apiBalance.value = null;
  apiBalanceError.value = "";
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

async function removeConversation(id) {
  const conversation = conversations.value.find((item) => item.id === id);
  if (!window.confirm(`删除“${conversation?.title || "该对话"}”及其全部消息？`)) return;

  deletingConversationId.value = id;
  errorMessage.value = "";

  try {
    await deleteConversationRequest(id);
    conversations.value = conversations.value.filter((item) => item.id !== id);

    if (activeConversationId.value === id) {
      localStorage.removeItem(ACTIVE_KEY);
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
  }[name] || name;
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
    localStorage.setItem(ACTIVE_RUN_STORAGE_KEY, JSON.stringify(resumableRun.value));
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
  } else if (event.type === "message.completed") {
    Object.assign(message, event.message, {
      steps: message.steps,
      status: "completed",
    });
    resumableRun.value = null;
    localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    if (apiKey.value) void refreshApiBalance(apiKey.value);
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
  if (!content || !canSend.value) return;

  if (!apiKey.value) {
    errorMessage.value = "请先在左下角设置 DeepSeek API Key";
    openApiKeyDialog();
    return;
  }

  const conversationId = activeConversationId.value;
  const optimisticMessage = {
    id: `local-${Date.now()}`,
    role: "user",
    content,
    created_at: new Date().toISOString(),
  };
  const streamingMessage = reactive({
    id: `stream-${Date.now()}`,
    role: "assistant",
    content: "",
    sources: [],
    steps: [],
    plan: null,
    runId: null,
    status: "streaming",
    created_at: new Date().toISOString(),
  });

  messages.value.push(optimisticMessage, streamingMessage);
  updateConversationTitle(content);
  draft.value = "";
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

onMounted(async () => {
  if (apiKey.value) void refreshApiBalance(apiKey.value);
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
        localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
      }
    } catch {
      resumableRun.value = null;
      localStorage.removeItem(ACTIVE_RUN_STORAGE_KEY);
    }
  }
});
</script>

<template>
  <div class="app-shell">
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
        class="new-chat-button documents-button"
        :class="{ 'documents-button--active': activeView === 'evaluations' }"
        @click="openEvaluations"
      >
        <span class="new-chat-button__icon">✓</span>
        Agent Eval
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
        <span
          class="status-dot"
          :class="{
            'status-dot--configured': apiKey && apiBalance?.is_available !== false,
            'status-dot--unavailable': apiBalance?.is_available === false,
          }"
        />
        <span class="sidebar__footer-copy">
          <span>{{ apiKey && tavilyApiKey ? "API Keys 已配置" : apiKey ? "DeepSeek 已配置" : "设置 API Key" }}</span>
          <small v-if="apiBalanceSummary">余额 {{ apiBalanceSummary }}</small>
          <small v-else-if="apiBalanceLoading">正在查询余额…</small>
          <small v-else-if="apiBalanceError && apiKey">余额查询失败</small>
        </span>
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
              <div v-else class="message__content">{{ message.content }}</div>
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
        <div class="composer-box">
          <textarea
            ref="composer"
            v-model="draft"
            rows="1"
            maxlength="10000"
            placeholder="给 Nano 发消息"
            aria-label="消息内容"
            @input="resizeComposer"
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
      @back="activeView = 'chat'"
    />

    <EvaluationsView
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
        <label class="api-key-field">
          <span>Tavily API Key（可选）</span>
          <input
            v-model="tavilyApiKeyDraft"
            type="password"
            autocomplete="off"
            placeholder="tvly-..."
            aria-label="Tavily API Key"
          />
        </label>
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
