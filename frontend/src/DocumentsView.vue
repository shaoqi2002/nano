<script setup>
import { computed, onMounted, ref, watch } from "vue";

import {
  deleteDocument,
  documentContentUrl,
  getDocumentText,
  listDocuments,
  uploadDocument,
} from "./api";
import { renderMarkdown } from "./markdown";


const emit = defineEmits(["back"]);
const documents = ref([]);
const activeDocumentId = ref(null);
const textPreview = ref("");
const errorMessage = ref("");
const isLoading = ref(true);
const isUploading = ref(false);
const isDeleting = ref(false);
const isPreviewLoading = ref(false);
const fileInput = ref(null);

const activeDocument = computed(() =>
  documents.value.find((document) => document.id === activeDocumentId.value),
);

const contentUrl = computed(() =>
  activeDocument.value ? documentContentUrl(activeDocument.value.id) : "",
);

function formatBytes(bytes) {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / (1024 * 1024)).toFixed(1)} MB`;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    year: "numeric",
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function fileIcon(document) {
  return {
    pdf: "PDF",
    markdown: "MD",
    text: "TXT",
    word: "DOC",
    image: "IMG",
  }[document.preview_kind] || "FILE";
}

async function loadDocuments() {
  isLoading.value = true;
  errorMessage.value = "";
  try {
    documents.value = await listDocuments();
    if (!documents.value.some((item) => item.id === activeDocumentId.value)) {
      activeDocumentId.value = documents.value[0]?.id || null;
    }
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isLoading.value = false;
  }
}

async function handleUpload(event) {
  const file = event.target.files?.[0];
  if (!file) return;

  isUploading.value = true;
  errorMessage.value = "";
  try {
    const document = await uploadDocument(file);
    documents.value.unshift(document);
    activeDocumentId.value = document.id;
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isUploading.value = false;
    event.target.value = "";
  }
}

async function removeActiveDocument() {
  const document = activeDocument.value;
  if (!document || !window.confirm(`删除“${document.original_name}”？此操作也会删除云端对象。`)) return;

  isDeleting.value = true;
  errorMessage.value = "";
  try {
    await deleteDocument(document.id);
    documents.value = documents.value.filter((item) => item.id !== document.id);
    activeDocumentId.value = documents.value[0]?.id || null;
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isDeleting.value = false;
  }
}

watch(activeDocument, async (document) => {
  textPreview.value = "";
  if (!document || !["text", "markdown", "word"].includes(document.preview_kind)) return;

  isPreviewLoading.value = true;
  errorMessage.value = "";
  try {
    textPreview.value = await getDocumentText(document.id);
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isPreviewLoading.value = false;
  }
}, { immediate: true });

onMounted(loadDocuments);
</script>

<template>
  <main class="documents-page">
    <header class="documents-topbar">
      <button class="back-button" aria-label="返回对话" @click="emit('back')">←</button>
      <div class="documents-heading">
        <strong>文档库</strong>
        <span>Backblaze B2</span>
      </div>
      <input
        ref="fileInput"
        class="visually-hidden"
        type="file"
        accept=".pdf,.md,.markdown,.txt,.csv,.json,.log,.docx,.png,.jpg,.jpeg,.gif,.webp"
        @change="handleUpload"
      >
      <button class="upload-button" :disabled="isUploading" @click="fileInput?.click()">
        {{ isUploading ? "正在上传…" : "上传文档" }}
      </button>
    </header>

    <div v-if="errorMessage" class="documents-error" role="alert">
      {{ errorMessage }}
    </div>

    <div class="documents-layout">
      <aside class="document-browser">
        <div class="document-browser__label">全部文档 · {{ documents.length }}</div>
        <div v-if="isLoading" class="document-state">正在加载文档…</div>
        <div v-else-if="documents.length === 0" class="document-state">
          <span class="empty-mark">↑</span>
          <strong>还没有文档</strong>
          <span>上传 PDF、Word、Markdown 或文本文件开始阅读。</span>
        </div>
        <button
          v-for="document in documents"
          v-else
          :key="document.id"
          class="document-row"
          :class="{ 'document-row--active': document.id === activeDocumentId }"
          @click="activeDocumentId = document.id"
        >
          <span class="document-icon">{{ fileIcon(document) }}</span>
          <span class="document-row__body">
            <strong>{{ document.original_name }}</strong>
            <span>{{ formatBytes(document.size_bytes) }} · {{ formatDate(document.created_at) }}</span>
          </span>
        </button>
      </aside>

      <section class="reader">
        <div v-if="!activeDocument" class="reader-empty">
          <div class="reader-empty__icon">N</div>
          <strong>选择一份文档开始阅读</strong>
        </div>

        <template v-else>
          <header class="reader-toolbar">
            <div>
              <strong>{{ activeDocument.original_name }}</strong>
              <span>{{ formatBytes(activeDocument.size_bytes) }}</span>
            </div>
            <div class="reader-actions">
              <a :href="documentContentUrl(activeDocument.id, true)">下载</a>
              <button :disabled="isDeleting" @click="removeActiveDocument">
                {{ isDeleting ? "删除中…" : "删除" }}
              </button>
            </div>
          </header>

          <div class="reader-content">
            <div v-if="isPreviewLoading" class="reader-status">正在读取文档…</div>
            <iframe
              v-else-if="activeDocument.preview_kind === 'pdf'"
              :key="activeDocument.id"
              class="pdf-reader"
              :src="contentUrl"
              :title="activeDocument.original_name"
            />
            <img
              v-else-if="activeDocument.preview_kind === 'image'"
              class="image-reader"
              :src="contentUrl"
              :alt="activeDocument.original_name"
            >
            <article
              v-else-if="activeDocument.preview_kind === 'markdown'"
              class="text-reader markdown-body"
              v-html="renderMarkdown(textPreview)"
            />
            <pre
              v-else-if="['text', 'word'].includes(activeDocument.preview_kind)"
              class="text-reader plain-reader"
            >{{ textPreview }}</pre>
            <div v-else class="reader-status">
              当前格式不支持在线预览，请下载后查看。
            </div>
          </div>
        </template>
      </section>
    </div>
  </main>
</template>

<style scoped>
.documents-page {
  display: flex;
  min-width: 0;
  height: 100vh;
  flex: 1;
  flex-direction: column;
  overflow: hidden;
  background: #202020;
}

.documents-topbar {
  display: flex;
  min-height: 62px;
  align-items: center;
  gap: 12px;
  padding: 10px 18px;
  border-bottom: 1px solid #353535;
  background: #242424;
}

.back-button,
.upload-button,
.reader-actions button {
  border: 0;
  cursor: pointer;
}

.back-button {
  width: 36px;
  height: 36px;
  border-radius: 9px;
  background: transparent;
  font-size: 20px;
}

.back-button:hover {
  background: #333;
}

.documents-heading {
  display: grid;
  flex: 1;
  gap: 2px;
}

.documents-heading strong {
  font-size: 15px;
}

.documents-heading span {
  color: #888;
  font-size: 11px;
}

.upload-button {
  padding: 9px 14px;
  border-radius: 9px;
  background: #f2f2f2;
  color: #171717;
  font-size: 13px;
  font-weight: 650;
}

.upload-button:disabled {
  cursor: wait;
  opacity: 0.5;
}

.visually-hidden {
  position: absolute;
  width: 1px;
  height: 1px;
  overflow: hidden;
  clip: rect(0, 0, 0, 0);
  white-space: nowrap;
}

.documents-error {
  padding: 10px 18px;
  border-bottom: 1px solid rgb(248 113 113 / 25%);
  background: rgb(127 29 29 / 24%);
  color: #fecaca;
  font-size: 13px;
}

.documents-layout {
  display: grid;
  min-height: 0;
  flex: 1;
  grid-template-columns: minmax(240px, 310px) 1fr;
}

.document-browser {
  min-height: 0;
  padding: 14px 10px;
  overflow-y: auto;
  border-right: 1px solid #353535;
  background: #1b1b1b;
}

.document-browser__label {
  padding: 3px 10px 11px;
  color: #888;
  font-size: 11px;
  font-weight: 650;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.document-state,
.reader-status,
.reader-empty {
  display: flex;
  align-items: center;
  justify-content: center;
  color: #929292;
}

.document-state {
  min-height: 220px;
  flex-direction: column;
  gap: 8px;
  padding: 20px;
  font-size: 13px;
  line-height: 1.5;
  text-align: center;
}

.document-state strong {
  color: #ddd;
  font-size: 14px;
}

.empty-mark {
  display: grid;
  width: 40px;
  height: 40px;
  margin-bottom: 4px;
  place-items: center;
  border: 1px solid #494949;
  border-radius: 12px;
  color: #ccc;
  font-size: 20px;
}

.document-row {
  display: flex;
  width: 100%;
  align-items: center;
  gap: 10px;
  padding: 10px;
  border: 0;
  border-radius: 10px;
  background: transparent;
  cursor: pointer;
  text-align: left;
}

.document-row:hover,
.document-row--active {
  background: #2c2c2c;
}

.document-icon {
  display: grid;
  width: 38px;
  height: 42px;
  flex: 0 0 38px;
  place-items: center;
  border: 1px solid #454545;
  border-radius: 8px;
  background: #252525;
  color: #9ed8cb;
  font-size: 9px;
  font-weight: 800;
}

.document-row__body {
  display: grid;
  min-width: 0;
  gap: 5px;
}

.document-row__body strong {
  overflow: hidden;
  color: #e5e5e5;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.document-row__body span {
  overflow: hidden;
  color: #777;
  font-size: 10px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reader {
  display: grid;
  min-width: 0;
  min-height: 0;
  grid-template-rows: auto 1fr;
}

.reader-empty {
  height: 100%;
  flex-direction: column;
  gap: 13px;
}

.reader-empty__icon {
  display: grid;
  width: 48px;
  height: 48px;
  place-items: center;
  border-radius: 15px;
  background: #f2f2f2;
  color: #171717;
  font-weight: 800;
}

.reader-toolbar {
  display: flex;
  min-height: 58px;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  padding: 9px 16px;
  border-bottom: 1px solid #353535;
}

.reader-toolbar > div:first-child {
  display: grid;
  min-width: 0;
  gap: 3px;
}

.reader-toolbar strong {
  overflow: hidden;
  font-size: 13px;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.reader-toolbar span {
  color: #777;
  font-size: 10px;
}

.reader-actions {
  display: flex;
  flex: 0 0 auto;
  gap: 7px;
}

.reader-actions a,
.reader-actions button {
  padding: 7px 10px;
  border-radius: 7px;
  background: #303030;
  color: #bbb;
  font-size: 11px;
  text-decoration: none;
}

.reader-actions a:hover,
.reader-actions button:hover {
  background: #3a3a3a;
  color: #eee;
}

.reader-actions button:last-child {
  color: #f3a7a7;
}

.reader-content {
  min-width: 0;
  min-height: 0;
  overflow: auto;
  background: #292929;
}

.reader-status {
  height: 100%;
  font-size: 13px;
}

.pdf-reader {
  width: 100%;
  height: 100%;
  border: 0;
  background: #fff;
}

.image-reader {
  display: block;
  max-width: calc(100% - 48px);
  max-height: calc(100% - 48px);
  margin: 24px auto;
  border-radius: 6px;
  box-shadow: 0 14px 50px rgb(0 0 0 / 35%);
}

.text-reader {
  width: min(820px, calc(100% - 40px));
  min-height: calc(100% - 40px);
  margin: 20px auto;
  padding: clamp(22px, 5vw, 54px);
  border: 1px solid #414141;
  border-radius: 8px;
  background: #222;
  box-shadow: 0 12px 45px rgb(0 0 0 / 18%);
}

.plain-reader {
  color: #dedede;
  font-family: inherit;
  font-size: 14px;
  line-height: 1.8;
  overflow-wrap: anywhere;
  white-space: pre-wrap;
}

@media (max-width: 760px) {
  .documents-layout {
    grid-template-columns: 130px minmax(0, 1fr);
  }

  .document-browser {
    padding: 9px 6px;
  }

  .document-browser__label {
    padding-right: 6px;
    padding-left: 6px;
  }

  .document-row {
    display: grid;
    justify-items: center;
    padding: 9px 5px;
  }

  .document-row__body {
    width: 100%;
    text-align: center;
  }

  .document-row__body span {
    display: none;
  }

  .reader-toolbar {
    padding: 7px 9px;
  }

  .reader-toolbar span {
    display: none;
  }

  .text-reader {
    width: calc(100% - 16px);
    margin: 8px;
    padding: 18px;
  }
}
</style>
