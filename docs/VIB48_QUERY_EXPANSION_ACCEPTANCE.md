# VIB-48 查询候选扩展阶段验收

日期：2026-09-30；启动基线 `442bc52`，工程提交 `e7b0af0`，分支 `codex/evidence-audit`。

## 实现与边界

- `retrieval_query.py` 定义不可静默扩大的 `explicit-orthography/v1`。有限字符组作为候选匹配依据；新增字符组须升级规则版本。支持表内繁简双向、混合书写和羣/群、峯/峰。不是完整繁简词典，也不是医学术语等价表。
- Exact 对 NFKC/小写后的查询和冻结 chunk 应用同一字形键；FTS 保留原 tokenizer/index，每个字符/二元词内 OR 已列字形，词之间 AND。当前二元词最多四个候选；去掉重复 token，不对整条查询生成指数级组合。FTS token 字符白名单及 SQL 参数绑定保留。
- Structured/Relation 只从冻结版本内已审核对象自身词形/方剂字段出发，匹配键相同。历史别名沿用自身已裁定 ConceptTerm 和自身精确提及锚点，不把比较对象或关联对象的其他别名传给当前身份，不多跳。
- 原 query、NFKC query、匹配键和策略在内部结果保留；研究审计与 benchmark 同时保存规则及实际排名。HTTP DTO 仍使用公开编号，`/retrieval/query` 保留原查询和 NFKC 查询，未暴露修订 UUID 或未发布候选。
- 发/發/髮、后/後、脏/臟/髒、术/朮/術、参/參、范/範等未列歧义映射保持原样。未列字符、未知词和未裁定概念不推断；同名不同类型/时代对象仍为独立身份。
- 不重写原文、概念词形、旧 FTS 或向量记录。已有邻段上下文仍属于 searchable chunk。Scope、精确 Published EvidenceRevision、历史引用隔离和模型门禁沿用原实现。
- 模型仅接收原有 NFKC 查询与已发布证据，不额外外发词形表或别名。服务本地/显式降级共用扩展；研究/benchmark 默认严格失败。
- 未发布质量分流仍为 `unpublished-exact/v1`，使用原查询的 NFKC 字面规则；字形扩展命中本身不新增问题。真实医学相关性阈值由 VIB-68 校准，此阶段不替代它。

## 实际验证

- 既有 Linux 容器 `tcm-vib54-py`，独立 PostgreSQL 容器 `tcm-handoff-test`；全程 LOCAL_ONLY、合成工程数据、0 次真实云调用。
- 首专项库 `tcm_vib48_query_target_test`：**4 passed、5 failed、0 skipped**（15.46 秒）。失败包含四处测试预期：既有 chunk 含邻段上下文、HTTP 查询活动版本全来源、研究任务去掉首尾空白，以及一处遗漏的较/較映射。修正预期并补齐明确字符组。
- 同库复验查询扩展集成：**6 passed、0 skipped**（16.92 秒）；规则边界单测另 **2 passed**（0.88 秒），方剂繁简/冻结字段用例首专项通过。
- 全新库 `tcm_vib48_query_final_test`：完整后端 **241 passed、0 failed、0 skipped**（366.14 秒），比启动基线增加8条查询扩展测试。仅从空库升至 head 建立测试前提；未重复迁移往返/旧数据探针，无 schema/model/dependency 变更。
- 完整后端 Ruff `--no-cache --ignore EXE002` 通过；最终 diff 检查通过。既有 Starlette TestClient 及 Alembic 配置弃用提示保留，不调整依赖。

覆盖：混合繁简与异体 Exact/FTS、索引内容不变、歧义和未知、同名独立身份、时代词形与来源 Scope、关系锚点、旧版精确 Evidence 与新版替换、方剂字段、本地 API 不读凭据、显式模型故障降级、研究冻结版本/范围/审计、benchmark 落库和严格模型失败、历史裁定不传播比较身份。完整回归同时覆盖既有发布门禁、质量问题和研究链。

## 状态与后续

本阶段工程验收完成，VIB-48 仍 In Progress：VIB-46 真实 C02/专家依赖未完成，真实模型、生产断网、Windows 密钥实机和医学相关性评测不能由合成测试宣告通过。没有前端/API DTO 变更，未重跑前端构建或浏览器；未修改业务/预览库、API 容器，未推送或部署。简短验收已同步 Linear 评论 `76be83b4-99d8-4a8a-b8c0-c32860d87d68`，详细工程证据保留本地。

后续开发采用增量流程：只读交接当前页及对应 Issue；专项先验证新行为，跨检索/研究链改动完成后仅做一次完整后端回归；无结构变更不重复迁移往返，无前端变更不重复 build/浏览器；测试通过后直接记录、提交，不再重复已通过的相同检查。失败只复验失败相关范围，再在需要时完整验证。
