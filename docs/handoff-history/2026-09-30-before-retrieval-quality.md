# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 codex/evidence-audit，工程基线 `ffc70b7`（VIB-48来源/证据多样性），启动 `25047fc`（上轮交接），此前代码 `2c0d282`（本地检索/降级/UI）。本轮接续文档另行提交，最新HEAD用git log核对。
- 启动工作区干净。代码、测试、README已提交 `ffc70b7`；backlog、需求矩阵、多样性验收、本交接与旧首页归档随文档提交，提交后git status应干净。全部为本轮范围，未改他人文件。
- 用户要求每轮完成可验证阶段后默认提交本地 Git；只提交本轮范围。未推送或部署，推送/发布仍按会话授权。
- 旧首页归档：docs/handoff-history/2026-09-30-before-retrieval-diversity.md，启动不读历史。
- 范围 V1 知识底座与理论研究。VIB-63/49/60/61 本地及 Linear Done；VIB-46/48 In Progress；VIB-45 本地完成、旧详细验收外发待授权；VIB-58 Windows 密钥实机待安全环境。
- 本轮简短验收已同步Linear评论 `3d9f12aa-a2a6-48f4-8909-35e64da67d3b`，VIB-48仍In Progress，依赖VIB-46/42。详细工程外发上轮曾被自动审批拒绝，本轮只同步简短结论，具体证据保留本地。

## 2 VIB-48 最新实现与实际验证

- 新 source-context/v1 对冻结KV/Index/Scope内精确修订排序：RRF候选截取前和最终返回前均应用多样性。credit / ((1 + 同来源已选数) * (1 + 同源修订段落交集比例累加))；首位保留最高相关候选，来源与上下文分别软惩罚。
- 重叠只依据同SourceRevision精确segment refs，比例分母取两条引用中较小段落数；不模糊匹配文字、不跨版本推断同义/等价。相同EvidenceRevision多通道去重，保留全部通道；不同Evidence身份引用相同段落只降低优先级，不合并或删身份，单来源可填满结果。
- 通道各至多300条，候选联合先批量读provenance；多样性候选池仍至多100条，再trace校验。不能恢复已被通道上限裁掉的结果。无校准的质量/无结果阈值；真实语义效果留给VIB-68。
- 正常重排保留供应商原分数排序、以1/(60+rank)正数credit施加多样性，负分不反转惩罚；失败重排用RRF，本地/向量失败降级同规则。原retrieval_score/rerank_score保留。
- API新增diversity说明：policy/relevance_rank/source_occurrence/context_overlap/selection_score，不含内部UUID。原query、精确引用、旧/search数组外形保留；UI尚未增加专门的排序说明展示。
- 研究EvidenceRetrievalEvent继续记实际rank/channels/精确修订，研究审计事件保存排名说明；benchmark保存策略版本/逐题精确排名，原六项指标只做数值汇总。无新迁移或依赖。
- 首库 tcm_vib48_diversity_verified_test 完整后端 **212 passed、1 failed、0 skipped**（396.21秒）。新单来源用例发现原加法惩罚稀释上下文重复，已改为两项相乘；失败用例与3条算法回归 **4 passed、0 skipped**（6.86秒）。不以首轮失败宣告完成。
- 最终新库 tcm_vib48_diversity_final_test 完整后端 **213 passed、0 skipped**（266.16秒），新增13条。两库均完成空库升0026、0026→0023→0026往返、两次alembic check无差异，旧合成概念/方剂内容/状态/null/版本0保留，测试库保留。
- 完整Ruff与git diff检查通过；前端TypeScript/Vite build通过。未改前端逻辑，未重跑浏览器，真实API新增说明在后端集成验证。
- 验收详情 docs/VIB48_DIVERSITY_ACCEPTANCE.md；旧结构/关系与降级证据见两份原专项验收。VIB-48仍未完成QualityIssue和查询候选扩展，不标Done。
- 全部LOCAL_ONLY/合成工程验证，0次真实云调用。未执行真实模型质量/训练/微调、生产断网/Windows凭据实机；未修改预览/业务库/API容器，未跑真实后端浏览器研究E2E。

## 3 既有知识与模型约束

- 本轮核对initial_corpus.json仍只有29条非方剂C01，C02完整方剂摘录未冻结，真实语料未APPROVE。VIB-46完整方剂/逐字段/术语裁定工程已实现，真实方剂与专家核对待补；古病案待VIB-47，真实Golden Set待VIB-68。
- local-exact-terms/v4保留v2/v3冻结批次；候选/裁定/字段来源不可变追加DRAFT，Evidence先审、知识后审、快照/激活复验。历史元数据冻结，未知保持null，不补造规范剂量或跨来源真值。
- 结构/关系只用自身冻结词形/字段/精确证据，从范围内概念出发，不模糊归并、不跨身份同义词传播、不多跳。历史引用不进入新快照，不以最新Evidence替代旧关联。显式空Scope为空且无模型调用；None按索引冻结来源过滤。
- 默认未授权查询纯本地且不读凭据；mode=local强制本地。服务模型故障降级需allow_model_fallback=True，研究和benchmark严格失败；模型/端点/KV/Index门禁、来源越界和DB/审计故障不可降级绕过。
- 用户曾问8B升级，未指定模型/预算授权，未切配置或付费调用；更强模型也需VIB-68资格验证。

## 4 下一条具体操作

- 本轮多样性阶段验证、工程提交和Linear简短同步完成；不重跑已通过的合成方剂/多样性专项。下一会话先核对git状态与C02是否新增冻结，再直接承接下项。
- 下一项：VIB-48未发布高相关片段转QualityIssue。先读backlog的VIB-48、retrieval.py候选查询和knowledge_publish.py::open_quality_issue，设计只在冻结Scope内生成可定位的质量问题，不把未发布内容加入证据结果。
- 覆盖未审Evidence/知识候选、旧版已发布与新版未审、范围越界、重复查询幂等、无命中、本地/降级/研究路径；保留QualityIssue门禁与人工流程，不自动Approve或编造高相关真值。
- 后续补繁简/异体/历史别名查询候选扩展完整验收。若C02负责人冻结准确摘录/来源/权利/哈希/专家安排，按实际内容承接VIB-46；否则推进不依赖真实语料的VIB-48。

## 5 安全运行与复现

- Windows原生Python/uv/Alembic曾触发应用程序错误弹窗，禁止换入口或提权重试。只用既有Linux容器tcm-vib54-py；tcm-handoff-test为独立数据库容器。Docker管道需正常权限。
- 复现：docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib48_diversity_recheck_test --full-suite。
- 脚本只接受tcm_*_test、LOCAL_ONLY，不打印凭据/不删旧库；有候选/字段/裁定数据不降级，迁移往返用新库。backend只读挂载，pytest禁缓存，Ruff --no-cache --ignore EXE002。
- 不启动/修改docker-api-1或tcm_preview_shanghanlun；预览库未升0024/0025/0026，API仍unhealthy，本轮未修复。tcm-vib63-forward仍停止；skip不等于通过。
