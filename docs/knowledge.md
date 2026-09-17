# 宿舍规章知识库

更新：2026-09-17。

## 当前范围

`knowledge/dormitory/checklist.json` 定义 10 个可从照片寻找直接证据的宿舍检查项。`knowledge/dormitory/regulations.json` 保存 25 条法规记录，来源、范围与缺口记录在 `knowledge/sources/README.md`。

当前数据是公共法规基线，不包含用户所在学校的内部制度。实验室场景尚未建立法规数据，因此不得借用宿舍条款生成实验室依据。

## 导入

应用启动时会校验并自动导入内置知识库。需要单独检查或更新数据库时，可在仓库根目录执行：

```powershell
.\.venv\Scripts\python.exe scripts\import_knowledge.py
```

也可以传入其他符合结构的文件：

```powershell
.\.venv\Scripts\python.exe scripts\import_knowledge.py knowledge\dormitory\regulations.json
```

导入前会验证场景、稳定 ID、正文、来源 URL、核验日期、关键词和检查项映射。数据库使用 `ON CONFLICT(id) DO UPDATE`，所以重复导入只更新同一 ID，不增加重复记录。

## 数据字段

每条记录必须包含：

- `id`：稳定、小写的条款 ID，后续修改正文时不得随意更换；
- `scene`：当前为 `dormitory`；
- `document_title`、`document_number`、`source_file`；
- `article`、`content`：可定位的条号和与检查项直接相关的正文；
- `source_url`、`verified_at`：可访问来源和最后核验日期；
- `keywords`：检索词，不放“安全”“问题”等宽泛词；
- `check_ids`：对应检查清单中的稳定 ID。

## 检索

后端调用示例：

```python
from backend.app.knowledge.retriever import retrieve_regulations

matches = retrieve_regulations(
    "dormitory",
    "门口堆放纸箱，堵住疏散通道",
    check_id="blocked_exit",
    limit=3,
)
```

检索先按场景过滤，再计算直接关键词、同义词和检查项 ID 分数，只返回得分大于零的记录。没有匹配时返回空数组，不选择任意条款兜底。返回值保留条款 ID、原文、出处、核验日期、命中词和分数，供下一步保存引用快照。

## 补充本校制度

取得学校正式文件后，应先确认文件仍有效且适用于当前校区和学生宿舍，再补充记录：

1. 保存正式文件名、发文单位、文号、发布日期或施行日期；
2. 逐条选择与可见检查项直接相关的正文，不复制与项目无关的处分条款；
3. 使用独立稳定 ID，并填写官方校内来源 URL 或可审计的文件位置；
4. 更新 `knowledge/sources/README.md` 的核验记录；
5. 执行导入和测试，确认核心隐患命中、无关输入不误配。
