# 中医知识研究与临床推理平台

本仓库按三份设计文档实施第一阶段 A（知识底座）和第一阶段 B（理论研究）。当前代码包含 E0/E1 基础、E2 来源导入、E3 结构化文本分段、E4 可追溯知识草稿、E5 人工校订与发布门禁，以及 E6 全文、向量和混合检索的后端能力：本地 API 与前端健康页、PostgreSQL 迁移、内容寻址文件存储、哈希链审计事件、持久化任务队列、来源解析、文本修订和证据引用。临床病例、处方与疗效功能不属于本阶段。

## 本地开发

需要 Python 3.11+、uv、Node.js 20+、Docker。数据库使用 PostgreSQL；运行时不自动修改表结构。

```powershell
docker compose up -d db
cd backend
uv sync --extra dev
uv run alembic upgrade head
uv run uvicorn tcm_platform.main:app --host 127.0.0.1 --port 8000
```

另开终端运行前端：

```powershell
cd frontend
npm install
npm run dev
```

打开 `http://127.0.0.1:5173`，可检索活动知识版本并查看每条证据的原文、上下文与引用定位。API 健康状态见 `http://127.0.0.1:8000/api/v1/system/health`。默认连接串仅用于本地开发；正式环境通过 `TCM_DATABASE_URL` 和 `TCM_DATA_ROOT` 配置。

### 本地 API 会话与命令合约

当前预览页保留只读的健康检查与已发布知识检索；检索的 HTTP 响应使用来源、证据和段落公开编号，内部修订 UUID 只用于服务和 CLI。任务查询 `GET /api/v1/jobs/{JOB-...}` 需要本地会话，且只接受公开编号。

桌面主进程在启动 API 时生成至少 32 字符的一次性随机密钥，通过 `TCM_BOOTSTRAP_SECRET` 注入进程；前端从主进程取得密钥后，向 `POST /api/v1/local-session/bootstrap` 提交 `{"bootstrap_secret":"..."}`。请求必须携带精确匹配 `TCM_LOCAL_ALLOWED_ORIGINS` 的 `Origin`。成功响应设置 HttpOnly、SameSite=Strict 的会话 Cookie，仅在这次响应体返回 CSRF token。密钥只可兑换一次，默认 5 分钟过期；没有主进程注入密钥时 bootstrap 返回 503。正式 HTTPS 回环部署需设置 `TCM_SECURE_SESSION_COOKIE=true`。桌面主进程接线属于后续 Desktop Supervisor 任务。

业务命令统一校验会话能力、精确 Origin 和 `X-CSRF-Token`；创建类命令要求 `Idempotency-Key`，有版本竞争的更新要求 `If-Match`，长任务返回 202、公开 `job_id` 和 `Location`。错误响应包含 `code`、`category`、`retryable`、`request_id`、`audit_ref` 和 `detail`。当前只开放会话管理与任务查询；来源和研究命令将在对应 API 任务接入这些合约。会话详情 `GET /api/v1/local-session` 返回 ETag；撤销会话 `DELETE /api/v1/local-session` 要求 `If-Match` 与 CSRF token。

测试：`cd backend; uv run pytest`。首次安装依赖需要访问包仓库。

### 真实模型检索预览

自动化回归使用固定输出的假向量模型，以稳定验证排序、版本和引用链；这不代表真实云模型已经通过联调。真实检索需要活动索引的 `embedding_model`、`rerank_model` 与 API 当前模型完全一致。不要将 API 指向自动回归数据库中的假模型索引。

隔离预览库可命名为 `tcm_preview_shanghanlun`：先运行迁移，设置 `TCM_DATABASE_URL` 和 `TCM_OUTBOUND_MODE=CLOUD_ALLOWED`，并把硅基流动密钥存入 OS Keychain，再运行 `python scripts/prepare_shanghanlun_preview.py`。仅在临时开发容器没有 Keychain 时，才显式设置 `TCM_ALLOW_ENV_API_KEYS=1`，并按变量名注入既有 `SILICONFLOW_API_KEY`；不要把密钥写入命令参数、文件或日志。脚本导入[公版《傷寒論》太阳病上篇的 29 条真实原文](backend/fixtures/README.md)，用真实向量模型建索引，再激活知识版本。旧预览索引没有冻结外发策略，脚本会核对固定语料、登记来源授权并重新建索引；这会再次调用云模型，须按当次授权执行。API 使用同一数据库、Keychain 与数据目录，并设置 `TCM_PREVIEW_CORPUS=shanghanlun_taiyang_upper`。`pwsh -NoProfile -File scripts/check_shanghanlun_preview.ps1` 经 5173 代理执行 6 个目标条文查询和截图中的“太阳病”查询；治理后于 2026-09-28 重新运行：7/7 正向检查通过，六个目标条文均在前 2 位；这仍非专家质量评测。无关问题仍可能返回候选，**当前没有经过校准的拒答门槛**。这些工程检查不代替专家审核或大规模检索质量评测。

## 来源导入 E2

当前通过命令行操作；文件导入 API 与知识工作区界面将在本地会话和权限边界完成后开放。以下命令在 `backend` 目录运行：

```powershell
uv run python -m tcm_platform.cli import-source "D:\资料\伤寒论.txt" --title "伤寒论" --source-type CLASSIC --edition "某整理本" --copyright-status AUTHORIZED
uv run python -m tcm_platform.cli parse-next
uv run python -m tcm_platform.cli segment-next
uv run python -m tcm_platform.cli show-import <上一步返回的 import_job_id>
uv run python -m tcm_platform.cli show-segments <来源修订 source_revision_id>
```

导入命令返回 `source_id`、`source_revision_id`、`import_job_id` 和解析任务 ID。同一著作的新版本可在导入命令中加 `--source-id <已有 source_id>`；新版本不会覆盖旧文件。`--request-key` 可用于命令重试去重。Markdown 也可按纯文本导入。解析成功后自动排入分段任务；`segment-next` 生成卷、篇章、节、条、段、句等层级和上下文、校验和，并记录相邻来源修订的增删改移对齐。无文本层 PDF 会保留原文件并标记 `OCR_REQUIRED`；OCR 和研究工作流仍在后续迭代。

## 可追溯知识草稿 E4

`show-segments` 会返回每个 `segment_revision_id`。用精确文本修订建立证据草稿，系统从原文拼接引文并验证连续范围；引文无法由调用方自行填写：

```powershell
uv run python -m tcm_platform.cli create-evidence <segment_revision_id> --strength DIRECT
uv run python -m tcm_platform.cli trace-evidence <evidence_revision_id>
uv run python -m tcm_platform.cli create-mention <segment_revision_id> 0 2 --type HERB
uv run python -m tcm_platform.cli create-concept "桂枝" --type HERB --evidence <evidence_revision_id> --mention <mention_id>
uv run python -m tcm_platform.cli create-herb "桂枝" --evidence <evidence_revision_id>
uv run python -m tcm_platform.cli create-formula "桂枝汤" --evidence <evidence_revision_id> --ingredient "桂枝" --ingredient "芍药"
uv run python -m tcm_platform.cli trace-knowledge formula_revision <formula_revision_id>
```

`create-relation <subject_concept_id> <object_concept_id> --type <关系类型> --assertion <断言> --evidence <evidence_revision_id>` 建立概念关系草稿。概念、关系、药物和方剂都须引用准确的 EvidenceRevision；`trace-knowledge` 可回溯到来源修订、段落修订、原文和定位。草稿对象只有通过人工审核并进入知识版本后才能供检索使用。

## 人工校订与发布门禁 E5

审核会保留每次人工决定；阻断级 QualityIssue 未解决时，不能批准对象或创建知识快照。先审核 EvidenceRevision，再审核引用它的概念、关系、药物或方剂：

```powershell
uv run python -m tcm_platform.cli open-quality-issue evidence_revision <evidence_revision_id> --type INVALID_EVIDENCE_LOCATION --severity BLOCKER --description "待核对原文"
uv run python -m tcm_platform.cli resolve-quality-issue <quality_issue_id> --reviewer expert-1 --note "已核对原文"
uv run python -m tcm_platform.cli review-knowledge evidence_revision <evidence_revision_id> --reviewer expert-1 --decision APPROVE --note "核对通过"
uv run python -m tcm_platform.cli snapshot-knowledge
uv run python -m tcm_platform.cli create-index-build <knowledge_version_id>
```

快照固定精确对象修订，可用 `compare-knowledge <左版本 ID> <右版本 ID>` 比较。`activate-knowledge <knowledge_version_id> <index_build_id>` 只在全文和向量索引均通过验证后，才会原子切换活动知识版本与索引版本。

## 云端模型与混合检索 E6

项目运行时直接调用云端 API，不需要下载或运行本地大模型。默认使用硅基流动的 `BAAI/bge-m3` 向量模型和 `BAAI/bge-reranker-v2-m3` 重排模型。外发默认 `LOCAL_ONLY`；云端使用需设置 `TCM_OUTBOUND_MODE=CLOUD_ALLOWED`，并对每个来源显式标记 `PUBLIC`、记录授权理由。旧来源迁移后均为 `RESTRICTED` 且未授权。使用 `set-model-key siliconflow` 在交互式提示中把密钥存入 OS Keychain；仅隔离开发容器可显式设置 `TCM_ALLOW_ENV_API_KEYS=1` 从环境变量读取。密钥不会写入数据库、日志或 Git。构建索引时，已审核证据文本会发给向量模型；检索时，查询和候选证据文本会发给向量及重排模型。研究任务的 Planner 与 Agent 也会将任务问题及可见证据发送给云端生成模型。来源授权撤销后，新外发调用会被拒绝；已发送的数据无法撤回。

`import-source` 可用 `--data-level PUBLIC --authorize-outbound --outbound-reason <理由>` 记录新来源的授权；已有来源用 `set-source-outbound-policy <source_id> --data-level PUBLIC --authorize --reason <理由> --actor <审核人>` 审核。检索 CLI 需加 `--allow-query-outbound`，研究启动需加 `--allow-question-outbound`；网页检索需要勾选本次检索词外发同意。活动索引和研究任务会冻结模式、来源范围、模型与策略版本；旧索引默认按 `LOCAL_ONLY` 处理，需重新构建才能使用云端模型。传输层拒绝超长输入，限制单进程并发与调用频率，对临时网络/HTTP 错误和生成 JSON 格式错误分别有限重试，连续失败短暂打开熔断器。

```powershell
$env:TCM_MODEL_PROVIDER = "siliconflow"
# Windows 首次配置：uv run python -m tcm_platform.cli set-model-key siliconflow
uv run python -m tcm_platform.cli build-index <index_build_id>
uv run python -m tcm_platform.cli activate-knowledge <knowledge_version_id> <index_build_id>
uv run python -m tcm_platform.cli search-published "太阳病脉浮" --limit 10 --allow-query-outbound
```

检索融合原文匹配、PostgreSQL 全文检索和 pgvector 相似度，再用云端模型重排；结果只来自当前活动知识版本中经人工审核的 EvidenceRevision，包含来源、原文、上下文、定位和精确段落修订。浏览器工作台通过 `GET /api/v1/retrieval/search?query=...` 展示结果与证据详情。索引构建时一次性校验全文行、向量行及维度；失败时不会切换活动版本。

可用人工标注的 Golden Set 对活动索引评测，标签为 `GOLD`、`COUNTER`、`OPTIONAL` 和 `HARD_NEGATIVE`：

```powershell
uv run python -m tcm_platform.cli add-golden-query "太阳病的脉象" --gold <evidence_revision_id> --counter <另一条反证 revision_id>
uv run python -m tcm_platform.cli run-retrieval-benchmark --k 10
```

评测记录 Precision@K、Recall@K、MRR、nDCG、反证召回率和返回证据的可追溯率，并关联知识版本及索引版本。`GOLD` 和 `COUNTER` 计入必须召回的证据；没有反证标注的题目，其反证召回率记为 0，汇总时应结合题目标签理解。可选使用阿里云百炼，但需设置 `TCM_MODEL_PROVIDER=aliyun`、`DASHSCOPE_API_KEY`、`TCM_DASHSCOPE_WORKSPACE_ID`，可通过 `TCM_DASHSCOPE_REGION` 调整地域。

## 研究任务与一轮纠错 E7/E8（进行中）

已建立研究任务、冻结的执行上下文、任务证据池、检索事件、首轮 AgentRun 与 Claim Pool。Planner 的子问题采用严格 JSON 合约；首轮 Classicist、HistoricalScholar、Theorist 的输入会在任何 Claim 生成前分别冻结。Agent 输出若包含不在任务证据池或本次可见集合中的 EvidenceRevision，整份输出拒绝写入。

生成模型默认使用硅基流动云端对话 API。联调模型为 `Qwen/Qwen3-8B`；运行前仍需显式设置 `TCM_RESEARCH_MODEL`。启动任务会将冻结模型路由的研究 Job 放入 PostgreSQL 队列，运行一个 Worker 即可自动完成 Planner、证据检索、首轮独立研究、Claim 审计，以及一轮 Critic→受限再检索→Rebuttal→修订审计：

```powershell
$env:TCM_RESEARCH_MODEL = "Qwen/Qwen3-8B"
uv run python -m tcm_platform.cli create-research-task "太阳病脉象的经典文献依据是什么" --source-id <source_id>
uv run python -m tcm_platform.cli start-research-task <task_id> --allow-question-outbound
uv run python -m tcm_platform.cli run-research-next --task-id <task_id>
```

常驻处理可运行 `uv run python -m tcm_platform.cli run-research-worker`。Worker 使用租约和心跳；业务写入与节点检查点在同一事务中提交，租约过期后根据已提交的任务状态和 AgentRun 恢复。暂停和取消请求在安全点生效；若模型调用正在进行，会等待该调用返回并丢弃其未提交的业务结果。可用 `pause-research-task <task_id>`、`resume-research-task <task_id>`、`cancel-research-task <task_id>` 控制任务。每次生成调用记录模型、请求/输出哈希、耗时、状态和接口返回的 token 用量，不保存原始提示词。停止决策后 Worker 会继续执行 Judge 和结构化报告；只有报告成功落库，任务和 Job 才进入 `COMPLETED`。也可按下列命令逐步调试：

```powershell
uv run python -m tcm_platform.cli plan-research-task <task_id>
uv run python -m tcm_platform.cli retrieve-research-task <task_id>
uv run python -m tcm_platform.cli prepare-first-round <task_id>
uv run python -m tcm_platform.cli run-first-round <task_id>
```

如需使用 DeepSeek 官方 API，可单独设置 `TCM_RESEARCH_PROVIDER=deepseek`、`TCM_RESEARCH_MODEL=deepseek-flash` 和 `DEEPSEEK_API_KEY`；向量和重排仍可保持硅基流动免费模型。DeepSeek 官方 Flash 按 token 计费，选择该路由前应查看[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)。已启动任务的模型路由不会被后续环境默认值改变。

历史研究角色只有在来源具有明确作者、时代、流派、版本或出版年元数据时才生成 Claim；其余情况记录空结果，避免把普通原文误标为历史事实。这是保守的临时门禁，文本中隐含的历史线索可能暂时无法进入历史角色。`Qwen/Qwen3-8B` 的真实联调曾产生超出原文的解释，因此当前 Claim 和自动审计仍是待复核研究材料，不能直接当作可靠结论。

## Claim 审计 E8（进行中）

对已完成首轮的 Claim，可先运行 `audit-claim-mechanical <claim_id>`，再运行 `audit-claim-semantic <claim_id>`。机械审计重新核验任务证据池、Agent 可见集合、冻结知识版本、审核状态和原文溯源；只有机械通过才向任务冻结的云端生成模型提交 Claim 与其已引用证据。语义结果保留 `SUPPORTED`、`PARTIALLY_SUPPORTED`、`UNSUPPORTED`、`CONTRADICTED`、`NOT_VERIFIABLE` 五种状态；每次审计都追加历史，Claim 上的 `audit_status` 仅供查询。当前自动语义判断仍是待审结果。

完成 Claim 审计后，可依次运行 `prepare-critic <task_id>`、`run-critic <agent_run_id>`、`retrieve-evidence-requests <task_id>`。Critic 只看到已完成审计的 Claim 及冻结的任务证据；它提出的 EvidenceRequest 才能触发再检索。检索沿用任务冻结的来源、知识版本、索引与模型路由，并记录每条请求的证据来源事件。

再检索请求全部结束后，手工调试可运行 `prepare-rebuttal <task_id>`、`run-rebuttal <agent_run_id>`、`audit-revised-claims <task_id>`。Rebuttal 对每条 Critique 给出 ACCEPT、PARTIAL_ACCEPT、REJECT 或 REVISE；REVISE 追加一条以旧 Claim 为 parent 的新 Claim，原断言保留。修订 Claim 从 PENDING 重新经过机械与语义审计，审计命令可在失败后重试未完成的修订。Rebuttal 的模型、Prompt 版本、轮次和冻结可见证据记录于 AgentRun；模型调用记录于 ModelInvocation。

不调用云端模型的可回放样例是 `backend/tests/test_research_integration.py::test_judge_report_preserves_citation_chain_and_is_database_immutable`。先在独立 PostgreSQL 测试库迁移到 `0020_outbound_source_policy`，然后按顺序运行 `tests/test_knowledge_publish_integration.py tests/test_research_integration.py`；前者发布样本知识，后者验证完整轮次、Judge、不可变报告、派生导出、节点检查点、暂停取消、租约恢复与非法输出重试。检查 pytest 的 skip 原因，不能把 skip 当作通过。

停止策略在启动研究任务时通过 `start-research-task <task-id> --workflow-config '{"min_debate_rounds":1,"max_debate_rounds":2,"mandatory_human_review":true}'` 冻结。Worker 按已审计 Claim、开放争议和证据缺口计算并保存每轮 StopEvaluation；人工复核时任务进入 `WAITING_HUMAN`，Job 完成并释放租约。用 `list-human-reviews <task-id>` 查看待处理请求，用 `resolve-human-review <request-id> --reviewer <name> --note <reason>` 记录处理结果并重新排队；Worker 从停止判断阶段续跑，不重做首轮。

Judge 只接收已完成审计的 Active Claim、最近 AuditResult、开放 Dispute/EvidenceGap 与冻结知识版本内已审核的精确 EvidenceRevision。输出只能为每条 Claim 选择允许的分类和理由 ID，不能生成新 Claim、改写断言或自由检索。`ResearchSynthesis` 保存 Judge 输入快照，ReportGenerator 仅复制审计文本、争议正反证据与原文定位生成 `StructuredReport`；数据库禁止更新或删除这两类记录。用 `show-structured-report <task_id>` 查看报告 JSON。

研究任务完成后，可用 `queue-report-export <task_id> --format markdown` 或 `--format docx` 排队独立导出，再用 `run-report-export-next --export-id <export_id>` 处理。`show-report-export <export_id>` 显示格式、渲染版本、Job 状态和 Artifact 哈希；`save-report-export <export_id> <output_path>` 将已完成文件保存到本地，不覆盖已有文件。相同报告、格式与渲染版本重复排队返回同一导出；失败可再次排队重试，不改变已完成研究任务。两种文件均列出五类结论、原文证据、争议、限制与研究过程，并提供内部引用跳转及可复制的来源修订和定位文字。当前网页尚无报告页面；研究详情与下载 API 属于后续工作台任务。

验收追踪：AC-1B-03/04 的 Claim 定向质疑、受限再检索、Rebuttal、追加修订与重新审计对应 `backend/src/tcm_platform/debate_service.py`、`research_service.py`、`audit_service.py`、`research_worker.py`、迁移 0012～0014，以及 `backend/tests/test_research_integration.py` 中的研究链集成测试。

## Claim 归并与争议 E9.1

Worker 在首轮审计后和辩论轮次结束时，按断言类型、规范化文本与精确来源版本归并重复 Claim；来源快照的时代和流派一并保留。原 Claim 与修订 Claim 都保留各自 ID，CanonicalClaimMember 指向其最新审计结果。明确的语义审计矛盾和 `CONTRADICTION` 质疑生成 Dispute；审计不充分、无法验证、质疑缺证或再检索无结果生成 EvidenceGap。新审计结果会把已过时的争议和缺口标为 `SUPERSEDED`，保留历史记录。未审计的反面材料不会被标成已证实的反证。命令 `normalize-claims <task_id>` 可幂等重放这些投影。自动归并只处理精确重复断言；跨断言的语义相似和隐含冲突需后续模型或人工提出明确关系，不会靠多数票推断。

## 设计约束

- PostgreSQL 是结构化权威数据源；Blob 文件在数据库登记前先原子写入磁盘。
- 审计事件在业务事务内追加；链头行加锁，避免并发序号冲突。
- 任务租约采用 PostgreSQL 行锁；外部调用不持有数据库事务。
- 当前健康页是只读界面。数据库就绪时显示 `DEGRADED`，直至常驻 Worker 与正式研究工作流完成；不会把基础设施就绪误报为平台 `READY`。

