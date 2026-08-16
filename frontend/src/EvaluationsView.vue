<script setup>
import { computed, onMounted, ref } from "vue";

import {
  getEvalDataset,
  getEvalRun,
  listEvalRuns,
  runEvalStream,
} from "./api";


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

function handleEvalEvent(event) {
  if (event.type === "eval.started") {
    activeRun.value = {
      id: event.run_id,
      status: "running",
      case_count: event.case_count,
      passed_count: 0,
      score: null,
      duration_ms: null,
    };
    results.value = [];
  } else if (event.type === "case.started") {
    progress.value = {
      caseId: event.case_id,
      title: event.title,
      index: event.index,
      total: event.total,
    };
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
          <h2>黄金测试集</h2>
          <p>{{ dataset?.description }}</p>
          <button
            v-for="item in dataset?.cases"
            :key="item.id"
            class="eval-case"
            :class="{ 'eval-case--selected': selectedIds.includes(item.id) }"
            @click="toggleCase(item.id)"
          >
            <span class="eval-checkbox">{{ selectedIds.includes(item.id) ? "✓" : "" }}</span>
            <span><strong>{{ item.title }}</strong><small>{{ item.mode }}</small></span>
          </button>
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
          <div><strong>{{ progress.title }}</strong><small>Agent 正在执行并评分…</small></div>
        </div>

        <div v-if="activeRun" class="eval-summary">
          <div><span>总分</span><strong>{{ activeRun.score === null ? "运行中" : `${Math.round(activeRun.score * 100)}%` }}</strong></div>
          <div><span>通过率</span><strong>{{ passRate }}</strong></div>
          <div><span>通过用例</span><strong>{{ activeRun.passed_count }}/{{ activeRun.case_count }}</strong></div>
          <div><span>总耗时</span><strong>{{ formatDuration(activeRun.duration_ms) }}</strong></div>
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
              <pre>{{ result.output }}</pre>
            </details>
          </article>
        </div>
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
.eval-sidebar p { margin: 2px 8px 8px; color: #777; font-size: 10px; line-height: 1.5; }
.eval-case { display: grid; grid-template-columns: 20px minmax(0, 1fr); gap: 7px; padding: 9px; border: 0; border-radius: 8px; background: transparent; color: #aaa; cursor: pointer; text-align: left; }
.eval-case:hover, .eval-case--selected { background: #2c2c2c; }
.eval-checkbox { display: grid; width: 17px; height: 17px; place-items: center; border: 1px solid #555; border-radius: 4px; color: #8fcaba; font-size: 10px; }
.eval-case > span:last-child { display: grid; gap: 3px; }
.eval-case strong { overflow: hidden; color: #ddd; font-size: 12px; text-overflow: ellipsis; white-space: nowrap; }
.eval-case small { color: #777; font-size: 9px; }
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
.eval-result pre { max-height: 300px; margin: 9px 0 0; padding: 10px; overflow: auto; border-radius: 7px; background: #1b1b1b; color: #bbb; font: 11px/1.6 inherit; white-space: pre-wrap; }
.eval-result__error { margin: 0 13px 8px; color: #e89c9c; font-size: 10px; }
@media (max-width: 760px) { .eval-layout { grid-template-columns: 150px minmax(0, 1fr); } .eval-summary { grid-template-columns: repeat(2, minmax(0, 1fr)); } .eval-result > header { grid-template-columns: 40px minmax(0, 1fr); } .eval-result header small { display: none; } }
</style>
