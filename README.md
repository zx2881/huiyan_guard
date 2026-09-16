# 慧眼安巡

慧眼安巡是一套“上传现场照片，直接输出校园安全整改建议”的安全巡检系统原型。用户选择检查场景并上传照片，系统保存现场证据，生成巡检记录和报告；正式版本将在此基础上接入视觉模型、规章检索、风险判断、整改建议生成和 AI 复核。

当前仓库是一个可以运行的演示原型，已经实现照片上传、SQLite 记录保存、历史记录查询和单次报告查看。当前演示模式没有接入真实视觉模型，上传后会生成“待人工确认的现场风险”，不会把无法从照片确认的内容伪装成确定事实。

完整的产品边界、数据维护原则和原始设计请参考 [慧眼安巡项目结构与数据维护说明.md](./慧眼安巡项目结构与数据维护说明.md)。

## 快速开始

需要 Python 3.11 或更高版本。

```bash
python -m venv .venv
# Windows PowerShell
.venv\Scripts\Activate.ps1
pip install -r requirements.txt
uvicorn backend.app.main:app --reload
```

要启用火山引擎方舟视觉分析，请先复制 `.env.example` 为 `.env`，填写方舟 API Key 和推理接入点 ID，再重启服务：

```powershell
Copy-Item .env.example .env
```

在 `.env` 中至少填写：

```env
ARK_API_KEY=你的火山方舟API_Key
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=ep-你的推理接入点ID
```

`ARK_MODEL` 填写方舟控制台中的推理接入点 ID，通常以 `ep-` 开头，并且该接入点必须使用支持图片输入的多模态模型。密钥只放在本机 `.env` 或服务器环境变量中，不要写进代码、网页或提交到 Git。缺少 API Key 或接入点 ID 时，系统会使用演示模式；两者配置完整后，新上传的照片才会调用火山视觉模型。

打开 <http://127.0.0.1:8000/>，选择“学生宿舍”或“实验室”，上传一张现场照片。报告保存到 `data/app.db`，原始照片保存到 `data/uploads/inspections/`。

页面地址：

- `/`：新建巡检、选择场景、上传照片；
- `/records`：查看历史巡检记录；
- `/report?id=编号`：查看单次巡检报告。

## 当前已经实现的功能

当前演示流程如下：

```text
选择场景 → 上传照片 → 保存照片 → 写入 SQLite → 生成待人工确认的演示隐患 → 查看报告
```

后端接口：

| 方法 | 地址 | 作用 |
|---|---|---|
| `POST` | `/api/inspections` | 上传照片并创建巡检记录，表单字段为 `scene` 和 `image` |
| `GET` | `/api/inspections` | 按编号倒序查询历史记录 |
| `GET` | `/api/inspections/{id}` | 查询某次巡检及隐患列表 |
| `GET` | `/api/dashboard` | 返回巡检总数、隐患总数和风险分布 |

示例：

```bash
curl -X POST http://127.0.0.1:8000/api/inspections \
  -F "scene=dormitory" \
  -F "image=@test.jpg"
```

## 当前代码如何配合

[backend/app/main.py](./backend/app/main.py) 是 FastAPI 入口，负责页面托管、照片上传、记录创建、报告查询和基础统计。

[backend/app/database.py](./backend/app/database.py) 初始化 SQLite，当前有三张表：

- `inspections`：保存巡检编号、场景、照片路径、状态、创建时间、完成时间和错误信息；
- `hazards`：保存隐患名称、位置、证据、风险等级、整改建议和规章引用；
- `regulations`：保存规章编号、适用场景、文件名称、条款原文和来源链接。

一个巡检可以包含多个隐患。当前演示版本每次只写入一条固定的“待人工确认”隐患；`regulations` 表已经建立，但尚未接入条款导入和检索。

前端页面为：

- [frontend/index.html](./frontend/index.html)：上传页面；
- [frontend/records.html](./frontend/records.html)：历史记录页面；
- [frontend/report.html](./frontend/report.html)：报告详情页面；
- [frontend/assets/css/common.css](./frontend/assets/css/common.css)：基础样式。

## 检查清单和规章的区别

`knowledge/` 保存项目自带的初始资料。[knowledge/dormitory/checklist.json](./knowledge/dormitory/checklist.json) 和 [knowledge/laboratory/checklist.json](./knowledge/laboratory/checklist.json) 是场景检查清单，告诉系统“需要检查什么”，例如“插线板是否被物品覆盖”。

规章知识库告诉系统“依据什么判断”。正式条款建议包含稳定编号、适用场景、文件名称、条款编号、核验过的原文、来源链接和核验日期。正式使用前，条款必须来自真实文件并经过人工核验，不能把示例文字当成学校规章、行业标准或法律依据。

## 后续功能如何加入

### 1. 增加真实分析状态和工作流

当前上传后直接设置为 `completed`。正式版本应至少支持：

```text
created → analyzing → completed
                    ↘ failed
```

需要时再细分为 `perceiving`、`classifying`、`retrieving`、`remediating` 和 `reviewing`。

建议新增：

```text
backend/app/workflow/state.py
backend/app/workflow/events.py
backend/app/workflow/runner.py
backend/app/services/inspection_service.py
backend/app/services/report_service.py
```

路由只处理请求和响应，服务层负责状态变化、AI 调用和数据库写入。模型失败时必须进入 `failed`，保存错误信息，不能错误地显示为完成。

### 2. 接入真实视觉模型

当前项目已经提供了第一版视觉模型接入代码：

- `backend/app/integrations/vision_client.py`：将本地图片转为 Base64，并通过火山方舟兼容接口调用视觉模型；
- `backend/app/agents/perceive.py`：读取当前场景的 `checklist.json`，把检查清单交给视觉模型；
- `backend/app/main.py`：上传后调用感知模块，并把结构化隐患写入 `hazards` 表。

建议继续完善或替换为：

```text
backend/app/integrations/vision_client.py
backend/app/agents/perceive.py
backend/app/agents/prompts/perceive.md
backend/app/schemas/hazard.py
```

`vision_client.py` 只负责调用外部视觉模型、超时和错误处理；`perceive.py` 把模型结果整理成统一格式：

```json
{
  "hazards": [
    {
      "name": "插线板被衣物覆盖",
      "location": "床铺右侧桌面",
      "evidence": "照片中可见插线板上方覆盖衣物",
      "confidence": 0.91
    }
  ],
  "image_quality": "good",
  "uncertain_items": []
}
```

照片不清晰或角度不足时，应明确返回“无法从当前照片确认”，不能强行生成确定结论。当前视觉模型调用完成后，隐患的风险、整改建议和规章依据仍会显示为“待接入”，因为风险分级、RAG 和整改建议尚未实现。

### 视觉模型调用的实际流程

```text
浏览器上传图片
    ↓
保存到 data/uploads/inspections/
    ↓
读取 knowledge/{scene}/checklist.json
    ↓
vision_client.py 将图片编码并请求模型
    ↓
模型返回 JSON：hazards、image_quality、uncertain_items
    ↓
写入 hazards 表
    ↓
报告页显示位置和证据
```

模型服务需要支持图片输入和 JSON 输出。如果你使用其他厂商，只需要重写 `VisionClient.analyze()`，保持返回结构不变；不要把供应商 SDK 代码直接写进路由。

### 3. 增加风险分级

建议新增 `backend/app/agents/classify.py` 和 `backend/app/integrations/text_client.py`。风险定义需要由项目团队确认，一个可用的初版是：

| 等级 | 含义 |
|---|---|
| `low` | 一般提示，建议关注 |
| `medium` | 存在明确问题，需要尽快整改 |
| `high` | 可能造成较大安全后果，需要优先处理 |
| `critical` | 可能造成严重事故，应立即采取措施 |

风险判断应综合隐患类型、照片证据、场景和规章条款，不能完全交给模型自由决定。

### 4. 导入真实规章并做 RAG 检索

建议新增：

```text
knowledge/dormitory/regulations.json
knowledge/laboratory/regulations.json
scripts/import_knowledge.py
backend/app/rag/embeddings.py
backend/app/rag/indexer.py
backend/app/rag/retriever.py
```

流程应为：

```text
读取 regulations.json → 校验字段 → 写入 SQLite → 生成向量并更新索引 → 用已知隐患测试检索
```

相同规章编号再次导入时应更新原记录而不是重复插入。检索结果必须保留条款原文和来源。没有找到适用条款时，应显示“当前知识库未检索到适用条款，请人工核验”，不能虚构条款。

### 5. 生成整改建议

建议新增：

```text
backend/app/agents/remediate.py
backend/app/agents/prompts/remediate.md
```

整改建议应包含可执行动作，例如移走覆盖物、检查插头破损情况、禁止在插线板周围堆放可燃物、安排管理员复核，而不是只输出“请及时整改”。

### 6. 加入 AI 复核

建议新增：

```text
backend/app/agents/review.py
backend/app/agents/prompts/review.md
```

复核需要检查照片证据、风险等级、规章适用性、建议针对性和不确定性。复核只是生成报告前的质量检查，不代表现场问题已经整改完成。

## 前端后续需要增加什么

上传页应加入图片预览、文件大小和格式校验、上传进度、拍摄角度提示和图片质量提示，建议拆出：

```text
frontend/assets/js/inspection.js
frontend/assets/css/inspection.css
```

分析过程中应显示“照片已保存、视觉识别中、正在匹配规章、正在判断风险、正在生成建议、正在复核”等步骤。原型阶段可以轮询 `GET /api/inspections/{id}`，正式版本可以增加 SSE 接口 `/api/inspections/{id}/events`。

正式报告还应展示图片质量、隐患数量、证据说明、规章原文和来源、不确定项、复核状态以及打印或导出功能。必须区分“未发现明确隐患”和“无法从当前照片确认”。

当前只有统计接口，后续可以增加 `frontend/dashboard.html`、`dashboard.js` 和 `dashboard.css`，展示巡检数量、隐患数量、风险分布、场景统计、隐患类型统计和时间趋势。

还需要增加知识库后台：

```text
frontend/admin/knowledge.html
frontend/assets/js/knowledge.js
backend/app/api/knowledge.py
backend/app/services/knowledge_service.py
```

后台应支持新增、修改、停用规章，查看来源和索引状态，并允许索引失败后重试。数据库写入成功但索引失败时，必须明确提示“规章已保存，但检索索引更新失败”。

## 推荐的正式代码分层

后续可以逐步整理为：

```text
backend/app/
├─ main.py / config.py / database.py
├─ api/          # 请求和响应
├─ schemas/      # Pydantic 输入输出格式
├─ models/       # 数据库模型
├─ services/     # 业务流程和数据库读写
├─ agents/       # 感知、分级、建议、复核
├─ workflow/     # 状态和执行顺序
├─ rag/          # 条款索引和检索
├─ integrations/ # 外部模型供应商
└─ utils/        # 文件和日志
```

`api` 不应塞入复杂 AI 逻辑；`agents` 不应直接处理网页；`rag` 只负责规章检索；`integrations` 隔离模型供应商，方便以后替换模型。

## 配置、安全和数据维护

模型密钥和运行参数应通过环境变量配置，不要写进代码或提交到 Git。建议 `.env.example` 包含：

```env
DATABASE_URL=sqlite:///./data/app.db
UPLOAD_DIR=./data/uploads/inspections
ARK_API_KEY=replace_me
ARK_BASE_URL=https://ark.cn-beijing.volces.com/api/v3
ARK_MODEL=ep-your-endpoint-id
TEXT_PROVIDER=your_provider
TEXT_API_KEY=replace_me
TEXT_MODEL=replace_me
MAX_UPLOAD_SIZE_MB=10
ALLOWED_IMAGE_TYPES=image/jpeg,image/png,image/webp
```

上线前还需要加入登录和权限、文件大小和格式限制、图片访问控制、日志脱敏、模型超时和重试、数据库备份以及数据库迁移。当前 `/uploads` 是静态公开目录，只适合本地演示；正式系统应改成经过权限检查的图片访问接口。

增加数据库字段时，不能直接删除 `data/app.db` 重建。应先备份，再使用迁移脚本或 Alembic，保证历史报告仍能打开。旧报告应保存当时引用的规章快照，不能随着规章修改而改变。

## 测试计划

建议增加：

```text
tests/
├─ conftest.py
├─ test_workflow.py
├─ test_rag.py
├─ test_inspection_api.py
└─ fixtures/images/ and annotations.json
```

重点验证上传校验、照片和数据库记录一致、工作流失败处理、条款检索场景隔离、重复导入更新、历史报告快照、多隐患展示，以及“未发现”和“无法确认”的区别。

## 推荐开发顺序

1. 拆分当前入口、服务和数据模型；
2. 增加分析状态和失败处理；
3. 增加上传大小、格式和图片质量校验；
4. 接入视觉模型，先完成“照片到结构化隐患”；
5. 导入真实规章并完成 SQLite 和向量索引；
6. 加入风险分级；
7. 加入整改建议；
8. 加入 AI 复核；
9. 完善报告、历史记录和统计看板；
10. 增加知识库后台、登录、权限、备份和部署配置。

正式巡检最终应形成：

```text
创建巡检 → 验证并保存照片 → 视觉识别 → 检索规章 → 判断风险 → 生成建议 → AI 复核 → 保存报告
```

任一步骤失败都应保存错误原因、将状态设为 `failed` 并允许重试。

## 当前范围边界

当前纳入宿舍和实验室演示场景、现场照片上传、巡检记录、报告查看、基础统计接口和检查清单模板。

当前暂不包含真实视觉模型、自动规章检索、整改结果提交、整改照片、复查和销项、整改完成率统计、实时视频、原生 App、小程序、复杂组织权限和消息推送。

“分析完成”只表示系统完成了本次分析报告，不表示现场问题已经整改完成。
