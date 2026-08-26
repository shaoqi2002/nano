import assert from "node:assert/strict";
import test from "node:test";

import {
  consumeEventStream,
  createJobApplication,
  createEvalCase,
  deleteEvalCase,
  documentContentUrl,
  getAgentRunEvents,
  getDeepSeekBalance,
  getEmbeddingStatus,
  getEvalDataset,
  getTavilyUsage,
  sendMessage,
  runEvalStream,
  restorePresetEvalCases,
  updateEvalCase,
  uploadDocument,
  updateJobApplicationStatus,
} from "../src/api.js";


test("builds inline and download document URLs", () => {
  assert.equal(documentContentUrl("doc-1"), "/api/documents/doc-1/content");
  assert.equal(
    documentContentUrl("doc-1", true),
    "/api/documents/doc-1/content?download=true",
  );
});

test("creates job applications and updates their status", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options) => {
    requests.push({ url, options });
    return {
      ok: true,
      status: 200,
      json: async () => ({ id: "job-1", status: "interviewing" }),
    };
  };

  try {
    await createJobApplication(
      "https://careers.example.com/job/1", "后端开发", "sk-test", "tvly-test"
    );
    await updateJobApplicationStatus("job-1", "interviewing");
    assert.equal(requests[0].options.headers["X-DeepSeek-API-Key"], "sk-test");
    assert.equal(requests[0].options.headers["X-Tavily-API-Key"], "tvly-test");
    assert.deepEqual(requests.map((item) => [
      item.url,
      item.options.method,
      JSON.parse(item.options.body),
    ]), [
      ["/api/job-applications", "POST", {
        job_url: "https://careers.example.com/job/1",
        notes: "后端开发",
      }],
      ["/api/job-applications/job-1/status", "PATCH", { status: "interviewing" }],
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("queries DeepSeek balance through the backend", async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return {
      ok: true,
      status: 200,
      json: async () => ({ is_available: true, balance_infos: [] }),
    };
  };

  try {
    await getDeepSeekBalance("sk-balance");
    assert.equal(captured.url, "/api/account/deepseek/balance");
    assert.equal(captured.options.headers["X-DeepSeek-API-Key"], "sk-balance");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("queries Tavily usage through the backend", async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return {
      ok: true,
      status: 200,
      json: async () => ({ key: { usage: 10, limit: 1000 }, account: {} }),
    };
  };

  try {
    await getTavilyUsage("tvly-usage");
    assert.equal(captured.url, "/api/account/tavily/usage");
    assert.equal(captured.options.headers["X-Tavily-API-Key"], "tvly-usage");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("validates the browser-configured embedding key", async () => {
  const originalFetch = globalThis.fetch;
  let captured;
  globalThis.fetch = async (url, options) => {
    captured = { url, options };
    return {
      ok: true,
      status: 200,
      json: async () => ({ configured: true, model: "text-embedding-v4" }),
    };
  };

  try {
    await getEmbeddingStatus(
      "sk-embedding",
      "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
    );
    assert.equal(captured.url, "/api/account/embedding/status");
    assert.equal(captured.options.headers["X-Embedding-API-Key"], "sk-embedding");
    assert.equal(
      captured.options.headers["X-Embedding-Base-URL"],
      "https://dashscope-us.aliyuncs.com/compatible-mode/v1",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("sends optional LLM judge settings", async () => {
  const originalFetch = globalThis.fetch;
  let capturedOptions;
  const encoder = new TextEncoder();
  globalThis.fetch = async (_url, options) => {
    capturedOptions = options;
    return {
      ok: true,
      status: 200,
      body: new ReadableStream({
        start(controller) {
          controller.enqueue(encoder.encode(
            "event: eval.completed\ndata: {\"run\":{\"score\":1}}\n\n",
          ));
          controller.close();
        },
      }),
    };
  };

  try {
    const events = [];
    await runEvalStream(
      ["case-1"], "sk-test", "", true, 0.6, "baseline-1",
      (event) => events.push(event),
    );
    assert.deepEqual(JSON.parse(capturedOptions.body), {
      case_ids: ["case-1"],
      judge_enabled: true,
      judge_weight: 0.6,
      baseline_run_id: "baseline-1",
    });
    assert.equal(events[0].type, "eval.completed");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("loads the versioned eval dataset", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl;
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => ({ version: "golden-v1", cases: [] }),
    };
  };

  try {
    const dataset = await getEvalDataset();
    assert.equal(dataset.version, "golden-v1");
    assert.equal(requestedUrl, "/api/evals/dataset");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("creates updates and deletes custom eval cases", async () => {
  const originalFetch = globalThis.fetch;
  const requests = [];
  globalThis.fetch = async (url, options = {}) => {
    requests.push({ url, options });
    return {
      ok: true,
      status: options.method === "DELETE" ? 204 : 200,
      json: async () => ({ id: "custom:case-1" }),
    };
  };

  try {
    await createEvalCase({ title: "Custom", prompt: "Test" });
    await updateEvalCase("custom:case-1", { title: "Updated", prompt: "Test" });
    await deleteEvalCase("custom:case-1");
    await deleteEvalCase("rag-definition");
    await restorePresetEvalCases();
    assert.deepEqual(requests.map((item) => [item.url, item.options.method]), [
      ["/api/evals/cases", "POST"],
      ["/api/evals/cases/case-1", "PUT"],
      ["/api/evals/cases/case-1", "DELETE"],
      ["/api/evals/cases/rag-definition", "DELETE"],
      ["/api/evals/cases/presets/restore", "POST"],
    ]);
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("loads persisted agent trace events", async () => {
  const originalFetch = globalThis.fetch;
  let requestedUrl;
  globalThis.fetch = async (url) => {
    requestedUrl = url;
    return {
      ok: true,
      status: 200,
      json: async () => [],
    };
  };

  try {
    assert.deepEqual(await getAgentRunEvents("run-1"), []);
    assert.equal(requestedUrl, "/api/agent-runs/run-1/events");
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("sends the selected agent mode", async () => {
  const originalFetch = globalThis.fetch;
  let capturedOptions;
  globalThis.fetch = async (_url, options) => {
    capturedOptions = options;
    return {
      ok: true,
      status: 200,
      json: async () => ({}),
    };
  };

  try {
    await sendMessage(
      "conversation-1", "research this", "sk-test", "", true, "research",
      "sk-embedding", "https://dashscope.aliyuncs.com/compatible-mode/v1", true,
    );
    assert.deepEqual(JSON.parse(capturedOptions.body), {
      message: "research this",
      attachments: [],
      use_rag: true,
      mode: "research",
      allow_write_tools: true,
    });
    assert.equal(capturedOptions.headers["X-Embedding-API-Key"], "sk-embedding");
    assert.equal(
      capturedOptions.headers["X-Embedding-Base-URL"],
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("uploads documents as multipart data without a JSON content type", async () => {
  const originalFetch = globalThis.fetch;
  let capturedOptions;
  globalThis.fetch = async (_url, options) => {
    capturedOptions = options;
    return {
      ok: true,
      status: 201,
      json: async () => ({ id: "doc-1" }),
    };
  };

  try {
    const file = new Blob(["hello"], { type: "text/plain" });
    await uploadDocument(
      file,
      "sk-embedding",
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
    assert.ok(capturedOptions.body instanceof FormData);
    assert.equal(capturedOptions.headers["Content-Type"], undefined);
    assert.equal(capturedOptions.headers["X-Embedding-API-Key"], "sk-embedding");
    assert.equal(
      capturedOptions.headers["X-Embedding-Base-URL"],
      "https://dashscope.aliyuncs.com/compatible-mode/v1",
    );
  } finally {
    globalThis.fetch = originalFetch;
  }
});

test("parses SSE events split across arbitrary chunks", async () => {
  const encoder = new TextEncoder();
  const chunks = [
    "event: tool.started\r\ndata: {\"call_id\":\"1\",",
    "\"name\":\"web_search\"}\r\n\r\n: keep-alive\n\n",
    "event: message.delta\ndata: {\"delta\":\"你好\"}\n\n",
  ];
  const response = {
    body: new ReadableStream({
      start(controller) {
        for (const chunk of chunks) controller.enqueue(encoder.encode(chunk));
        controller.close();
      },
    }),
  };
  const events = [];

  await consumeEventStream(response, (event) => events.push(event));

  assert.deepEqual(events, [
    { type: "tool.started", call_id: "1", name: "web_search" },
    { type: "message.delta", delta: "你好" },
  ]);
});
