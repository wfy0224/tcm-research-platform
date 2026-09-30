# VIB-48 结构与关系检索工程验收

日期：2026-09-30。起点：`e852c48`，分支 `codex/evidence-audit`。

## 本轮交付

- `retrieval_structured.py` 提供 `structured` 和 `relation` 候选通道，接入 `search_published` 的 RRF 融合。研究任务复用原检索入口，新增通道写入 EvidenceRetrievalEvent。
- 概念、关系、关系两个端点和方剂修订必须属于指定 KnowledgeVersion，且为 REVIEWED；每条候选证据必须同时在该版本的 EvidenceRevision 集合、指定 IndexBuild 和来源 Scope 内。
- 概念只匹配自身已审核词形；词形时代/流派须与概念一致。NFKC/大小写规范化用于匹配，同时保留服务调用传入的原 query。无繁简推定、模糊归并、跨身份同义词扩展或多跳图遍历。
- 人工裁定概念仅用 provenance 中自己的 mention anchors 解析证据；对照概念的证据和额外裁定依据不能替代自身锚点。未发布的原候选或新版概念不能参与旧版本检索。
- 关系从来源范围内命中的概念出发，返回关系自己的精确引用；只命中范围外概念时，不返回范围内的关系证据。
- 方剂按冻结修订的原名/药味匹配，版本1仅返回相应 `original_name` 或 `ingredients.N.original_name` 字段所引用的 EvidenceRevision；旧版本0沿已审核 FormulaEvidence 链。身份上的可变当前名称不参与历史修订匹配。
- 历史 KnowledgeVersionReference 不作为检索入口，不将旧关联替换为最新 Evidence 修订。若当前快照已排除旧引用，该对象不给出结构候选；旧版本仍解析旧精确证据。
- 显式 `source_ids=[]` 直接返回空列表且不调用模型。默认来源范围也始终使用索引冻结的 source set，未知范围拒绝。benchmark 显式固定知识版本/索引，完成时仍复核活动指针。

## 验证与复现

- 新增10条合成数据库集成测试：同原词独立身份/来源隔离；晚审核与活动版本切换；旧证据不替代新版；空 Scope 无模型调用；未知 Scope 拒绝；时代词形/NFKC/原 query/SQL 参数化；跨来源关系锚点；方剂逐字段/草稿/繁简不推定；历史同义词自身锚点；研究池记录新通道和固定旧版本。
- 首库 `tcm_vib48_structured_initial_test`：175 passed、1 failed、0 skipped，107.09秒。失败为新方剂夹具缺少服用说明，既有完整方剂抽取规则正确拒绝；补齐夹具，生产方剂规则未修改。首库与所有旧数据保留。
- 最终新库 `tcm_vib48_structured_verified_test`：**177 passed、0 skipped**，115.25秒；比基线167条新增10条。最终代码包含 benchmark 固定版本和研究任务通道用例。
- 新空库升至0026，0026→0023→0026往返，两次 `alembic check` 无差异；合成旧概念/方剂内容、状态、null及版本0保留。全部库和旧失败数据保留。
- 完整后端/测试/迁移/脚本 Ruff 已通过；无新增模型/迁移。测试只使用既有 Linux 容器，禁止 Windows 原生 Python/uv/Alembic 重试。

```powershell
docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib48_structured_recheck_test --full-suite
```

脚本只接受 `tcm_*_test`，固定 LOCAL_ONLY，不打印凭据、不删除旧库。有候选/字段/裁定数据时不降级；迁移往返使用新空库。

## 尚未完成

VIB-48 保持 In Progress：无密钥/断网本地 Exact/FTS/结构查询、UI 明示降级、证据浏览联调、多样性、未发布高相关片段转 QualityIssue、范围内查询候选规范化/裁定扩展的完整验收仍待补。

Linear 已同步 In Progress 和本轮工程证据，评论 `533b394a-dbc2-4924-83ad-70340e6bb71f`。工程提交 `c9bc6f6`；验收及接续文档另行提交，最新 HEAD 以 git log 为准。

C02 仍未冻结，VIB-46 的真实完整方剂/专家核对仍未完成；本轮合成夹具不是正式术语标准、专家真值或真实模型质量评估。无真实云调用、模型切换、付费、推送或部署；未修改预览/业务库或 API 容器，未跑前端和浏览器。正式 Golden Set 与模型资格属于 VIB-68。
