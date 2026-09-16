# 慧眼安巡代码仓库

当前是巡检原型：上传现场照片、保存 SQLite 记录、查询历史和查看基础报告。视觉客户端已接入上传流程，配置完整时调用火山方舟；没有完整配置时生成明确标注的演示提示。真实视觉调用尚待验收，风险等级、规章引用和整改建议目前仍是占位内容。

本 README 只说明现有代码如何运行。开发范围、顺序与 9/28 前的校赛准备计划统一见 [项目实施方案](docs/01_项目实施方案.md)，当前能力证据见 [当前进展](docs/02_当前进展.md)。

## 安装与启动

在本目录执行，使用 Python 3.11 或更高版本：

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

启用真实视觉模型时，将 `.env.example` 复制为 `.env`，填写 `ARK_API_KEY`、`ARK_BASE_URL`、`ARK_MODEL`。`ARK_MODEL` 使用支持图片输入的实际接入点/模型标识。已有 `.env` 时直接编辑，不要覆盖已有密钥。修改后重启。

```powershell
.\.venv\Scripts\python.exe -m uvicorn backend.app.main:app --reload --port 8000
```

打开 [本地巡检页面](http://127.0.0.1:8000/)。数据库和上传目录由程序自动创建，目前无需也没有独立初始化脚本。上述为安装步骤；本次盘点使用现有环境验证了基础接口，尚未完成这套依赖的全新环境安装验收。

## 现有页面与接口

| 页面 | 用途 |
| --- | --- |
| `/` | 选择场景、上传照片 |
| `/records` | 历史记录 |
| `/report?id=编号` | 单次基础报告 |

| 接口 | 用途 |
| --- | --- |
| `POST /api/inspections` | 表单 `scene` + `image` 创建巡检；当前等待模型完成后返回 |
| `GET /api/inspections` | 查询历史 |
| `GET /api/inspections/{id}` | 查询巡检及隐患 |
| `GET /api/dashboard` | 基础计数，尚需修正无隐患/演示提示计数 |

## 文件与数据

- `backend/app/main.py`：页面托管、上传、查询、统计及当前业务流程。
- `backend/app/database.py`：SQLite 连接与建表。
- `backend/app/agents/perceive.py`：加载场景清单并调用视觉客户端。
- `backend/app/integrations/vision_client.py`：模型请求与基础 JSON 解析。
- `frontend/`：三个 HTML 页面与公共样式。
- `knowledge/`：宿舍/实验室检查清单；规章数据和检索尚未实现。
- `samples/测试.jpg`：交接时提供的一张样图，无标注，不是正式评测集。
- `data/app.db`、`data/uploads/inspections/`：运行时生成的数据和照片。

检查清单告诉系统“查什么”，真实规章提供“判断依据”，巡检记录保存“这次发生了什么”，三类数据分开维护。当前代码把数据库和图片目录固定在本工程 `data/` 内，`.env.example` 中的 `DATABASE_URL`、`UPLOAD_DIR` 尚未被读取；后续按实施方案统一配置。

密钥不提交 Git；数据库升级先备份再迁移；未来正式报告保存引用快照，不能让知识库更新改变历史报告。当前图片通过 `/uploads` 公开访问，尚未提供访问权限控制。

## 后续开发入口

按实施方案第 1–8 步逐项完成：开发基线 → 稳定视觉 → 真实规章 → 分级/建议/进度 → 人工确认与报告 → 部署与复核 → 评测回放 → 材料和校赛演练。已经存在的页面和代码继续复用；新接口、部署脚本、检索和复核模块在实现前均属于计划。

赛事通知、报名指南、评分表、官方模板、原始参赛 Word 和本地核验附件不随仓库发布。项目计划和进展文档位于 `docs/`；文档提及的赛事原件需从团队本地资料获取。
