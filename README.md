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

测试：`cd backend; uv run pytest`。首次安装依赖需要访问包仓库。

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

项目运行时直接调用云端 API，不需要下载或运行本地大模型。默认使用硅基流动的 `BAAI/bge-m3` 向量模型和 `BAAI/bge-reranker-v2-m3` 重排模型。将 `SILICONFLOW_API_KEY` 配置在运行后端的环境中；密钥不会写入数据库、日志或 Git。构建索引时，已审核证据文本会发给向量模型；检索时，查询和候选证据文本会发给向量及重排模型。研究任务的 Planner 与 Agent 也会将任务问题及可见证据发送给云端生成模型。导入需保密的资料前，应先确认可向云端提供这些内容。

```powershell
$env:TCM_MODEL_PROVIDER = "siliconflow"
# SILICONFLOW_API_KEY 应通过本机安全环境预先配置
uv run python -m tcm_platform.cli build-index <index_build_id>
uv run python -m tcm_platform.cli activate-knowledge <knowledge_version_id> <index_build_id>
uv run python -m tcm_platform.cli search-published "太阳病脉浮" --limit 10
```

检索融合原文匹配、PostgreSQL 全文检索和 pgvector 相似度，再用云端模型重排；结果只来自当前活动知识版本中经人工审核的 EvidenceRevision，包含来源、原文、上下文、定位和精确段落修订。浏览器工作台通过 `GET /api/v1/retrieval/search?query=...` 展示结果与证据详情。索引构建时一次性校验全文行、向量行及维度；失败时不会切换活动版本。

可用人工标注的 Golden Set 对活动索引评测，标签为 `GOLD`、`COUNTER`、`OPTIONAL` 和 `HARD_NEGATIVE`：

```powershell
uv run python -m tcm_platform.cli add-golden-query "太阳病的脉象" --gold <evidence_revision_id> --counter <另一条反证 revision_id>
uv run python -m tcm_platform.cli run-retrieval-benchmark --k 10
```

评测记录 Precision@K、Recall@K、MRR、nDCG、反证召回率和返回证据的可追溯率，并关联知识版本及索引版本。`GOLD` 和 `COUNTER` 计入必须召回的证据；没有反证标注的题目，其反证召回率记为 0，汇总时应结合题目标签理解。可选使用阿里云百炼，但需设置 `TCM_MODEL_PROVIDER=aliyun`、`DASHSCOPE_API_KEY`、`TCM_DASHSCOPE_WORKSPACE_ID`，可通过 `TCM_DASHSCOPE_REGION` 调整地域。

## 研究任务基础 E7（进行中）

已建立研究任务、冻结的执行上下文、任务证据池、检索事件、首轮 AgentRun 与 Claim Pool。Planner 的子问题采用严格 JSON 合约；首轮 Classicist、HistoricalScholar、Theorist 的输入会在任何 Claim 生成前分别冻结。Agent 输出若包含不在任务证据池或本次可见集合中的 EvidenceRevision，整份输出拒绝写入。

生成模型默认使用硅基流动云端对话 API。联调使用用户确认免费的 `Qwen/Qwen3-8B`；运行前仍需显式设置 `TCM_RESEARCH_MODEL`。启动任务会将冻结模型路由的研究 Job 放入 PostgreSQL 队列，运行一个 Worker 即可自动完成 Planner、证据检索和首轮独立研究：

```powershell
$env:TCM_RESEARCH_MODEL = "Qwen/Qwen3-8B"
uv run python -m tcm_platform.cli create-research-task "太阳病脉象的经典文献依据是什么" --source-id <source_id>
uv run python -m tcm_platform.cli start-research-task <task_id>
uv run python -m tcm_platform.cli run-research-next --task-id <task_id>
```

常驻处理可运行 `uv run python -m tcm_platform.cli run-research-worker`。Worker 使用租约和心跳；节点提交前核验租约，进程中断后从已提交的任务状态与 AgentRun 继续。暂停和取消请求在安全点生效；若模型调用正在进行，会等待该调用返回并丢弃其未提交的业务结果。可用 `pause-research-task <task_id>`、`resume-research-task <task_id>`、`cancel-research-task <task_id>` 控制任务。每次生成调用记录模型、请求/输出哈希、耗时、状态和接口返回的 token 用量，不保存原始提示词。也可按下列命令逐步调试：

```powershell
uv run python -m tcm_platform.cli plan-research-task <task_id>
uv run python -m tcm_platform.cli retrieve-research-task <task_id>
uv run python -m tcm_platform.cli prepare-first-round <task_id>
uv run python -m tcm_platform.cli run-first-round <task_id>
```

如需使用 DeepSeek 官方 API，可单独设置 `TCM_RESEARCH_PROVIDER=deepseek`、`TCM_RESEARCH_MODEL=deepseek-flash` 和 `DEEPSEEK_API_KEY`；向量和重排仍可保持硅基流动免费模型。DeepSeek 官方 Flash 按 token 计费，选择该路由前应查看[官方价格](https://api-docs.deepseek.com/quick_start/pricing/)。已启动任务的模型路由不会被后续环境默认值改变。

历史研究角色只有在来源具有明确作者、时代、流派、版本或出版年元数据时才生成 Claim；其余情况记录空结果，避免把普通原文误标为历史事实。这是保守的临时门禁，文本中隐含的历史线索可能暂时无法进入历史角色。`Qwen/Qwen3-8B` 的真实联调曾产生超出原文的解释，因此当前 Claim 只是待审研究草稿，不能直接当作可靠结论。首轮后的语义审计与纠错闭环将在 E8 实现。

## Claim 审计 E8（进行中）

对已完成首轮的 Claim，可先运行 `audit-claim-mechanical <claim_id>`，再运行 `audit-claim-semantic <claim_id>`。机械审计重新核验任务证据池、Agent 可见集合、冻结知识版本、审核状态和原文溯源；只有机械通过才向任务冻结的云端生成模型提交 Claim 与其已引用证据。语义结果保留 `SUPPORTED`、`PARTIALLY_SUPPORTED`、`UNSUPPORTED`、`CONTRADICTED`、`NOT_VERIFIABLE` 五种状态；每次审计都追加历史，Claim 上的 `audit_status` 仅供查询。当前自动语义判断仍是待审结果，Critic、重检索与 Rebuttal 尚在实现中。

## 设计约束

- PostgreSQL 是结构化权威数据源；Blob 文件在数据库登记前先原子写入磁盘。
- 审计事件在业务事务内追加；链头行加锁，避免并发序号冲突。
- 任务租约采用 PostgreSQL 行锁；外部调用不持有数据库事务。
- 当前健康页是只读界面。数据库就绪时显示 `DEGRADED`，直至常驻 Worker 与正式研究工作流完成；不会把基础设施就绪误报为平台 `READY`。

