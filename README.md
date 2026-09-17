# 慧眼安巡代码仓库

当前原型已具备从照片上传、后台分析到人工复核和打印报告的完整主链路：系统依次执行视觉识别、规章检索、内部风险分级和整改建议，保存法规引用快照，并允许确认、修正、标记误报或人工补录。AI 原始结论与每次人工操作分开留档。项目提供单进程 Docker 部署、访问保护、写请求限流、数据备份恢复和可选内部 AI 复核。宿舍知识库有 25 条可追溯法规记录。真实视觉效果仍待团队提供凭据或 YOLO 权重及现场样图验收。

本 README 只说明现有代码如何运行。开发范围、顺序与 9/28 前的校赛准备计划统一见 [项目实施方案](docs/01_项目实施方案.md)，当前能力证据见 [当前进展](docs/02_当前进展.md)。

## 安装与启动

在本目录执行，使用 Python 3.11 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启用当前可用的方舟视觉模型时，将 `.env.example` 复制为 `.env`，保持 `VISION_PROVIDER=ark`，再填写 `ARK_API_KEY`、`ARK_BASE_URL`、`ARK_MODEL`。`ARK_MODEL` 使用支持图片输入的实际接入点/模型标识。已有 `.env` 时直接编辑，不要覆盖已有密钥。修改后重启。

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

打开 [本地巡检页面](http://127.0.0.1:8000/)。数据库和上传目录由程序自动创建，目前无需也没有独立初始化脚本。2026-09-17 已在仓库独立虚拟环境中按 `requirements-dev.txt` 完成安装、测试和 Uvicorn 启动验收。

健康检查地址为 <http://127.0.0.1:8000/api/health>。它只验证应用和 SQLite 是否可用，并报告视觉模型是否配置，不会请求模型服务。

## 配置

配置统一由 `backend/app/config.py` 读取。可以使用仓库根目录的 `.env`，也可以设置同名环境变量；环境变量优先。

| 变量 | 默认值 | 说明 |
| --- | --- | --- |
| `DATABASE_URL` | `sqlite:///./data/app.db` | 当前只支持本地 SQLite 文件 |
| `UPLOAD_DIR` | `./data/uploads/inspections` | 巡检图片目录 |
| `ARK_API_KEY` | 空 | 火山方舟 API Key |
| `ARK_BASE_URL` | 方舟兼容 API 地址 | 模型服务基础地址 |
| `ARK_MODEL` | 空 | 支持图片输入的接入点或模型标识 |
| `VISION_PROVIDER` | `ark` | `ark` 使用现有方舟适配器；`yolo` 只启用预留入口，当前不会加载模型 |
| `YOLO_MODEL_PATH` | 空 | 未来 YOLO 权重路径预留 |
| `YOLO_DEVICE` | `auto` | 未来 YOLO 推理设备预留，如 `cpu` 或 `cuda:0` |
| `YOLO_CONFIDENCE_THRESHOLD` | `0.25` | 未来 YOLO 检测置信度阈值预留 |
| `YOLO_INPUT_SIZE` | `640` | 未来 YOLO 输入尺寸预留 |
| `MAX_UPLOAD_BYTES` | `10485760` | 单张上传图片最大字节数，默认 10 MiB |
| `MAX_IMAGE_PIXELS` | `25000000` | 图片解码后的最大总像素数 |
| `VISION_REQUEST_TIMEOUT_SECONDS` | `30` | 方舟单次请求超时 |
| `VISION_TOTAL_TIMEOUT_SECONDS` | `75` | 一次视觉分析的总体时间预算 |
| `VISION_JSON_RETRIES` | `2` | 方舟输出 JSON/结构错误后的修正次数，范围 0–2 |
| `TEXT_API_KEY` | 空 | 可选的 OpenAI 兼容文本模型 API Key |
| `TEXT_BASE_URL` | 方舟兼容 API 地址 | 文本模型服务基础地址 |
| `TEXT_MODEL` | 空 | 文本模型接入点或模型标识；为空时使用透明规则模式 |
| `TEXT_REQUEST_TIMEOUT_SECONDS` | `30` | 文本模型单次请求超时 |
| `ENABLE_AI_REVIEW` | `false` | 启用内部报告复核；必须先配置文本模型 |
| `APP_ACCESS_USERNAME` | 空 | 公网/真实照片部署的 HTTP Basic Auth 用户名 |
| `APP_ACCESS_PASSWORD` | 空 | 与用户名同时设置；不要提交 Git |
| `REQUIRE_ACCESS_CONTROL` | `false` | 为 true 时缺访问凭据将拒绝启动；Compose 强制启用 |
| `WRITE_RATE_LIMIT_PER_MINUTE` | `30` | 单进程内每个客户端每分钟写请求上限 |

相对数据库和上传路径始终以仓库根目录为基准，不受启动命令所在目录影响。数据库连接在每次事务结束后显式关闭。公网部署必须同时设置访问用户名和密码，并通过 HTTPS 访问；健康检查保持公开且不返回敏感信息。

YOLO 的运行时、权重、类别映射和依赖尚未加入生产依赖。把 `VISION_PROVIDER` 改为 `yolo` 后，健康检查会显示已选择 YOLO 但未配置完成，巡检仍明确进入演示模式，不会伪装为已识别。具体接入边界见 [YOLO 接入预留](docs/yolo-接入预留.md)。

## 规章知识库

应用启动时会校验并自动导入内置宿舍知识库。更新 `knowledge/dormitory/regulations.json` 后也可以手工执行：

```powershell
.\.venv\Scripts\python.exe scripts\import_knowledge.py
```

导入程序会先校验字段、来源 URL、日期、关键词和检查项，再按稳定 ID 更新 SQLite；重复执行不会产生重复条款。当前宿舍清单有 10 个可见检查项，25 条知识记录来自《高等学校消防安全管理规定》《中华人民共和国消防法》和《教育系统重大事故隐患判定指南》。学校内部公寓制度尚未提供，因此没有写入具体功率阈值、校内处分或本校检查频次。数据格式、检索用法和新增校级文件流程见 [知识库说明](docs/knowledge.md)。

## 自动化测试

开发环境安装与运行：

```powershell
.\.venv\Scripts\python.exe -m pip install -r requirements-dev.txt
.\.venv\Scripts\python.exe -m pytest
```

测试使用临时数据库和临时上传目录，不读取真实模型凭据、不调用付费 API，也不会写入仓库的 `data/`。当前测试覆盖图片校验、视觉结构、知识导入/检索、后台步骤、规则分级、引用快照、失败重试、重启恢复、人工复核审计和安全报告渲染。真实模型服务需由团队配置凭据后另做手工验收。

## 生产部署与数据保护

仓库提供 `Dockerfile`、`compose.yaml` 和固定单进程的生产启动脚本。复制 `.env.example` 为 `.env` 并填写访问凭据后运行：

```powershell
docker compose up -d --build
```

SQLite 和上传图片统一保存在挂载的 `data/`。备份、校验恢复、HTTPS 要求和上线检查清单见 [部署、备份与恢复](docs/deployment.md)。应用运行期间可执行一致性备份；恢复前必须停止服务并显式传入 `--confirm`。

## 现有页面与接口

| 页面 | 用途 |
| --- | --- |
| `/` | 选择场景、预览/压缩并上传照片 |
| `/records` | 可搜索、按状态筛选的历史记录 |
| `/report?id=编号` | 复核、补录和打印单次报告 |

| 接口 | 用途 |
| --- | --- |
| `POST /api/inspections` | 表单 `scene` + `image` 创建巡检；真实分析返回 202 后后台执行 |
| `GET /api/inspections` | 查询历史 |
| `GET /api/inspections/{id}` | 查询巡检及隐患 |
| `POST /api/inspections/{id}/retry` | 重试失败或服务重启中断的巡检 |
| `PATCH /api/hazards/{id}` | 确认、修正或标记误报，并记录审计信息 |
| `POST /api/inspections/{id}/hazards` | 人工补录隐患 |
| `GET /api/dashboard` | 巡检数、真实隐患数与风险分布 |
| `GET /api/health` | SQLite、模型、内部复核和访问保护配置状态 |

字段、响应、错误语义以及尚未实现的计划接口见 [API 契约](docs/api.md)。

## 文件与数据

- `backend/app/config.py`：集中读取并校验环境配置。
- `backend/app/main.py`：应用工厂、页面托管、上传、查询、健康检查和统计。
- `backend/app/database.py`：SQLite 连接、事务、显式关闭与建表。
- `backend/app/schemas/inspection.py`：与视觉提供方无关的严格输出结构。
- `backend/app/utils/images.py`：上传体积、真实格式、完整性和像素限制校验。
- `backend/app/agents/perceive.py`：加载场景清单并调用视觉客户端。
- `backend/app/integrations/vision_provider.py`：视觉适配器统一契约，后续业务层只依赖它。
- `backend/app/integrations/vision_factory.py`：按 `VISION_PROVIDER` 选择适配器。
- `backend/app/integrations/vision_client.py`：当前可用的方舟适配器。
- `backend/app/integrations/yolo_client.py`：YOLO 接入预留，带 `TODO(YOLO)`，尚不加载运行时。
- `backend/app/knowledge/`：法规数据校验模型和按场景、关键词、同义词检索模块。
- `backend/app/workflow/runner.py`：分析步骤、状态、引用快照和失败处理。
- `backend/app/agents/review.py`：可选内部复核，最多自动重做一次，仍不通过则转人工。
- `backend/app/backup.py`：SQLite 一致性备份、图片校验清单和恢复。
- `backend/app/agents/classify.py`、`remediate.py`：风险分级与整改建议，支持规则和可选文本模型。
- `backend/app/integrations/text_client.py`：可选 OpenAI 兼容文本模型适配器。
- `scripts/`：生产启动、知识导入、数据备份和确认式恢复命令。
- `frontend/`：三个响应式 HTML 页面、公共样式、上传压缩、安全报告渲染、人工复核与打印脚本。
- `knowledge/`：宿舍/实验室检查清单、宿舍法规数据及来源核验记录。
- `samples/测试.jpg`：交接时提供的一张样图，无标注，不是正式评测集。
- `data/app.db`、`data/uploads/inspections/`：运行时生成的数据和照片。

检查清单告诉系统“查什么”，真实规章提供“判断依据”，巡检记录保存“这次发生了什么”，三类数据分开维护。数据库和图片目录分别由 `DATABASE_URL`、`UPLOAD_DIR` 控制。

密钥不提交 Git；数据库升级先备份再迁移；正式报告保存引用快照，不能让知识库更新改变历史报告。配置 `APP_ACCESS_USERNAME` 和 `APP_ACCESS_PASSWORD` 后，页面、API 和 `/uploads` 图片统一受访问保护；未配置时只适合本机原型和公开样例。

## 后续开发入口

实施方案第 1–6 步的仓库工程已完成，下一步进入真实服务器/手机验收和第 7 步评测与离线回放。YOLO 运行时、权重和类别映射仍通过既有适配器边界接入，不影响复核与报告数据结构。

赛事通知、报名指南、评分表、官方模板、原始参赛 Word 和本地核验附件不随仓库发布。项目计划和进展文档位于 `docs/`；文档提及的赛事原件需从团队本地资料获取。
