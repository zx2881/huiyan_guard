# YOLO 接入预留

更新：2026-09-17。项目计划采用 YOLO 进行本地视觉识别；当前只完成接入边界和配置预留，**没有安装 YOLO 依赖、加载权重或执行推理**。

## 已预留的位置

| 位置 | 作用 | 后续 YOLO 工作 |
| --- | --- | --- |
| `backend/app/config.py` | `VISION_PROVIDER` 和 `YOLO_*` 配置 | 保持字段名；按最终模型补充必要配置 |
| `backend/app/integrations/vision_provider.py` | 所有视觉模型的统一输入/输出契约 | 不修改业务层，YOLO 适配器返回相同结构 |
| `backend/app/integrations/vision_factory.py` | 根据配置选择方舟或 YOLO | 完成 YOLO 后将其 `enabled` 设为真实可用状态 |
| `backend/app/integrations/yolo_client.py` | 唯一允许放 YOLO 运行时和权重加载代码的位置 | 实现权重加载、推理、类别映射和结果转换 |
| `backend/app/agents/perceive.py` | 读取检查清单并调用提供方无关的视觉接口 | 保持不依赖 YOLO SDK |
| `backend/app/main.py` | 依据适配器是否可用决定真实推理或演示模式 | 不读取权重、不处理原始检测框 |

所有预留点都有 `TODO(YOLO)` 标注。当前设置 `VISION_PROVIDER=yolo` 时，`/api/health` 会返回 `vision_provider: "yolo"` 和 `vision: "unconfigured"`；上传巡检会明确显示 YOLO 尚未接入，不会伪造识别结果。

## YOLO 接入时需要完成的工作

1. **确定任务类型和标签。**宿舍巡检更适合目标检测：先列出可由照片直接识别的类别，例如插线板被覆盖、通道堆物、明火、违规电器。每个类别要有足够且授权使用的标注图片。YOLO 不能可靠判断照片外、遮挡处或需要规则推理的事项。
2. **准备数据与评测集。**训练、验证和最终评测图片分开；每张保留来源、使用授权、场景和标注版本。不能用训练图片直接宣称准确率。
3. **确定运行方式。**确认权重格式、推理框架版本、CPU/GPU、显存、模型大小、推理耗时与部署镜像。此时再把必要依赖固定到 `requirements-yolo.txt` 或部署镜像中，避免现在无权重时增加安装体积。
4. **实现 `YoloVisionClient.analyze()`。**加载一次权重，执行图片推理，将类别 ID、边界框和置信度映射为统一输出。`location` 应由相对位置或区域描述生成；`evidence` 必须说明实际检测到的对象；不确定项必须保留而不是猜测。
5. **建立类别映射。**把 YOLO 类别映射到 `knowledge/{scene}/checklist.json` 的稳定检查项 ID，并将不支持的项目写入 `uncertain_items`。不要让类别名直接成为规章匹配依据。
6. **接入第二步的稳定化能力。**复用图片内容校验、大小限制、输入压缩、统一 schema、超时、错误分类、无隐患保存和报告安全渲染。YOLO 通常不需要“JSON 修复重试”，但仍需要模型加载失败、推理超时和无检测结果处理。
7. **验证再切换。**先在 `VISION_PROVIDER=yolo` 的测试环境跑完单元测试和标注图集，再将 `YoloVisionClient.enabled` 改为实际可用。此时健康检查的 `vision` 才能报告 `configured`。

## 统一输出契约

无论来自方舟还是 YOLO，业务层只接收：

```json
{
  "image_quality": "good",
  "hazards": [
    {
      "check_id": "socket_cover",
      "name": "插线板被衣物覆盖",
      "location": "照片右下方桌面区域",
      "evidence": "检测到插线板及其上方覆盖的衣物",
      "confidence": 0.91
    }
  ],
  "uncertain_items": ["插线板插头是否破损无法从当前角度确认"]
}
```

`check_id` 必须来自当前场景检查清单，后续规章检索优先使用该稳定 ID；无法映射时返回 `null` 并进入人工核验。`confidence` 是模型输出的检测分数，不等同于整体识别准确率。检测框、类别 ID、模型版本和原始分数可以在内部调试日志或评测结果中保存；公开报告应面向巡检人员展示可理解的证据和位置。

## 第二步受到的影响

不受影响：前端压缩预览、后端文件校验、SQLite 保存、报告展示、无隐患处理、后续规章检索、风险分级、人工确认。

需要按 YOLO 调整：视觉推理适配器、类别映射、模型加载/超时策略、部署依赖、训练/标注/评测。原设计中针对大模型的“强制 JSON 输出和 JSON 修复重试”只适用于方舟适配器；YOLO 应做检测结果结构校验和推理失败处理。

因此，第二步仍然应该先完成，只需把“视觉输出稳定化”写成适配器无关的能力，并在具体实现时为方舟和 YOLO 分别采用合适的错误处理方式。
