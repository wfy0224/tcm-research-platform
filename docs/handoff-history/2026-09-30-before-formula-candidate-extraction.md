# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 codex/evidence-audit，HEAD ab755a2（VIB-63 真实隔离 E2E）；VIB-45/46 增量均未提交，没有提交或部署。
- 本轮新增 knowledge_terms.py、0026_term_resolution.py、test_term_resolution_integration.py；修改 extraction/models/service/publish/CLI、抽取扫描测试、复现脚本及 README/backlog/追踪矩阵/验收文档。
- 启动时已有 VIB-45 parsing/fixture/测试及 VIB-46 extraction/0024/formula provenance/0025 等未提交改动，全部保留；AGENTS.md、交接及历史目录保留。上一首页归档 docs/handoff-history/2026-09-30-before-term-resolution.md。
- 当前范围 V1 知识底座与理论研究。VIB-63/49/60/61 本地及 Linear Done；VIB-46 本轮回读 In Progress，VIB-40 Done。VIB-45 本地验收完成，旧具体验收同步仍待授权；VIB-58 仍待 Windows 密钥实机验证。

## 2 VIB-46 当前交付与实际验证

- extract_source_candidates 使用 local-exact-terms/v3，仅 SEGMENTED 精确来源修订及最外层片段。同原词多类型保留独立概念/提及，按原词/类型/冻结时代/流派保留身份；不跨来源合并、不猜繁简/历史同义词。歧义标记 AMBIGUOUS_DRAFT 和不可降级的 requires_term_resolution，直接 APPROVE 拒绝，命名关系跳过歧义端点。旧 v2 批次保持。
- 新 knowledge_terms.py::adjudicate_term / CLI adjudicate-term 支持 NORMALIZE/HISTORICAL_SYNONYM/DISTINCT/UNRESOLVED。必须提供校订者、解释及精确 Evidence/片段修订和 Unicode 区间。可选部分原提及，复制到新 DRAFT，原概念/提及/审核状态保留；时代/流派沿用原概念，包括 null。
- 历史同义词必须指明已审核对照，并引用对照 Evidence 的精确范围；新概念继承对照名称/类型但保留原时代/流派及独立身份，原词登记有范围的 HISTORICAL。trace 返回解释、裁定者、原/复制提及、精确引文/哈希和对照快照；没有全局字符串合并或检索自动扩展。
- APPROVE 先审全部所引 Evidence，再验裁定；UNRESOLVED 不能批准，快照/激活继续复验，绕过服务改状态仍被拦。已发布校订审核后使用 supersede_reviewed_object 谱系，新旧版本分别保留新旧行并可切回；原关系引用须另行校订。
- 0026 数据库触发器冻结裁定、来源及新概念内容/词形/证据/提及，已审核或进入任意 KV 的概念内容/关联也冻结；原提及不可重绑/改位置，歧义标记不可清除。状态仍经审核服务单独处理；后续校订追加 DRAFT。有裁定或歧义标记数据时降级拒绝。
- 既有 FormulaFieldSource/0025 保存逐字段及药味序号来源、Unicode 区间、值/原文/哈希与规范解释；完整性在批准/快照/激活复验。旧已审核版本0沿原链保持，旧待审须追加版本1；规范剂量等未知保持 null，不换算古代单位。详见验收文档。
- 最终新独立库 tcm_vib46_terms_full_test 完整后端 **136 passed、0 skipped**（76.36秒）；较此前113条新增22条术语集成+1条多类型扫描，含实际29条候选、方剂33条专项及既有研究/API/导出回归。
- 最终新库空库升0024→合成旧方剂/旧概念探针→0026，0026→0023→0026往返，两次 alembic check 无差异。旧概念名称/类型/null时代流派/DRAFT保持，标记false且无补造裁定；旧方剂版本0/字段/状态保持。完整后端及脚本 Ruff、git diff --check通过。
- 首轮独立库 tcm_vib46_terms_initial_test 专项70 passed、0 skipped（34.47秒）；其后补历史同义词精确对照证据与激活/有数据降级用例，再跑最终完整136条。两个库及此前失败/验证库均保留。仅 Starlette/httpx 和 Alembic 旧分隔符配置弃用提示。
- 实际语料未 APPROVE；合成裁定不代表正式术语标准、专家复核或模型质量。未跑前端/浏览器/真实云模型，未改业务/预览库或 API。VIB-46 工程增量完成，但整个 Issue 仍在实施。
- 详细边界、CLI契约及复现见 docs/VIB46_KNOWLEDGE_CANDIDATES_ACCEPTANCE.md。Linear 已同步136条工程结论（评论 2ebeb7c4-1ec0-490c-832c-e2ca71151906），保持 In Progress；VIB-45 旧具体验收评论曾被自动审批拒绝，未经对应授权不重复外发。

## 3 下一条具体操作

- 继续 **VIB-46 完整方剂候选抽取**。先读 backlog VIB-46、验收文档未完成项及 backend/fixtures/initial_corpus.json 的 C02 状态，不回读历史。
- 入口 knowledge_extraction.py、knowledge_service.py::create_formula、knowledge_formula_provenance.py::FormulaFieldSourceSpec、test_knowledge_extraction_integration.py。为明确药味/原剂量/炮制/煎服原文实现保守本地候选 DRAFT 和逐字段引用，复用现有审核完整性门禁；条件不明确保持未知，方名提及不生成缺药味的完整方剂。
- C02 未冻结时先使用明确标为合成的工程文本实现规则/事务/引用测试，不宣告真实语料验收。真实完整方剂及专项校订仍需负责人“测试人员”冻结 C02 同章摘录、来源/权利说明/哈希并安排专家复核。C01 只有方名条文，不能补造完整药味剂量/煎服真值。
- 实际术语歧义/历史同义词仍需专家核对，种子词表不是标准；古病案由 VIB-47 选定、Golden Set由 VIB-68 补齐。无需等待这些输入即可推进上述方剂工程。

## 4 运行限制与复现入口

- Windows 原生 Python/uv/Alembic 曾触发应用程序错误弹窗，禁止换入口或提权重试。本轮只用既有 Linux 容器 tcm-vib54-py；Docker 管道需沙箱权限。tcm-vib54-py、tcm-handoff-test 已运行。
- 复现：docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib46_terms_recheck_test --full-suite。只接受 tcm_*_test、LOCAL_ONLY，不打印凭据/不删除旧库；已有候选/新版方剂/术语数据不降级。skip不等于通过。
- backend只读挂载：pytest禁缓存，PYTHONDONTWRITEBYTECODE=1；Ruff --no-cache --ignore EXE002（Windows挂载权限误报）。完整回归使用新库验证迁移往返；旧失败数据保留。
- 不启动或修改 docker-api-1、tcm_preview_shanghanlun。预览库仍未升0024/0025/0026，新代码可能提示旧schema；API原有unhealthy，本轮不修复/不验收预览健康。tcm-vib63-forward仍停止。
