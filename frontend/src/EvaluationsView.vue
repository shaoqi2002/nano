<script setup>
import { computed, onMounted, ref } from "vue";

import {
  createEvalCase,
  deleteEvalCase,
  getEvalDataset,
  getEvalRun,
  listEvalRuns,
  runEvalStream,
  updateEvalCase,
} from "./api";
import EvalCaseForm from "./EvalCaseForm.vue";
import { renderMarkdown } from "./markdown";


const emit = defineEmits(["back", "configure-keys"]);
const props = defineProps({
  apiKey: { type: String, default: "" },
  tavilyApiKey: { type: String, default: "" },
});

const dataset = ref(null);
const selectedIds = ref([]);
const runs = ref([]);
const activeRun = ref(null);
const results = ref([]);
const progress = ref(null);
const isLoading = ref(true);
const isRunning = ref(false);
const errorMessage = ref("");
const controller = ref(null);
const judgeEnabled = ref(false);
const judgeWeight = ref(0.5);
const editorOpen = ref(false);
const editingCase = ref(null);
const isSavingCase = ref(false);

const selectedCount = computed(() => selectedIds.value.length);
const passRate = computed(() => {
  if (!activeRun.value?.case_count) return "—";
  return `${Math.round((activeRun.value.passed_count / activeRun.value.case_count) * 100)}%`;
});

function formatDuration(value) {
  if (value === null || value === undefined) return "—";
  return value < 1000 ? `${value} ms` : `${(value / 1000).toFixed(1)} s`;
}

function formatDate(value) {
  return new Intl.DateTimeFormat("zh-CN", {
    month: "2-digit",
    day: "2-digit",
    hour: "2-digit",
    minute: "2-digit",
  }).format(new Date(value));
}

function toggleCase(id) {
  selectedIds.value = selectedIds.value.includes(id)
    ? selectedIds.value.filter((item) => item !== id)
    : [...selectedIds.value, id];
}

async function reloadDataset() {
  const currentIds = new Set(selectedIds.value);
  dataset.value = await getEvalDataset();
  selectedIds.value = dataset.value.cases
    .filter((item) => currentIds.has(item.id))
    .map((item) => item.id);
}

function openCaseEditor(item = null) {
  editingCase.value = item;
  editorOpen.value = true;
}

async function saveCase(definition) {
  if (isSavingCase.value) return;
  isSavingCase.value = true;
  errorMessage.value = "";
  try {
    const saved = editingCase.value?.editable
      ? await updateEvalCase(editingCase.value.id, definition)
      : await createEvalCase(definition);
    await reloadDataset();
    if (!selectedIds.value.includes(saved.id)) selectedIds.value.push(saved.id);
    editorOpen.value = false;
    editingCase.value = null;
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isSavingCase.value = false;
  }
}

async function removeCase(item) {
  if (!window.confirm(`删除自定义用例“${item.title}”？历史评测结果会保留。`)) return;
  errorMessage.value = "";
  try {
    await deleteEvalCase(item.id);
    selectedIds.value = selectedIds.value.filter((id) => id !== item.id);
    await reloadDataset();
  } catch (error) {
    errorMessage.value = error.message;
  }
}

function handleEvalEvent(event) {
  if (event.type === "eval.started") {
    activeRun.value = {
      id: event.run_id,
      status: "running",
      case_count: event.case_count,
      passed_count: 0,
      score: null,
      duration_ms: null,
      config: {
        judge_enabled: event.judge_enabled,
        judge_weight: judgeWeight.value,
        judge_model: "configured judge model",
      },
    };
    results.value = [];
  } else if (event.type === "case.started") {
    progress.value = {
      caseId: event.case_id,
      title: event.title,
      index: event.index,
      total: event.total,
      judging: false,
    };
  } else if (event.type === "case.judging") {
    progress.value = { ...progress.value, judging: true };
  } else if (event.type === "case.completed") {
    results.value.push(event.result);
    activeRun.value = {
      ...activeRun.value,
      passed_count: results.value.filter((item) => item.passed).length,
      score: results.value.reduce((sum, item) => sum + item.score, 0) / results.value.length,
    };
  } else if (event.type === "eval.completed") {
    activeRun.value = { ...activeRun.value, ...event.run };
    progress.value = null;
  } else if (event.type === "eval.failed") {
    throw new Error(event.message || "评测运行失败");
  }
}

async function startEval() {
  if (!props.apiKey) {
    emit("configure-keys");
    return;
  }
  if (!selectedIds.value.length || isRunning.value) return;
  isRunning.value = true;
  errorMessage.value = "";
  controller.value = new AbortController();
  try {
    await runEvalStream(
      selectedIds.value,
      props.apiKey,
      props.tavilyApiKey,
      judgeEnabled.value,
      judgeWeight.value,
      handleEvalEvent,
      controller.value.signal,
    );
    runs.value = await listEvalRuns();
  } catch (error) {
    if (error.name === "AbortError") {
      activeRun.value = { ...activeRun.value, status: "cancelled" };
      progress.value = null;
    } else {
      errorMessage.value = error.message;
    }
  } finally {
    isRunning.value = false;
    controller.value = null;
  }
}

async function openRun(id) {
  errorMessage.value = "";
  try {
    const run = await getEvalRun(id);
    activeRun.value = run;
    results.value = run.results || [];
  } catch (error) {
    errorMessage.value = error.message;
  }
}

onMounted(async () => {
  try {
    [dataset.value, runs.value] = await Promise.all([
      getEvalDataset(),
      listEvalRuns(),
    ]);
    selectedIds.value = dataset.value.cases.map((item) => item.id);
    if (runs.value.length) await openRun(runs.value[0].id);
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isLoading.value = false;
  }
});
</script>

<template>
  <main class="eval-page">
    <header class="eval-topbar">
      <button class="back-button" aria-label="返回对话" @click="emit('back')">←</button>
      <div>
        <strong>Agent Eval</strong>
        <span v-if="dataset">{{ dataset.version }}</span>
      </div>
      <button
        v-if="isRunning"
        class="stop-button"
        @click="controller?.abort()"
      >停止</button>
      <button
        v-else
        class="run-button"
        :disabled="!selectedCount"
        @click="startEval"
      >运行 {{ selectedCount }} 个用例</button>
    </header>

    <div v-if="errorMessage" class="eval-error">{{ errorMessage }}</div>
    <div v-if="isLoading" class="eval-loading">正在加载评测集…</div>

    <div v-else class="eval-layout">
      <aside class="eval-sidebar">
        <section>
          <div class="eval-sidebar__title">
            <h2>评测用例</h2>
            <button type="button" @click="openCaseEditor()">＋ 新建</button>
          </div>
          <p>{{ dataset?.description }}</p>
          <label class="judge-toggle">
            <input v-model="judgeEnabled" type="checkbox">
            <span>
              <strong>LLM-as-a-Judge</strong>
              <small>启用后每个用例增加一次模型调用</small>
            </span>
          </label>
          <label v-if="judgeEnabled" class="judge-weight">
            <span>Judge 权重 {{ Math.round(judgeWeight * 100) }}%</span>
            <input v-model.number="judgeWeight" type="range" min="0.1" max="0.9" step="0.1">
          </label>
          <div
            v-for="item in dataset?.cases"
            :key="item.id"
            class="eval-case-row"
          >
            <button
              class="eval-case"
              :class="{ 'eval-case--selected': selectedIds.includes(item.id) }"
              @click="toggleCase(item.id)"
            >
              <span class="eval-checkbox">{{ selectedIds.includes(item.id) ? "✓" : "" }}</span>
              <span>
                <strong>{{ item.title }}</strong>
                <small>{{ item.mode }} · {{ item.source === "custom" ? "自定义" : "预置" }}</small>
              </span>
            </button>
            <div v-if="item.editable" class="eval-case-actions">
              <button type="button" title="编辑" @click="openCaseEditor(item)">✎</button>
              <button type="button" title="删除" @click="removeCase(item)">×</button>
            </div>
          </div>
        </section>
        <section class="eval-history">
          <h2>历史运行</h2>
          <button
            v-for="run in runs"
            :key="run.id"
            :class="{ 'eval-history__item--active': activeRun?.id === run.id }"
            @click="openRun(run.id)"
          >
            <strong>{{ Math.round((run.score || 0) * 100) }}%</strong>
            <span>{{ run.passed_count }}/{{ run.case_count }} · {{ formatDate(run.created_at) }}</span>
          </button>
        </section>
      </aside>

      <section class="eval-content">
        <div v-if="progress" class="eval-progress">
          <span>{{ progress.index }}/{{ progress.total }}</span>
          <div>
            <strong>{{ progress.title }}</strong>
            <small>{{ progress.judging ? "LLM Judge 正在独立评审…" : "Agent 正在执行测试用例…" }}</small>
          </div>
        </div>

        <div v-if="activeRun" class="eval-summary">
          <div><span>总分</span><strong>{{ activeRun.score === null ? "运行中" : `${Math.round(activeRun.score * 100)}%` }}</strong></div>
          <div><span>通过率</span><strong>{{ passRate }}</strong></div>
          <div><span>通过用例</span><strong>{{ activeRun.passed_count }}/{{ activeRun.case_count }}</strong></div>
          <div><span>总耗时</span><strong>{{ formatDuration(activeRun.duration_ms) }}</strong></div>
        </div>
        <div v-if="activeRun?.config?.judge_enabled" class="judge-banner">
          Judge 已启用 · 权重 {{ Math.round((activeRun.config.judge_weight || 0.5) * 100) }}%
          · {{ activeRun.config.judge_model }}
        </div>

        <div v-if="!activeRun" class="eval-empty">选择用例并运行第一次评测。</div>
        <div v-else class="eval-results">
          <article
            v-for="result in results"
            :key="result.id || result.case_id"
            class="eval-result"
            :class="result.passed ? 'eval-result--passed' : 'eval-result--failed'"
          >
            <header>
              <span>{{ result.passed ? "PASS" : "FAIL" }}</span>
              <strong>{{ result.title }}</strong>
              <small>{{ Math.round(result.score * 100) }}% · {{ formatDuration(result.duration_ms) }}</small>
            </header>
            <p v-if="result.error" class="eval-result__error">{{ result.error }}</p>
            <details>
              <summary>查看评分和输出</summary>
              <div class="eval-checks">
                <span
                  v-for="(passed, name) in result.metrics?.checks"
                  :key="name"
                  :class="{ 'eval-check--failed': !passed }"
                >{{ passed ? "✓" : "×" }} {{ name }}</span>
              </div>
              <div v-if="result.metrics?.judge" class="judge-result">
                <header>
                  <strong>LLM Judge</strong>
                  <span>{{ Math.round(result.metrics.judge.normalized_score * 100) }}%</span>
                </header>
                <div>
                  <span>正确性 {{ result.metrics.judge.correctness }}/5</span>
                  <span>完整性 {{ result.metrics.judge.completeness }}/5</span>
                  <span>依据性 {{ result.metrics.judge.groundedness }}/5</span>
                  <span>指令遵循 {{ result.metrics.judge.instruction_following }}/5</span>
                </div>
                <section class="eval-markdown-panel">
                  <strong>评分说明</strong>
                  <div
                    class="markdown-body"
                    v-html="renderMarkdown(result.metrics.judge.reason)"
                  />
                </section>
              </div>
              <p v-else-if="result.metrics?.judge_error" class="eval-result__error">
                Judge 失败，已回退到确定性评分：{{ result.metrics.judge_error }}
              </p>
              <section class="eval-markdown-panel eval-output-markdown">
                <strong>Agent 输出</strong>
                <div class="markdown-body" v-html="renderMarkdown(result.output)" />
              </section>
            </details>
          </article>
        </div>
      </section>
    </div>

    <div v-if="editorOpen" class="eval-dialog-backdrop" @click.self="editorOpen = false">
      <section class="eval-case-dialog" aria-label="自定义评测用例">
        <header>
          <div>
            <strong>{{ editingCase?.editable ? "编辑自定义用例" : "新建自定义用例" }}</strong>
            <span>选择预置模板后，只需调整需要变化的条件</span>
          </div>
          <button type="button" aria-label="关闭" @click="editorOpen = false">×</button>
        </header>
        <div v-if="isSavingCase" class="eval-case-saving">正在保存…</div>
        <EvalCaseForm
          v-else
          :initial-case="editingCase"
          :options="dataset.form_options"
          :templates="dataset.cases"
          @cancel="editorOpen = false"
          @save="saveCase"
        />
      </section>
    </div>
  </main>
</template>

<style scoped>
.eval-page { display: flex; width: 100%; height: 100vh; flex-direction: column; overflow: hidden; background: #202020; }
.eval-topbar { display: flex; min-height: 62px; align-items: center; gap: 12px; padding: 10px 18px; border-bottom: 1px solid #353535; background: #242424; }
.eval-topbar > div { display: grid; flex: 1; gap: 2px; }
.eval-topbar strong { font-size: 15px; }
.eval-topbar span { color: #888; font-size: 10px; }
.back-button, .run-button, .stop-button { border: 0; border-radius: 8px; cursor: pointer; }
.back-button { width: 36px; height: 36px; background: transparent; color: #ccc; font-size: 20px; }
.run-button, .stop-button { padding: 9px 13px; background: #e6e6e6; color: #181818; font-weight: 650; }
.stop-button { background: #553333; color: #f2bcbc; }
.run-button:disabled { cursor: not-allowed; opacity: .45; }
.eval-error { padding: 9px 18px; background: #512828; color: #f4b5b5; font-size: 12px; }
.eval-loading, .eval-empty { display: grid; height: 100%; place-items: center; color: #888; }
.eval-layout { display: grid; min-height: 0; flex: 1; grid-template-columns: 280px minmax(0, 1fr); }
.eval-sidebar { min-height: 0; padding: 14px 10px; overflow-y: auto; border-right: 1px solid #353535; background: #1b1b1b; }
.eval-sidebar section { display: grid; gap: 6px; }
.eval-sidebar h2 { margin: 4px 8px 0; color: #aaa; font-size: 11px; text-transform: uppercase; }
.eval-sidebar__title { display: flex; align-items: center; justify-content: space-between; }
.eval-sidebar__title button { margin-right: 5px; padding: 4px 7px; border: 1px solid #414141; border-radius: 6px; background: #292929; color: #9ac8bd; cursor: pointer; font-size: 9px; }
.eval-sidebar p { margin: 2px 8px 8px; color: #777; font-size: 10px; line-height: 1.5; }
.judge-toggle { display: grid; grid-template-columns: 18px minmax(0, 1fr); gap: 7px; margin: 2px 8px 8px; padding: 9px; border: 1px solid #3d3d3d; border-radius: 8px; cursor: pointer; }
.judge-toggle input { margin: 2px 0 0; accent-color: #82c9b9; }
.judge-toggle > span { display: grid; gap: 3px; }
.judge-toggle strong { color: #ccc; font-size: 11px; }
.judge-toggle small, .judge-weight span { color: #777; font-size: 9px; }
.judge-weight { display: grid; gap: 5px; margin: 0 8px 9px; }
.judge-weight input { width: 100%; accent-color: #82c9b9; }
.eval-case-row { position: relative; display: grid; }
.eval-case { display: grid; width: 100%; grid-template-columns: 20px minmax(0, 1fr); gap: 7px; padding: 9px 54px 9px 9px; border: 0; border-radius: 8px; background: transparent; color: #aaa; cursor: pointer; text-align: left; }
.eval-case:hover, .eval-case--selected { background: #2c2c2c; }
.eval-checkbox { display: grid; width: 17px; height: 17px; place-items: center; border: 1px solid #555; border-radius: 4px; color: #8fcaba; font-size: 10px; }
.eval-case > span:last-child { display: grid; gap: 3px; }
.eval-case strong { overflow: hidden; color: #ddd; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.eval-case small { color: #777; font-size: 9px; }
.eval-case-actions { position: absolute; top: 50%; right: 6px; display: flex; gap: 2px; transform: translateY(-50%); }
.eval-case-actions button { display: grid; width: 20px; height: 20px; place-items: center; border: 0; border-radius: 5px; background: #353535; color: #999; cursor: pointer; }
.eval-case-actions button:hover { background: #444; color: #ddd; }
.eval-history { margin-top: 20px; padding-top: 12px; border-top: 1px solid #333; }
.eval-history button { display: flex; align-items: center; justify-content: space-between; padding: 8px; border: 0; border-radius: 7px; background: transparent; color: #aaa; cursor: pointer; }
.eval-history button:hover, .eval-history__item--active { background: #292929 !important; }
.eval-history button strong { color: #9ed8cb; font-size: 12px; }
.eval-history button span { font-size: 9px; }
.eval-content { min-width: 0; padding: clamp(14px, 3vw, 28px); overflow-y: auto; }
.eval-progress { display: flex; align-items: center; gap: 12px; margin-bottom: 12px; padding: 12px; border: 1px solid #4b4935; border-radius: 10px; background: #302e23; }
.eval-progress > span { color: #e1c66f; font-size: 12px; }
.eval-progress div { display: grid; gap: 2px; }
.eval-progress strong { font-size: 12px; }
.eval-progress small { color: #8f8b78; font-size: 10px; }
.eval-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 10px; margin-bottom: 18px; }
.eval-summary div { display: grid; gap: 5px; padding: 14px; border: 1px solid #393939; border-radius: 10px; background: #272727; }
.eval-summary span { color: #888; font-size: 10px; }
.eval-summary strong { color: #ddd; font-size: 18px; }
.judge-banner { margin: -8px 0 14px; padding: 8px 11px; border: 1px solid #3d4946; border-radius: 8px; background: #26312f; color: #9dbab3; font-size: 10px; }
.eval-results { display: grid; gap: 9px; }
.eval-result { overflow: hidden; border: 1px solid #3b3b3b; border-radius: 10px; background: #262626; }
.eval-result > header { display: grid; grid-template-columns: 44px minmax(0, 1fr) auto; align-items: center; gap: 9px; padding: 11px 13px; }
.eval-result header span { color: #85c5b6; font-size: 9px; font-weight: 800; }
.eval-result--failed header span { color: #e68c8c; }
.eval-result header strong { font-size: 12px; }
.eval-result header small { color: #888; font-size: 10px; }
.eval-result details { padding: 0 13px 12px; }
.eval-result summary { color: #888; cursor: pointer; font-size: 10px; }
.eval-checks { display: flex; flex-wrap: wrap; gap: 5px; margin-top: 9px; }
.eval-checks span { padding: 4px 6px; border-radius: 5px; background: #29413a; color: #9ed8cb; font-size: 9px; }
.eval-checks .eval-check--failed { background: #4a2929; color: #e6a0a0; }
.eval-markdown-panel { display: grid; gap: 7px; margin-top: 9px; padding: 10px; border-radius: 7px; background: #1b1b1b; }
.eval-markdown-panel > strong { color: #8faaa4; font-size: 9px; letter-spacing: .04em; text-transform: uppercase; }
.eval-markdown-panel .markdown-body { color: #bbb; font-size: 11px; line-height: 1.65; }
.eval-markdown-panel .markdown-body :deep(:first-child) { margin-top: 0; }
.eval-markdown-panel .markdown-body :deep(:last-child) { margin-bottom: 0; }
.eval-output-markdown { max-height: 420px; overflow: auto; }
.eval-result__error { margin: 0 13px 8px; color: #e89c9c; font-size: 10px; }
.judge-result { display: grid; gap: 7px; margin-top: 9px; padding: 10px; border: 1px solid #3a4643; border-radius: 8px; background: #202a28; }
.judge-result header { display: flex; justify-content: space-between; }
.judge-result header strong { color: #b5d9d0; font-size: 11px; }
.judge-result header span { color: #8fcaba; font-size: 11px; font-weight: 700; }
.judge-result > div { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); gap: 5px; }
.judge-result > div span { color: #999; font-size: 9px; }
.eval-dialog-backdrop { position: fixed; z-index: 30; display: grid; padding: 24px; background: rgb(9 9 9 / 76%); backdrop-filter: blur(3px); inset: 0; place-items: center; }
.eval-case-dialog { display: grid; width: min(980px, 96vw); height: min(860px, 92vh); min-height: 0; grid-template-rows: auto minmax(0, 1fr); overflow: hidden; border: 1px solid #414141; border-radius: 14px; background: #272727; box-shadow: 0 24px 80px rgb(0 0 0 / 55%); }
.eval-case-dialog > header { display: flex; min-height: 68px; align-items: center; justify-content: space-between; padding: 14px 19px; border-bottom: 1px solid #393939; background: #252525; }
.eval-case-dialog > header div { display: grid; gap: 3px; }
.eval-case-dialog > header strong { color: #e0e0e0; font-size: 15px; }
.eval-case-dialog > header span { color: #747474; font-size: 10px; }
.eval-case-dialog > header button { display: grid; width: 31px; height: 31px; place-items: center; border: 0; border-radius: 7px; background: transparent; color: #929292; cursor: pointer; font-size: 19px; }
.eval-case-dialog > header button:hover { background: #343434; color: #ddd; }
.eval-case-saving { padding: 40px; color: #888; text-align: center; }
@media (max-width: 760px) { .eval-layout { grid-template-columns: 150px minmax(0, 1fr); } .eval-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } .eval-result > header { grid-template-columns: 40px minmax(0, 1fr); } .eval-result header small { display: none; } .eval-dialog-backdrop { padding: 0; } .eval-case-dialog { width: 100vw; height: 100vh; max-height: none; border: 0; border-radius: 0; } }
</style>
