import assert from "node:assert/strict";
import test from "node:test";

import { renderMarkdown } from "../src/markdown.js";


test("renders structured Markdown and safe external links", () => {
  const output = renderMarkdown(
    "### 标题\n\n**重点**\n\n- 来源：[新华社](https://example.com/news)",
  );

  assert.match(output, /<h3>标题<\/h3>/);
  assert.match(output, /<strong>重点<\/strong>/);
  assert.match(output, /<ul>/);
  assert.match(output, /href="https:\/\/example\.com\/news"/);
  assert.match(output, /target="_blank"/);
  assert.match(output, /rel="noopener noreferrer"/);
});

test("does not allow raw HTML or unsafe link protocols", () => {
  const output = renderMarkdown(
    '<script>alert("xss")</script> [危险链接](javascript:alert(1))',
  );

  assert.doesNotMatch(output, /<script>/);
  assert.doesNotMatch(output, /href="javascript:/);
});
