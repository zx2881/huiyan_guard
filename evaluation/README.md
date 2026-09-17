# 离线评测数据约定

`scripts/evaluate.py` 将人工标注与系统输出分开保存。仓库只提交格式示例；真实校园照片、实际标注、预测明细和指标 JSON 保存在本地忽略目录中，不随源码发布。

建议目录：

```text
evaluation/
├── dataset.json              # 真实人工标注，Git 忽略
├── images/                   # 来源合规的现场图片，Git 忽略
├── results/                  # 预测与机器可读指标，Git 忽略
└── examples/                 # 可提交的无图片格式示例
```

每张图片必须记录唯一 ID、`smoke` 或 `validation` 分组、场景、相对图片路径、来源和使用权限、人工标注的可见隐患及无法确认项目。先冻结 `validation` 标注，再调整提示词、阈值或 YOLO 类别映射；已经用于调参的图片不能继续冒充独立验证集。

隐患按规范化后的标签一对一精确匹配。确需合并同义标签时，在数据集顶层 `label_aliases` 显式登记，不能在得到结果后临时修改口径。失败和缺失请求按空预测计入漏报。耗时从提交上传开始，到报告进入 `completed` 或 `failed` 为止。

用已有预测验证工具和报告格式：

```powershell
.\.venv\Scripts\python.exe scripts\evaluate.py `
  --dataset evaluation\examples\dataset.example.json `
  --predictions evaluation\examples\predictions.example.json `
  --json-output evaluation\results\example-metrics.json `
  --report docs\evaluation.md
```

配置真实视觉模型并启动服务后采集真实预测：

```powershell
$env:APP_ACCESS_USERNAME = "评测账号"
$env:APP_ACCESS_PASSWORD = "评测密码"
.\.venv\Scripts\python.exe scripts\evaluate.py `
  --dataset evaluation\dataset.json `
  --base-url https://你的服务地址 `
  --predictions-output evaluation\results\predictions.json `
  --json-output evaluation\results\metrics.json `
  --report docs\evaluation.md
```

访问密码只从环境变量读取。报告不复制图片和密钥；真实评测结束后可单独提交脱敏的 `docs/evaluation.md`，提交前仍需人工核对样本数、模型标识和示例警告是否正确。
