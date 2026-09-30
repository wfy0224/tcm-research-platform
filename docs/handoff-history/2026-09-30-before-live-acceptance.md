# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 codex/evidence-audit，工程基线 `e7b0af0`（VIB-48查询候选扩展），启动 HEAD `442bc52`。本轮接续文档另行提交，最新 HEAD 用 git log 核对。
- 启动工作区干净。代码/测试/README已提交 `e7b0af0`，本交接/backlog/需求矩阵/验收/归档随文档提交；提交后工作区应干净。全部本轮范围，没有他人改动。
- 每轮完成可验证阶段后默认提交本地 Git，只提交本轮范围；未推送或部署。
- 替代首页归档 docs/handoff-history/2026-09-30-before-query-expansion.md；启动不读历史。
- V1 知识底座与理论研究。VIB-63/49/60/61 Done；VIB-46/48 In Progress；VIB-45 本地完成、旧详细验收外发待授权；VIB-58 Windows 密钥实机待安全环境。
- 本轮 Linear 简短验收已同步评论 `76be83b4-99d8-4a8a-b8c0-c32860d87d68`，状态仍 In Progress；详细工程证据留本地，早先外发审批限制不扩大。
- 用户追问遗留验收为何未继续：上一轮直接转VIB-47的顺序已纠正。先补完VIB-46/48可执行验收，不能把全部真实环境验收笼统标成外部阻塞。此次只调整接续记录，未新增运行验收；此前工程/测试结果不变，旧首页归档docs/handoff-history/2026-09-30-before-acceptance-priority.md。

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

- 优先收尾VIB-46/48遗留验收，不直接开始VIB-47。按两份专项验收的未完成项建立逐项清单：已通过/现在可运行/真实阻塞；每个阻塞写具体缺失输入和解除操作，不用“真实环境待补”笼统带过。
- 第一条操作：读取backend/scripts/check_knowledge_api_live.py及既有真实后端隔离验收入口，核对当前容器可用性、独立测试库/模型配置与会话中已有授权；先实施不需付费或Windows故障运行时的真实后端API/本地检索及断网降级验收。网络隔离只作用于专用验收进程/容器，不断开用户主机或改业务/预览库。
- C02真实方剂逐字段与术语验收：核对是否已有准确摘录/来源/权利/哈希与专家安排；缺什么列什么，准备可审查验收材料，不能用合成测试替代专家结论。真实云调用若需要新的费用/外发授权，先完成隔离方案和全部无需该授权的准备，再请求具体授权。
- Windows凭据实机受既有应用错误禁令约束，不重试同运行时；VIB-68专家Golden Set/相关性评测按对应Issue承担。只有遗留可执行验收已闭环、其余阻塞明确后，才承接VIB-47古病案兼容对象。

## 5 增量开发与安全验证

- 用户本轮要求剔除冗余耗时：启动仅当前交接/Git增量/对应Issue；不重新盘点全项目或读历史归档。实现后先验证新行为，跨核心链路阶段收尾仅一次完整后端回归；失败只复验相关范围，新的修正确有必要时再完整验证。
- 无schema/model/migration变更不重复已通过的迁移往返/旧数据探针；无前端变更不重复已通过的build/模拟浏览器。尚未执行的真实后端E2E/环境验收不属于冗余，仍须按缺口完成。通过后直接记录/同步/提交，不重复相同检查。
- Windows原生Python/uv/Alembic曾触发应用程序错误弹窗，禁止换入口或提权重试；只用既有Linux容器tcm-vib54-py与独立DB容器tcm-handoff-test，Docker需正常管道权限。
- Docker验证设置PYTHONPATH=/workspace/backend/src、PYTHONDONTWRITEBYTECODE=1、工作目录/workspace/backend、TCM_OUTBOUND_MODE=LOCAL_ONLY。从容器环境解析数据库URL后只把database切到命名的tcm_*_test，不打印凭据；pytest -q -p no:cacheprovider tests；Ruff --no-cache --ignore EXE002。
- 本轮没有改验证脚本；现有verify_knowledge_extraction.py默认含旧数据/迁移往返，仅变更涉及这些范围时再用。新库只upgrade head是测试前提，不是重复迁移验收。
- 不启动/修改docker-api-1或tcm_preview_shanghanlun；预览库未升0024/0025/0026，API仍unhealthy，tcm-vib63-forward仍停止。
