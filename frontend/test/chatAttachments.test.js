import assert from "node:assert/strict";
import test from "node:test";

import {
  CHAT_ATTACHMENT_ACCEPT,
  attachmentTypeLabel,
  fileToChatAttachment,
} from "../src/chatAttachments.js";


test("accepts PPTX files as chat-local document attachments", async () => {
  const originalFileReader = globalThis.FileReader;
  globalThis.FileReader = class {
    readAsDataURL(file) {
      this.result = `data:${file.type};base64,UEsDBA==`;
      this.onload();
    }
  };
  try {
    const file = {
      name: "roadmap.pptx",
      type: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
      size: 6,
    };
    const attachment = await fileToChatAttachment(file);
    assert.equal(attachment.kind, "document");
    assert.equal(attachmentTypeLabel(attachment), "PPTX");
    assert.match(CHAT_ATTACHMENT_ACCEPT, /\.pptx/);
  } finally {
    globalThis.FileReader = originalFileReader;
  }
});
