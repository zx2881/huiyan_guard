const root = document.getElementById("report");
const id = new URLSearchParams(location.search).get("id");
const activeSteps = new Set(["queued", "perceiving", "retrieving", "classifying", "remediating"]);
const stepLabels = {
  queued: "等待分析",
  perceiving: "视觉识别",
  retrieving: "检索规章",
  classifying: "风险分级",
  remediating: "生成整改建议",
  completed: "分析完成",
  failed: "分析失败",
};

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function field(label, value, wide = false) {
  const paragraph = element("p", undefined, wide ? "wide" : "");
  paragraph.append(element("b", `${label}：`), document.createTextNode(value || "未记录"));
  return paragraph;
}

function badge(text, className = "") {
  return element("span", text, `badge ${className}`.trim());
}

function qualityLabel(value) {
  return {good: "良好", poor: "较差", uncertain: "无法确认"}[value] || "未记录";
}

function riskLabel(value) {
  return {low: "低风险", medium: "中风险", high: "高风险", needs_review: "待人工核验"}[value] || "待人工核验";
}

function priorityLabel(value) {
  return {immediate: "立即处理", high: "优先处理", normal: "常规处理", manual_review: "人工核验"}[value] || "人工核验";
}

function reviewLabel(value) {
  return {pending: "待确认", confirmed: "已确认", corrected: "已修正", rejected: "已标记误报"}[value] || "待确认";
}

function reviewBadgeClass(value) {
  return {confirmed: "badge-success", corrected: "badge-accent", rejected: "badge-danger", pending: "badge-warning"}[value] || "badge-warning";
}

function formatDate(value) {
  if (!value) return "未记录";
  const date = new Date(value);
  return Number.isNaN(date.getTime()) ? value : date.toLocaleString("zh-CN");
}

function durationLabel(startedAt, completedAt) {
  if (!startedAt || !completedAt) return "未记录";
  const seconds = Math.max(0, Math.round((new Date(completedAt) - new Date(startedAt)) / 1000));
  if (!Number.isFinite(seconds)) return "未记录";
  return seconds < 60 ? `${seconds} 秒` : `${Math.floor(seconds / 60)} 分 ${seconds % 60} 秒`;
}

async function responseJson(response) {
  const result = await response.json().catch(() => ({}));
  if (!response.ok) throw new Error(result.detail || "请求未完成");
  return result;
}

function reportHeading(data, subtitle) {
  const heading = element("div", undefined, "report-heading");
  const copy = element("div");
  copy.append(element("p", subtitle, "eyebrow"), element("h1", `巡检报告 #${data.id}`), element("p", formatDate(data.created_at), "muted"));
  const actions = element("div", undefined, "button-row no-print");
  const history = element("a", "返回历史", "button-link button-secondary");
  history.href = "/records";
  actions.append(history);
  heading.append(copy, actions);
  return {heading, actions};
}

function renderProgress(data) {
  const {heading} = reportHeading(data, "正在生成");
  const title = element("h2", stepLabels[data.current_step] || "正在分析");
  const progress = element("progress");
  progress.max = 100;
  progress.value = data.progress || 0;
  progress.setAttribute("aria-label", `分析进度 ${data.progress || 0}%`);
  root.replaceChildren(heading, title, element("p", `进度 ${data.progress || 0}%`, "muted"), progress, element("p", "页面会自动更新，请勿重复上传。", "muted"));
}

function renderFailure(data) {
  const {heading, actions} = reportHeading(data, "任务中断");
  const button = element("button", "重新分析");
  button.addEventListener("click", async () => {
    button.disabled = true;
    try {
      await responseJson(await fetch(`/api/inspections/${encodeURIComponent(data.id)}/retry`, {method: "POST"}));
      loadReport();
    } catch (error) {
      button.disabled = false;
      root.append(element("p", error.message, "error-state"));
    }
  });
  actions.append(button);
  root.replaceChildren(heading, element("h2", "分析失败"), element("p", data.error || "分析流程未能完成。", "error-state"));
}

function renderRegulations(section, regulations, fallback, fallbackUrl) {
  section.append(element("h4", "法规依据"));
  if (!regulations.length) {
    const paragraph = element("p", fallback || "未检索到适用条款，请人工核验。", "muted");
    if (fallbackUrl) {
      const link = element("a", "查看来源");
      link.href = fallbackUrl;
      link.target = "_blank";
      link.rel = "noopener noreferrer";
      paragraph.append(document.createTextNode(" "), link);
    }
    section.append(paragraph);
    return;
  }
  const list = element("ol", undefined, "regulation-list");
  regulations.forEach(regulation => {
    const item = element("li");
    const link = element("a", `${regulation.document_title} ${regulation.article}`);
    link.href = regulation.source_url;
    link.target = "_blank";
    link.rel = "noopener noreferrer";
    item.append(link, document.createTextNode(`：${regulation.content}`));
    list.append(item);
  });
  section.append(list);
}

function labeledControl(labelText, name, value, kind = "input", options = []) {
  const label = element("label", labelText);
  let control;
  if (kind === "textarea") {
    control = element("textarea");
    control.value = value || "";
  } else if (kind === "select") {
    control = element("select");
    options.forEach(([optionValue, optionLabel]) => {
      const option = element("option", optionLabel);
      option.value = optionValue;
      option.selected = optionValue === value;
      control.append(option);
    });
  } else {
    control = element("input");
    control.value = value || "";
  }
  control.name = name;
  label.append(control);
  return label;
}

async function saveReview(hazardId, payload, status) {
  status.textContent = "正在保存…";
  try {
    await responseJson(await fetch(`/api/hazards/${encodeURIComponent(hazardId)}`, {
      method: "PATCH",
      headers: {"Content-Type": "application/json"},
      body: JSON.stringify(payload),
    }));
    status.textContent = "已保存";
    await loadReport();
  } catch (error) {
    status.textContent = `保存失败：${error.message}`;
    status.className = "error-state small";
  }
}

function createEditForm(hazard) {
  const form = element("form", undefined, "edit-form no-print");
  form.hidden = true;
  const grid = element("div", undefined, "form-grid");
  const riskOptions = [["low", "低风险"], ["medium", "中风险"], ["high", "高风险"], ["needs_review", "待人工核验"]];
  const priorityOptions = [["immediate", "立即处理"], ["high", "优先处理"], ["normal", "常规处理"], ["manual_review", "人工核验"]];
  grid.append(
    labeledControl("隐患名称", "name", hazard.name),
    labeledControl("位置", "location", hazard.location),
    labeledControl("证据", "evidence", hazard.evidence, "textarea"),
    labeledControl("风险等级", "risk", hazard.risk, "select", riskOptions),
    labeledControl("分级理由", "risk_reason", hazard.risk_reason, "textarea"),
    labeledControl("处理优先级", "priority", hazard.priority, "select", priorityOptions),
    labeledControl("建议完成时间", "suggested_deadline", hazard.suggested_deadline),
    labeledControl("整改建议", "advice", hazard.advice, "textarea"),
  );
  const checks = labeledControl("人工核验项，每行一项", "manual_checks", (hazard.manual_checks || []).join("\n"), "textarea");
  checks.className = "wide";
  const note = labeledControl("修改说明", "note", "", "textarea");
  note.className = "wide";
  grid.append(checks, note);
  const actions = element("div", undefined, "button-row");
  const save = element("button", "保存修正");
  save.type = "submit";
  const cancel = element("button", "取消", "button-secondary");
  cancel.type = "button";
  const status = element("span", "", "muted small");
  cancel.addEventListener("click", () => { form.hidden = true; });
  actions.append(save, cancel, status);
  form.append(grid, actions);
  form.addEventListener("submit", async event => {
    event.preventDefault();
    save.disabled = true;
    const values = new FormData(form);
    const payload = Object.fromEntries(values.entries());
    payload.manual_checks = String(payload.manual_checks || "").split("\n").map(item => item.trim()).filter(Boolean);
    payload.human_status = "corrected";
    await saveReview(hazard.id, payload, status);
    save.disabled = false;
  });
  return form;
}

function renderAudit(section, actions) {
  if (!actions.length) return;
  const details = element("details", undefined, "no-print");
  details.append(element("summary", `人工操作记录（${actions.length}）`));
  const list = element("ol", undefined, "audit-list");
  const labels = {confirmed: "确认无误", corrected: "修正结果", rejected: "标记误报", reset_pending: "恢复待确认", manual_added: "人工补录", updated: "更新结果"};
  actions.forEach(action => {
    const note = action.note ? `，说明：${action.note}` : "";
    list.append(element("li", `${formatDate(action.created_at)} ${labels[action.action_type] || action.action_type}${note}`));
  });
  details.append(list);
  section.append(details);
}

function renderHazard(hazard) {
  const section = element("article", undefined, "hazard-item");
  section.dataset.review = hazard.human_status || "pending";
  const title = element("div", undefined, "hazard-title");
  title.append(
    element("h3", hazard.name || "未命名隐患"),
    badge(riskLabel(hazard.risk), hazard.risk === "high" ? "badge-danger" : hazard.risk === "medium" ? "badge-warning" : ""),
    badge(reviewLabel(hazard.human_status), reviewBadgeClass(hazard.human_status)),
    badge(hazard.source === "manual" ? "人工补录" : "AI 识别"),
  );
  const fields = element("div", undefined, "hazard-fields");
  fields.append(
    field("位置", hazard.location),
    field("置信度", hazard.confidence === null || hazard.confidence === undefined ? "人工记录" : `${Math.round(hazard.confidence * 100)}%`),
    field("证据", hazard.evidence, true),
    field("分级理由", hazard.risk_reason, true),
    field("处理优先级", priorityLabel(hazard.priority)),
    field("建议完成时间", hazard.suggested_deadline),
    field("整改建议", hazard.advice, true),
  );
  section.append(title, fields);
  const checks = Array.isArray(hazard.manual_checks) ? hazard.manual_checks : [];
  if (checks.length) {
    section.append(element("h4", "现场核验项"));
    const list = element("ul");
    checks.forEach(item => list.append(element("li", item)));
    section.append(list);
  }
  renderRegulations(section, Array.isArray(hazard.regulations) ? hazard.regulations : [], hazard.regulation, hazard.source_url);
  if (hazard.original_data && hazard.human_status === "corrected") {
    const original = element("details");
    const originalFields = element("div", undefined, "hazard-fields small");
    originalFields.append(
      field("名称", hazard.original_data.name),
      field("位置", hazard.original_data.location),
      field("证据", hazard.original_data.evidence, true),
      field("风险", riskLabel(hazard.original_data.risk)),
      field("建议", hazard.original_data.advice, true),
    );
    original.append(element("summary", "查看 AI 原始结论"), originalFields);
    section.append(original);
  }
  const review = element("div", undefined, "review-actions no-print");
  const actions = element("div", undefined, "button-row");
  const confirm = element("button", "确认无误");
  const edit = element("button", "修正内容", "button-secondary");
  const reject = element("button", "标记误报", "button-danger");
  const status = element("span", "", "muted small");
  const editForm = createEditForm(hazard);
  confirm.addEventListener("click", () => saveReview(hazard.id, {human_status: "confirmed", note: "人工确认无误"}, status));
  edit.addEventListener("click", () => { editForm.hidden = !editForm.hidden; });
  reject.addEventListener("click", () => saveReview(hazard.id, {human_status: "rejected", note: "人工复核标记为误报"}, status));
  actions.append(confirm, edit, reject, status);
  review.append(actions, editForm);
  section.append(review);
  renderAudit(section, Array.isArray(hazard.actions) ? hazard.actions : []);
  return section;
}

function createManualForm(inspectionId) {
  const form = element("form", undefined, "inline-form no-print");
  form.hidden = true;
  const grid = element("div", undefined, "form-grid");
  const riskOptions = [["needs_review", "待人工核验"], ["low", "低风险"], ["medium", "中风险"], ["high", "高风险"]];
  const priorityOptions = [["manual_review", "人工核验"], ["normal", "常规处理"], ["high", "优先处理"], ["immediate", "立即处理"]];
  grid.append(
    labeledControl("隐患名称", "name", ""),
    labeledControl("位置", "location", ""),
    labeledControl("现场证据", "evidence", "", "textarea"),
    labeledControl("风险等级", "risk", "needs_review", "select", riskOptions),
    labeledControl("分级理由", "risk_reason", "", "textarea"),
    labeledControl("处理优先级", "priority", "manual_review", "select", priorityOptions),
    labeledControl("建议完成时间", "suggested_deadline", "请现场负责人确定"),
    labeledControl("整改建议", "advice", "", "textarea"),
  );
  const checks = labeledControl("人工核验项，每行一项", "manual_checks", "", "textarea");
  checks.className = "wide";
  const regulation = labeledControl("补充依据，可选", "regulation", "", "textarea");
  regulation.className = "wide";
  grid.append(checks, regulation, labeledControl("依据链接，可选", "source_url", ""), labeledControl("补录说明，可选", "note", ""));
  const controls = element("div", undefined, "button-row");
  const save = element("button", "保存补录");
  save.type = "submit";
  const cancel = element("button", "取消", "button-secondary");
  cancel.type = "button";
  const status = element("span", "", "muted small");
  cancel.addEventListener("click", () => { form.hidden = true; });
  controls.append(save, cancel, status);
  form.append(element("h3", "人工补录隐患"), grid, controls);
  ["name", "location", "evidence", "risk_reason", "advice"].forEach(name => {
    form.elements[name].required = true;
  });
  form.addEventListener("submit", async event => {
    event.preventDefault();
    save.disabled = true;
    status.textContent = "正在保存…";
    const values = Object.fromEntries(new FormData(form).entries());
    values.manual_checks = String(values.manual_checks || "").split("\n").map(item => item.trim()).filter(Boolean);
    for (const key of ["regulation", "source_url", "note"]) if (!values[key]) delete values[key];
    try {
      await responseJson(await fetch(`/api/inspections/${encodeURIComponent(inspectionId)}/hazards`, {
        method: "POST",
        headers: {"Content-Type": "application/json"},
        body: JSON.stringify(values),
      }));
      await loadReport();
    } catch (error) {
      save.disabled = false;
      status.textContent = `保存失败：${error.message}`;
      status.className = "error-state small";
    }
  });
  return form;
}

function metaStrip(data) {
  const meta = element("dl", undefined, "meta-strip");
  const provider = data.mode === "demo" ? "演示模式" : (data.model_info?.vision_provider || "视觉模型").toUpperCase();
  [["检查场景", data.scene === "dormitory" ? "学生宿舍" : "实验室"], ["图片质量", qualityLabel(data.image_quality)], ["分析耗时", durationLabel(data.started_at, data.completed_at)], ["识别来源", provider]].forEach(([label, value]) => {
    const item = element("div");
    item.append(element("dt", label), element("dd", value));
    meta.append(item);
  });
  return meta;
}

function renderCompleted(data) {
  const {heading, actions} = reportHeading(data, "巡检结果");
  const print = element("button", "打印报告", "button-secondary");
  print.addEventListener("click", () => window.print());
  actions.append(print);
  const overview = element("div", undefined, "report-overview");
  const photo = element("img");
  photo.className = "photo";
  photo.src = `/uploads/${encodeURIComponent(data.image_path)}`;
  photo.alt = "巡检现场照片";
  const summary = element("div", undefined, "summary-block");
  summary.append(element("h2", "照片结论"), element("p", data.summary || "暂无总结"));
  const uncertain = Array.isArray(data.uncertain_items) ? data.uncertain_items : [];
  summary.append(element("h3", "无法确认的区域"));
  if (uncertain.length) {
    const list = element("ul");
    uncertain.forEach(item => list.append(element("li", item)));
    summary.append(list);
  } else {
    summary.append(element("p", "没有额外不确定项。", "muted"));
  }
  summary.append(element("p", "结论仅覆盖照片可见范围，所有风险项需由现场人员确认。", "notice-state small"));
  overview.append(photo, summary);

  const hazards = Array.isArray(data.hazards) ? data.hazards : [];
  const sectionHeading = element("div", undefined, "section-heading");
  sectionHeading.append(element("h2", `隐患与复核（${hazards.length}）`));
  const add = element("button", "人工补录隐患", "button-secondary no-print");
  sectionHeading.append(add);
  const manualForm = createManualForm(data.id);
  add.addEventListener("click", () => { manualForm.hidden = !manualForm.hidden; });
  const list = element("div", undefined, "hazard-list");
  if (hazards.length) hazards.forEach(hazard => list.append(renderHazard(hazard)));
  else list.append(element("p", "当前照片可见范围内未发现明确隐患，可继续现场核查或人工补录。", "empty-state"));
  root.replaceChildren(heading, metaStrip(data), overview, sectionHeading, manualForm, list);
}

async function loadReport() {
  try {
    const data = await responseJson(await fetch(`/api/inspections/${encodeURIComponent(id)}`));
    if (activeSteps.has(data.status)) {
      renderProgress(data);
      window.setTimeout(loadReport, 800);
    } else if (data.status === "failed") {
      renderFailure(data);
    } else {
      renderCompleted(data);
    }
  } catch (error) {
    root.replaceChildren(element("h1", "报告无法加载"), element("p", error.message, "error-state"));
  }
}

if (!id) root.replaceChildren(element("h1", "缺少报告编号"), element("p", "请从历史记录打开报告。", "error-state"));
else loadReport();
