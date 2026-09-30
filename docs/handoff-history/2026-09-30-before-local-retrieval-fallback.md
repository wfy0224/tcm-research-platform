# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 codex/evidence-audit，工程基线c9bc6f6（VIB-48结构/关系检索）；此前e852c48（接续文档）、86c6299（VIB-45/46）。接续文档另行提交，最新HEAD用git log核对。未推送或部署。
- VIB-48代码、测试与README已提交c9bc6f6；backlog、本交接、专项验收及交接归档随文档提交。本次提交后工作区应干净，以git status --short核对。
- 用户明确要求不要每轮留着不提交：今后完成可验证开发阶段后，默认提交本轮改动到本地Git并记录提交号；保留他人改动，只提交已识别的本轮范围。推送/发布仍按会话授权执行。
- 被替代首页：docs/handoff-history/2026-09-30-before-structured-retrieval.md。启动不必读历史；VIB-45/46详细工程证据在其专项验收文档。
- 范围V1知识底座与理论研究。VIB-63/49/60/61本地及Linear Done；VIB-46/48 In Progress；VIB-45本地完成、旧具体验收外发待授权；VIB-58 Windows密钥实机待安全环境。VIB-48状态与本轮证据已同步Linear，评论533b394a-dbc2-4924-83ad-70340e6bb71f。

## 2 VIB-48 当前实现与实际验证

- retrieval_structured.structured_candidates新增structured/relation通道并接入search_published RRF。已审核概念/关系/关系两端/方剂修订须是冻结KV成员；候选Evidence必须同时是该KV成员、指定索引片段和来源Scope内REVIEWED精确修订。
- 概念按自己词形匹配，词形时代/流派必须与概念相同；NFKC/大小写只用于查询匹配，返回保留原query。无繁简推定、模糊归并、跨身份同义词传播或多跳遍历。人工裁定仅用自身mention anchors，不借比较概念/额外裁定证据扩大来源。
- 关系只从范围内命中的概念出发，返回自身精确Evidence；范围外命中不会返回范围内关系。方剂匹配冻结original_name/药味，版本1仅返回对应字段来源，旧版本0沿旧FormulaEvidence；不匹配身份的可变当前名称。
- 历史引用不进入新快照候选，不用最新Evidence代替旧关联；旧版本仍可解析旧修订。source_ids=[]为空且不调用模型，None也按索引冻结source set过滤。benchmark显式固定KV/Index；研究任务原入口记录新通道，任务旧版本不随活动版本变化。
- 最终新独立库tcm_vib48_structured_verified_test完整后端 **177 passed、0 skipped**（115.25秒），比基线167条新增10条。含来源/旧版本/草稿/空范围/SQL参数化/NFKC/历史裁定/方剂字段/研究池验证。
- 新空库升0026、0026→0023→0026往返、两次alembic check无差异；合成旧方剂/概念内容、状态、null和版本0保留。完整后端/测试/迁移/脚本Ruff及diff检查通过。无新增迁移或依赖。
- 首库tcm_vib48_structured_initial_test：175过1失、0 skip（107.09秒）：新方剂测试漏服用说明，被既有完整抽取规则正确拒绝，补齐夹具后通过；生产方剂规则未改。两座库及全部失败/旧数据保留。
- 详情docs/VIB48_STRUCTURED_RETRIEVAL_ACCEPTANCE.md。VIB-48仅完成本地结构/关系准备，仍未完成无密钥/断网降级、UI提示、多样性、未发布高相关内容QualityIssue、查询候选扩展完整验收。
- 全部LOCAL_ONLY/合成工程验证，不代表专家术语/真实语料/模型质量。未修改预览/业务库/API容器，未跑前端/浏览器/真实云模型，无训练或微调。

## 3 既有知识与模型约束

- C02完整方剂摘录仍未冻结；backend/fixtures/initial_corpus.json只有29条非方剂C01，真实语料未APPROVE。VIB-46完整方剂/逐字段/术语裁定工程已实现，真实方剂与专家核对仍待补，不标Done。古病案待VIB-47，真实Golden Set待VIB-68。
- local-exact-terms/v4保留v2/v3冻结批次；候选、裁定和字段来源不可变、追加DRAFT，Evidence先审，知识后审，快照/激活复验。来源历史元数据冻结，未知保持null；不得补造规范剂量或跨来源真值。
- 用户曾问8B是否要升级；已建议核心研究模型升级并做同一专家样本对照，8B保留基线。没有具体模型/预算授权，未切配置或发起付费调用。更强模型也需VIB-68引文忠实度/无支持断言/拒答/成本/时延资格验证。
- VIB-45旧具体验收曾被自动审批拒绝，未经对应授权不重复外发；本轮VIB-48工程结论同步成功。

## 4 下一条具体操作

- 先核对initial_corpus.json是否有负责人“测试人员”冻结的C02及来源/权利/哈希/专家安排。若有，按实际排版承接VIB-46；若仍无，直接继续VIB-48，不重跑合成方剂验收或编造真实真值。
- **下一项：VIB-48无密钥/断网本地检索降级**。读取main.py的检索API/模型创建、model_runtime.py及相关适配器（先用rg定位）、retrieval.py与frontend/src/main.tsx。设计显式本地Exact/FTS/structured/relation路径，保持冻结KV/Index/Scope门禁，保留query，返回降级原因给UI；证据浏览不依赖云模型。
- 先覆盖缺密钥、网络/模型故障与范围过滤用例，再接API及UI显示。区分明确本地模式/已授权云失败和未授权外发；禁止静默扩大范围或以草稿回退。发布仍要求完整索引，不能拿降级绕过知识发布门禁。
- 接着补多样性、未发布高相关片段转QualityIssue和查询扩展专项。全部验收前VIB-48不标Done；VIB-46依赖仍保留。完成可验证阶段后提交本轮代码和接续文档，不再默认留未提交增量。

## 5 安全运行与复现

- Windows原生Python/uv/Alembic曾触发应用程序错误弹窗，禁止换入口或提权重试。仅用既有Linux容器tcm-vib54-py；tcm-vib54-py和tcm-handoff-test运行，Docker管道可用。
- 复现：docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib48_structured_recheck_test --full-suite。
- 脚本仅接受tcm_*_test、LOCAL_ONLY，不打印凭据/不删除旧库；有候选/字段/裁定数据不降级，迁移往返用新库。backend只读挂载，pytest禁缓存，PYTHONDONTWRITEBYTECODE=1；Ruff --no-cache --ignore EXE002。
- 不启动/修改docker-api-1或tcm_preview_shanghanlun；预览库未升0024/0025/0026，API仍unhealthy，本轮未修复/验收。tcm-vib63-forward仍停止。skip不等于通过。
