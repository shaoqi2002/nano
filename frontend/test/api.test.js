import assert from "node:assert/strict";
import test from "node:test";

import {
  documentContentUrl,
  uploadDocument,
} from "../src/api.js";


test("builds inline and download document URLs", () => {
  assert.equal(documentContentUrl("doc-1"), "/api/documents/doc-1/content");
  assert.equal(
    documentContentUrl("doc-1", true),
    "/api/documents/doc-1/content?download=true",
  );
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
