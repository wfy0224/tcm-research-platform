# V1 需求追踪矩阵（实施中）

本表记录 VIB-59 API 基础合约、VIB-49 知识版本校订与回退、VIB-60 知识 API、VIB-61 研究 API，以及已验收并同步 Linear Done 的 VIB-63 研究工作区。VIB-72 将补齐 Stage 1A/1B 的全部 AC、设计差异和最终验收证据。

| 需求/设计 | Issue | 实现入口 | 验证 | 边界 |
| --- | --- | --- | --- | --- |
| AC-1A-01、需求 3.2、LLD 附录 C：初始语料、来源与 OCR 决策 | VIB-45 | `fixtures/initial_corpus.json`、`parsing.py`、`VIB45_INITIAL_CORPUS_ACCEPTANCE.md` | 用户确认文本首批及负责人“测试人员”；29条真实原文导入、逐条溯源及未审核草稿排除；纯无文字/混合 PDF 无分段/证据、不进入快照且保留原件；独立库专项 20 passed、0 skipped，Ruff 与 diff 检查通过 | OCR 延后；TXT 页1为逻辑页；专家复核未完成；方剂/古病案待扩充，不代表 VIB-46/47/68 验收；本地完成，Linear 待同步 |
| LLD 5/6：本机启动密钥、一次性交换、HttpOnly 会话、精确 Origin、CSRF | VIB-59 | `local_auth.py`、`main.py`、`0019_local_session_api.py` | `test_local_api_integration.py::test_one_use_bootstrap_cookie_csrf_origin_and_revocation` | Desktop Main 注入密钥由 VIB-70 接线；无密钥时返回 503 |
| AC-1A-02/04、需求 3.2、LLD 4–5：知识候选、术语与方剂字段 | VIB-46 | `knowledge_extraction.py`、`knowledge_formula_extraction.py`、`knowledge_formula_provenance.py`、`knowledge_terms.py`、`0024/0025/0026`、`knowledge_publish.py`、`cli.py`；`VIB46_KNOWLEDGE_CANDIDATES_ACCEPTANCE.md` | 实际29条最外层候选定位/冻结来源且0方剂；逐字段/药味精确引用、规范依据、审核/快照/激活门禁；同原词多类型、范围化人工裁定/历史同义词及精确对照、未知保留、冻结/替换谱系；v4 合成完整方剂规则、药味计数/条件拒绝、跨段溯源、同事务回滚/并发幂等/旧v3保留/跨章节隔离，新增24条规则+7条集成；完整后端167 passed、0 skipped，0026往返/旧数据保留/模型检查/Ruff/diff通过 | 语义/模型质量未评测，实际术语专家核对仍待补；真实 C02 完整方剂摘录/专项审核未完成；合成规则通过不等于真实方剂验收，旧版0已审核方剂保持原整段溯源；本地及Linear In Progress |
| LLD 5/6：actor 能力和 API/DB 引用边界 | VIB-59 | `api_contract.py::Actor`、`resolve_public_id`、`enqueue_actor_job` | `test_local_api_integration.py::test_actor_job_public_reference_idempotency_and_preconditions` | 业务写 API 由 VIB-60/61 使用这些服务入口 |
| LLD 12.1/12.4：严格 DTO、公开编号、稳定错误 | VIB-59 | `main.py`、`api_contract.py` | 会话、任务、检索接口集成断言；`test_knowledge_publish_integration.py` 验证检索不返回内部修订 UUID | CLI/Agent 内部仍使用精确 UUID；浏览器检索只展示公开编号和修订号 |
| LLD 12.1/12.4：幂等、ETag/If-Match、长任务 202 | VIB-59 | `api_contract.py`、`main.py` 会话撤销及 Job 查询 | `test_local_api_integration.py` 验证幂等冲突、412/428、202 与 Location | 来源/研究长任务路由由 VIB-60/61 接入，不能将合约助手当作端到端业务验收 |
| AC-1A-06、LLD 14.3：已发布对象追加修订、版本比较与受控切换 | VIB-49 | `knowledge_publish.py`、`knowledge_service.py`、`0021_knowledge_supersession.py`、`0022_reference_manifest.py` | `test_knowledge_publish_integration.py` 验证修订谱系、旧引用影响、双索引门禁、失败不切换、旧任务固定 KV/Index；完整后端 61 passed、0 skipped | 历史引用专用清单不进入当前检索索引；旧 KV 可切回 |
| AC-1A-06、LLD 14.4：发布快速回退快照 | VIB-49 | `release_snapshot.py`、`0023_release_snapshot.py`、`activate-knowledge`/`restore-release-snapshot` CLI | 专项用例验证不可变 CAS 工件、哈希和指针校验、工件缺失拒绝恢复；0023 迁移往返、`alembic check`、Ruff、预览健康通过 | 只覆盖原数据库和索引仍可用的本机快速回退；完整 Portable Backup/灾难恢复由 VIB-66 验收 |
| AC-1A-01/06/08、LLD 12.2：来源、知识、证据与版本质量 API | VIB-60 | `knowledge_api.py`、`knowledge_worker.py`、`api_contract.py`、`check_knowledge_api_live.py` | `test_knowledge_api_integration.py` 验证导入→分段→审核→发布 Job、质量阻断、冲突、故障重试及旧活动版本保留；隔离库完整后端 62 passed、0 skipped；真实硅基流动发布与检索 3 次调用均完成 | 单条公版原文的真实冒烟只证明链路，不计作 VIB-68 模型资格或生产部署 |
| AC-1B-07/08、LLD 12.2/12.3：研究控制、完整过程详情与 SSE | VIB-61 | `research_api.py`、`research_views.py`、`research_service.py`、`stop_service.py` | `test_research_integration.py` 验证 API→Worker→辩论/报告、暂停恢复与旧幂等键重放（含首次空操作）、创建态取消、人工审核和 SSE 快照/游标；隔离库最终完整后端 62 passed、0 skipped，Ruff 与 diff 检查通过 | REST 为事实源；SSE 仅提供任务事件与公开任务编号，客户端重连先读取快照；真实模型质量仍由 VIB-68 验收 |
| AC-1B-07/08、LLD 13.5/13.6：研究工作区与过程时间线 | VIB-63 | `ResearchWorkspace.tsx`、`check_research_e2e.mjs`、`serve_research_e2e.py`、`style.css` | 2026-09-30：Edge→真实隔离 API/研究 Worker→人工审核→恢复→Markdown/DOCX 实下载、六 Tab、Round/Claim、allowed_actions、真实 SSE、刷新恢复及 375px 布局均通过；模拟浏览器回归通过，独立库后端 2 passed、0 skipped；[验收证据](VIB63_RESEARCH_WORKSPACE_ACCEPTANCE.md) | 使用假模型，0 次真实云调用；桌面密钥交接由 VIB-70 完成，真实模型质量由 VIB-68 验收；2026-09-30 已同步 Linear Done 和简短验收结论，完整内部证据保留本地 |

VIB-59 隔离数据库验证：`0018→0019→0018→0019`、`alembic check` 无差异；后端 51 passed、0 skipped；Ruff、前端构建及 diff 检查通过。真实云模型和正式桌面壳未运行。
