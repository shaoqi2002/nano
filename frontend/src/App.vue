<script setup>
import { computed, nextTick, onMounted, ref } from "vue";

import {
  createConversation,
  deleteConversation as deleteConversationRequest,
  getMessages,
  listConversations,
  sendMessage,
} from "./api";
import { renderMarkdown } from "./markdown";


const ACTIVE_KEY = "nano-agent-active-conversation";
const API_KEY_STORAGE_KEY = "nano-deepseek-api-key";
const TAVILY_API_KEY_STORAGE_KEY = "nano-tavily-api-key";

const conversations = ref([]);
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
const deletingConversationId = ref(null);

const activeConversation = computed(() =>
  conversations.value.find((item) => item.id === activeConversationId.value),
);

const canSend = computed(
  () => draft.value.trim().length > 0 && !isSending.value && activeConversationId.value,
);

function rememberActiveConversation(id) {
  activeConversationId.value = id;
  localStorage.setItem(ACTIVE_KEY, id);
}

function openApiKeyDialog() {
  apiKeyDraft.value = apiKey.value;
  tavilyApiKeyDraft.value = tavilyApiKey.value;
  apiKeyDialogOpen.value = true;
  sidebarOpen.value = false;
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
}

function clearApiKey() {
  apiKey.value = "";
  apiKeyDraft.value = "";
  tavilyApiKey.value = "";
  tavilyApiKeyDraft.value = "";
  localStorage.removeItem(API_KEY_STORAGE_KEY);
  localStorage.removeItem(TAVILY_API_KEY_STORAGE_KEY);
  apiKeyDialogOpen.value = false;
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

  if (id === activeConversationId.value && messages.value.length) {
    sidebarOpen.value = false;
    return;
  }

  errorMessage.value = "";
  isLoading.value = true;
  rememberActiveConversation(id);

  try {
    const result = await getMessages(id);
    messages.value = result.messages;
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

  messages.value.push(optimisticMessage);
  updateConversationTitle(content);
  draft.value = "";
  errorMessage.value = "";
  isSending.value = true;
  resizeComposer();
  await scrollToBottom();

  try {
    await sendMessage(
      conversationId,
      content,
      apiKey.value,
      tavilyApiKey.value,
    );
    const history = await getMessages(conversationId);
    messages.value = history.messages;
    await scrollToBottom();
  } catch (error) {
    errorMessage.value = error.message;
    try {
      const history = await getMessages(conversationId);
      messages.value = history.messages;
    } catch {
      // Keep the optimistic message when the server cannot be reached.
    }
  } finally {
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

onMounted(async () => {
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
        <span>{{ apiKey && tavilyApiKey ? "API Keys 已配置" : apiKey ? "DeepSeek 已配置" : "设置 API Key" }}</span>
      </button>
    </aside>

    <main class="chat-panel">
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
              <div
                v-if="message.role === 'assistant'"
                class="message__content markdown-body"
                v-html="renderMarkdown(message.content)"
              />
              <div v-else class="message__content">{{ message.content }}</div>
              <div class="message__meta">
                <span>{{ formatDate(message.created_at) }}</span>
                <button
                  v-if="message.role === 'assistant'"
                  class="copy-button"
                  aria-label="复制回答"
                  @click="copyMessage(message.content)"
                >
                  复制
                </button>
              </div>
            </div>
          </article>

          <article v-if="isSending" class="message message--assistant">
            <div class="assistant-avatar">N</div>
            <div class="typing-indicator" aria-label="正在生成回答">
              <span />
              <span />
              <span />
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
            class="send-button"
            :disabled="!canSend"
            aria-label="发送消息"
            @click="submitMessage"
          >
            ↑
          </button>
        </div>
        <p class="composer-hint">Enter 发送 · Shift + Enter 换行</p>
      </footer>
    </main>

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
          />
        </label>
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
  </div>
</template>
