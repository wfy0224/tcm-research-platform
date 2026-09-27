# 中医知识研究与临床推理平台

本仓库按三份设计文档实施第一阶段 A（知识底座）和第一阶段 B（理论研究）。当前代码包含 E0/E1 基础、E2 来源导入、E3 结构化文本分段，以及 E4 可追溯知识草稿：本地 API 与前端健康页、PostgreSQL 迁移、内容寻址文件存储、哈希链审计事件、持久化任务队列、来源解析、文本修订和证据引用。临床病例、处方与疗效功能不属于本阶段。

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

打开 `http://127.0.0.1:5173`。API 健康状态见 `http://127.0.0.1:8000/api/v1/system/health`。默认连接串仅用于本地开发；正式环境通过 `TCM_DATABASE_URL` 和 `TCM_DATA_ROOT` 配置。

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

导入命令返回 `source_id`、`source_revision_id`、`import_job_id` 和解析任务 ID。同一著作的新版本可在导入命令中加 `--source-id <已有 source_id>`；新版本不会覆盖旧文件。`--request-key` 可用于命令重试去重。Markdown 也可按纯文本导入。解析成功后自动排入分段任务；`segment-next` 生成卷、篇章、节、条、段、句等层级和上下文、校验和，并记录相邻来源修订的增删改移对齐。无文本层 PDF 会保留原文件并标记 `OCR_REQUIRED`；OCR、知识发布、检索和研究工作流仍在后续迭代。

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

`create-relation <subject_concept_id> <object_concept_id> --type <关系类型> --assertion <断言> --evidence <evidence_revision_id>` 建立概念关系草稿。概念、关系、药物和方剂都须引用准确的 EvidenceRevision；`trace-knowledge` 可回溯到来源修订、段落修订、原文和定位。当前对象仅为 `DRAFT`，不能作为已发布知识提供给研究任务；人工校订和发布门禁属于 E5。

## 人工校订与发布门禁 E5

审核会保留每次人工决定；阻断级 QualityIssue 未解决时，不能批准对象或创建知识快照。先审核 EvidenceRevision，再审核引用它的概念、关系、药物或方剂：

```powershell
uv run python -m tcm_platform.cli open-quality-issue evidence_revision <evidence_revision_id> --type INVALID_EVIDENCE_LOCATION --severity BLOCKER --description "待核对原文"
uv run python -m tcm_platform.cli resolve-quality-issue <quality_issue_id> --reviewer expert-1 --note "已核对原文"
uv run python -m tcm_platform.cli review-knowledge evidence_revision <evidence_revision_id> --reviewer expert-1 --decision APPROVE --note "核对通过"
uv run python -m tcm_platform.cli snapshot-knowledge
uv run python -m tcm_platform.cli create-index-build <knowledge_version_id> --configuration '{"strategy":"hybrid-v1"}'
```

快照固定精确对象修订，可用 `compare-knowledge <左版本 ID> <右版本 ID>` 比较。`activate-knowledge <knowledge_version_id> <index_build_id>` 只在全文和向量索引均通过验证后，才会原子切换活动知识版本与索引版本。当前索引构建接口尚未接入 E6，因此待构建索引会阻止发布；不会把未完成的知识标为 `READY`。

## 设计约束

- PostgreSQL 是结构化权威数据源；Blob 文件在数据库登记前先原子写入磁盘。
- 审计事件在业务事务内追加；链头行加锁，避免并发序号冲突。
- 任务租约采用 PostgreSQL 行锁；外部调用不持有数据库事务。
- 当前健康页是只读界面。数据库就绪时显示 `DEGRADED`，直至常驻 Worker 与正式研究工作流完成；不会把基础设施就绪误报为平台 `READY`。

