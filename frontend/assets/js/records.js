const list = document.getElementById("list");
const search = document.getElementById("history-search");
const statusFilter = document.getElementById("history-status");
const active = new Set(["queued", "perceiving", "retrieving", "classifying", "remediating"]);
let records = [];

function element(tag, text, className) {
  const node = document.createElement(tag);
  if (text !== undefined) node.textContent = text;
  if (className) node.className = className;
  return node;
}

function statusInfo(status) {
  if (status === "completed") return ["已完成", "badge-success", "completed"];
  if (status === "failed") return ["失败", "badge-danger", "failed"];
  if (active.has(status)) return ["分析中", "badge-warning", "active"];
  return [status || "未知", "", "other"];
}

function render() {
  const query = search.value.trim().toLowerCase();
  const selected = statusFilter.value;
  const filtered = records.filter(record => {
    const info = statusInfo(record.status);
    const matchesStatus = selected === "all" || selected === info[2];
    const haystack = `${record.id} ${record.scene} ${record.summary || ""}`.toLowerCase();
    return matchesStatus && (!query || haystack.includes(query));
  });
  list.replaceChildren();
  if (!filtered.length) {
    list.append(element("p", records.length ? "没有符合筛选条件的记录。" : "还没有巡检记录，上传一张现场照片即可开始。", "empty-state"));
    return;
  }
  filtered.forEach(record => {
    const row = element("article", undefined, "history-row");
    const main = element("div", undefined, "history-main");
    const title = element("h2", `#${record.id} ${record.scene === "dormitory" ? "学生宿舍" : "实验室"}`);
    const [label, badgeClass] = statusInfo(record.status);
    title.append(document.createTextNode(" "), element("span", label, `badge ${badgeClass}`));
    main.append(title, element("p", record.summary || "暂无分析摘要", "muted"), element("p", new Date(record.created_at).toLocaleString("zh-CN"), "small muted"));
    const link = element("a", active.has(record.status) ? "查看进度" : "查看报告", "button-link button-secondary");
    link.href = `/report?id=${encodeURIComponent(record.id)}`;
    row.append(main, link);
    list.append(row);
  });
}

search.addEventListener("input", render);
statusFilter.addEventListener("change", render);

fetch("/api/inspections")
  .then(response => {
    if (!response.ok) throw new Error("历史记录请求失败");
    return response.json();
  })
  .then(data => {
    records = Array.isArray(data) ? data : [];
    render();
  })
  .catch(error => list.replaceChildren(element("p", `加载失败：${error.message}`, "error-state")));
