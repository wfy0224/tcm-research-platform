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

知识检索默认在本地执行 Exact/FTS/Structured/Relation，不需要模型密钥或查询外发授权。勾选本次查询外发同意后才创建云客户端；缺密钥、凭据存储不可用、外发策略禁止或模型故障时显示原因与已完成通道。向量调用失败回退本地融合排序，重排失败保留已完成向量通道并按融合得分排序。证据详情来自本地精确修订，不依赖模型。降级仍要求完整已发布的 KV/Index，不能查询草稿或扩大冻结来源范围。

`GET /api/v1/retrieval/query?query=...` 返回 `query_text`（保留原输入）、`normalized_query`、`mode`（`LOCAL`/`HYBRID`/`DEGRADED`）、安全原因码 `reasons`、已执行通道 `channels` 和公开编号的 `results`；无结果时也保留状态。可用 `mode=local` 强制本地，或 `allow_remote_query=true` 授权尝试已配置云模型。旧 `/api/v1/retrieval/search` 保留数组响应并支持同一本地/降级路径。研究服务与 benchmark 的既有模型路径默认仍严格失败，只有显式 `allow_model_fallback=True` 才允许模型故障降级。

研究工作区位于同一页面。桌面程序提供一次性启动密钥后，先建立本地会话，再填写研究问题与可选来源范围；选择已创建任务可查看 Summary、Claims、Debate、Evidence、Disputes、Report 六个视图。开始研究需填写已配置的 `provider/model` 路由并确认本次问题外发授权。暂停、恢复、取消、人工审核和报告导出按钮由任务返回的 `allowed_actions` 控制。Claims 显示过程草稿与审计，只有 Report 显示完成后的最终报告；Markdown/DOCX 生成完成后才出现下载入口。浏览器刷新后 CSRF 凭据从当前标签页的 `sessionStorage` 恢复；新标签页需要桌面程序重新建立会话。桌面主进程的密钥交接仍属 VIB-70。前端浏览器交互可在已安装 Edge 的 Windows 环境用 `cd frontend; npm run check:research-browser` 验证；此检查使用隔离的模拟 API，不会调用云模型。

真实隔离浏览器验收入口为 `npm run check:research-e2e`（Node 22+、Windows Edge、既有 Linux 测试容器）。它连接实际 API、研究 Worker 与报告导出 Worker，固定使用 `tcm_vib60_test` 和假模型，验证暂停/恢复、完整辩论、人工审核、Markdown/DOCX 浏览器下载、真实 SSE 与刷新恢复；0 次真实云调用。测试环境启动命令和验收证据见 [VIB-63 验收记录](docs/VIB63_RESEARCH_WORKSPACE_ACCEPTANCE.md)。

### 本地 API 会话与命令合约

当前预览页保留只读的健康检查与已发布知识检索；检索的 HTTP 响应使用来源、证据和段落公开编号，内部修订 UUID 只用于服务和 CLI。任务查询 `GET /api/v1/jobs/{JOB-...}` 需要本地会话，且只接受公开编号。

桌面主进程在启动 API 时生成至少 32 字符的一次性随机密钥，通过 `TCM_BOOTSTRAP_SECRET` 注入进程；前端从主进程取得密钥后，向 `POST /api/v1/local-session/bootstrap` 提交 `{"bootstrap_secret":"..."}`。请求必须携带精确匹配 `TCM_LOCAL_ALLOWED_ORIGINS` 的 `Origin`。成功响应设置 HttpOnly、SameSite=Strict 的会话 Cookie，仅在这次响应体返回 CSRF token。密钥只可兑换一次，默认 5 分钟过期；没有主进程注入密钥时 bootstrap 返回 503。正式 HTTPS 回环部署需设置 `TCM_SECURE_SESSION_COOKIE=true`。桌面主进程接线属于后续 Desktop Supervisor 任务。

业务命令统一校验会话能力、精确 Origin 和 `X-CSRF-Token`；来源导入和知识发布要求 `Idempotency-Key`，长任务返回公开 `job_id`。错误响应包含 `code`、`category`、`retryable`、`request_id`、`audit_ref` 和 `detail`。会话详情 `GET /api/v1/local-session` 返回 ETag；撤销会话 `DELETE /api/v1/local-session` 要求 `If-Match` 与 CSRF token。知识对象通过追加新草稿、修订和替换关系校订；HTTP 不提供覆盖已发布行的 PATCH。

`/api/v1/knowledge` 已提供来源导入与列表、来源修订分段、Evidence 草稿及 batch/detail、Concept/Relation/Herb/Formula 草稿与详情、人工审核、质量问题与质量报告、知识快照、发布 Job、版本比较及受控切换。来源导入请求使用严格 JSON：`metadata`、`file_format`（`txt`/`pdf`/`docx`）、`content_base64`，可选已有 `source_id`；同一 `Idempotency-Key` 重试返回同一来源修订和解析 Job。草稿 Evidence 引用段落公开编号及来源修订号，例如 `SEG-...@1`；审核对象引用 `EV-...@1` 或知识对象公开编号。导入解析后运行 `parse-next` 和 `segment-next`；发布请求冻结模型/端点配置并返回 Job，运行 `publish-next` 才会建立索引并通过门禁激活。发布失败保留旧活动 KV/Index，修复模型或索引问题后可用新 `Idempotency-Key` 重提同一版本；`GET /api/v1/jobs/{JOB-...}` 和版本详情可查询结果。真实发布会调用配置的向量模型，执行前需确认来源外发授权、模型配置及调用费用。

真实模型的隔离冒烟脚本为 `backend/scripts/check_knowledge_api_live.py`：它只接受 `tcm_vib60_live_test` 数据库与专用 `/tmp/tcm_vib60_live_store`，默认只检查环境并报告 `real_calls: 0`；加 `--execute` 才会导入一条已固定的公版原文，通过 API 发布并执行一次真实检索。需显式设置 `TCM_OUTBOUND_MODE=CLOUD_ALLOWED`、`TCM_ALLOW_ENV_API_KEYS=1`，将既有 `SILICONFLOW_API_KEY` 仅注入该临时容器进程，并设置 `PYTHONPATH=/workspace/backend/src`。脚本不得指向预览库；真实调用和费用应在执行前确认。

测试：`cd backend; uv run pytest`。首次安装依赖需要访问包仓库。

### 真实模型检索预览

自动化回归使用固定输出的假向量模型，以稳定验证排序、版本和引用链；这不代表真实云模型已经通过联调。真实检索需要活动索引的 `embedding_model`、`rerank_model` 与 API 当前模型完全一致。不要将 API 指向自动回归数据库中的假模型索引。

隔离预览库可命名为 `tcm_preview_shanghanlun`：先运行迁移，设置 `TCM_DATABASE_URL` 和 `TCM_OUTBOUND_MODE=CLOUD_ALLOWED`，并把硅基流动密钥存入 OS Keychain，再运行 `python scripts/prepare_shanghanlun_preview.py`。仅在临时开发容器没有 Keychain 时，才显式设置 `TCM_ALLOW_ENV_API_KEYS=1`，并按变量名注入既有 `SILICONFLOW_API_KEY`；不要把密钥写入命令参数、文件或日志。脚本导入[公版《傷寒論》太阳病上篇的 29 条真实原文](backend/fixtures/README.md)，用真实向量模型建索引，再激活知识版本。旧预览索引没有冻结外发策略，脚本会核对固定语料、登记来源授权并重新建索引；这会再次调用云模型，须按当次授权执行。API 使用同一数据库、Keychain 与数据目录，并设置 `TCM_PREVIEW_CORPUS=shanghanlun_taiyang_upper`。`pwsh -NoProfile -File scripts/check_shanghanlun_preview.ps1` 经 5173 代理执行 6 个目标条文查询和截图中的“太阳病”查询；治理后于 2026-09-28 重新运行：7/7 正向检查通过，六个目标条文均在前 2 位；这仍非专家质量评测。无关问题仍可能返回候选，**当前没有经过校准的拒答门槛**。这些工程检查不代替专家审核或大规模检索质量评测。

## 来源导入 E2

来源导入也可通过上述 API 操作；以下命令在 `backend` 目录运行：

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

来源完成分段后，`extract-knowledge <source_revision_id>` 用 `local-exact-terms/v4` 本地规则生成待审候选，`trace-extraction <extraction_id>` 返回批次、实体字符区间、关系原句和精确 Evidence 溯源。抽取只处理最外层可引用片段，避免段落和句子重复；同一来源修订与规则版本重复执行返回同一批次，失败时草稿和审计一起回滚。同批次只归并同类型原词，不猜测繁简/历史同义词，也不跨来源、时代或流派合并。一个原词可保留多种类型候选，此时标为歧义并禁止直接批准，也不从歧义端点推定命名关系。种子词表和明确命名关系只用于工程验证，缺失词汇不会被自动补造；条件、否定和禁忌原句保留，方名提及不会生成缺少药味的完整方剂。旧 v2/v3 批次保持原记录。

v4 在同一结构父节点、同类型的连续片段中识别明确的“方名方”标题、完整药味列表和“右/上×味”煎服段，返回 `formula_count`、`formulas`。药味必须逐项包含原剂量，数量吻合；支持分号/顿号/换行分隔及括号炮制说明。合成示例为 `合成測試湯方：桂枝三兩（去皮）；芍藥三兩。右二味，以水七升，分溫服。`。共享剂量、缺药味、模糊剂量、替代药物、条件标题或未知列表文字均跳过整方；规则覆盖范围有限，真实方剂 C02 尚未冻结。新方剂和逐字段引用与批次共用事务，所有内容仍为 DRAFT，先审 Evidence 再审方剂。单位只复制原单位字符，规范剂量、比例、角色、药物绑定及未明确字段保持 null；煎服段完整保留，跨段引用附连接依据，不自动拆解禁忌或剂型。来源时代/流派保留在批次和精确来源链，不推定为方剂字段。

`adjudicate-term <source_concept_id> --decision <NORMALIZE|HISTORICAL_SYNONYM|DISTINCT|UNRESOLVED> --basis <解释依据> --actor <校订者> --sources <JSON文件>` 追加人工术语裁定草稿。NORMALIZE 可用 `--name` 和 `--type` 指定规范名和类型；DISTINCT 明确保留独立含义；UNRESOLVED 保留原含义与未知字段且不能批准。`--mention <mention_id>` 可重复传入以选定部分提及，省略则选择原概念全部提及。时代和流派沿用来源概念，包括 null。原概念和原提及保持不变，新概念复制精确字符区间；裁定记录及其内容、词形、证据关联和提及不可原位更改，后续校订再次追加草稿。

术语 sources 文件是以下对象的数组，字符区间按 Unicode 左闭右开计数，必须属于精确 EvidenceRevision。HISTORICAL_SYNONYM 还必须用 `--related-concept <已审核对照概念ID>` 指明对照，并在 sources 中引用其证据的精确范围；新概念继承对照名称和类型，但保留原时代/流派及独立身份，原词登记为有范围的 HISTORICAL 词形，不产生全局字符串合并。

```json
[{"evidence_revision_id":"<UUID>","segment_revision_id":"<UUID>","start_offset":0,"end_offset":3}]
```

`trace-knowledge concept <新概念ID>` 返回裁定者、解释、原词与复制提及、精确来源和对照快照。草稿须先审核所引 Evidence，再单独审核概念；审核、知识快照和激活均复验裁定。已发布概念的校订审核后继续使用 `supersede-knowledge concept <旧ID> <新ID>`；新旧知识版本分别保留相应对象。仅创建裁定不会改变原候选审核状态或自动更新其关系引用。

`create-formula` 另支持 `--method`、`--dosage-form`、`--preparation`、`--cautions`，以及与 `--ingredient` 互斥的 `--ingredient-spec <UTF-8 JSON 文件>`。文件为 IngredientSpec 对象数组，例如：

```json
[{"original_name":"桂枝","amount_original":"三兩","amount_normalized":null,"unit":"兩","dose_ratio":null,"role":null,"processing":"去皮","herb_id":null}]
```

不明确的规范剂量、配伍角色和时代/流派保留 null，不自动换算古代单位。校订方剂时传原 `--formula-id` 建新 DRAFT 修订，再单独审核；旧修订及快照保留。

`--field-sources <UTF-8 JSON 文件>` 保存逐字段引用，文件为对象数组。例如原文片段以“桂枝湯”开头时：

```json
[{"field_key":"original_name","evidence_revision_id":"<UUID>","segment_revision_id":"<UUID>","start_offset":0,"end_offset":3,"basis":null}]
```

字段键为修订字段名或 `ingredients.<从0开始的序号>.<字段名>`；每个有值字段在批准前必须具备引用。区间按 Python Unicode 字符计数，左闭右开，必须落在该 Evidence 实际引用的片段修订中。一个字段可引用多个范围；值与引文不同，以及规范剂量、比例、角色、药物绑定、时代或流派等解释字段，必须填 `basis` 说明依据。未知字段保持 null，不登记虚构引用。仅有部分引用的草稿可保存；审核、快照和激活都复验完整来源。旧已审核修订保留原版本标记，旧待审草稿须追加新修订。`trace-knowledge formula_revision` 返回字段值、原文区间和解释依据。

完整进度和隔离验证命令见 `docs/VIB46_KNOWLEDGE_CANDIDATES_ACCEPTANCE.md`。本机原生 Python/uv 已有运行限制，验证使用该文档中的 Linux 容器入口。

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

校订已发布的概念、关系或药物时，先用现有 `create-concept`、`create-relation` 或 `create-herb` 建新草稿并审核，再执行 `supersede-knowledge <concept|relation|herb> <旧对象 ID> <新对象 ID>` 登记追加修订。新快照选择已审核的新对象；旧知识版本仍保留原对象。若关系仍指向已替换概念，或方剂仍指向已替换药物，须先修订这些引用后才能创建新快照。`compare-knowledge` 会显示修订谱系和旧 Evidence 引用影响。

新快照若保留了引用旧 EvidenceRevision 的已审核知识对象，会把这些历史引用单独冻结并校验哈希；历史引用用于溯源和版本比较，不进入当前 Evidence 检索索引。旧研究任务继续使用启动时冻结的知识版本与索引。

从已有活动版本切换时，`activate-knowledge` 会返回 `release_snapshot_id`，并把切换前后的 KV/Index 指针及清单哈希保存为不可变的本地 CAS 工件。需要快速切回时运行 `restore-release-snapshot <release_snapshot_id>`；系统先核对工件哈希、当前活动指针和旧版本双索引，再原子切回。首次发布没有旧活动版本，因此没有可恢复的 Release Snapshot。该快照依赖原数据库与索引仍可用；完整数据库和文件的灾难恢复属于 Portable Backup，不能用它替代。

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

检索融合原文匹配、PostgreSQL 全文检索、pgvector 相似度，以及已发布概念/方剂的结构候选和已发布关系的引用候选，再用配置的模型重排。结构候选仅匹配当前快照中已审核对象自己的词形、方剂原名/药味；不推断繁简或跨对象历史同义词。裁定概念仅返回自身提及锚点，方剂版本1按对应字段引用定位；历史引用不替换成新版证据。所有通道只返回冻结知识版本/索引与来源范围内已审核、已索引的 EvidenceRevision，包含原文和精确引用；显式空来源列表返回空结果。研究任务和 benchmark 固定版本，服务结果保留原 query 与 NFKC 规范查询。浏览器工作台通过 `GET /api/v1/retrieval/search?query=...` 展示结果与证据详情。索引构建时一次性校验全文行、向量行及维度；失败时不会切换活动版本。无密钥时支持本地 Exact/FTS/Structured/Relation，授权调用模型失败时显式降级；`/retrieval/query` 和工作台显示模式、原因与完成通道。成功查询会在冻结索引对应的精确来源修订内执行本地未发布内容精确匹配扫描，生成可定位的 WARNING QualityIssue 供人工核对；候选和问题描述不进入证据结果或模型输入。按规则/目标跨查询去重，已解决或豁免的问题保留人工决定；数据库或审计写入失败时检索失败。此匹配规则不代表已校准的医学相关性阈值，详见 docs/VIB48_QUALITY_TRIAGE_ACCEPTANCE.md。VIB-48 的查询候选扩展完整验收仍待补。

检索在重排候选截取前及最终返回前应用 `source-context/v1`：按相关性 credit 对同来源和精确引用段落重叠做软惩罚，保留首位最相关候选；不同证据身份不合并，单一来源仍可填满结果。API 返回 `diversity` 排序说明，研究审计和 benchmark 保存策略及实际排名；原 RRF/重排分数保留。说明用于解释排序，不表示医学可信度；通道上限外的候选不能靠多样性恢复。详见 [多样性工程验收](docs/VIB48_DIVERSITY_ACCEPTANCE.md)。

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

研究任务完成后，可用 `queue-report-export <task_id> --format markdown` 或 `--format docx` 排队独立导出，再用 `run-report-export-next --export-id <export_id>` 处理。`show-report-export <export_id>` 显示格式、渲染版本、Job 状态和 Artifact 哈希；`save-report-export <export_id> <output_path>` 将已完成文件保存到本地，不覆盖已有文件。相同报告、格式与渲染版本重复排队返回同一导出；失败可再次排队重试，不改变已完成研究任务。两种文件均列出五类结论、原文证据、争议、限制与研究过程，并提供内部引用跳转及可复制的来源修订和定位文字。网页研究工作区已显示最终报告与导出入口；`/api/v1/research/tasks/{task_id}` 提供服务端计算的 `allowed_actions`，`/details` 及 `/claims`、`/audits`、`/debate`、`/disputes`、`/human-reviews` 提供已落库的研究过程，`/report` 与 `/exports/{format}` 提供最终报告和导出。写命令需本地会话、CSRF 与 `Idempotency-Key`。`/events` 是 SSE 通知，首次连接和重连均先发送无事件 ID 的 `snapshot` 指针，客户端先 GET 任务状态与需要的详情，再按 `Last-Event-ID` 消费补发事件；事件数据仅含公开任务编号。`?follow=false` 可取有限历史批次后关闭连接。网页报告工作台由 VIB-63 接入。

验收追踪：AC-1B-03/04 的 Claim 定向质疑、受限再检索、Rebuttal、追加修订与重新审计对应 `backend/src/tcm_platform/debate_service.py`、`research_service.py`、`audit_service.py`、`research_worker.py`、迁移 0012～0014，以及 `backend/tests/test_research_integration.py` 中的研究链集成测试。

## Claim 归并与争议 E9.1

Worker 在首轮审计后和辩论轮次结束时，按断言类型、规范化文本与精确来源版本归并重复 Claim；来源快照的时代和流派一并保留。原 Claim 与修订 Claim 都保留各自 ID，CanonicalClaimMember 指向其最新审计结果。明确的语义审计矛盾和 `CONTRADICTION` 质疑生成 Dispute；审计不充分、无法验证、质疑缺证或再检索无结果生成 EvidenceGap。新审计结果会把已过时的争议和缺口标为 `SUPERSEDED`，保留历史记录。未审计的反面材料不会被标成已证实的反证。命令 `normalize-claims <task_id>` 可幂等重放这些投影。自动归并只处理精确重复断言；跨断言的语义相似和隐含冲突需后续模型或人工提出明确关系，不会靠多数票推断。

## 设计约束

- PostgreSQL 是结构化权威数据源；Blob 文件在数据库登记前先原子写入磁盘。
- 审计事件在业务事务内追加；链头行加锁，避免并发序号冲突。
- 任务租约采用 PostgreSQL 行锁；外部调用不持有数据库事务。
- 当前健康页是只读界面。数据库就绪时显示 `DEGRADED`，直至常驻 Worker 与正式研究工作流完成；不会把基础设施就绪误报为平台 `READY`。
