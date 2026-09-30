# VIB-48 未发布内容质量分流验收

日期：2026-09-30。启动基线 `38cecfc`，工程提交 `74beabe`，分支 `codex/evidence-audit`。本阶段为本地工程验证，VIB-48 保持 In Progress。

## 实现与边界

- `retrieval_quality.py` 的 `unpublished-exact/v1` 在一次成功检索结束、返回证据之前扫描本地候选。模型故障的显式降级共用此路径；严格模型失败、非法 Scope/模型/发布门禁不写问题。数据库和审计失败直接传播，质量扫描整批回滚。
- 来源范围取指定 KV/Index 中已审核、已索引 Evidence 的精确 SourceRevision，再与冻结来源 ID Scope 相交。仅有来源 ID 不授权扫描它的更新修订；历史引用也不扩展扫描修订。显式空 Scope 不扫描、不调用模型。
- Evidence 引文、原始片段、关系断言采用 NFKC/大小写规范后的查询全文包含匹配；概念自身词形、药物自身词形、方剂原名/药味采用自身完整词形在查询中的包含匹配。概念词形需匹配自身时代/流派，裁定概念需自身提及锚点。不跨身份传播别名、不多跳、不用向量或云模型评价未发布内容。
- 扫描 DRAFT 和 REVIEWED 但尚未发布的候选；任何 READY 版本已发布过的精确目标不重复报未发布问题，REJECTED 目标排除。知识候选必须有本范围内的精确 Evidence 关联，另一来源的关联不授权命中。
- 没有 Evidence 引用的最外层可引用片段可转 `text_segment_revision` 问题，覆盖 CLAUSE/PARAGRAPH/COMMENTARY/NOTE/CASE_NOTE/FORMULA_TEXT/SENTENCE。可引用父片段与句子子片段不重复报；父片段已有自身或直接子片段的 Evidence 引用时不再报原始片段。被拒绝 Evidence 的引用也保留，避免把人工拒绝转换成新的原始片段问题。
- 自动创建 `RETRIEVAL_UNPUBLISHED_EXACT_V1`、WARNING、OPEN 的 QualityIssue。精确匹配是保守工程命中规则，**不是经过校准的“高相关”医学质量阈值**；仅提示人工核对，不自动 APPROVE、规范化或设置 BLOCKER。既有人工 BLOCKER、Evidence 先审及发布门禁保留。
- 问题描述保存策略、匹配依据、原 query/NFKC query、冻结 KV/Index、首次研究 task（如有）、精确来源/Evidence/segment 修订、原文哈希和结构定位。一个目标多条合格依据时，按确定顺序保存首条 Evidence 的段落引用；不声称完整列出全部依据。
- 自动问题以规则类型+目标去重，跨查询、版本与人工解决/豁免保留首次观察。目标行锁避免并发重复；先取得整批目标锁，再写审计，避免持有审计头锁时等待另一批目标。`open_quality_issue` 新增可选共享事务和去重，原人工入口默认行为保留，无新迁移或依赖。
- 每次最多新增100个目标；已有问题在截取前排除，后续查询可继续处理剩余匹配。该上限约束写入数量，不代表大语料扫描的性能验收。
- 未发布候选和 QualityIssue 描述不加入检索结果、重排文档、研究证据池或浏览器检索 DTO。旧版已发布 Evidence 仍按精确修订返回，新版草稿仅转问题。既有已发布 Evidence 的冻结上下文保持原语义。

## 实际验证

- 首库 `tcm_vib48_quality_initial_test` 完整后端：**227 passed、1 failed、0 skipped**，306.37秒。失败是新增并发用例用 UUID 比较 `EventLog.aggregate_id` 字符串字段；并发检索、6个唯一问题已通过断言。修正为字符串 ID，保留失败库。
- 同库质量扫描专项：**18 passed、0 skipped**，84.10秒，包含修正后的并发问题/审计链、人工解决与豁免、旧发布/新草稿、待审知识、已审未发布、同来源更新修订、其他来源、空范围/无命中、NFKC词形范围、拒绝 Evidence、纯未发布命中、本地 API、模型故障/严格失败、原子回滚、写入上限续扫、人工门禁和研究任务上下文。
- 补上外层 COMMENTARY/NOTE/CASE_NOTE/FORMULA_TEXT 和句子引用不重复转父片段两条用例后，最终新库 `tcm_vib48_quality_final_test` 完整后端：**233 passed、0 failed、0 skipped**，327.57秒，相对基线新增20条质量扫描集成用例。
- 首库空库升0026、0026→0023→0026往返、两次 Alembic 模型检查无差异；旧合成概念/方剂内容、DRAFT/null/版本0保留。最终新库也已完成上述迁移检查，测试数据与两库均保留。
- 完整生产代码与测试 Ruff、最终 diff/暂存 diff 检查通过。本轮后端改动，检索 DTO 不变；未改前端，未重跑前端 build 或浏览器。
- 全部 LOCAL_ONLY/合成工程验证，0次真实云调用；未修改预览/业务库或 API 容器，未执行真实模型质量、生产断网或 Windows 凭据实机验收。

## 下一步

补繁简、异体、历史别名查询候选扩展的完整验收，保留原 query 和冻结 Scope，不把词形相似当作身份合并或医学等价。真实相关性阈值/Golden Set 留给 VIB-68；VIB-46 的真实 C02/专家依赖仍待补。
