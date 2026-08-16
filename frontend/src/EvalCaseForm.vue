<script setup>
import { onBeforeUnmount, onMounted, ref } from "vue";

import { buildEvalFormSchema, caseToSubmission, submissionToCase } from "./evalForm";


const emit = defineEmits(["cancel", "save"]);
const props = defineProps({
  initialCase: { type: Object, default: null },
  options: { type: Object, required: true },
  templates: { type: Array, default: () => [] },
});

const host = ref(null);
const isReady = ref(false);
const loadError = ref("");
let form = null;
let appliedTemplateId = null;

onMounted(async () => {
  try {
    const [{ Formio }] = await Promise.all([
      import("@formio/js"),
      import("@formio/js/dist/formio.form.min.css"),
    ]);
    form = await Formio.createForm(
      host.value,
      buildEvalFormSchema(props.options, props.templates),
      { noAlerts: true },
    );
    form.submission = { data: caseToSubmission(props.initialCase || {}) };
    form.on("change", (event) => {
      if (event?.changed?.component?.key !== "template_id") return;
      const templateId = event.data.template_id;
      if (!templateId || templateId === appliedTemplateId) return;
      const template = props.templates.find((item) => item.id === templateId);
      if (template) {
        appliedTemplateId = templateId;
        form.submission = {
          data: { ...caseToSubmission(template), template_id: template.id },
        };
      }
    });
    form.on("submit", (submission) => emit("save", submissionToCase(submission.data)));
    isReady.value = true;
  } catch (error) {
    loadError.value = error.message || "表单加载失败";
  }
});

function submitForm() {
  form?.submit();
}

onBeforeUnmount(() => {
  form?.destroy(true);
  form = null;
});
</script>

<template>
  <div class="eval-form-shell">
    <div class="eval-form-scroll">
      <div v-if="!isReady && !loadError" class="eval-form-state">正在加载动态表单…</div>
      <div v-if="loadError" class="eval-form-state eval-form-state--error">{{ loadError }}</div>
      <div ref="host" class="eval-formio" :class="{ 'eval-formio--loading': !isReady }" />
    </div>
    <footer class="eval-form-actions">
      <span>字段标记 <b>*</b> 为必填项</span>
      <button type="button" class="eval-form-cancel" @click="emit('cancel')">取消</button>
      <button type="button" class="eval-form-submit" :disabled="!isReady" @click="submitForm">保存用例</button>
    </footer>
  </div>
</template>

<style scoped>
.eval-form-shell { display: grid; min-height: 0; grid-template-rows: minmax(0, 1fr) auto; }
.eval-form-scroll { position: relative; min-height: 0; padding: 18px 20px 24px; overflow-y: auto; scrollbar-color: #555 transparent; scrollbar-width: thin; }
.eval-form-state { position: absolute; z-index: 2; display: grid; color: #777; font-size: 11px; inset: 0; place-items: center; }
.eval-form-state--error { color: #dc9292; }
.eval-formio { color: #bbb; font-size: 12px; }
.eval-formio--loading { min-height: 260px; opacity: 0; }
.eval-form-actions { display: grid; grid-template-columns: minmax(0, 1fr) auto auto; align-items: center; gap: 8px; padding: 12px 20px; border-top: 1px solid #393939; background: #242424; }
.eval-form-actions span { color: #696969; font-size: 9px; }
.eval-form-actions span b { color: #b86f6f; }
.eval-form-cancel, .eval-form-submit { min-width: 82px; padding: 8px 13px; border-radius: 8px; cursor: pointer; font-size: 11px; }
.eval-form-cancel { border: 1px solid #474747; background: transparent; color: #aaa; }
.eval-form-cancel:hover { border-color: #5a5a5a; background: #303030; color: #ddd; }
.eval-form-submit { border: 1px solid #cfe3de; background: #dbe9e6; color: #18201e; font-weight: 700; }
.eval-form-submit:hover:not(:disabled) { background: #edf5f3; }
.eval-form-submit:disabled { cursor: not-allowed; opacity: .45; }
.eval-formio :deep(*) { box-sizing: border-box; }
.eval-formio :deep(.formio-form) { display: grid; gap: 14px; }
.eval-formio :deep(.formio-component), .eval-formio :deep(.form-group) { width: 100%; margin: 0; }
.eval-formio :deep(.form-label), .eval-formio :deep(.col-form-label) { display: inline-block; margin: 0 0 6px; color: #aaa; font-size: 10px; font-weight: 600; letter-spacing: .01em; }
.eval-formio :deep(.field-required::after) { color: #b86f6f; }
.eval-formio :deep(.form-text), .eval-formio :deep(.help-block) { display: block; margin-top: 5px; color: #666; font-size: 9px; line-height: 1.45; }
.eval-formio :deep(.form-control), .eval-formio :deep(.form-select) { display: block; width: 100%; min-height: 39px; padding: 8px 10px; border: 1px solid #444; border-radius: 7px; outline: 0; background: #202020; color: #ddd; font: inherit; transition: border-color 150ms, box-shadow 150ms; }
.eval-formio :deep(textarea.form-control) { min-height: 92px; resize: vertical; line-height: 1.55; }
.eval-formio :deep(.form-control::placeholder) { color: #5f5f5f; }
.eval-formio :deep(.form-control:focus), .eval-formio :deep(.form-select:focus) { border-color: #659c90; box-shadow: 0 0 0 2px rgb(101 156 144 / 13%); }
.eval-formio :deep(.eval-template-select) { padding: 12px 14px; border: 1px solid #3d4b48; border-radius: 9px; background: rgb(46 70 65 / 18%); }
.eval-formio :deep(.eval-form-section.card), .eval-formio :deep(.eval-form-section .card) { overflow: hidden; border: 1px solid #3d3d3d; border-radius: 10px; background: #292929; }
.eval-formio :deep(.eval-form-section > .card-header), .eval-formio :deep(.eval-form-section .card-header) { min-height: 38px; padding: 10px 13px; border-bottom: 1px solid #3b3b3b; background: #2e2e2e; color: #b7ccc7; font-size: 11px; font-weight: 700; }
.eval-formio :deep(.eval-form-section > .card-body), .eval-formio :deep(.eval-form-section .card-body) { display: grid; gap: 14px; padding: 14px; }
.eval-formio :deep(.eval-grid > .row) { display: grid; gap: 14px; margin: 0; }
.eval-formio :deep(.eval-grid > .row > [class*="col-"]) { width: auto; max-width: none; padding: 0; }
.eval-formio :deep(.eval-grid--identity > .row) { grid-template-columns: minmax(0, 2fr) minmax(220px, .8fr); }
.eval-formio :deep(.eval-grid--two > .row) { grid-template-columns: repeat(2, minmax(0, 1fr)); }
.eval-formio :deep(.eval-grid--three > .row) { grid-template-columns: repeat(3, minmax(0, 1fr)); }
.eval-formio :deep(.eval-expectations-grid > .row > [class*="col-"]) { display: grid; align-content: start; gap: 14px; }
.eval-formio :deep(.form-check) { color: #aaa; font-size: 10px; }
.eval-formio :deep(.form-check-inline) { display: inline-flex; align-items: center; margin: 0 14px 0 0; }
.eval-formio :deep(.form-check-input) { width: 14px; height: 14px; margin-right: 6px; border: 1px solid #626262; background-color: #202020; accent-color: #75b8a8; }
.eval-formio :deep(.form-check-input:checked) { border-color: #75b8a8; background-color: #75b8a8; }
.eval-formio :deep(.formio-component-selectboxes .form-check) { display: inline-flex; min-height: 30px; align-items: center; margin: 0 5px 6px 0; padding: 6px 9px; border: 1px solid #414141; border-radius: 7px; background: #252525; }
.eval-formio :deep(.formio-component-selectboxes .form-check:has(.form-check-input:checked)) { border-color: #4f756c; background: #293733; color: #a9d0c7; }
.eval-formio :deep(.choices) { width: 100%; margin: 0; }
.eval-formio :deep(.choices__inner), .eval-formio :deep(.choices__input) { width: 100%; min-height: 39px; border: 1px solid #444; border-radius: 7px; background: #202020; color: #ddd; font-size: 11px; }
.eval-formio :deep(.choices__list--dropdown) { z-index: 20; border-color: #494949; background: #282828; color: #ddd; }
.eval-formio :deep(.choices__list--dropdown .choices__item--selectable.is-highlighted) { background: #35423f; }
.eval-formio :deep(.choices__list--multiple .choices__item) { border-color: #4e756c; border-radius: 5px; background: #315047; color: #c6e0da; }
.eval-formio :deep(.alert-danger) { padding: 8px 10px; border: 1px solid #684141; border-radius: 7px; background: #3a2929; color: #e4aaaa; font-size: 10px; }
@media (max-width: 760px) {
  .eval-form-scroll { padding: 14px; }
  .eval-formio :deep(.eval-grid--identity > .row), .eval-formio :deep(.eval-grid--two > .row), .eval-formio :deep(.eval-grid--three > .row) { grid-template-columns: 1fr; }
  .eval-form-actions { grid-template-columns: 1fr 1fr; }
  .eval-form-actions span { display: none; }
}
</style>
