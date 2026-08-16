import assert from "node:assert/strict";
import test from "node:test";

import {
  consumeEventStream,
  documentContentUrl,
  getAgentRunEvents,
  getEvalDataset,
  sendMessage,
  uploadDocument,
} from "../src/api.js";


test("builds inline and download document URLs", () => {
  assert.equal(documentContentUrl("doc-1"), "/api/documents/doc-1/content");
  assert.equal(
    documentContentUrl("doc-1", true),
    "/api/documents/doc-1/content?download=true",
  );
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
    await sendMessage("conversation-1", "research this", "sk-test", "", true, "research");
    assert.deepEqual(JSON.parse(capturedOptions.body), {
      message: "research this",
      use_rag: true,
      mode: "research",
    });
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
    await uploadDocument(file);
    assert.ok(capturedOptions.body instanceof FormData);
    assert.equal(capturedOptions.headers["Content-Type"], undefined);
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
