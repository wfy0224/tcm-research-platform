# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 codex/evidence-audit，工程基线 `2c0d282`（VIB-48 本地检索/模型降级/UI）；此前 `71d15a3`（交接）、`c9bc6f6`（结构/关系检索）、`86c6299`（VIB-45/46）。本轮接续文档另行提交，最新 HEAD 用 git log 核对。未推送或部署。
- 本轮代码、测试、前端与 README 已提交 `2c0d282`；backlog、需求矩阵、专项验收、本交接与旧首页归档随文档提交。文档提交后工作区应干净，用 git status --short 核对。
- 用户明确要求每轮完成可验证阶段后默认提交到本地 Git；只提交已识别的本轮范围，保留他人改动。推送/发布仍按会话授权。
- 旧首页归档：docs/handoff-history/2026-09-30-before-local-retrieval-fallback.md。启动不读历史。
- 范围 V1 知识底座与理论研究。VIB-63/49/60/61 本地及 Linear Done；VIB-46/48 In Progress；VIB-45 本地完成、旧详细验收外发待授权；VIB-58 Windows 密钥实机待安全环境。
- VIB-48 本轮简短工程验收结论已同步 Linear，评论 `a03d60ad-4e18-4ab9-b2e1-7bb77c405602`。完整评论因包含内部提交/测试/实现细节被自动审批拒绝；不重试详细外发，具体证据保留本地。

## 2 VIB-48 最新实现与实际验证

- search_published 的 embedder=None 为明确本地 Exact/FTS/Structured/Relation；默认 API 未授权查询外发时不创建云客户端或读取凭据。mode=local 即使有外发同意也强制本地；原 query 保留。
- API 授权尝试云模型后，缺密钥/凭据不可用/配置无效回退本地；外发策略禁止不调用模型。向量故障回退本地且不请求重排；重排故障保留已完成向量通道按 RRF 排序，失败通道不记完成、rerank_score=null。
- model_errors.py 区分可降级模型错误与数据库/审计故障；来源越界、冻结模型/端点不一致、KV/Index/双索引未 READY 仍拒绝。服务模型故障降级显式 allow_model_fallback=True；研究和 benchmark 原路径保持严格失败。
- 新 GET /api/v1/retrieval/query 返回 query_text/normalized_query/mode/reasons/channels/results；空结果也有状态，错误详情不进入降级原因。旧 /search 数组合约保留。
- 前端支持无同意勾选检索，显示模式/原因/通道和结构/关系中文名，保留输入空白；证据详情读取本地响应，后续 API 错误清除旧状态。
- 最终新独立库 `tcm_vib48_local_fallback_verified_test` 完整后端 **200 passed、0 skipped**（173.89秒）；比起点177条新增23条。首库 `tcm_vib48_local_fallback_initial_test` **192 passed、0 skipped**（223.35秒），随后增加8条传输/正常通道/重排策略用例，两轮均无失败。
- 两个新库均完成空库升0026、0026→0023→0026往返、两次 alembic check 无差异，旧合成概念/方剂内容/状态/null/版本0保留。无新迁移或依赖，全部测试库保留。
- 完整后端/测试/迁移/脚本 Ruff 与 git diff 检查通过。前端 TypeScript/Vite build、npm run check:research-browser 通过；浏览器为隔离模拟 API/headless Edge，覆盖本地无同意查询→详情→缺密钥/重排失败→空结果/发布错误、既有研究回归和375px。首次沙箱 CDP 连接关闭，正常权限重跑通过，无应用程序错误弹窗。
- 详情 docs/VIB48_LOCAL_RETRIEVAL_ACCEPTANCE.md；结构/关系原证明在 docs/VIB48_STRUCTURED_RETRIEVAL_ACCEPTANCE.md。VIB-48 仍未完成多样性、未发布高相关内容 QualityIssue、查询候选扩展完整验收，不标 Done。
- 全部 LOCAL_ONLY/合成工程验证。未执行真实供应商/生产断网/Windows凭据实机验收；没有模型质量评测、训练或微调，0 次真实云调用。未修改预览/业务库/API容器，未跑真实后端浏览器研究E2E。

## 3 既有知识与模型约束

- C02 完整方剂摘录仍未冻结；backend/fixtures/initial_corpus.json 只有29条非方剂 C01，真实语料未 APPROVE。VIB-46 完整方剂/逐字段/术语裁定工程已实现，真实方剂与专家核对仍待补；古病案待VIB-47，真实Golden Set待VIB-68。
- local-exact-terms/v4 保留v2/v3冻结批次；候选、裁定和字段来源不可变、追加DRAFT，Evidence先审、知识后审，快照/激活复验。来源历史元数据冻结，未知保持null，不补造规范剂量或跨来源真值。
- 结构/关系通道只用自身冻结词形/字段/精确证据；关系从范围内概念出发，无模糊归并、跨身份同义词传播或多跳遍历；历史引用不进入新快照，不以最新Evidence替代旧关联。显式空Scope为空且无模型调用，None也按索引冻结source set过滤。
- 用户曾问8B升级；已建议同一专家样本对照。没有具体模型/预算授权，未切配置或发起付费调用；更强模型也需VIB-68资格验证。

## 4 下一条具体操作

- 先核对 initial_corpus.json 是否有负责人“测试人员”冻结的C02及来源/权利/哈希/专家安排；有则按实际排版承接VIB-46，无则直接继续VIB-48，不重跑合成方剂或编造真实真值。
- **下一项：VIB-48 来源/证据多样性**。先读 docs/DEVELOPMENT_BACKLOG.md 的VIB-48小节和 retrieval.py 的RRF候选/最终排序、retrieval_structured.py；在冻结Scope内设计可解释的去重/多样性，避免同一来源或相近上下文占满候选。
- 先用合成独立库覆盖多来源、单来源、重复上下文、同证据多通道、旧版本、空Scope和本地/降级模式；返回仍为Published精确修订，不能为多样性扩大来源或替换历史Evidence。再接研究池记录/benchmark，仅跑有必要的回归。
- 后续补未发布高相关内容转QualityIssue及查询候选扩展专项；未发布片段仅进入质量流程、不进入证据结果。全部验收前VIB-48不标Done，VIB-46依赖保留。
- 完成可验证阶段后提交本轮代码与接续文档；详细Linear外发若仍被拒绝只同步安全简短结论，保留本地证据。

## 5 安全运行与复现

- Windows原生Python/uv/Alembic曾触发应用程序错误弹窗，禁止换入口或提权重试。只用既有Linux容器tcm-vib54-py；tcm-handoff-test为独立数据库容器。Docker管道需正常权限。
- 复现：docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib48_local_fallback_recheck_test --full-suite。
- 脚本只接受tcm_*_test、LOCAL_ONLY，不打印凭据/不删除旧库；有候选/字段/裁定数据不降级，迁移往返用新库。backend只读挂载，pytest禁缓存，Ruff --no-cache --ignore EXE002。
- 不启动/修改docker-api-1或tcm_preview_shanghanlun；预览库未升0024/0025/0026，API仍unhealthy，本轮未修复。tcm-vib63-forward仍停止；skip不等于通过。
