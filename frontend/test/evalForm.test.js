import assert from "node:assert/strict";
import test from "node:test";

import {
  buildEvalFormSchema,
  caseToSubmission,
  submissionToCase,
} from "../src/evalForm.js";


test("builds click-oriented controls from backend options", () => {
  const schema = buildEvalFormSchema({
    modes: ["chat", "research"],
    tools: ["web_search"],
    nodes: ["planner"],
    roles: ["supervisor"],
    events: ["agent.delegated"],
    fault_injections: ["none", "researcher_once"],
  }, [{ id: "preset", title: "Preset", source: "builtin" }]);
  const components = JSON.stringify(schema.components);

  assert.match(components, /selectboxes/);
  assert.match(components, /web_search/);
  assert.match(components, /agent\.delegated/);
  assert.match(components, /Preset/);
  assert.match(components, /researcher_once/);
});

test("round trips eval cases through Formio submission values", () => {
  const submission = caseToSubmission({
    id: "custom:one",
    title: "Research",
    prompt: "Research this",
    mode: "research",
    expected_tools: ["web_search"],
    expected_roles: ["supervisor"],
    min_chars: 300,
    max_duration_ms: 120000,
    pass_threshold: 0.75,
    min_citations: 2,
    require_citation_provenance: true,
    fault_injection: "researcher_once",
  });
  const definition = submissionToCase(submission);

  assert.deepEqual(definition.expected_tools, ["web_search"]);
  assert.deepEqual(definition.expected_roles, ["supervisor"]);
  assert.equal(definition.min_chars, 300);
  assert.equal(definition.max_duration_ms, 120000);
  assert.equal(definition.pass_threshold, 0.75);
  assert.equal(definition.min_citations, 2);
  assert.equal(definition.require_citation_provenance, true);
  assert.equal(definition.fault_injection, "researcher_once");
  assert.equal("id" in definition, false);
});
