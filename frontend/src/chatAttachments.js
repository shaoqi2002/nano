export const CHAT_ATTACHMENT_ACCEPT = [
  "image/png", "image/jpeg", "image/webp", "image/gif",
  ".txt", ".md", ".csv", ".json", ".xml", ".yaml", ".yml", ".log",
  ".html", ".css", ".js", ".ts", ".py", ".java", ".c", ".cpp", ".h", ".sql", ".sh",
  ".pdf", ".docx", ".pptx",
].join(",");

const IMAGE_TYPES = new Set(["image/png", "image/jpeg", "image/webp", "image/gif"]);
const TEXT_EXTENSIONS = new Set([
  "txt", "md", "csv", "json", "xml", "yaml", "yml", "log", "html", "css",
  "js", "ts", "py", "java", "c", "cpp", "h", "sql", "sh",
]);
const MAX_IMAGE_BYTES = 5 * 1024 * 1024;
const MAX_TEXT_BYTES = 200 * 1024;
const MAX_DOCUMENT_BYTES = 10 * 1024 * 1024;
export const MAX_CHAT_ATTACHMENTS = 8;
export const MAX_CHAT_ATTACHMENT_BYTES = 15 * 1024 * 1024;

function extension(name) {
  return String(name || "").split(".").pop().toLowerCase();
}

function readDataUrl(file) {
  return new Promise((resolve, reject) => {
    const reader = new FileReader();
    reader.onload = () => resolve(String(reader.result));
    reader.onerror = () => reject(reader.error || new Error("读取图片失败"));
    reader.readAsDataURL(file);
  });
}

export async function fileToChatAttachment(file) {
  if (IMAGE_TYPES.has(file.type)) {
    if (file.size > MAX_IMAGE_BYTES) throw new Error(`${file.name} 超过 5 MB`);
    const dataUrl = await readDataUrl(file);
    return {
      kind: "image",
      name: file.name || "粘贴的图片",
      media_type: file.type,
      data: dataUrl.slice(dataUrl.indexOf(",") + 1),
      previewUrl: dataUrl,
      byteSize: file.size,
    };
  }
  const fileExtension = extension(file.name);
  if (["pdf", "docx", "pptx"].includes(fileExtension)) {
    if (file.size > MAX_DOCUMENT_BYTES) throw new Error(`${file.name} 超过 10 MB`);
    const mediaType = {
      pdf: "application/pdf",
      docx: "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
      pptx: "application/vnd.openxmlformats-officedocument.presentationml.presentation",
    }[fileExtension];
    const dataUrl = await readDataUrl(file);
    return {
      kind: "document",
      name: file.name,
      media_type: mediaType,
      data: dataUrl.slice(dataUrl.indexOf(",") + 1),
      byteSize: file.size,
    };
  }
  if (file.type.startsWith("text/") || TEXT_EXTENSIONS.has(fileExtension)) {
    if (file.size > MAX_TEXT_BYTES) throw new Error(`${file.name} 超过 200 KB`);
    return {
      kind: "text",
      name: file.name || "粘贴的文本",
      media_type: file.type || "text/plain",
      content: await file.text(),
      byteSize: file.size,
    };
  }
  throw new Error(`${file.name || "该文件"} 不是支持的文本或图片格式`);
}

export function attachmentPayload(attachment) {
  const { previewUrl, byteSize, ...payload } = attachment;
  return payload;
}

export function attachmentPreviewUrl(attachment) {
  if (attachment.previewUrl) return attachment.previewUrl;
  if (attachment.kind === "image" && attachment.data) {
    return `data:${attachment.media_type};base64,${attachment.data}`;
  }
  return "";
}

export function attachmentTypeLabel(attachment) {
  if (attachment.kind === "image") return "IMG";
  if (attachment.kind === "document") {
    if (attachment.media_type === "application/pdf") return "PDF";
    if (attachment.media_type.includes("presentationml")) return "PPTX";
    return "DOCX";
  }
  return "TXT";
}
