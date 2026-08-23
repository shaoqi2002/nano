<script setup>
import { computed, onMounted, reactive, ref } from "vue";

import {
  createJobApplication,
  deleteJobApplication,
  listJobApplications,
  updateJobApplication,
  updateJobApplicationStatus,
} from "./api";


const emit = defineEmits(["back"]);
const applications = ref([]);
const isLoading = ref(true);
const isCreating = ref(false);
const savingId = ref(null);
const errorMessage = ref("");
const expandedId = ref(null);
const query = ref("");
const statusFilter = ref("all");
const form = reactive({ jobUrl: "", notes: "" });
const editDraft = reactive({});

const statuses = [
  { value: "preparing", label: "准备投递" },
  { value: "applied", label: "已投递" },
  { value: "written_test", label: "笔试中" },
  { value: "interviewing", label: "面试中" },
  { value: "offer", label: "已录用" },
  { value: "rejected", label: "未通过" },
  { value: "withdrawn", label: "已终止" },
];

const statusLabels = Object.fromEntries(statuses.map((item) => [item.value, item.label]));
const filteredApplications = computed(() => {
  const keyword = query.value.trim().toLowerCase();
  return applications.value.filter((item) => {
    const matchesStatus = statusFilter.value === "all" || item.status === statusFilter.value;
    const haystack = [item.company, item.role, item.location, item.channel, item.notes]
      .join(" ")
      .toLowerCase();
    return matchesStatus && (!keyword || haystack.includes(keyword));
  });
});
const summary = computed(() => ({
  total: applications.value.length,
  active: applications.value.filter((item) => ["written_test", "interviewing"].includes(item.status)).length,
  offers: applications.value.filter((item) => item.status === "offer").length,
  recent: applications.value.filter((item) => {
    const age = Date.now() - new Date(item.created_at).getTime();
    return age <= 7 * 24 * 60 * 60 * 1000;
  }).length,
}));

function formatDate(value, includeTime = false) {
  const options = includeTime
    ? { month: "2-digit", day: "2-digit", hour: "2-digit", minute: "2-digit" }
    : { year: "numeric", month: "2-digit", day: "2-digit" };
  return new Intl.DateTimeFormat("zh-CN", options).format(new Date(value));
}

function hostname(url) {
  try {
    return new URL(url).hostname.replace(/^www\./, "");
  } catch {
    return url;
  }
}

async function loadApplications() {
  isLoading.value = true;
  errorMessage.value = "";
  try {
    applications.value = await listJobApplications();
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isLoading.value = false;
  }
}

async function submitApplication() {
  if (!form.jobUrl.trim()) return;
  isCreating.value = true;
  errorMessage.value = "";
  try {
    const application = await createJobApplication(form.jobUrl.trim(), form.notes.trim());
    applications.value.unshift(application);
    form.jobUrl = "";
    form.notes = "";
    openDetails(application);
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    isCreating.value = false;
  }
}

function openDetails(application) {
  if (expandedId.value === application.id) {
    expandedId.value = null;
    return;
  }
  expandedId.value = application.id;
  Object.assign(editDraft, {
    company: application.company,
    role: application.role,
    location: application.location,
    channel: application.channel,
    job_url: application.job_url,
    notes: application.notes,
    applied_at: application.applied_at,
  });
}

function replaceApplication(updated) {
  const index = applications.value.findIndex((item) => item.id === updated.id);
  if (index >= 0) applications.value[index] = updated;
}

async function changeStatus(application, event) {
  const previous = application.status;
  const next = event.target.value;
  application.status = next;
  savingId.value = application.id;
  errorMessage.value = "";
  try {
    replaceApplication(await updateJobApplicationStatus(application.id, next));
  } catch (error) {
    application.status = previous;
    errorMessage.value = error.message;
  } finally {
    savingId.value = null;
  }
}

async function saveDetails(application) {
  savingId.value = application.id;
  errorMessage.value = "";
  try {
    replaceApplication(await updateJobApplication(application.id, { ...editDraft }));
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    savingId.value = null;
  }
}

async function removeApplication(application) {
  if (!window.confirm(`删除 ${application.company} 的 ${application.role} 投递记录？`)) return;
  savingId.value = application.id;
  errorMessage.value = "";
  try {
    await deleteJobApplication(application.id);
    applications.value = applications.value.filter((item) => item.id !== application.id);
    if (expandedId.value === application.id) expandedId.value = null;
  } catch (error) {
    errorMessage.value = error.message;
  } finally {
    savingId.value = null;
  }
}

onMounted(loadApplications);
</script>

<template>
  <main class="jobs-page">
    <header class="jobs-topbar">
      <button class="jobs-icon-button" aria-label="返回对话" title="返回" @click="emit('back')">←</button>
      <div>
        <strong>秋招投递</strong>
        <span>把每一次尝试都放在看得见的地方</span>
      </div>
    </header>

    <div class="jobs-scroll">
      <div class="jobs-content">
        <section class="jobs-summary" aria-label="投递概览">
          <article><span>全部投递</span><strong>{{ summary.total }}</strong></article>
          <article><span>流程进行中</span><strong>{{ summary.active }}</strong></article>
          <article><span>最近 7 天</span><strong>{{ summary.recent }}</strong></article>
          <article class="jobs-summary__offer"><span>Offer</span><strong>{{ summary.offers }}</strong></article>
        </section>

        <form class="job-capture" @submit.prevent="submitApplication">
          <div class="job-capture__heading">
            <div>
              <strong>记一笔新投递</strong>
              <span>填入链接和你手边的信息，其余字段会先帮你整理出来。</span>
            </div>
            <button type="submit" :disabled="isCreating || !form.jobUrl.trim()">
              {{ isCreating ? "正在整理" : "加入投递表" }}
            </button>
          </div>
          <label>
            <span>投递地址</span>
            <input
              v-model="form.jobUrl"
              type="url"
              required
              placeholder="https://career.example.com/jobs/123"
            >
          </label>
          <label>
            <span>补充描述</span>
            <textarea
              v-model="form.notes"
              rows="3"
              maxlength="5000"
              placeholder="例如：公司：字节跳动，岗位：后端开发，地点：上海；内推，学长说一周内留意邮件"
            />
          </label>
        </form>

        <div v-if="errorMessage" class="jobs-error" role="alert">{{ errorMessage }}</div>

        <section class="jobs-table-section">
          <header class="jobs-table-tools">
            <div>
              <strong>投递记录</strong>
              <span>{{ filteredApplications.length }} 条</span>
            </div>
            <div class="jobs-filters">
              <input v-model="query" type="search" placeholder="搜索公司、岗位或地点">
              <select v-model="statusFilter" aria-label="按状态筛选">
                <option value="all">全部状态</option>
                <option v-for="item in statuses" :key="item.value" :value="item.value">
                  {{ item.label }}
                </option>
              </select>
            </div>
          </header>

          <div v-if="isLoading" class="jobs-empty">正在载入投递记录...</div>
          <div v-else-if="applications.length === 0" class="jobs-empty">
            <strong>第一行还空着</strong>
            <span>从上方加入一条投递，之后的进度都可以在这里更新。</span>
          </div>
          <div v-else-if="filteredApplications.length === 0" class="jobs-empty">
            没有符合当前筛选条件的记录
          </div>

          <div v-else class="jobs-table-wrap">
            <table class="jobs-table">
              <thead>
                <tr>
                  <th>公司 / 岗位</th>
                  <th>地点</th>
                  <th>投递渠道</th>
                  <th>投递日期</th>
                  <th>当前状态</th>
                  <th><span class="visually-hidden">操作</span></th>
                </tr>
              </thead>
              <tbody>
                <template v-for="application in filteredApplications" :key="application.id">
                  <tr :class="{ 'jobs-row--expanded': expandedId === application.id }">
                    <td>
                      <strong>{{ application.company }}</strong>
                      <span>{{ application.role }}</span>
                    </td>
                    <td>{{ application.location || "待补充" }}</td>
                    <td>
                      <a :href="application.job_url" target="_blank" rel="noopener noreferrer">
                        {{ application.channel || hostname(application.job_url) }} ↗
                      </a>
                    </td>
                    <td>{{ formatDate(application.applied_at) }}</td>
                    <td>
                      <select
                        class="job-status"
                        :class="`job-status--${application.status}`"
                        :value="application.status"
                        :disabled="savingId === application.id"
                        :aria-label="`更新 ${application.company} 的投递状态`"
                        @change="changeStatus(application, $event)"
                      >
                        <option v-for="item in statuses" :key="item.value" :value="item.value">
                          {{ item.label }}
                        </option>
                      </select>
                    </td>
                    <td>
                      <button
                        class="jobs-icon-button"
                        :aria-label="expandedId === application.id ? '收起详情' : '查看详情'"
                        :title="expandedId === application.id ? '收起' : '详情'"
                        @click="openDetails(application)"
                      >{{ expandedId === application.id ? "↑" : "↓" }}</button>
                    </td>
                  </tr>
                  <tr v-if="expandedId === application.id" class="job-detail-row">
                    <td colspan="6">
                      <div class="job-detail">
                        <form class="job-edit-form" @submit.prevent="saveDetails(application)">
                          <div class="job-detail__heading">
                            <strong>投递信息</strong>
                            <span>自动整理不准的地方，可以直接修正。</span>
                          </div>
                          <div class="job-edit-grid">
                            <label><span>公司</span><input v-model="editDraft.company" required></label>
                            <label><span>岗位</span><input v-model="editDraft.role" required></label>
                            <label><span>地点</span><input v-model="editDraft.location"></label>
                            <label><span>渠道</span><input v-model="editDraft.channel"></label>
                            <label><span>投递日期</span><input v-model="editDraft.applied_at" type="date"></label>
                            <label class="job-edit-grid__wide"><span>投递链接</span><input v-model="editDraft.job_url" type="url" required></label>
                            <label class="job-edit-grid__wide"><span>备注</span><textarea v-model="editDraft.notes" rows="3" /></label>
                          </div>
                          <div class="job-edit-actions">
                            <button type="button" class="job-delete" @click="removeApplication(application)">删除记录</button>
                            <button type="submit" :disabled="savingId === application.id">保存修改</button>
                          </div>
                        </form>

                        <aside class="job-timeline">
                          <div class="job-detail__heading">
                            <strong>状态历史</strong>
                            <span>每次下拉选择都会留在这里。</span>
                          </div>
                          <ol>
                            <li v-for="event in application.events" :key="event.id">
                              <span class="job-timeline__dot" />
                              <div>
                                <strong>{{ statusLabels[event.to_status] }}</strong>
                                <span>{{ formatDate(event.created_at, true) }}</span>
                                <small v-if="event.note">{{ event.note }}</small>
                              </div>
                            </li>
                          </ol>
                        </aside>
                      </div>
                    </td>
                  </tr>
                </template>
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </div>
  </main>
</template>

<style scoped>
.jobs-page { display: grid; min-width: 0; height: 100vh; flex: 1; grid-template-rows: auto 1fr; overflow: hidden; background: #f5f6f8; color: #202124; color-scheme: light; }
.jobs-topbar { display: flex; min-height: 64px; align-items: center; gap: 12px; padding: 10px 22px; border-bottom: 1px solid #dedfe3; background: #fff; }
.jobs-topbar > div { display: grid; gap: 2px; }
.jobs-topbar strong { font-size: 16px; }
.jobs-topbar span { color: #74777d; font-size: 12px; }
.jobs-icon-button { display: grid; width: 34px; height: 34px; flex: 0 0 34px; place-items: center; border: 1px solid transparent; border-radius: 6px; background: transparent; color: #53565c; cursor: pointer; font-size: 18px; }
.jobs-icon-button:hover { border-color: #d4d6da; background: #f0f1f3; }
.jobs-scroll { min-height: 0; overflow: auto; }
.jobs-content { width: min(1320px, calc(100% - 40px)); margin: 0 auto; padding: 28px 0 48px; }
.jobs-summary { display: grid; grid-template-columns: repeat(4, minmax(0, 1fr)); border: 1px solid #dedfe3; border-radius: 8px; background: #fff; }
.jobs-summary article { display: grid; gap: 7px; padding: 18px 22px; border-right: 1px solid #e7e8eb; }
.jobs-summary article:last-child { border-right: 0; }
.jobs-summary span { color: #777a80; font-size: 12px; }
.jobs-summary strong { font-size: 26px; font-variant-numeric: tabular-nums; }
.jobs-summary__offer strong { color: #14765a; }
.job-capture { display: grid; gap: 15px; margin-top: 18px; padding: 20px 22px; border: 1px solid #dedfe3; border-radius: 8px; background: #fff; }
.job-capture__heading, .jobs-table-tools, .job-edit-actions { display: flex; align-items: center; justify-content: space-between; gap: 18px; }
.job-capture__heading > div, .jobs-table-tools > div:first-child, .job-detail__heading { display: grid; gap: 4px; }
.job-capture__heading span, .job-detail__heading span { color: #777a80; font-size: 12px; }
.job-capture label, .job-edit-form label { display: grid; gap: 6px; color: #5f6268; font-size: 12px; }
input, textarea, select { min-width: 0; border: 1px solid #cfd1d6; border-radius: 6px; outline: 0; background: #fff; color: #202124; font: inherit; }
input, select { height: 38px; padding: 0 11px; }
textarea { width: 100%; resize: vertical; padding: 10px 11px; line-height: 1.5; }
input:focus, textarea:focus, select:focus { border-color: #287a65; box-shadow: 0 0 0 3px rgb(40 122 101 / 10%); }
button[type="submit"] { min-height: 36px; padding: 0 15px; border: 0; border-radius: 6px; background: #176b57; color: #fff; cursor: pointer; font-weight: 650; }
button[type="submit"]:hover { background: #115745; }
button:disabled { cursor: wait; opacity: .5; }
.jobs-error { margin-top: 16px; padding: 11px 13px; border: 1px solid #e7b5b5; border-radius: 6px; background: #fff1f1; color: #a42c2c; font-size: 13px; }
.jobs-table-section { margin-top: 18px; border: 1px solid #dedfe3; border-radius: 8px; overflow: hidden; background: #fff; }
.jobs-table-tools { min-height: 64px; padding: 12px 18px; border-bottom: 1px solid #e4e5e8; }
.jobs-table-tools > div:first-child { grid-template-columns: auto auto; align-items: baseline; column-gap: 8px; }
.jobs-table-tools span { color: #85888e; font-size: 12px; }
.jobs-filters { display: flex; gap: 8px; }
.jobs-filters input { width: 240px; }
.jobs-filters select { width: 130px; }
.jobs-table-wrap { overflow-x: auto; }
.jobs-table { width: 100%; min-width: 950px; border-collapse: collapse; table-layout: fixed; }
.jobs-table th { padding: 11px 14px; border-bottom: 1px solid #e4e5e8; background: #f8f9fa; color: #777a80; font-size: 11px; font-weight: 650; text-align: left; }
.jobs-table th:nth-child(1) { width: 25%; }.jobs-table th:nth-child(2) { width: 12%; }.jobs-table th:nth-child(3) { width: 17%; }.jobs-table th:nth-child(4) { width: 13%; }.jobs-table th:nth-child(5) { width: 17%; }.jobs-table th:nth-child(6) { width: 52px; }
.jobs-table td { padding: 13px 14px; border-bottom: 1px solid #ececef; color: #55585e; font-size: 13px; vertical-align: middle; }
.jobs-table tbody > tr:not(.job-detail-row):hover { background: #fafbfb; }
.jobs-table td:first-child { display: table-cell; }
.jobs-table td:first-child strong, .jobs-table td:first-child span { display: block; overflow: hidden; text-overflow: ellipsis; white-space: nowrap; }
.jobs-table td:first-child strong { color: #202124; font-size: 14px; }
.jobs-table td:first-child span { margin-top: 4px; color: #73767c; }
.jobs-table a { display: block; overflow: hidden; color: #176b57; text-decoration: none; text-overflow: ellipsis; white-space: nowrap; }
.jobs-table a:hover { text-decoration: underline; }
.jobs-row--expanded { background: #f7faf9; }
.job-status { width: 116px; height: 32px; border: 0; padding: 0 28px 0 10px; font-size: 12px; font-weight: 650; }
.job-status--preparing { background: #edf0f3; color: #626870; }.job-status--applied { background: #e8f1fb; color: #29659b; }.job-status--written_test { background: #fff2d7; color: #8a5a00; }.job-status--interviewing { background: #f1eafb; color: #6c3da0; }.job-status--offer { background: #e2f4ec; color: #14765a; }.job-status--rejected, .job-status--withdrawn { background: #f3e8e8; color: #995050; }
.jobs-empty { display: grid; min-height: 210px; place-content: center; gap: 7px; color: #80838a; font-size: 13px; text-align: center; }
.jobs-empty strong { color: #42454a; font-size: 15px; }
.job-detail-row td { padding: 0; background: #f7faf9; }
.job-detail { display: grid; grid-template-columns: minmax(0, 2fr) minmax(260px, 1fr); gap: 0; border-bottom: 1px solid #dfe8e5; }
.job-edit-form, .job-timeline { padding: 22px; }
.job-edit-form { border-right: 1px solid #dfe5e3; }
.job-edit-grid { display: grid; grid-template-columns: repeat(2, minmax(0, 1fr)); gap: 13px; margin-top: 16px; }
.job-edit-grid__wide { grid-column: 1 / -1; }
.job-edit-actions { margin-top: 16px; }
.job-delete { min-height: 34px; padding: 0 10px; border: 0; background: transparent; color: #aa3838; cursor: pointer; }
.job-timeline ol { display: grid; gap: 0; margin: 18px 0 0; padding: 0; list-style: none; }
.job-timeline li { position: relative; display: grid; grid-template-columns: 15px 1fr; gap: 10px; min-height: 60px; }
.job-timeline li:not(:last-child)::before { position: absolute; top: 12px; bottom: -2px; left: 5px; width: 1px; background: #cbd8d4; content: ""; }
.job-timeline__dot { position: relative; z-index: 1; width: 11px; height: 11px; margin-top: 2px; border: 3px solid #f7faf9; border-radius: 50%; background: #2b806a; box-shadow: 0 0 0 1px #2b806a; }
.job-timeline li div { display: grid; gap: 3px; }
.job-timeline li strong { color: #303338; font-size: 13px; }.job-timeline li span { color: #85888e; font-size: 11px; }.job-timeline li small { color: #65686e; font-size: 11px; }
@media (max-width: 900px) { .jobs-summary { grid-template-columns: repeat(2, 1fr); }.jobs-summary article:nth-child(2) { border-right: 0; }.jobs-summary article:nth-child(-n+2) { border-bottom: 1px solid #e7e8eb; }.job-detail { grid-template-columns: 1fr; }.job-edit-form { border-right: 0; border-bottom: 1px solid #dfe5e3; } }
@media (max-width: 760px) { .jobs-content { width: calc(100% - 24px); padding-top: 16px; }.jobs-topbar { padding: 8px 12px; }.job-capture__heading, .jobs-table-tools { align-items: stretch; flex-direction: column; }.job-capture__heading button { align-self: stretch; }.jobs-filters input { width: 100%; }.jobs-filters select { width: 120px; }.job-edit-grid { grid-template-columns: 1fr; }.job-edit-grid__wide { grid-column: auto; } }
</style>
