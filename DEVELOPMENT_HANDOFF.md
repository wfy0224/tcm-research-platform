# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 codex/evidence-audit，工程基线 `74beabe`（VIB-48未发布内容质量分流），启动 `38cecfc`，此前多样性代码 `ffc70b7`。本轮接续文档另行提交，最新HEAD用git log核对。
- 启动工作区干净。代码、测试、README已提交 `74beabe`；backlog、需求矩阵、质量分流验收、本交接与旧首页归档随文档提交，提交后git status应干净。全部本轮范围，未改他人文件。
- 用户要求每轮完成可验证阶段后默认提交本地Git，只提交本轮范围。未推送或部署，推送/发布仍按会话授权。
- 旧首页归档：docs/handoff-history/2026-09-30-before-retrieval-quality.md，启动不读历史。
- 范围V1知识底座与理论研究。VIB-63/49/60/61本地及Linear Done；VIB-46/48 In Progress；VIB-45本地完成、旧详细验收外发待授权；VIB-58 Windows密钥实机待安全环境。
- 本轮简短验收已同步Linear评论 `5b90b9d7-ce2b-4a21-84a3-b44aa736c3c3`；VIB-48仍In Progress，依赖VIB-46/42。详细工程证据保留本地，早先外发审批限制不扩大。

## 2 VIB-48 最新实现与实际验证

- 新retrieval_quality.py的unpublished-exact/v1在成功检索返回前扫描本地未发布候选，只用冻结KV/Index内已索引Evidence的精确SourceRevision与来源Scope交集。仅来源ID不授权更新修订，历史引用不扩大扫描范围。
- Evidence引文/关系断言/最外层可引用片段匹配规范化查询全文；概念自身词形、药物词形、方剂原名/药味匹配查询中的完整自身词形。NFKC/大小写规范，概念时代/流派和自身裁定提及锚点限制保留；不跨身份别名传播、不多跳、不评估未发布内容的向量分数。
- DRAFT/REVIEWED但未在任何READY版本发布的候选命中转WARNING QualityIssue。REJECTED目标排除；原始片段仅无自身/直接子片段Evidence引用的最外层可引用片段，拒绝Evidence引用也保留，避免重新引入人工拒绝。
- 问题保存策略/匹配依据/原query/NFKC query、首次冻结KV/Index/task（如有）、精确来源/Evidence/segment修订、原文哈希与结构定位。多条依据确定性保存首条，不声称完整列出全部。精确命中不是校准的医学高相关阈值，只提示人工核对，不自动Approve/Blocker。
- 规则类型+目标跨查询/版本去重，解决/豁免不重新打开，保留首次观察。整批先锁目标再写审计，问题与审计同事务；每次至多新增100个目标，已有问题在截取前排除，后续查询可续扫。上限不代表大语料性能验收。
- open_quality_issue新增可选共享事务/去重，原人工默认行为和BLOCKER/Evidence先审/发布门禁保留。无新迁移或依赖。未发布候选/问题描述不进入结果、重排文档、研究池或浏览器检索DTO；旧发布Evidence和冻结上下文保持精确引用。
- 本地/混合/显式故障降级共用质量扫描；严格模型失败、Scope/模型/发布门禁失败不写问题。质量扫描DB/审计失败传播且整批回滚，不以降级绕过。
- 首库tcm_vib48_quality_initial_test完整后端 **227 passed、1 failed、0 skipped**（306.37秒）。新并发测试错用UUID比较EventLog.aggregate_id字符串字段，修正为字符串；同库质量专项 **18 passed、0 skipped**（84.10秒），失败库保留。
- 再补外层注释/病案/方剂片段与句子引用去重2条，最终新库tcm_vib48_quality_final_test完整后端 **233 passed、0 failed、0 skipped**（327.57秒），较基线新增20条质量扫描用例。
- 两库完成空库升0026、0026→0023→0026往返、两次alembic check无差异，旧合成概念/方剂内容/状态/null/版本0保留。完整Ruff、最终diff/暂存diff检查通过；测试库保留。
- 验收docs/VIB48_QUALITY_TRIAGE_ACCEPTANCE.md。本轮后端改动，API集成覆盖质量信息隔离；未改前端、未重跑build/浏览器。既有结构/降级/多样性验收见各专项文档，不需重复完整验收。
- 全部LOCAL_ONLY/合成工程验证，0次真实云调用。未执行真实模型质量、生产断网/Windows凭据实机；未修改预览/业务库/API容器，未跑真实后端浏览器研究E2E。VIB-48未完成查询候选扩展与真实依赖，不标Done。

## 3 既有知识与模型约束

- initial_corpus.json仍只有29条非方剂C01，C02完整方剂摘录未冻结，真实语料未APPROVE。VIB-46完整方剂/逐字段/术语裁定工程已实现，真实方剂与专家核对待补；古病案待VIB-47，真实Golden Set/相关性阈值待VIB-68。
- local-exact-terms/v4保留v2/v3冻结批次；候选/裁定/字段来源不可变追加DRAFT，Evidence先审、知识后审、快照/激活复验。历史元数据冻结，未知保持null，不补造规范剂量或跨来源真值。
- 结构/关系只用自身冻结词形/字段/精确证据，从范围内概念出发，不模糊归并、不跨身份同义词传播、不多跳。历史引用不进入新快照，不以最新Evidence替代旧关联。显式空Scope为空且无模型调用；None按索引冻结来源过滤。
- 默认未授权查询纯本地且不读凭据；mode=local强制本地。服务模型故障降级需allow_model_fallback=True，研究和benchmark严格失败；模型/端点/KV/Index门禁、来源越界和DB/审计故障不可降级绕过。
- 用户曾问8B升级，未指定模型/预算授权，未切配置或付费调用；更强模型也需VIB-68资格验证。

## 4 下一条具体操作

- 本轮质量分流阶段验证、工程提交和Linear简短同步完成；不重跑已通过的合成方剂/多样性/质量分流专项。下一会话先核对git状态与C02是否新增冻结，再直接承接下项。
- 下一项VIB-48：繁简/异体/历史别名查询候选扩展完整验收。先读backlog的VIB-48、retrieval.py::tokenize/search_published、retrieval_structured.py::structured_candidates和knowledge_terms.py的自身裁定词形入口，明确候选扩展与身份/Scope隔离。
- 以明确词形映射及已裁定自身词形生成候选，不凭字符串相似归并、不跨对象传播别名、不补造医学等价；保留原query和精确KV/Index/来源修订。覆盖歧义/未知、历史版本、范围外词形、本地/降级/研究/benchmark；必要时为规则版本写验收边界。
- 若C02负责人冻结准确摘录/来源/权利/哈希/专家安排，按实际内容承接VIB-46；否则推进不依赖真实语料的VIB-48。

## 5 安全运行与复现

- Windows原生Python/uv/Alembic曾触发应用程序错误弹窗，禁止换入口或提权重试。只用既有Linux容器tcm-vib54-py；tcm-handoff-test为独立数据库容器。Docker管道需正常权限。
- 复现：docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib48_quality_recheck_test --full-suite。
- 脚本只接受tcm_*_test、LOCAL_ONLY，不打印凭据/不删旧库；有候选/字段/裁定数据不降级，迁移往返用新库。backend只读挂载，pytest禁缓存，Ruff --no-cache --ignore EXE002。
- 不启动/修改docker-api-1或tcm_preview_shanghanlun；预览库未升0024/0025/0026，API仍unhealthy，本轮未修复。tcm-vib63-forward仍停止；skip不等于通过。
