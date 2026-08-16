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
let form = null;
let appliedTemplateId = null;

onMounted(async () => {
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
});

onBeforeUnmount(() => {
  form?.destroy(true);
  form = null;
});
</script>

<template>
  <div class="eval-form-shell">
    <div ref="host" class="eval-formio" />
    <button type="button" class="eval-form-cancel" @click="emit('cancel')">取消</button>
  </div>
</template>

<style scoped>
.eval-form-shell { display: grid; gap: 9px; }
.eval-form-cancel { justify-self: end; padding: 7px 12px; border: 1px solid #494949; border-radius: 7px; background: transparent; color: #aaa; cursor: pointer; }
.eval-formio { color: #bbb; font-size: 12px; }
.eval-formio :deep(.form-control), .eval-formio :deep(.form-select) { border-color: #494949; background: #222; color: #ddd; }
.eval-formio :deep(.form-control:focus), .eval-formio :deep(.form-select:focus) { border-color: #6aa99a; box-shadow: 0 0 0 2px rgb(106 169 154 / 15%); }
.eval-formio :deep(.form-label), .eval-formio :deep(.col-form-label) { color: #aaa; font-size: 11px; }
.eval-formio :deep(.card) { border-color: #414141; background: #292929; }
.eval-formio :deep(.card-header) { border-color: #414141; background: #303030; color: #bbb; }
.eval-formio :deep(.form-check-input) { border-color: #666; background-color: #222; }
.eval-formio :deep(.form-check-input:checked) { border-color: #75b8a8; background-color: #75b8a8; }
.eval-formio :deep(.btn-primary) { border-color: #d8e8e4; background: #d8e8e4; color: #18201e; }
.eval-formio :deep(.choices__inner), .eval-formio :deep(.choices__input) { border-color: #494949; background: #222; color: #ddd; }
.eval-formio :deep(.choices__list--dropdown) { border-color: #494949; background: #282828; color: #ddd; }
</style>
