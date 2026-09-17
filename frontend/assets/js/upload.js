const form = document.getElementById("inspection-form");
const input = document.getElementById("image-input");
const previewPanel = document.getElementById("preview-panel");
const preview = document.getElementById("image-preview");
const info = document.getElementById("image-info");
const message = document.getElementById("message");
const submitButton = document.getElementById("submit-button");

const allowedTypes = new Set(["image/jpeg", "image/png", "image/webp"]);
let processedImage = null;
let previewUrl = null;

function humanSize(bytes) {
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(1)} KB`;
  return `${(bytes / 1024 / 1024).toFixed(2)} MB`;
}

function canvasBlob(canvas) {
  return new Promise((resolve, reject) => {
    canvas.toBlob(
      blob => blob ? resolve(blob) : reject(new Error("图片压缩失败")),
      "image/jpeg",
      0.85,
    );
  });
}

async function prepareImage(file) {
  if (!allowedTypes.has(file.type)) throw new Error("请选择 JPEG、PNG 或 WebP 图片");
  const bitmap = await createImageBitmap(file);
  const scale = Math.min(1, 1600 / Math.max(bitmap.width, bitmap.height));
  const width = Math.max(1, Math.round(bitmap.width * scale));
  const height = Math.max(1, Math.round(bitmap.height * scale));
  const canvas = document.createElement("canvas");
  canvas.width = width;
  canvas.height = height;
  const context = canvas.getContext("2d");
  context.drawImage(bitmap, 0, 0, width, height);
  bitmap.close();
  const blob = await canvasBlob(canvas);
  return {blob, width, height};
}

input.addEventListener("change", async () => {
  processedImage = null;
  previewPanel.hidden = true;
  message.textContent = "";
  const file = input.files[0];
  if (!file) return;
  try {
    const result = await prepareImage(file);
    processedImage = result.blob;
    if (previewUrl) URL.revokeObjectURL(previewUrl);
    previewUrl = URL.createObjectURL(result.blob);
    preview.src = previewUrl;
    info.textContent = `原图 ${humanSize(file.size)}，处理后 ${humanSize(result.blob.size)}，${result.width} × ${result.height}px`;
    previewPanel.hidden = false;
  } catch (error) {
    input.value = "";
    message.textContent = `图片处理失败：${error.message}`;
  }
});

form.addEventListener("submit", async event => {
  event.preventDefault();
  if (!processedImage) {
    message.textContent = "请先选择并等待图片处理完成";
    return;
  }
  submitButton.disabled = true;
  message.textContent = "正在分析，请勿重复提交…";
  const data = new FormData(form);
  data.set("image", processedImage, "inspection.jpg");
  try {
    const response = await fetch("/api/inspections", {method: "POST", body: data});
    const result = await response.json();
    if (!response.ok) throw new Error(result.detail || "未知错误");
    message.textContent = result.status === "queued"
      ? `任务已创建，报告编号 ${result.id}`
      : `完成，报告编号 ${result.id}`;
    location.href = `/report?id=${encodeURIComponent(result.id)}`;
  } catch (error) {
    message.textContent = `提交失败：${error.message}`;
    submitButton.disabled = false;
  }
});
