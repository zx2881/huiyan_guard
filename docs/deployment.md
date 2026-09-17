# 部署、备份与恢复

本文对应实施方案第 6 步，目标是单机、单应用进程部署。SQLite、上传图片和进程内任务不支持多实例并发，不要增加 Uvicorn worker 数或同时启动多个容器。

## 上线前配置

复制 `.env.example` 为 `.env`，至少确认以下内容：

```dotenv
DATABASE_URL=sqlite:///./data/app.db
UPLOAD_DIR=./data/uploads/inspections
APP_ACCESS_USERNAME=reviewer
APP_ACCESS_PASSWORD=请替换为独立强密码
WRITE_RATE_LIMIT_PER_MINUTE=30
```

部署到公网或保存真实校园照片时，`APP_ACCESS_USERNAME` 和 `APP_ACCESS_PASSWORD` 必须同时设置。健康检查 `/api/health` 保持公开，但不返回密钥、路径或报告内容。页面、接口和 `/uploads` 图片都受 HTTP Basic Auth 保护。

`compose.yaml` 固定设置 `REQUIRE_ACCESS_CONTROL=true`，因此缺少访问凭据时容器会拒绝启动，不会意外以开放模式上线。本机直接运行时默认仍允许开放模式，便于使用公开样例调试。

方舟或文本模型配置按 README 填写。只有文本模型已经配置时才可设置 `ENABLE_AI_REVIEW=true`。YOLO 仍使用预留配置，当前镜像不包含 YOLO 运行时或权重。

## Docker Compose 启动

Linux 主机先准备可写的数据目录：

```bash
mkdir -p data/uploads/inspections
sudo chown -R 10001:10001 data
docker compose up -d --build
docker compose ps
curl http://127.0.0.1:8000/api/health
```

Windows Docker Desktop 可直接创建 `data/` 后运行 `docker compose up -d --build`。容器只启动一个 Uvicorn worker，`./data` 挂载至 `/app/data`。更新代码时先备份，再执行 `docker compose up -d --build`。

建议在服务器防火墙只开放反向代理端口，并由 Caddy 或 Nginx 提供 HTTPS。若直接暴露 8000 端口，Basic Auth 凭据会在明文 HTTP 中传输，不可用于公网。

## 本机生产启动

不使用 Docker 时，在已经安装依赖并配置 `.env` 的仓库目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\start_production.py
```

该脚本固定使用一个进程，不启用热重载。

## 一致性备份

应用运行期间可以备份。脚本使用 SQLite backup API 获取一致数据库副本，同时复制上传图片并写入 SHA-256 清单：

```powershell
.\.venv\Scripts\python.exe scripts\backup_data.py --output E:\huiyan-backups
```

备份目录包含 `app.db`、`uploads/` 和 `manifest.json`。将备份保存在仓库和 `data/` 之外；备份可能包含现场照片，不得提交 Git 或放入公开网盘。

## 恢复演练

恢复前必须停止应用，避免运行中的进程继续写数据库或图片：

```powershell
docker compose down
.\.venv\Scripts\python.exe scripts\restore_data.py --source E:\huiyan-backups\huiyan-backup-时间戳 --confirm
docker compose up -d
```

恢复工具先校验清单、数据库完整性和每张图片的 SHA-256，再以同目录临时文件替换当前数据。没有 `--confirm` 时拒绝执行。恢复后检查 `/api/health`、历史记录、图片和至少一份报告。

## 上线验收

1. 未登录访问首页和 `/uploads/任意文件` 返回 401，健康检查返回 200。
2. 用手机流量完成上传、等待分析、查看法规、人工确认和打印/PDF。
3. 重启容器后，历史记录、报告和照片仍可读取。
4. 连续重复提交触发 429，并带 `Retry-After`。
5. 页面源代码、健康接口、错误响应和交付包中没有密钥。
6. 执行一次备份和恢复演练，记录备份目录、时间、数据库大小和图片数量。
7. 保存 `v0.6.0` 或后续稳定标签作为回滚点。

## 本地工程验收记录

2026-09-17 已使用 Docker Desktop 完成镜像构建。运行镜像时使用非 root 用户 `huiyan`，镜像内不包含 `.env`、测试、样例图片或赛事资料。临时容器启用访问保护后，健康检查返回 200，未授权首页返回 401，授权首页返回 200；创建演示报告并重启容器后，数据库记录和图片路径仍可读取。容器内一致性备份成功生成数据库、1 张图片和校验清单。

Playwright 在 390×844 手机视口检查了报告和内联修正表单，页面内容宽度与视口同为 390px，无横向溢出，浏览器控制台没有错误或警告。这些结果证明本地构建和响应式工程可用，不替代公网 HTTPS、手机流量和真实模型验收。

公网服务器地址、HTTPS 证书和真实模型凭据尚未提供，因此仓库只能完成部署工程和本地容器验收，不能据此宣称外网手机链路已经通过。
