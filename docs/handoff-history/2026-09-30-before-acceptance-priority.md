# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 codex/evidence-audit，工程基线 `e7b0af0`（VIB-48查询候选扩展），启动 HEAD `442bc52`。本轮接续文档另行提交，最新 HEAD 用 git log 核对。
- 启动工作区干净。代码/测试/README已提交 `e7b0af0`，本交接/backlog/需求矩阵/验收/归档随文档提交；提交后工作区应干净。全部本轮范围，没有他人改动。
- 每轮完成可验证阶段后默认提交本地 Git，只提交本轮范围；未推送或部署。
- 替代首页归档 docs/handoff-history/2026-09-30-before-query-expansion.md；启动不读历史。
- V1 知识底座与理论研究。VIB-63/49/60/61 Done；VIB-46/48 In Progress；VIB-45 本地完成、旧详细验收外发待授权；VIB-58 Windows 密钥实机待安全环境。
- 本轮 Linear 简短验收已同步评论 `76be83b4-99d8-4a8a-b8c0-c32860d87d68`，状态仍 In Progress；详细工程证据留本地，早先外发审批限制不扩大。

## 2 本阶段成果与实际验证

- VIB-48 查询候选扩展：retrieval_query.py 的 explicit-orthography/v1 使用有限可审查字符组，支持表内繁简、混合字形与羣/群、峯/峰。发/發/髮、后/後、脏/臟/髒、术/朮/術、参/參、范/範等歧义映射不加入，未知保持原样。
- Exact 使用 NFKC/小写字形键；FTS 字符/二元词内 OR、词间 AND，去重 token，二元词至多四个字形，不生成整句指数级组合。tokenizer、旧 FTS、向量索引和原文不重写，无迁移或新依赖。
- Structured/Relation 只匹配冻结版本/Scope 内已审核对象自身词形与方剂字段；历史裁定只用自身锚点，不跨身份传播比较对象别名，不多跳，不替换历史 Evidence。原 query/NFKC/策略保留；研究审计和 benchmark 落库策略与实际排名。
- 服务本地/显式故障降级共用扩展，研究/benchmark 默认严格失败。模型只接收既有 NFKC query 与已发布证据，不外发扩展表/未发布候选。未发布质量扫描仍按 unpublished-exact/v1 的原查询字面规则；扩展命中不自动新增问题，不声称医学等价或已校准相关性。
- 首专项库 tcm_vib48_query_target_test：4 passed、5 failed、0 skipped（15.46秒）；四处测试预期误解邻段 chunk/HTTP全来源/任务去空白，另较/較映射遗漏。修正后同库集成6 passed、0 skipped（16.92秒），边界单测另2 passed（0.88秒），方剂扩展专项首轮通过。
- 全新 tcm_vib48_query_final_test 完整后端 **241 passed、0 failed、0 skipped**（366.14秒，新增8条测试）；本轮仅空库升级head建立前提，未重复迁移往返/旧数据探针（无schema/model变更）。完整Ruff、diff/暂存diff通过；测试库保留。
- 验收 docs/VIB48_QUERY_EXPANSION_ACCEPTANCE.md；既有结构/降级/多样性/质量分流验收见相应专项文档。无前端或 HTTP DTO 变更，未重跑 build/浏览器。
- 全程 LOCAL_ONLY/合成工程数据，0次真实云调用；未修改预览/业务库/API容器。VIB-48查询扩展工程阶段完成，仍受VIB-46真实C02/专家依赖与真实环境验收约束，不标Done。

## 3 既有知识与模型约束

- initial_corpus.json仍只有29条非方剂C01；C02完整方剂摘录/权利/来源/哈希/专家安排未冻结，真实语料未APPROVE。VIB-46工程已补齐，真实方剂与专家核对待补；古病案待VIB-47，真实Golden Set/相关性阈值待VIB-68。
- local-exact-terms/v4保留v2/v3冻结批次；候选/裁定/字段来源不可变追加DRAFT，Evidence先审、知识后审、快照/激活复验。未知保持null，不补造规范剂量或跨来源真值。
- 每个通道只返回冻结KV/Index/Scope内已审核并已索引的精确EvidenceRevision。None用冻结来源，显式空Scope无结果/模型调用，历史引用不授权替换新版。
- 默认未授权查询纯本地且不读凭据；mode=local强制本地。服务故障降级需allow_model_fallback=True，研究和benchmark严格失败；模型/端点/KV/Index/来源门禁及DB/审计故障不可降级绕过。
- 用户曾问8B升级，未指定模型/预算授权，未切配置或付费调用；更强模型仍需VIB-68资格验证。

## 4 下一条具体操作

- 本阶段回归/工程提交/Linear简短同步完成，不重复已验收的VIB-48工程专项。若C02已由负责人冻结，直接承接VIB-46真实完整方剂/逐字段/专家验收；否则推进不依赖它的VIB-47古病案兼容对象工程阶段。
- VIB-47：只读 backlog 该节及直接依赖，回读 Linear 状态；需要领域细节再读设计中的 LLD 18.1/需求2.5。先查 models.py、source_import.py、knowledge_service.py、knowledge_api.py 的精确来源/段落/Evidence入口，再实现 CaseRecord 双表示映射、同古病案幂等导入和追加修订影响查询；不开放现代诊疗界面/推理。
- 真实古病案来源未冻结时先用明确标注的合成病案验工程引用/并发/修订门禁，不补造真实患者或医学真值。

## 5 增量开发与安全验证

- 用户本轮要求剔除冗余耗时：启动仅当前交接/Git增量/对应Issue；不重新盘点全项目或读历史归档。实现后先验证新行为，跨核心链路阶段收尾仅一次完整后端回归；失败只复验相关范围，新的修正确有必要时再完整验证。
- 无 schema/model/migration 变更不重复迁移往返/旧数据探针；无前端变更不重复 build/浏览器。通过后直接记录/同步/提交，不再重复相同检查。测试运行时完成独立文档工作，避免空等。
- Windows原生Python/uv/Alembic曾触发应用程序错误弹窗，禁止换入口或提权重试；只用既有Linux容器tcm-vib54-py与独立DB容器tcm-handoff-test，Docker需正常管道权限。
- Docker验证设置PYTHONPATH=/workspace/backend/src、PYTHONDONTWRITEBYTECODE=1、工作目录/workspace/backend、TCM_OUTBOUND_MODE=LOCAL_ONLY。从容器环境解析数据库URL后只把database切到命名的tcm_*_test，不打印凭据；pytest -q -p no:cacheprovider tests；Ruff --no-cache --ignore EXE002。
- 本轮没有改验证脚本；现有verify_knowledge_extraction.py默认含旧数据/迁移往返，仅变更涉及这些范围时再用。新库只upgrade head是测试前提，不是重复迁移验收。
- 不启动/修改docker-api-1或tcm_preview_shanghanlun；预览库未升0024/0025/0026，API仍unhealthy，tcm-vib63-forward仍停止。
