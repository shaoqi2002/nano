const LABELS = {
  chat: "快速回答",
  research: "深度研究",
  document_search: "文档检索",
  web_search: "网页搜索",
  web_extract: "网页读取",
  deep_research: "深度研究工具",
  agent: "Chat Agent",
  tools: "工具执行",
  finalize: "最终回答",
  planner: "Supervisor / Planner",
  writer: "Writer",
  reviewer: "Reviewer",
  revise: "Reviser",
  supervisor: "Supervisor",
  web_researcher: "Web Researcher",
  document_analyst: "Document Analyst",
  general_researcher: "General Researcher",
  "plan.ready": "计划已生成",
  "agent.delegated": "任务已分派",
  "agent.retrying": "Agent 自动重试",
  "agent.completed": "Agent 完成",
  "agent.failed": "Agent 失败",
  "review.completed": "审核完成",
  "tool.started": "工具开始",
  "tool.completed": "工具完成",
};

function values(items = []) {
  return items.map((value) => ({ label: LABELS[value] || value, value }));
}

export function buildEvalFormSchema(options = {}, templates = []) {
  return {
    display: "form",
    components: [
      {
        type: "select",
        key: "template_id",
        label: "预置模板",
        description: "选择后自动填充完整规则，也可以从空白开始。",
        placeholder: "空白用例",
        customClass: "eval-template-select",
        data: {
          values: templates
            .filter((item) => item.source === "builtin")
            .map((item) => ({ label: item.title, value: item.id })),
        },
        clearOnRefresh: false,
      },
      {
        type: "panel",
        title: "基础信息",
        customClass: "eval-form-section",
        components: [
          {
            type: "columns",
            key: "identity_layout",
            customClass: "eval-grid eval-grid--identity",
            columns: [
              {
                width: 8,
                components: [{
                  type: "textfield",
                  key: "title",
                  label: "用例名称",
                  placeholder: "例如：Supervisor 多任务分派",
                  validate: { required: true, maxLength: 120 },
                  input: true,
                }],
              },
              {
                width: 4,
                components: [{
                  type: "radio",
                  key: "mode",
                  label: "Agent 模式",
                  values: values(options.modes || ["chat", "research"]),
                  defaultValue: "chat",
                  inline: true,
                  validate: { required: true },
                }],
              },
            ],
          },
          {
            type: "textarea",
            key: "prompt",
            label: "测试 Prompt",
            placeholder: "描述希望 Agent 完成的任务和输出要求…",
            rows: 5,
            autoExpand: true,
            validate: { required: true, maxLength: 10000 },
            input: true,
          },
        ],
      },
      {
        type: "panel",
        title: "评分规则",
        customClass: "eval-form-section",
        components: [
          {
            type: "columns",
            key: "terms_layout",
            customClass: "eval-grid eval-grid--two",
            columns: [
              {
                width: 6,
                components: [{
                  type: "tags",
                  key: "required_terms",
                  label: "必须包含",
                  placeholder: "输入关键词后按 Enter",
                }],
              },
              {
                width: 6,
                components: [{
                  type: "tags",
                  key: "forbidden_terms",
                  label: "禁止出现",
                  placeholder: "输入关键词后按 Enter",
                }],
              },
            ],
          },
          {
            type: "columns",
            key: "limits_layout",
            customClass: "eval-grid eval-grid--three",
            columns: [
              {
                width: 4,
                components: [{
                  type: "select",
                  key: "min_chars",
                  label: "最低回答长度",
                  data: { values: values(["0", "20", "50", "100", "300", "500", "1000"]) },
                  defaultValue: "100",
                }],
              },
              {
                width: 4,
                components: [{
                  type: "select",
                  key: "max_duration_ms",
                  label: "最长运行时间",
                  data: { values: [
                    { label: "不限", value: "" },
                    { label: "60 秒", value: "60000" },
                    { label: "2 分钟", value: "120000" },
                    { label: "3 分钟", value: "180000" },
                    { label: "4 分钟", value: "240000" },
                    { label: "5 分钟", value: "300000" },
                  ] },
                  defaultValue: "120000",
                }],
              },
              {
                width: 4,
                components: [{
                  type: "select",
                  key: "pass_threshold",
                  label: "通过阈值",
                  data: { values: [
                    { label: "60%", value: "0.6" },
                    { label: "70%", value: "0.7" },
                    { label: "75%", value: "0.75" },
                    { label: "80%", value: "0.8" },
                    { label: "90%", value: "0.9" },
                    { label: "100%", value: "1" },
                  ] },
                  defaultValue: "0.8",
                }],
              },
            ],
          },
        ],
      },
      {
        type: "panel",
        title: "Agent 执行预期",
        customClass: "eval-form-section",
        components: [
          {
            type: "columns",
            key: "expectations_layout",
            customClass: "eval-grid eval-grid--two eval-expectations-grid",
            columns: [
              {
                width: 6,
                components: [
                  {
                    type: "selectboxes",
                    key: "expected_tools",
                    label: "工具调用",
                    values: values(options.tools),
                  },
                  {
                    type: "selectboxes",
                    key: "expected_nodes",
                    label: "工作流节点",
                    values: values(options.nodes),
                  },
                ],
              },
              {
                width: 6,
                components: [
                  {
                    type: "selectboxes",
                    key: "expected_roles",
                    label: "Agent 角色",
                    values: values(options.roles),
                  },
                  {
                    type: "selectboxes",
                    key: "expected_events",
                    label: "运行事件",
                    values: values(options.events),
                  },
                ],
              },
            ],
          },
        ],
      },
      {
        type: "panel",
        title: "LLM Judge",
        customClass: "eval-form-section",
        components: [{
          type: "textarea",
          key: "judge_rubric",
          label: "评分标准",
          description: "描述正确性、完整性、依据性和格式方面的通过要求。",
          rows: 3,
          defaultValue: "回答应准确、完整、有依据，并遵循用户的格式和边界要求。",
          validate: { required: true, maxLength: 3000 },
        }],
      },
    ],
  };
}

const ARRAY_FIELDS = [
  "required_terms", "forbidden_terms", "expected_tools", "expected_nodes",
  "expected_roles", "expected_events",
];

function selectBoxes(values = []) {
  return Object.fromEntries(values.map((value) => [value, true]));
}

export function caseToSubmission(item = {}) {
  const data = { ...item };
  data.mode = item.mode || "chat";
  for (const field of ["expected_tools", "expected_nodes", "expected_roles", "expected_events"]) {
    data[field] = selectBoxes(item[field]);
  }
  data.required_terms = item.required_terms || [];
  data.forbidden_terms = item.forbidden_terms || [];
  data.min_chars = String(item.min_chars ?? 100);
  data.max_duration_ms = item.max_duration_ms == null ? "" : String(item.max_duration_ms);
  data.pass_threshold = String(item.pass_threshold ?? 0.8);
  data.judge_rubric = item.judge_rubric
    || "回答应准确、完整、有依据，并遵循用户的格式和边界要求。";
  return data;
}

function arrayValue(value) {
  if (Array.isArray(value)) return value.map(String).filter(Boolean);
  if (value && typeof value === "object") {
    return Object.entries(value).filter(([, selected]) => selected).map(([key]) => key);
  }
  return [];
}

export function submissionToCase(data) {
  const result = { ...data };
  delete result.template_id;
  delete result.submit;
  delete result.id;
  delete result.source;
  delete result.editable;
  for (const field of ARRAY_FIELDS) result[field] = arrayValue(data[field]);
  result.min_chars = Number(data.min_chars || 0);
  result.max_duration_ms = data.max_duration_ms ? Number(data.max_duration_ms) : null;
  result.pass_threshold = Number(data.pass_threshold || 0.8);
  return result;
}
