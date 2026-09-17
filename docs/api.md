# 慧眼安巡 API 契约

更新：2026-09-17。本文只描述当前代码已经提供的接口。

## 运行约定

- 基础地址由部署环境决定，本地默认为 `http://127.0.0.1:8000`。
- 时间字段为 UTC ISO 8601 字符串。
- API 成功响应为 JSON；页面路由返回 HTML，静态资源返回对应文件。
- 当前没有登录和权限控制，上传照片通过 `/uploads/{文件名}` 公开读取，只适合原型和合规演示图片。
- 视觉提供方可用时，上传请求保存图片和任务后立即返回，后台单进程执行分析；前端轮询详情接口。当前不支持多进程共享任务队列。

## 当前页面路由

| 方法 | 路径 | 行为 |
| --- | --- | --- |
| GET | `/` | 新建巡检页面 |
| GET | `/records` | 历史巡检页面 |
| GET | `/report?id={巡检编号}` | 单次报告页面 |
| GET | `/assets/{路径}` | 前端静态资源 |
| GET | `/uploads/{文件名}` | 已上传图片；当前无访问控制 |

## 当前 API

### GET /api/health

只检查应用和 SQLite 是否可用，不调用外部模型，也不返回路径、密钥或原始异常。

成功，HTTP 200：

```json
{"status":"ok","database":"ok","vision":"unconfigured","vision_provider":"ark","text":"rules","ai_review":"disabled","access":"open"}
```

`vision` 为 `configured` 或 `unconfigured`；`vision_provider` 为 `ark` 或 `yolo`。`text` 为 `configured` 或 `rules`。`ai_review` 为 `disabled`、`configured` 或 `misconfigured`，最后一种表示已要求启用但缺文本模型配置。`access` 为 `open` 或 `protected`。当前 `yolo` 是预留适配器。健康状态只说明配置情况，不证明真实推理效果。数据库不可用时返回 HTTP 503：

```json
{"status":"error","database":"unavailable"}
```

### POST /api/inspections

请求为 `multipart/form-data`：

| 字段 | 类型 | 说明 |
| --- | --- | --- |
| `scene` | string | `dormitory` 或 `laboratory` |
| `image` | file | JPEG、PNG 或 WebP；默认不超过 10 MiB、2500 万像素 |

后端分块读取并验证真实图片内容、完整性、格式和像素尺寸。声明 MIME 必须与实际格式一致。浏览器会先把图片长边压到不超过 1600px 并转为 JPEG，但后端校验仍是最终边界。

成功，HTTP 200：

```json
{"id":1,"status":"queued","mode":"vision"}
```

- `mode=demo`：视觉提供方不能执行真实推理时返回 HTTP 200 和 `completed`，不创建占位隐患。
- `mode=vision`：返回 HTTP 202 和 `queued`，后台执行视觉识别、条款检索、分级及建议。
- `mode=replay`：只存在于 `scripts/seed_demo.py` 生成的离线历史报告，不由创建接口返回，也不代表实时分析。回放记录为只读；修改隐患或补录隐患返回 HTTP 409，仪表盘统计排除这类记录。

上传校验错误仍直接返回 400/413。任务创建成功后的视觉、文本或工作流错误写入巡检的 `failed` 状态和安全错误字段，由详情接口读取。

### GET /api/inspections

返回巡检对象数组，按 `id` 倒序。当前对象字段：

| 字段 | 类型/空值 | 说明 |
| --- | --- | --- |
| `id` | integer | 巡检编号 |
| `scene` | string | 场景 |
| `image_path` | string | 上传目录内的文件名 |
| `status` | string | `queued`、`perceiving`、`retrieving`、`classifying`、`remediating`、`reviewing`、`completed` 或 `failed` |
| `current_step` | string | 当前执行步骤 |
| `progress` | integer | 0–100 的阶段进度，不代表模型内部百分比 |
| `created_at` | string | 创建时间 |
| `completed_at` | string/null | 完成时间 |
| `error` | string/null | 失败说明 |
| `image_quality` | string/null | `good`、`poor`、`uncertain` 或旧记录空值 |
| `uncertain_items` | array | 无法仅从照片确认的项目 |
| `summary` | string/null | 当前照片可见范围的总结或演示提示 |
| `mode` | string | `vision`、`demo`、离线历史 `replay` 或旧记录 `unknown` |
| `model_info` | object/null | 视觉提供方与文本处理模式，不包含密钥 |
| `retry_count` | integer | 已发起重试次数 |
| `review_status` | string | `disabled`、`not_required`、`passed`、`revised_passed`、`manual_required` 或 `error_manual_required` |
| `review_summary` | string/null | 内部复核总结，不代表现场整改完成 |
| `review_findings` | array | 问题所属轮次、隐患序号、检查区域和说明 |
| `review_attempts` | integer | 最多 2 次复核 |
| `review_redo_count` | integer | 自动重做次数，最大为 1 |

### GET /api/inspections/{id}

返回单个巡检对象，并增加 `hazards` 数组。编号不存在时返回 HTTP 404：`{"detail":"巡检记录不存在"}`。

隐患除基础证据外，还返回 `confidence`、`risk_reason`、`priority`、`suggested_deadline`、`manual_checks`、`classification_method`、`remediation_method`、`source`、`human_status`、`original_data`、`actions` 和 `regulations` 引用快照数组。模型只能引用检索结果中存在的条款 ID。`original_data` 保留首次 AI 结论；`actions` 保存人工操作前后值、说明、时间和未认证操作者标记。演示模式和无明确隐患结果均返回空数组。

### POST /api/inspections/{id}/retry

仅允许 `failed` 记录重试，视觉模型必须已配置且原始图片仍存在。成功返回 HTTP 202 和 `queued`；不存在返回 404，状态或配置不允许返回 409。并发重复重试会因状态已变为 `queued` 而被拒绝。

### PATCH /api/hazards/{id}

人工确认、修正或标记误报。请求为 JSON，可提交 `name`、`location`、`evidence`、`risk`、`risk_reason`、`priority`、`suggested_deadline`、`advice`、`manual_checks`、`human_status` 和可选 `note`。`human_status` 为 `pending`、`confirmed`、`corrected` 或 `rejected`。只修改内容而未传状态时，系统自动标记为 `corrected`。

每次操作都写入 `hazard_actions`，保留修改前后值、说明和 UTC 时间。当前系统没有登录功能，因此 `actor` 固定为 `unauthenticated`，不能据此推断操作者身份。隐患不存在返回 404，无有效修改返回 422。

### POST /api/inspections/{id}/hazards

在已完成的巡检中人工补录隐患。请求为 JSON，至少包含名称、位置、现场证据、风险等级、分级理由和整改建议；可补充优先级、建议时间、人工核验项、依据文字、HTTPS 来源链接及说明。成功返回 HTTP 201，新增记录的 `source` 为 `manual`、`human_status` 为 `confirmed`，并写入一条 `manual_added` 审计记录。巡检未完成返回 409。

### GET /api/dashboard

返回：

```json
{
  "total_inspections": 1,
  "total_hazards": 0,
  "risk_distribution": []
}
```

统计计算未被人工标记为 `rejected` 的隐患；演示模式、无隐患记录和误报不会增加隐患数。历史数据库若已有旧占位记录，本次迁移不会破坏性删除。

## 访问保护与限流

设置 `APP_ACCESS_USERNAME` 和 `APP_ACCESS_PASSWORD` 后，除 `/api/health` 外的页面、接口、静态文件和上传图片均要求 HTTP Basic Auth。缺少或错误凭据返回 401。公网必须由 HTTPS 反向代理保护，否则 Basic Auth 凭据会以可还原形式经过网络。

所有 `POST`、`PUT`、`PATCH`、`DELETE` API 共享单进程滑动窗口限流。超过 `WRITE_RATE_LIMIT_PER_MINUTE` 返回 HTTP 429、`Retry-After` 和安全错误消息。该机制用于阻止重复提交和简单滥用，不是多实例网关限流。

## 当前数据表

- `inspections`：在原字段外保存执行进度、模型信息、重试次数，以及内部复核状态、总结、问题、次数和重做次数。
- `hazards`：在基础证据、等级和建议外保存置信度、分级理由、优先级、建议时间、人工核验项、生成方法、来源、人工状态、AI 原始值和更新时间。
- `hazard_actions`：保存确认、修正、误报和人工补录的前后值、说明、未认证操作者标记与时间。
- `regulation_snapshots`：保存当次条款 ID、文件信息、原文、URL 和检索时间，知识库更新不改变旧报告。
- `regulations`：`id`、`scene`、`document_title`、`document_number`、`source_file`、`article`、`content`、`source_url`、`verified_at`、`keywords`、`check_ids`。应用启动时校验并幂等导入宿舍数据，工作流在 `retrieving` 步骤按场景和隐患证据检索。

SQLite 路径由 `DATABASE_URL` 控制，上传路径由 `UPLOAD_DIR` 控制。相对路径均以仓库根目录为基准。

当前执行状态为 `queued → perceiving → retrieving → classifying → remediating → reviewing（启用时）→ completed`，任一步骤可转为 `failed`。内部复核只允许一次自动重做；第二次仍不通过或复核服务异常时，保留报告并转人工复核。
