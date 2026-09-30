# 中医知识研究与临床推理平台开发交接

> **2026-09-29 暂停交接**：用户要求本次更新后暂停，后续在新对话继续。分支 `codex/evidence-audit`、HEAD `0c3a714`；本次仅核对交接、Git 状态和 VIB-60 的范围，读取 `main.py`、`api_contract.py` 的现有 API 契约，**没有修改业务代码、运行测试或变更 VIB-60 状态**。工作区仍只有原有未跟踪 `AGENTS.md`、本文件、`docs/`。下次收到“继续”直接承接 **VIB-60**：先检查来源导入服务、Job Worker 与现有知识发布服务的调用边界，再实现来源/知识/证据/版本质量路由及隔离库集成验证。VIB-49 本地已验收，Linear 同步仍因自动审批拒绝而待明确授权；勿绕过。

> **最新状态，2026-09-29 VIB-49 本地验收通过**：分支 `codex/evidence-audit`，HEAD `0c3a714`（前序 `ad41f6a`）。`0023_release_snapshot` 在已有 Active 的知识版本切换时，以不可变 CAS 工件冻结切换前后 KV/Index 和清单哈希；激活事件关联 Release Snapshot ID。`restore-release-snapshot` 校验工件哈希、当前指针和旧版本双索引后原子切回，缺工件或损坏索引时原 Active 保留。首次发布没有旧活动版本，不产生可恢复快照。专项集成测试还覆盖旧研究任务冻结 KV/Index、历史 Evidence 引用、不可变触发器和切回。全新隔离库从空库迁移至 0023，完整后端 **61 passed、0 skipped**；独立迁移库完成 0022→0023→0022→0023，`alembic check` 无差异；Ruff 和 diff 检查通过。预览库迁移前备份 `backend/data/tcm_preview_pre_0023_20260929.dump` 467297 字节，SHA256 `426ca71c0ece4326060fecda54d5e36a0d4ac1e7ed4462307c1da639b0da2078`，容器内外一致且 `pg_restore -l` 可解析；预览库现为 0023，8001 API 重启后 5173 健康接口 `schema=current`、数据库及文件存储可用。Release Snapshot 是依赖原数据库与索引的本机快速回退清单，不能替代 VIB-66 的加密 Portable Backup/灾难恢复。本地 VIB-49 验收通过；Linear 仍 In Progress，前次同步评论被自动审批拒绝，勿换路径绕过；需用户明确授权发送该摘要后同步。下一项按原计划承接 VIB-60 来源、知识、证据与版本质量 API。原有未跟踪 `AGENTS.md`、本文件、`docs/` 保留，Windows Python/uv/Alembic 继续禁用。

> **最新状态，2026-09-29 VIB-49 0022 增量已提交**：分支 `codex/evidence-audit`，HEAD `ad41f6a`。`0022_reference_manifest` 为新 KV 冻结历史 EvidenceRevision 引用专用记录和 SHA256 清单；它们用于溯源及版本比较，不进入当前检索索引。激活时复核引用清单。集成用例已验证含旧引用版本建索引、激活后仅检索新 Evidence，以及旧研究任务在活动版本切换后仍按启动时的 KV/Index 检索旧 Evidence。专用迁移库完成 0021→0022→0021→0022，`alembic check` 无差异；Ruff 通过，完整后端 **61 passed、0 skipped**，`git diff --check` 通过。预览库升级前备份 `backend/data/tcm_preview_pre_0022_20260929.dump`，464405 字节，SHA256 `17deac2f577a54c1141cfbf2173735590e4735c6c44c9d437aa5fa53b235bd88`，容器内外一致且 `pg_restore -l` 可解析；预览库现为 0022，重启 8001 临时 API 后 5173 代理健康接口显示 `schema=current`、数据库和文件存储可用，整体 `DEGRADED` 为既有健康规则。业务文件无未提交改动；原有未跟踪 `AGENTS.md`、本文件、`docs/` 保留。**VIB-49 仍 In Progress**：LLD 14.4 区分发布/迁移快速恢复的 Release Snapshot 与换机恢复的 Portable Backup；当前 `BackupRecord` 仅有状态和哈希骨架，尚无真正的发布快照工件及与 KV/Index 的可核验关联。下一步实现并验证 Release Snapshot 的真实工件、恢复路径和激活关联，再决定 VIB-49 验收；VIB-66 负责完整加密 Portable Backup。Linear 进展评论因自动审批认为向未经确认的第三方发送项目/测试/备份元数据有风险而被拒绝，未执行；本地记录已保存，勿换路径绕过。VIB-58 Windows Credential Manager Python 实机验证仍待安全环境。

> **最新状态，2026-09-29 VIB-49 未验证增量**：分支 `codex/evidence-audit`，HEAD 仍为 `729b212`。工作区未提交的 `0022_reference_manifest`、`models.py`、`knowledge_publish.py`、`main.py`、知识发布集成测试，已为新 KV 增加历史 EvidenceRevision 引用专用记录及 SHA256 清单；旧引用不会进入当前检索索引，激活时复核引用记录和清单，版本比较显示引用变化。集成用例增加含旧引用版本的建索引、激活、检索仅命中新修订、切回旧版；**新增代码及迁移尚未通过运行验证**。第一次迁移尝试因 Alembic 版本号超过 32 字符被拒绝并回滚，已缩短为 `0022_reference_manifest`；随后 Docker 命令被自动审批的额度限制拒绝，未执行。仅 `git diff --check` 通过。预览库仍按上次记录处于 0021，不能把 `main.py` 的 0022 目标版本视作数据库已升级。原有未跟踪 `AGENTS.md`、本文件和 `docs/` 保留；VIB-49 保持 In Progress，Linear 状态未同步本次未验证增量。下一次先在审批可用时用隔离迁移库确认当前版本，执行 0021→0022→0021→0022、`alembic check`、Ruff 和完整后端测试（核对 0 skip）；成功后再备份并迁移预览库、验健康，然后继续真实 Backup/Release Snapshot 关联与旧研究任务冻结 KV/Index 专项验收。Windows Python/uv/Alembic 禁止重试。

> **最新状态，2026-09-29 VIB-49 接续**：分支 `codex/evidence-audit`，HEAD `729b212`。新增 `0021_knowledge_supersession` 及已审核 Concept/Relation/Herb 的追加修订谱系；`supersede-knowledge` CLI 显式连接新旧对象，快照只选新对象，旧 KV 仍可切回。新对象引用未纳入当前 Evidence、关系指向被替换概念、方剂指向被替换药物时，新快照拒绝创建。集成用例走通概念和关系校订、受阻后修复、新 KV 激活和旧 KV 切回；完整后端 **61 passed、0 skipped**，Ruff、`git diff --check`、0021 在独立迁移库升级→回退→升级、`alembic check` 均通过。预览库迁移前备份 `backend/data/tcm_preview_pre_0021_20260928.dump` 461339 字节，SHA256 `980c83cfef1c4eef10b2f2033dca15b3426640585d35a0914cb1474434cc5e47`，容器内外一致；预览库现为 0021，最新本地 API 已重启，5173 代理健康接口显示 `schema=current`、数据库/文件存储可用。原有未跟踪 `AGENTS.md`、本文件、`docs/` 保留。VIB-49 仍 In Progress：既有旧数据的跨修订引用可能仍存在，当前门禁仅约束新增替换链；真实备份/Release Snapshot 联动及旧研究任务固定 KV/Index 的专项验收仍待做。下次先处理这些旧引用的可回放修复与新快照一致性，再补备份联动；不要把本轮局部门禁当作全量一致性已完成。VIB-58 的 Windows 密钥实机验证仍待安全环境。

> **最新状态，2026-09-28 VIB-49 进行中**：分支 `codex/evidence-audit`，HEAD `9ad9e2f`；VIB-58 预览验收说明另已提交 `7270ec3`。按用户恢复的原计划，当前承接 VIB-49。已补同一 Evidence/Formula 的修订替换比较与旧引用影响、历史切换前对目标索引片段/向量实物的复核，以及切换审计中原 KV/Index 指针。集成用例验证成功切回和损坏索引拒绝切回、原 Active 保留。独立测试库完整后端 **61 passed、0 skipped**，Ruff 与 diff 检查通过；Linear VIB-49 为 In Progress。下一步处理已发布 Concept/Relation/Herb 的追加修订、旧引用处理及真实备份快照关联，再补旧研究任务固定版本的专项验证。VIB-58 仅余 Windows Credential Manager Python 实机读写未验证，保持 In Progress；Windows Python/uv/Alembic 入口不得运行。VIB-61 的已提交 API 增量仍非整个 Issue 完成。原有未跟踪 `AGENTS.md`、本文件、`docs/` 保留。

> **VIB-49 引用一致性停点**：现有快照选择最新已审核 EvidenceRevision，却仍纳入引用旧修订的已审核知识对象。曾试加激活门禁，完整回归因既有旧引用而 60 passed、1 failed；门禁及其测试已撤回，复跑完整回归恢复 **61 passed、0 skipped**，业务工作区仍为 HEAD `9ad9e2f`。下次先在 `knowledge_service.py`、`knowledge_publish.py` 和相应模型/迁移中设计可执行的对象追加修订或替换及引用迁移，再加一致性门禁；不要直接重加这条拒绝条件而使现有发布流程整体失效。

> **最新状态，2026-09-28 原计划接续**：分支 `codex/evidence-audit`，HEAD `295f2f9`（另有 README 验收说明待提交）。用户取消临时的主功能提前安排，仍按原 Issue 依赖推进。VIB-58 的独立预览库已从 `0019` 备份并迁移到 `0020_outbound_source_policy`，公版来源经核对后显式授权并重建治理索引；经 5173 的真实检索 7/7 正向检查通过，调用日志含策略版本与哈希。完整后端 **61 passed、0 skipped**，Ruff 通过。Windows Python/uv/Alembic 会弹应用程序错误，故 Windows Credential Manager 的 Python 实机读写仍未验证，VIB-58 保持 In Progress。下一项按原依赖承接 **VIB-49 校订修订与版本切换**，密钥实机验证在安全运行环境可用后补做。VIB-61 的 `cadb7c8` 只是已提交增量，状态仍为 Backlog。原有未跟踪 `AGENTS.md`、本文件、`docs/` 保留。

> **最新状态，2026-09-28 恢复原计划**：用户取消了本会话提出的功能提前安排，后续按原 Issue 依赖和里程碑推进。分支 `codex/evidence-audit`，HEAD `cadb7c8`；其中 VIB-61 的研究任务/报告 HTTP 增量已提交并通过隔离库完整后端 **60 passed、0 skipped** 和 Ruff，尚不满足整个 Issue 验收。刚写的基础版上传/本地检索代码未提交，已撤回；现有预览库仍未迁移 0020。当前承接项恢复为 **VIB-58 外发治理剩余验收**，之后按 VIB-49、VIB-60/62 和 VIB-61/63 等原依赖接续。Windows 本机 Python/uv/Alembic 入口仍禁止启动。原有未跟踪 `AGENTS.md`、本文件、`docs/` 保留。下方“主功能提前”段落已作废。

> **最新快照，2026-09-28 VIB-58 进行中**：分支 `codex/evidence-audit`，HEAD `ba69cab`（开发基线 `4c805ac`）。本轮已实现来源数据级别/显式外发授权、`LOCAL_ONLY` 默认拒绝、任务和索引冻结策略、complete/embed/rerank 调用前复核、查询与研究问题的单次同意、云端点/大小/并发/频率/熔断、传输与格式重试分离、脱敏调用日志，以及标准库直连 Windows Credential Manager。迁移 `0020_outbound_source_policy` 仅在独立空测试库完成升级→回退→升级与 `alembic check`；后端隔离库 **59 passed、0 skipped**，Ruff、前端构建和 diff 检查通过。**Windows Credential Manager 实机读写、既有预览库迁移/重建索引、治理后的真实云检索未验证**；未启动真实付费调用，也未改动现有预览库。Linear VIB-58 已改 In Progress；下一步先做 Windows 密钥实机验证，再在明确授权下迁移预览库、重建旧索引并跑 7 个真实查询。业务改动已提交；原有未跟踪 `AGENTS.md`、本文件和 `docs/` 须保留。Windows 本机 Python/uv/Alembic 入口曾触发错误弹窗，不得再次运行；实机密钥验证需要不触发该运行时的独立方式。下方旧快照由本段覆盖。

> **最新快照，2026-09-28 真实《傷寒論》检索预览已接通**：分支 `codex/evidence-audit`，HEAD `4c805ac`。用户授权使用公版《傷寒論》后，固定维基文库修订 `2607901` 的太阳病上篇 29 条原文，导入独立库 `tcm_preview_shanghanlun`，用真实硅基流动 `BAAI/bge-m3` 建立并激活索引，实际查询调用 `BAAI/bge-reranker-v2-m3`。当前 `http://127.0.0.1:5173/` 可展示该语料；经 5173 代理的健康接口 HTTP 200，`database=connected`、`schema=current`、`blob_store=available`、`preview_corpus=shanghanlun_taiyang_upper`，整体 `state=DEGRADED` 是既有健康规则。`pwsh -NoProfile -File backend/scripts/check_shanghanlun_preview.ps1` 实测 6 个预设条文问题和用户截图中的“太阳病”问题均命中（7/7）；无关的现代胰岛素问题仍返回 5 条候选，未有专家校准的拒答门槛。原文转写、工程自动审核、开发者选择的查询标签均非专家 Golden Set；不可宣称 VIB-68 完成。真实来源、脚本、启动设置和限制见 `backend/fixtures/README.md`、`README.md`。完整后端 51 passed、0 skipped；Ruff、前端构建、diff 检查通过。容器内文件存储 `/tmp/tcm_preview_shanghanlun_store` 已用 `docker cp` 备份到被忽略的本机 `backend/data/shanghanlun_preview_store`；如容器重建，须将备份复制回相同路径，或用相同配置重新运行种子脚本。API/前端均是临时进程，重启后须重新启动并向容器按变量名转发既有 `SILICONFLOW_API_KEY`，不得打印或写盘密钥。业务改动已提交；原有未跟踪 `AGENTS.md`、本文件、`docs/` 保留。VIB-68 的初步证据已同步到 Linear 评论，任务状态保持 Backlog。**下一开发项仍是 VIB-58 模型网关治理与外发控制；VIB-68 后续需要专家标注、反证/歧义/无结果评测和阈值校准。**下方早期快照由本段覆盖。

> **2026-09-28 检索密钥故障处理**：用户在 5173 检索页收到 `SILICONFLOW_API_KEY is not configured`。本地 HTTP 复现为 503；核对发现 Windows 进程/机器环境已有密钥，但 `tcm-vib54-py` 容器未继承。已用 `docker exec -e SILICONFLOW_API_KEY` 按变量名转发既有环境值，重启容器内 8001 的临时 API；未打印、写盘或提交密钥。用不会发起云端调用的空白查询复查，响应由缺密钥 503 变为预期参数校验 400；健康代理仍 HTTP 200、`schema=current`。**正常检索的云端响应尚未实测**；用户可刷新页面重试。进程或容器重启后需在启动 API 时再次传入该环境变量，VIB-58/70 应改为正式密钥管理和启动接线。无业务代码改动，HEAD 仍 `7ed5368`，Linear 状态不变。下一开发项仍是 VIB-58。

> **最新快照，2026-09-28 VIB-59 已提交**：分支 `codex/evidence-audit`，HEAD `7ed5368`。一次性启动密钥兑换持久 HttpOnly 会话、回环 Host/精确 Origin/CSRF、actor 能力与公开编号解析、严格 DTO/错误码、幂等 Job、ETag/If-Match 和 202 通用契约已实现；旧检索 HTTP 响应改为公开编号，内部 Agent/CLI 仍保留精确修订 UUID。两座隔离库在 `0019_local_session_api`，第二库完成 `0018→0019→0018→0019`，`alembic check` 无差异；完整后端 **51 passed、0 skipped**，专项回归 3 passed，Ruff、前端构建、diff 检查通过。5173 预览页和健康代理 HTTP 200，健康接口 `schema=current`、`state=DEGRADED`（既定健康规则）。VIB-59 已在本地任务清单及需求追踪矩阵记录验收，Linear 已同步 Done 并附证据。当前业务工作区无未提交改动；`AGENTS.md`、本文件、`docs/` 仍未跟踪，含本次本地记录，须保留。**下一项 VIB-58 模型网关治理与外发控制**；VIB-60/61 将消费 VIB-59 的 API 契约，VIB-70 再接线桌面主进程的一次性密钥。当前可向用户展示的 5173 页面仍为检索/证据页，没有报告工作台。Windows 本机 Python/uv/Alembic 入口继续禁止重试。下方较早快照由本段覆盖。

> **最终快照，2026-09-28 VIB-57/E9 已提交**：分支 `codex/evidence-audit`，HEAD `86e3a5d`。`0018_report_export` 与 `report_export.py` 让已完成 StructuredReport 以独立可重试 Job 派生 Markdown/DOCX Artifact，冻结研究过程、保留格式/渲染版本和可复制的原文引用定位。两座隔离数据库已升级到 0018，第二库回退再升级；`alembic check` 无差异，完整后端 **48 passed、0 skipped**，Ruff（忽略 Windows 只读挂载 EXE002 误判）和 `git diff --check` 通过。Word 实际将样本 DOCX 渲染成 4 页，逐页确认中文原文、内部引用及分页无截断/重叠。真实云模型未调用。Linear VIB-57 和 E9 父任务 VIB-53 均 Done 并附验收评论；业务工作区无未提交改动，原有未跟踪 `AGENTS.md`、本文件和 `docs/` 保留。**下一项 VIB-59 本地会话、权限边界与 API 通用合约**：优先打通后续报告查询/下载及研究工作台依赖；VIB-58 模型网关可独立接续。当前 5173 仍只有检索/证据页，没有报告网页。Windows 本机 Python/uv/Alembic 入口继续禁止重试。下方旧快照由本快照覆盖。

> **2026-09-28 预览复核**：迁移至 0018 后已重启容器内 8001 API；`http://127.0.0.1:5173/` 与经 Vite 代理的 `/api/v1/system/health` 均 HTTP 200，后者返回 `schema=current`、`database=connected`、`blob_store=available`、`state=DEGRADED`（当前健康状态既定逻辑）。Vite、API 和转发容器均为临时本机进程，机器重启后需重新启动；检索的真实云模型调用未执行。

> **最终快照，2026-09-28 VIB-56 已提交**：分支 `codex/evidence-audit`，HEAD `d6479c2`。Judge 严格消费已审计 Active Claim、最新 AuditResult、开放 Dispute/EvidenceGap 与冻结知识版本的已审核 EvidenceRevision；不可变 ResearchSynthesis/StructuredReport 已落库。Worker 只有在结构化报告写入成功后才完成研究任务。官方 Python 容器使用项目声明的 `psycopg` 和隔离 PostgreSQL：`0017` 迁移升级、回退再升级及 `alembic check` 通过，完整后端 **45 passed、0 skipped**，Ruff（忽略 Windows 只读挂载 EXE002 误判）与 `git diff --check` 通过。真实云模型未调用。Linear VIB-56 已同步 Done 并附验收评论；业务工作区无未提交改动，原有未跟踪 `AGENTS.md`、本文件与 `docs/` 保留。**下一项 VIB-57 Markdown/DOCX 报告导出及重试**：先读本地清单 VIB-57 与 Linear，再以 StructuredReport 为输入做独立派生 Job/Artifact、失败隔离和可追溯导出。当前 5173 前端只展示检索/证据，尚无研究报告页面。Windows 本机 Python/uv/Alembic 入口继续禁止重试。下方较早快照由本快照覆盖。

> **2026-09-28 本地预览恢复**：用户反馈 `127.0.0.1:5173` 拒绝连接；确认无 Node/Vite 进程监听后，已用隐藏的 Node 进程启动 `frontend/node_modules/vite/bin/vite.js --host 127.0.0.1 --port 5173 --strictPort`（PID 32268）。已有可信 `tcm-vib54-py` 容器以 `PYTHONPATH=/workspace/backend/src` 在容器内 8001 运行最新 API；官方 `python:3.11-slim` 容器 `tcm-preview-forward` 将本机 `127.0.0.1:8000` 转发到容器 API。前端首页、模块资源与 `/api/v1/system/health` 经 Vite 代理均返回 HTTP 200；健康状态 `DEGRADED` 是当前 `main.py` 在数据库、schema、文件存储均正常时的既定状态。检索会调用云端模型，本次未执行。无业务代码改动；预览进程是临时运行态，若重启机器需重新启动。下一开发项仍为 VIB-56。

> **最终快照，2026-09-28 VIB-55 已提交**：分支 `codex/evidence-audit`，HEAD `b7397d3`。冻结 WorkflowConfig、可复算 StopEvaluation、多轮 Critic/Rebuttal、WAITING_HUMAN 请求和正确阶段续跑已落地；业务工作区无未提交改动，原有未跟踪 `AGENTS.md`、本文件与 `docs/` 保留。官方 Python 容器使用项目声明的 `psycopg` 和隔离数据库：迁移 `0016` 升级、回退、再升级及 `alembic check` 通过，完整后端 **40 passed、0 skipped**，Ruff（忽略 Windows 只读挂载 EXE002 误判）及 `git diff --check` 通过。真实云模型未调用。Linear VIB-55 已同步 Done。**下一项 VIB-56 Judge 综合与不可变 Structured Report**：先读本地清单 VIB-56 与 Linear；以审计 Claim、Dispute/EvidenceGap、StopEvaluation 和冻结上下文为输入，实现 Judge 严格只读与结构化报告落库，报告成功后才将任务标为最终完成。Windows 本机 Python/uv/Alembic 入口继续禁止重试。下方 VIB-54/VIB-55 旧状态由本快照覆盖。

> **最终快照，2026-09-28 VIB-54 已提交**：分支 `codex/evidence-audit`，HEAD `2f321d2`（E9.1 CanonicalClaim/Dispute/EvidenceGap）；业务工作区无未提交改动，原有未跟踪 `AGENTS.md`、本文件和 `docs/` 保留。VIB-54 的隔离数据库迁移、`alembic check`、官方 Python 容器中的完整后端 **38 passed、0 skipped**、Ruff（忽略 Windows 只读挂载误判的 EXE002）及 `git diff --check` 均通过；真实云模型未调用。`tcm-vib54-py` 官方 Python 容器保留供接续验证，`backend` 只读挂载；`tcm_vib54_test` 有回归测试数据，`tcm_vib54_migration_test` 已升级到 0015。**下一项 VIB-55 StopEvaluator/人工中断恢复**，先读本地清单与 Linear，再以 VIB-54 的 Dispute/EvidenceGap 为输入。Windows 本机 Python/uv/Alembic 入口继续禁止重试。下方“VIB-54 进行中”段落是本次中途记录，由此快照覆盖。

> **最新快照，2026-09-28 VIB-54 验收通过**：业务分支 `codex/evidence-audit`，交接编写时基线 HEAD `a7fda2f`；本次新增 `0015_canonical_claim_dispute_gap`、`claim_normalization.py`、CanonicalClaim/Member、Dispute、EvidenceGap、Worker 两处增量规范化及 CLI 重放。Docker 官方 `python:3.11-slim` 容器只读挂载 `backend`，使用项目声明的 `psycopg` 驱动和隔离库 `tcm_vib54_test`：完整后端 **38 passed、0 skipped**；Ruff 在只读 Windows 挂载下忽略误报的 EXE002 后通过，`git diff --check` 通过；`alembic check` 无差异。另一隔离库 `tcm_vib54_migration_test` 完成 `0014→0015→0014→0015`。未调用真实云模型。VIB-54 的代码等待提交及 Linear 完成状态同步；原有未跟踪 `AGENTS.md`、本文件与 `docs/` 保留。**下一项 VIB-55 确定性 StopEvaluator 与人工中断恢复**；先读其本地验收与 Linear 状态，承接当前 `DEBATE_ROUND_COMPLETE`、Dispute 和 EvidenceGap。Windows 原生 Python/uv/Alembic 入口继续禁止重试。

> **最新快照，2026-09-28 VIB-54 进行中**：分支 `codex/evidence-audit`，基线 HEAD 仍为 `a7fda2f`。本次工作区新增 `claim_normalization.py`、`0015_canonical_claim_dispute_gap`、CanonicalClaim/Member/Dispute/EvidenceGap 模型、Worker 首轮与辩论结束时的增量归并、CLI `normalize-claims` 和集成用例；更新 README 与本地任务记录。VIB-54 在 Linear 已置 In Progress，**尚未验收/提交**。`git diff --check` 通过；0015 迁移、Alembic check、Ruff、后端测试均未完成。自动审批拒绝了将整个仓库挂载给已有第三方 Linux 镜像的命令（项目内容暴露风险），明确要求不要换方式绕过；Windows 本机 Python/uv/Alembic 入口依旧禁止重试，Ruff 原生可执行文件长时间无输出后已中止。隔离 PostgreSQL 容器可访问，已创建空的 `tcm_vib54_test` 数据库，未迁移。原有未跟踪 `AGENTS.md`、本文件和 `docs/` 均保留。**下一条操作**：在获准的可信隔离环境验证 0015 迁移与 `alembic check`，按知识发布→研究集成顺序及完整套件检查失败/skip，修复后再决定 VIB-54 完成与提交；其间复核当前争议记录中正反证据的语义和旧审计重放行为。

> **最新快照，2026-09-28 VIB-52 完成**：分支 `codex/evidence-audit`，HEAD `a7fda2f`（Worker 自动执行一轮审计→Critic→再检索→Rebuttal→修订审计，迁移 `0014`）。独立 Docker PostgreSQL 测试库已升级到 `0014`；另一隔离库完成 `0014` 升级→回退→再升级，`alembic check` 无差异。完整后端 **35 passed、0 skipped**，`ruff check src tests migrations` 与 `git diff --check` 通过。测试容器使用 `psycopg2`，项目声明的 `psycopg` 和真实云模型质量尚未在本次验证。VIB-52 与 E8 父任务 VIB-44 均已在 Linear Done 并有验收评论；此前 VIB-50/51 也已 Done。**下一项：先读 VIB-53 父任务，再实施 VIB-54 CanonicalClaim/Dispute/EvidenceGap**。业务代码已提交，原有未跟踪 `AGENTS.md`、本文件和 `docs/` 保留。Windows 原生 Python/Alembic/uv 曾触发错误弹窗，不要换入口重试；继续使用隔离 Linux 容器。

> **最新快照，2026-09-28**：分支 `codex/evidence-audit`，HEAD `e326916`（VIB-51 Rebuttal/追加 Claim/重新审计；前置 VIB-50 为 `7921585`）。VIB-50/51 均已在 Linear 标记 Done 并写入验收评论。Docker 中的独立 PostgreSQL 新库从空库升级到 `0011`，再升级到 `0013`，`alembic check` 无待执行迁移；知识发布＋研究集成测试在原测试库和新迁移库各 **7 passed、0 skipped**；后端 Ruff 与 `git diff --check` 通过。测试使用 Linux 镜像中的 `psycopg2`，项目声明的 `psycopg` 尚未在此容器中验证；Fake 模型测试不代表真实模型语义质量。**当前下一项 VIB-52 Worker 自动串联**；VIB-44 父任务仍进行中。业务代码已提交，保留原有未跟踪 `AGENTS.md`、本文件和 `docs/`。Windows Python/Alembic/uv 入口仍禁止重试，后续继续用隔离容器。

> 2026-09-28 接续更新：HEAD 仍为 `7921585`，分支 `codex/evidence-audit`。VIB-51 已静态复核并继续修改：`submit_rebuttal_output` 现在核对冻结的 Critique/原 Claim 内容、最近 AuditResult 与原 Claim 引用；研究集成用例补冻结后修改拒绝、幂等不重复写入、语义审计失败后恢复。后端完整 `ruff check src tests migrations` 与 `git diff --check` 通过。**Python 集成测试及本次迁移验证仍未运行**：先前 Windows Python/Alembic/uv 入口发生应用程序错误；本次 Docker daemon 不可用，尝试隐藏启动 Docker Desktop 后进程退出且 daemon 仍不可用；WSL 查询被拒绝。不要在 Windows 上换同运行时入口重试。未提交业务文件仍为 `README.md`、`backend/src/tcm_platform/{cli,debate_service}.py`、`backend/tests/test_research_integration.py`；另有原有 `AGENTS.md`、本文件、`docs/`，全部保留。Linear VIB-51 已改为 In Progress，并写入本次进展评论；**不要标 Done 或提交代码作为已验收**。下一条操作是在安全的独立环境完成 0011→0013 迁移和知识发布＋研究集成测试，检查失败与 skip，修复后提交并同步验收证据；VIB-50 的验收测试也待补。

> 2026-09-27 本次中断补记：用户要求结束本会话。VIB-51 已开始但**未完成、未运行新代码测试**。未提交改动为 `backend/src/tcm_platform/debate_service.py`（Rebuttal 冻结输入、严格输出校验、追加 Claim、修订审计入口）、`backend/src/tcm_platform/cli.py`（三个调试命令）、`backend/tests/test_research_integration.py`（新增 Rebuttal/修订断言）、`README.md`，以及原有未提交的 `AGENTS.md`、本文件、`docs/`。本次仅在独立 `tcm-handoff-test` PostgreSQL 容器上完成空库升级至 `0013` 和 `alembic check`；**VIB-50/51 集成测试、ruff 与 VIB-51 代码验证均未执行**。Windows 执行 `alembic.exe`、`python.exe` 曾弹出 `0xc0000142`、`0xc06d007e` 应用程序错误；用户明确要求停止触发。此偏好已写入 `C:\Users\wangfeiyu\.codex\AGENTS.md`，下次不要以其他 Python/Alembic/uv 入口反复重试。下一步先静态复核上述未提交代码，在可确认不会弹窗的独立环境验证迁移与研究集成测试；依据结果修复并完成 VIB-51，再同步 Linear。Linear 核对时 VIB-50 仍为 In Progress、VIB-51 仍为 Backlog，均无评论；本次未改状态。

> 新会话在本项目发送“继续”，根目录 AGENTS.md 会引导读取本文件。完整任务见 [开发任务与验收清单](docs/DEVELOPMENT_BACKLOG.md)。本文件用于直接进入开发，不要求重做总体规划。上面较早日期的补记是历史停点，均已由最新快照覆盖。

## 1 接手后先做什么

1. 在仓库根目录检查分支、HEAD、工作区改动，确认实际代码比本快照是否更新。
2. 阅读本文件第 2～5 节，再读准备承接的 Linear Issue 或本地任务清单。代码职责位置见第 6 节。
3. **当前承接项：VIB-60 来源、知识、证据与版本质量 API**。VIB-49 已在本地完成并提交至 `0c3a714`，Linear 同步因自动审批拒绝待明确授权；先按本地清单和最新可读 Issue 验收进入 VIB-60，保留原有交接资料。VIB-58 的 Windows 密钥实机验证待安全环境恢复。
4. 若当前 E8 文件仍由另一会话编辑，保留其改动并核对归属；可先承接 VIB-45 语料盘点或 VIB-72 需求矩阵。VIB-58/59 也能提前推进，但会涉及共享配置、模型或 API 文件，先明确编辑范围。
5. 独立 PostgreSQL 容器 `tcm-handoff-test` 已运行；`tcm_vib54_test` 与 `tcm_vib54_migration_test` 均在 `0019_local_session_api`，另有前次测试库。官方 Python 容器 `tcm-vib54-py` 只读挂载 `backend` 并使用 `psycopg`，可供接续验证；先确认 Docker 可访问和库名。**Windows 原生 Python/Alembic/uv 入口曾触发错误弹窗；不要再次启动这些入口试错。**

**接手完成的判据**：已确认当前代码快照、选择一个可执行 Issue、理解其验收条件、知道需要修改和验证的模块。完成这些即可开发，不再重复拆分整份路线。

本文件没有替后续会话授予发布、付费模型调用或部署权限；按当次用户请求和已有授权执行相应动作。

## 2 仓库、范围与信息来源

**当前覆盖**：HEAD `729b212`；预览库已迁移到 `0021`，VIB-49 的修订谱系已提交，完整后端 61 passed、0 skipped。以下表格中的 `7ed5368` 与 51 passed 是历史快照。

| 项目 | 内容 |
| --- | --- |
| 本机工作目录 | `D:\DevelopProject\videcoding\zhongyi` |
| Git 远程 | [wfy0224/tcm-research-platform](https://github.com/wfy0224/tcm-research-platform) |
| 核对时分支 | `codex/evidence-audit` |
| 核对时 HEAD | `7ed5368`：VIB-59 本地会话与 API 契约；前序 VIB-57 为 `86e3a5d` |
| Linear 项目 | [中医知识研究与临床推理平台](https://linear.app/vibecoding-demo/project/中医知识研究与临床推理平台-ff55cb340ab9)，项目标识 `P-VIB-2` |
| Linear 团队 | `Vibecoding-demo`，Issue 前缀 `VIB` |
| 在线路线 | [完整开发流程与实施计划](https://linear.app/vibecoding-demo/document/完整开发流程与实施计划-2026-09-27-43cfca6e9aba) |
| 离线任务 | [DEVELOPMENT_BACKLOG.md](docs/DEVELOPMENT_BACKLOG.md)：51 项索引、42 项新增任务的依赖与验收 |
| 本次验证范围 | 官方 Linux Python 容器中使用 `psycopg` 验证 `0019` 双隔离库升级、第二库回退/再升级与 `alembic check`；完整后端 51 passed、0 skipped；Ruff、前端构建与 `git diff --check` 通过；没有调用真实云模型 |

**当前 V1 只做 Stage 1A 知识底座与 Stage 1B 理论研究。** 古病案兼容 CaseRecord 是 Stage 1A 的数据接口要求；现代病例、临床辨证、患者处方和疗效规律不进入当前 V1 UI/API/领域实现。

根目录三份设计文档是需求和架构依据：

- `中医知识研究与临床推理平台_需求规格说明书_V1.docx`：功能范围、阶段划分、AC 验收编号。
- `中医理论辅助研究工具_V1_系统总体设计说明书_HLD.docx`：模块、边界、冻结上下文、可靠性和性能目标。
- `中医知识研究与临床推理平台_V1_系统详细设计说明书_LLD.docx`：可执行详细设计，重点第 4～8、11、17～18 章；开发 API/UI 时再读第 12～13 章。

需求与设计决定目标行为；源码和迁移决定实际实现；测试/运行结果决定是否已验证；Linear 决定工作安排。遇到差异记录到 VIB-72，不能单凭 README 标题或 Issue 状态判定整个阶段完成。

以下两段对话在编写时因没有 `read_thread` 工具而未读取：
- Codex：hostId `local`，threadId `01a0e1b6-0692-7c53-9d97-847ecef4f13f`。
- ChatGPT：conversationId `6ab7e3ae-8310-83e9-b137-117da1716a47`，标题“推荐中医大模型”。

若后续具备读取能力，先读取正文再引用其中决策；ChatGPT 可从 turnLimit=10 开始。该缺口已记录在 VIB-72，不阻止已明确范围内的 E8 工作。

## 3 当前交付状态

**VIB-58 当前状态**：既有预览迁移、治理索引与真实云检索已验证；Windows Credential Manager 的 Python 实机读写仍未验证，因此保持 In Progress。详见根目录最新快照和本地任务清单。

**VIB-49 当前状态**：本地验收通过。已验证修订比较、引用影响、历史切换门禁、Concept/Relation/Herb 追加修订、0022 历史引用清单、旧任务冻结 KV/Index，以及 0023 Release Snapshot 工件与恢复路径。Linear 仍 In Progress，进展评论同步被自动审批拒绝；Portable Backup/灾难恢复归 VIB-66。

| 范围 | 已有能力 | 状态边界 |
| --- | --- | --- |
| E0/E1，VIB-36/37 | FastAPI/React、PG/pgvector、Alembic/CI、CAS、事件哈希链、持久化 Job/租约/检查点 | Done；BackupRecord 是骨架，不等于真备份恢复 |
| E2/E3，VIB-38/39 | TXT/DOCX/文本 PDF、不可变来源修订、卷篇章节条段句、对齐与定位 | Done；扫描件仅 OCR_REQUIRED |
| E4/E5，VIB-40/41 | 实体/概念/关系/药物/方剂/Evidence 草稿；审核、QualityIssue、快照、双索引发布门禁 | Done；完整自动抽取、校订 UI、古病案双表示等另有补齐任务 |
| E6，VIB-42 | Exact/FTS/Vector、云端重排、只读检索页和证据详情、Golden Set 框架 | Done；结构/关系检索、真实评测集和断网降级待补齐 |
| E7，VIB-43 | 冻结任务、Planner、三角色首轮隔离、Claim Pool、Worker、暂停/恢复/取消、ModelInvocation | Linear Done；Worker 当前终点仍为 FIRST_ROUND_COMPLETE |
| E8，VIB-44 | `afe47f2` 的追加式审计；`7921585` 的 Critic/再检索；`e326916` 的 Rebuttal/修订；`a7fda2f` 的 Worker 串联 | E8 父任务与 VIB-50/51/52 均在 Linear Done；E9 争议、Judge 与报告待做 |
| E9.1，VIB-54 | CanonicalClaim/Member、Dispute、EvidenceGap 与 Worker 归并接入 | 已验证：完整后端 38 passed、0 skipped；0015 升级/回退、Alembic 差异与 Ruff 通过。跨断言语义关系保持保守；Judge/报告未做 |
| E9.2，VIB-55 | 冻结停止策略、可复算 StopEvaluation、多轮上限、人工中断与续跑 | 已验证：完整后端 40 passed、0 skipped；0016 升级/回退、Alembic 差异与 Ruff 通过。Judge/报告留给 VIB-56 |
| E9.3，VIB-56 | Judge 只读综合、五类结论、不可变 ResearchSynthesis/StructuredReport、报告成功后最终完成 | 已验证：完整后端 45 passed、0 skipped；0017 升级/回退、Alembic 差异与 Ruff 通过。Markdown/DOCX 导出留给 VIB-57 |
| E9.4，VIB-57 | 独立 Job/Artifact 派生 Markdown/DOCX、格式与版本幂等、失败重试、内部引用跳转 | 已验证：完整后端 48 passed、0 skipped；0018 升级/回退、Alembic 差异与 Ruff 通过；Word 渲染 4 页无版面缺陷。E9 父任务 VIB-53 Done；网页展示待 VIB-61/63 |
| API 基础，VIB-59 | 本地会话、安全命令边界、公开编号、Job/错误通用契约 | 已验证：完整后端 51 passed、0 skipped；0019 升级/回退、Alembic 差异、Ruff 与前端构建通过。桌面密钥接线待 VIB-70，业务写路由待 VIB-60/61 |

README 中 E7 标题仍写“进行中”，但 Linear 的 E7 Issue 已完成其首轮交付范围；以这里的能力边界理解差异。历史记录中的“30 项测试通过”等属于之前会话，不能冒充本次或当前工作区验证结果。

## 4 工作区与迁移

**最新覆盖**：HEAD `0c3a714`；新隔离库 `tcm_vib49_release_test` 与迁移库 `tcm_vib58_migration_test`、预览库 `tcm_preview_shanghanlun` 均已迁移到 `0023_release_snapshot`。预览库 0023 前备份 SHA256 `426ca71c0ece4326060fecda54d5e36a0d4ac1e7ed4462307c1da639b0da2078`；旧 0022/0021/0020 前备份及 CAS 备份仍保留。完整后端 61 passed、0 skipped，迁移往返、`alembic check`、Ruff 与 diff 检查通过；5173 预览健康 `schema=current`。原有未跟踪 `AGENTS.md`、本文件和 `docs/` 保留。下面旧版本快照由此覆盖。

**最新覆盖**：HEAD `7ed5368`；业务代码已提交，仍未跟踪的 `AGENTS.md`、`DEVELOPMENT_HANDOFF.md`、`docs/` 为既有本地交接资料，本次更新了后两者。测试库迁移链尾部现为 `0018_report_export → 0019_local_session_api`；两座隔离库均在 0019，生产库未迁移。下面 0014 与旧工作区叙述仅是历史记录。

**2026-09-28 VIB-57 当前覆盖说明**：业务代码已提交 `86e3a5d`，无未提交业务改动；原有未跟踪 `AGENTS.md`、本文件和 `docs/` 保留。迁移链尾部现在是 `0015_canonical_claim_dispute_gap → 0016_stop_review → 0017_judge_report → 0018_report_export`，`main.py:SCHEMA_REVISION` 为 `0018_report_export`。两座独立测试库均在 0018；正式或其他存量数据库升级前仍需先查 `alembic current`。下方 0014/0017 链尾与旧工作区段落仅为历史记录。

**2026-09-28 VIB-56 当前覆盖说明**：业务代码已提交 `d6479c2`，无未提交业务改动；原有未跟踪 `AGENTS.md`、本文件和 `docs/` 保留。实际迁移链尾部是 `0014_research_node_checkpoints → 0015_canonical_claim_dispute_gap → 0016_stop_review → 0017_judge_report`，`main.py:SCHEMA_REVISION` 为 `0017_judge_report`。两座独立测试库均在 0017；正式/其他存量数据库升级前仍需先查 `alembic current`。下方 0014 链尾和旧工作区段落仅为历史记录。

编写交接期间，另一会话将 E8.1 业务改动提交为 `792158584b3045f1004d49c140cbf7bdfc787ccd`（2026-09-27 21:22，提交信息 `VIB-50: complete critic evidence request retrieval`）。该提交包括：

- `README.md`、`cli.py`、`main.py`、`models.py`、`research_service.py` 和研究集成测试。
- 新增 `debate_service.py`、迁移 `0012_debate` 和 `0013_retrieval_request_unique`。
- 对已有 `0010_research_control*` 迁移的一处修改；检查存量数据库升级时需连同历史迁移核对。

本次开发前，业务工作区无未提交改动；原有未提交的是 `AGENTS.md`、`DEVELOPMENT_HANDOFF.md`、`docs/DEVELOPMENT_BACKLOG.md`。本次又修改了 `backend/src/tcm_platform/debate_service.py`、`backend/src/tcm_platform/cli.py`、`backend/tests/test_research_integration.py`、`README.md`，均未提交。后续接手先看实时 git status，保留这些改动。另一个 checkout 不会自动包含未提交文件。

**最新工作区覆盖说明**：上述 VIB-51 四个业务文件已提交为 `e326916`；当前剩余未跟踪的是原有 `AGENTS.md`、本文件和 `docs/`。不要把旧段落中的“未提交业务文件”当作当前状态。

**2026-09-28 再更新**：VIB-52 的 `README.md`、迁移 `0014`、Worker/审计/辩论服务、Job 恢复、模型和研究集成测试已提交 `a7fda2f`。当前业务工作区无未提交改动；保留原有未跟踪交接文件。

当前文件中的迁移链尾部为：

```text
0010_research_control
  → 0011_audit_result
  → 0012_debate
  → 0013_retrieval_request_unique
  → 0014_research_node_checkpoints
```

`0012` 增加 Critique/EvidenceRequest/Rebuttal 等；`0013` 为同一 EvidenceRequest 与 EvidenceRevision 的检索事件增加唯一约束；`0014` 允许同一 Job generation 的多条原子节点检查点并调整恢复判定。当前 `main.py:SCHEMA_REVISION` 为 `0014_research_node_checkpoints`。**仅独立测试库**已确认位于 `0014`；正式或其他存量数据库仍需先用 `alembic current` 检查。存量数据若存在重复事件，0013 唯一约束迁移需要处理方案，不能盲目删历史。

## 5 下一项开发的具体切入点

**最新下一步**：按原计划承接 VIB-60 来源、知识、证据与版本质量 API。先读 `docs/DEVELOPMENT_BACKLOG.md` VIB-60 及直接依赖、Linear 最新状态，再在 VIB-59 本地会话/公开编号/Job 合约上实现用户可操作的来源、知识审核和版本质量 API；不要重做已提交的 VIB-49 或把 Release Snapshot 当作 Portable Backup。VIB-49 本地验收已写入需求矩阵，Linear 同步被自动审批拒绝，待用户明确授权，勿绕过。VIB-58 Windows Credential Manager Python 实机读写待安全环境，研究 API 增量 `cadb7c8` 留给后续 VIB-61。

**VIB-58 并行验收**：Windows Credential Manager 实机验证不得运行会弹错的 Windows Python/uv 入口；真实云端预览需先在当次授权下迁移独立预览库到 0020、重建旧索引、运行 7 个真实检索问题并核对脱敏调用日志。未通过时不把 VIB-58 标 Done，也不绕过默认禁外发策略。

### VIB-58 模型网关治理与外发控制

承接 `docs/DEVELOPMENT_BACKLOG.md` 的 VIB-58 及 Linear 最新状态；检查 `cloud_models.py`、`research_runtime.py`、`retrieval.py`、`config.py` 和 `ModelInvocation`。目标是 complete/embed/rerank 的数据级别与来源授权、LOCAL_ONLY/fallback 禁止绕过、冻结 Prompt/Workflow/检索策略、密钥存储、长度/限流/熔断、重试及脱敏调用记录。不要自行切换默认模型或调用付费模型。先按应用调用链定位全部外发入口，再做可验证的统一门禁。VIB-59 的 API 契约已提交，不需重做；Desktop Main 密钥注入归 VIB-70。

### VIB-50 E8.1 已提交的前置能力

当前 `debate_service.py` 已有：

- `prepare_critic_round`：为首轮已审计 Claim 准备 Critic Run。
- `critic_visible_context`：构建 Critic 可见上下文。
- `submit_critic_output` / `execute_critic`：校验并持久化 Critique/EvidenceRequest。
- `retrieve_evidence_requests`：沿用冻结 Scope、KV/Index 与检索模型，调用正式检索，再经 `add_task_evidence` 登记证据和来源事件。

现有 CLI 已出现 `prepare-critic`、`run-critic`、`retrieve-evidence-requests`；测试中已有非法质疑整份拒绝、池外 Evidence 拒绝和重复再检索不重复事件的断言。这些代码已随 `7921585` 提交；2026-09-28 已通过隔离数据库的相关集成测试，Linear VIB-50 已同步 Done。

验收核对清单（供缺少历史验证记录时使用）：
1. 核验所有质疑目标属于本任务和本次可见已审计 Claim；输出非法时不部分提交。
2. 再检索只能由 EvidenceRequest 发起，不能扩大冻结范围；无结果也留下明确状态。
3. 重试、重复调用和数据库唯一约束一致；检查模型调用前后任务控制状态和冻结输入。
4. 验证 0011→0012→0013 升级、模型与 Schema 一致、相关集成测试实际执行而非跳过。
5. 留存提交/测试证据，再更新 VIB-50。保留 VIB-44 进行中，直到 VIB-51/52 也完成。

### VIB-51 E8.2 Rebuttal 与 Claim 修订

以现有 Rebuttal 表和 Claim/Audit 服务为基础，先对照 LLD 第 4.5、7.3、7.4、8 章确定合约。表存在不代表服务已经实现。

**2026-09-27 停点**：`debate_service.py` 已加入 `prepare_rebuttal_round`、`rebuttal_visible_context`、`submit_rebuttal_output`、`execute_rebuttal`、`audit_revised_claims`。合约要求每条可见 Critique 恰好一个回答，支持四种 action；REVISE 追加 `parent_claim_id` 指向旧 Claim 的新 Claim，原 Claim 内容不改。Rebuttal AgentRun 冻结 Critique、原 Claim、审计摘要和可见证据；提交时校验任务、模型、冻结版本、证据池及精确修订，整份响应在一个事务中提交。CLI 已增加 `prepare-rebuttal`、`run-rebuttal`、`audit-revised-claims`。`test_research_worker_resumes_from_frozen_task_and_checkpoints` 已加四种 action、池外/未知引用整份拒绝、重复提交、旧 Claim 保留和新 Claim 机械/语义审计断言。**这些新代码和测试尚未运行，也未静态复核完毕；不能宣称 VIB-51 完成。**

**2026-09-28 复核结果**：`submit_rebuttal_output` 已增加冻结的质疑/原 Claim 内容、最新审计 ID 和原证据引用核对；`test_research_worker_resumes_from_frozen_task_and_checkpoints` 已补原 Claim 变化整份拒绝、重复提交不重复写入、语义审计非法引用后保留 `PENDING_SEMANTIC` 并重试的断言。Ruff 与 diff 格式检查通过；数据库集成测试尚未执行，因此不能宣称 VIB-51 完成。Linear VIB-51 已同步为 In Progress 并记录进展；VIB-50 仍待补验收。

**2026-09-28 验收结果**：VIB-51 已提交 `e326916`；独立新测试库 `0011→0012→0013` 升级和 `alembic check` 通过，知识发布＋研究集成测试在原测试库与新迁移库各 7 passed、0 skipped，后端 Ruff 通过。Linear VIB-51 已同步 Done，AC-1B-03/04 的本地追踪见任务清单。测试使用 `psycopg2`，项目声明的 `psycopg` 与真实云模型效果未在本次验证。

建议实现顺序：
1. 定义严格 Rebuttal 输出合约及 ACCEPT/PARTIAL_ACCEPT/REJECT/REVISE 语义，关联准确 Critique 和目标 Claim。
2. 冻结本次输入快照和可见证据集，只允许引用任务证据池内且本次可见的精确修订。
3. REVISE 产生追加式 Claim 修订并保留旧版本，系统附加来源、角色、模型、Prompt、轮次等 provenance。
4. 对新修订重新执行机械审计与语义审计，保留 AuditResult 历史；未审修订不进入最终综合。
5. 补重试幂等、非法跨任务引用、非法部分输出、旧 Claim 不变及修订重新审计的验证，再提供 CLI 调试入口。

详细父子关系、前置条件与验收见本地任务清单 VIB-51。CanonicalClaim 的增量归并属于 VIB-54，应保留接口但不要把 E9 整体并入本项。

### VIB-52 E8.3 Worker 自动串联

现有 `research_worker.py:run_next_research_job` 在 FIRST_ROUND_COMPLETE 完成 Job。E8 目前可以通过 CLI 分段运行；下一步让 Worker 持久化驱动 Critique→Re-Retrieval→Rebuttal→Audit。

**2026-09-28 验收结果**：`a7fda2f` 将首轮 Claim 审计、Critic、EvidenceRequest 再检索、Rebuttal、修订 Claim 审计串成同一持久化 Job；业务写入与节点检查点同事务，终态为 `DEBATE_ROUND_COMPLETE`。独立测试库迁移 `0014` 升级/回退/再升级、`alembic check`、完整后端 35 passed、0 skipped，Ruff 通过。集成用例覆盖暂停、取消、租约失效、generation 变化、非法输出、重试不重复 Claim/Rebuttal；README 有 Fake 模型可回放入口。Linear VIB-52 和父任务 VIB-44 均 Done。

必须覆盖节点输入/提交/检查点/转移、暂停取消安全点、失租或 generation 变化后丢弃、崩溃恢复先 reconcile、重试无重复业务对象。首轮只执行一次。完整停止规则、Dispute、Judge 与 Report 留给 E9。

### 下一项 VIB-54 E9.1 CanonicalClaim、Dispute 与 EvidenceGap

**2026-09-28 验收结果**：`0015` 在新隔离库升级后 `alembic check` 无差异，另一库完成 `0014→0015→0014→0015`；官方 Python 3.11 容器使用声明的 `psycopg` 驱动，完整后端 38 passed、0 skipped。Ruff `--no-cache --ignore EXE002` 通过（Windows 文件挂载在 Linux 中都被误判可执行），`git diff --check` 通过。冲突、未验证缺口、重复归并、修订保留、时代/流派指纹和新审计覆盖旧争议的用例已执行。自动化只归并精确重复文本，跨断言语义关系等待明确输入；这项边界已写 README。下一项是 VIB-55，不把 Judge/Report 混入 VIB-54。

**2026-09-28 当前停点**：`backend/src/tcm_platform/claim_normalization.py:normalize_task_claims` 已实现保守重复归并与审计/质疑驱动的 Dispute/EvidenceGap；模型在 `models.py`，迁移 `0015`，Worker 在首轮审计和轮次结束处调用，CLI 暴露幂等重放。`test_research_integration.py` 新增冲突、缺口、重复归并与重放断言，`test_claim_normalization.py` 核对时代/流派边界。以上均未在数据库实际运行；先验证迁移/测试，特别核对 `_source_context` 的来源快照、两次 Worker 调用事务、争议正反证据来源和重放后状态。未提交业务文件见最新快照；不要按下段旧的“下一条操作”重新从零设计。

先读取本地任务清单的 VIB-53 父任务与 VIB-54 条目，核对 Linear 最新状态。以已审计的首轮/修订 Claim、Critique/Rebuttal 和来源证据为输入；增量归并时保留原 Claim、时代与流派边界，将矛盾与证据缺口持久化并可回放。VIB-55 停止规则和 VIB-56 Judge/Report 不并入此项。

**下一条具体操作**：读 `models.py` 中 Claim/AuditResult/Critique/Rebuttal 及现有研究状态，结合 LLD 7.3/7.6 明确 CanonicalClaim、Dispute、EvidenceGap 的字段、唯一键和溯源，再设计迁移与增量服务；先写覆盖冲突、无证据缺口、修订不覆盖旧 Claim 的集成用例。

### VIB-55 E9.2 停止判断与人工恢复

**2026-09-28 验收结果**：提交 `b7397d3`。`stop_service.py:WorkflowConfig` 在 `start_research_task` 冻结进执行上下文；`evaluate_stop` 从最新 AuditResult、当前轮 Critique、开放 Dispute/EvidenceGap 和已处理的人工复核形成持久化快照与哈希，`evaluate_snapshot` 可重算决策。`debate_service.py` 与 Worker 可按冻结上限执行多轮；`WAITING_HUMAN` 保存中断/恢复阶段和原因，原子完成 Job 释放租约，`resolve_human_review` 记录处理并重排同一 Job，续跑仅重算停止阶段。CLI 有 `--workflow-config`、`list-human-reviews`、`resolve-human-review`。迁移 `0016_stop_review` 在两座隔离测试库升级，第二库回退再升级；`alembic check` 无差异；完整后端 40 passed、0 skipped；Ruff 与 diff 检查通过。Fake 模型测试不代表真实云模型质量。

**2026-09-28 VIB-56 验收结果**：提交 `d6479c2`；`judge_service.py` 冻结经审计 Claim/Dispute/EvidenceGap/已审核 Evidence 的输入，Judge 只返回已有 Claim 与理由 ID 的分类。`0017_judge_report` 存储不可变 ResearchSynthesis 与 StructuredReport，Worker 将报告落库和任务最终完成放在同一事务；CLI `show-structured-report` 可读。两座隔离库升级，其中一座回退再升级；`alembic check` 无差异；完整后端 45 passed、0 skipped；Ruff 与 diff 检查通过。Linear VIB-56 Done 并有验收评论。Fake 模型用例不代表真实云模型质量。

**历史切入点：VIB-57（已完成）**。此前以 StructuredReport 为输入，设计独立 Markdown/DOCX 导出 Job、格式/版本指纹、可重试状态和 Artifact provenance；实现及验证结果见下节。当前 5173 前端仅检索/证据页，报告网页展示尚待 VIB-61/63。

### VIB-57 E9.4 报告导出与重试

**2026-09-28 验收结果**：提交 `86e3a5d`。`report_export.py` 用不可变 StructuredReport 与导出时冻结的 AgentRun/Audit/Critique/Rebuttal/Stop/HumanReview 过程快照生成 Markdown/DOCX；文件保留五类结论、原文引用、争议、缺口、研究过程与内部跳转，CLI 支持排队、处理、查看、保存。`0018_report_export` 记录格式/渲染版本、独立 Job/Artifact；同一版本重复请求幂等，渲染/登记失败只重试导出。两座隔离库升级，第二库 0017→0018→0017→0018；`alembic check` 无差异；完整后端 48 passed、0 skipped；Ruff 与 diff 检查通过。Word 渲染样本 4 页并逐页确认无截断和重叠。Linear VIB-57 与 E9 父任务 VIB-53 已同步 Done。样本用 Fake 模型，真实质量仍待 VIB-68。

**下一条具体操作：VIB-59**。先读本地清单 VIB-59 与 Linear 最新状态，对照 LLD 5、6、12.1/12.4；检查 `main.py` 现有 health/只读检索、CLI 服务入口和 `models.py` 的用户/权限基础。先实现 loopback bootstrap→HttpOnly session、精确 Origin/CSRF 与服务层 actor/能力边界，再定义 strict DTO、public ID、错误码、Idempotency-Key、ETag/If-Match 和长任务 202 合约，并用 API 集成用例验证。VIB-61 可随后暴露报告查询/导出下载，VIB-63 才能在网页展示研究时间线；当前 5173 页面仍只有检索/证据。VIB-58 模型网关独立但仍是正式运行前必做任务。

## 6 代码导航与固定约束

路径均相对于仓库根目录。

| 需要做什么 | 先读哪些文件 |
| --- | --- |
| 研究对象与引用不变量 | `backend/src/tcm_platform/models.py`、`research_service.py`、`enums.py` |
| Planner/首轮合约及调用 | `research_runtime.py`、`research_service.py` |
| 机械/语义审计 | `audit_service.py`、迁移 `0011_audit_result*` |
| 质疑/再检索/后续反驳 | `debate_service.py`、`research_service.py:add_task_evidence` |
| Job/控制/恢复 | `jobs.py`、`research_worker.py`、`research_service.py` |
| 云端模型与路由 | `cloud_models.py`、`config.py`；调用记录见研究运行时 |
| 导入/分段 | `source_import.py`、`parsing.py`、`segment_service.py`、`segmentation.py` |
| 知识校订/发布/检索 | `knowledge_service.py`、`knowledge_publish.py`、`retrieval.py`、`retrieval_benchmark.py` |
| API/CLI | `main.py`、`cli.py`；现有 HTTP 入口只有 health 和只读检索 |
| UI | `frontend/src/main.tsx`、`style.css`；目前是检索/证据页 |
| E8 回归 | `backend/tests/test_research_integration.py` |
| 迁移与 CI | `backend/migrations/versions/`、`.github/workflows/ci.yml` |

表中省略前缀的后端文件均位于 `backend/src/tcm_platform/`。

开发时保留这些不变量：
- Evidence 引用必须存在、审核状态允许、属于冻结知识版本、任务证据池和本 AgentRun Visible Set；任何一项失败，整份 Agent 输出拒绝。
- Published/Completed 对象通过新 Revision/Version 演进。AuditResult 是历史权威，Claim.audit_status 只是投影。
- 首轮角色在数据层隔离；Source/Evidence 内容是数据，不是工具权限或系统指令。
- 模型输出走 Syntax→Schema→Reference→Domain 校验，业务 ID 和 provenance 由后端分配。
- 外部模型调用与数据库短事务分开；业务、Event、Checkpoint 的提交需保持一致，提交前核验租约和任务状态。
- 知识与索引同时验证后原子切换 Active；研究任务固定自己的 KV/Index/模型等上下文。
- Judge 只消费经审计材料；五类语义审计中 NOT_VERIFIABLE 不等于 FALSE；合理争议无需多数票共识。
- 本地会话与服务端权限完成前，不直接把 CLI 写操作暴露成任意网页可调用的接口。

## 7 启动与验证

### 接手只读检查

在 PowerShell 中执行：

```powershell
Set-Location 'D:\DevelopProject\videcoding\zhongyi'
git status --short
git branch --show-current
git log -5 --oneline
git diff --stat
```

当前机器路径不同则替换工作目录。工具可用性用 `Get-Command uv,node,npm,docker` 检查；后端要求 Python ≥3.11，现有 CI 使用 Python 3.13、Node 22。

### 独立测试环境

集成测试会写数据库，部分会切换活动知识版本；不要指向真实资料库。以下创建独立 PG 容器，端口 55432。先用 `docker ps -a --filter name=tcm-handoff-test` 检查是否已有同名容器或其他会话使用；已有可用实例则复用，或选新的名称/端口，不删除旧实例。

```powershell
docker run --detach --name tcm-handoff-test --publish 127.0.0.1:55432:5432 --env POSTGRES_DB=tcm_handoff_test --env POSTGRES_USER=tcm_test --env POSTGRES_PASSWORD=tcm_test_only pgvector/pgvector:pg16
docker exec tcm-handoff-test pg_isready -U tcm_test -d tcm_handoff_test
```

等待 pg_isready 明确就绪后，在同一个 PowerShell 会话设置专用环境：

```powershell
Set-Location 'D:\DevelopProject\videcoding\zhongyi\backend'
$env:TCM_DATABASE_URL = 'postgresql+psycopg://tcm_test:tcm_test_only@127.0.0.1:55432/tcm_handoff_test'
$env:TCM_DATA_ROOT = Join-Path $env:TEMP 'tcm-handoff-test-data'
uv sync --extra dev --frozen
uv run alembic heads
uv run alembic current
uv run alembic upgrade head
uv run alembic check
uv run ruff check src tests migrations
uv run pytest -q -rs
```

以上凭据只是隔离测试示例，不是现有密钥。新建独立测试库可直接迁移；包含正式资料的环境需先做可恢复备份并核对迁移影响。测试结束后，该 shell 中的 TCM_DATABASE_URL 仍指向测试库；不要用它误操作真实资料。

**必须看 skip 原因。** 研究测试依赖已发布知识/索引；无迁移或无样本时会 pytest.skip。只跑研究文件不足以确认功能已验证。需定向检查 E8 时，可在同一次 pytest 中先运行会发布样本的知识测试，再运行研究测试：

```powershell
uv run pytest -q -rs tests/test_knowledge_publish_integration.py tests/test_research_integration.py
```

该知识测试使用 FakeEmbedder 创建、审核、建索引并发布测试 Evidence，研究测试复用其活动版本；仍需检查实际 skip 和失败结果。后续应把跨文件样本前置显式化为 fixture，避免依赖测试排序。合约测试用 Fake 模型验证流程，不代表真实模型语义质量。

前端验证：

```powershell
Set-Location 'D:\DevelopProject\videcoding\zhongyi\frontend'
npm ci
npm run build
```

### 开发服务与手工演示

日常开发环境使用根目录 `compose.yaml`，详细命令见 [README](README.md)。数据库迁移需先确认目标连接；已有真实资料时先备份。后端在 backend 目录启动：

```powershell
uv run uvicorn tcm_platform.main:app --host 127.0.0.1 --port 8000
```

前端在另一个终端的 frontend 目录执行 `npm run dev`，访问 `http://127.0.0.1:5173`。健康检查为 `http://127.0.0.1:8000/api/v1/system/health`。当前正常基础设施仍可能返回 DEGRADED；尚未完整实现正式工作流和 Supervisor，不能仅为 UI 好看改成 READY。

CLI 参数用 `uv run python -m tcm_platform.cli --help` 核对。公开样本从来源→分段→Evidence→人工审核→快照→建索引→激活→研究任务，完整例子见 README；不要从别的数据库复制 UUID。

E8 手工节点顺序是：首轮完成 → 对相关 Claim 做 mechanical/semantic audit → prepare-critic 返回 run_id → run-critic → retrieve-evidence-requests。后两个模型相关节点需要已有授权的模型配置；本交接不自动执行。

## 8 模型与数据边界

当前实现直接使用云端 API，不要求下载大模型：

- 检索 provider：`TCM_MODEL_PROVIDER=siliconflow`；密钥变量 `SILICONFLOW_API_KEY`；现有默认模型为 BAAI/bge-m3 与 BAAI/bge-reranker-v2-m3。
- 研究联调已有 Qwen/Qwen3-8B 路由，运行前显式配置 `TCM_RESEARCH_MODEL`。具体 provider 配置以 cloud_models.py 和 README 为准。
- DeepSeek 是显式可选路由。保持已有默认选择；新增付费调用按用户当次授权处理，历史“免费”描述不当作现行价格保证。
- 密钥留在环境或后续 OS Keychain；文档、测试夹具、日志和提交只记录变量名/secret_ref，不打印密钥。
- 生成、Embedding、Rerank 都可能外发文本。正式外发策略由 VIB-58 补齐；断网本地查询由 VIB-48 补齐。
- 当前首轮 Claim 和自动审计是待复核研究材料；Qwen 小样例曾出现超出原文的解释，真实模型效果需 VIB-68 的样本和专家评价。

## 9 做完如何交接

一个 Issue 达到完成标准时，记录：
1. 完成的行为和关联 Issue，修改文件与数据库/API/Agent Contract 变化。
2. 实际执行命令和结果，分别说明通过、失败、跳过、未验证部分及模型测试是否真实调用。
3. 可复核提交或 PR、迁移路径、剩余风险；保留无关工作区改动。
4. 更新 Linear 状态和验收证据；没有 Linear 工具时，写明待同步内容，不声称已同步。
5. 更新本文件的快照状态、未提交清单和下一项任务；写到具体函数/用例和下一条操作。只有任务范围或依赖变化时才更新本地任务清单。这个收尾动作是下一会话只发“继续”即可开发的前提。

VIB-50 完成不能把整个 E8 标 Done；E0–E7 的 Done 也不等于 Stage 1A/1B 验收。最终验收入口为 VIB-73/74。

## 10 新会话的使用方式

在 **同一个项目目录** 新开会话，直接发送：

```text
继续
```

根目录 AGENTS.md 会引导接手会话读取本文件、简短核对最新差异，再进入上述下一项任务。无需再次提供项目背景或粘贴长指令。

默认下一步是 VIB-54 CanonicalClaim、Dispute 与 EvidenceGap：先读 VIB-53 父任务和 VIB-54 验收，再从已审计 E8 材料设计增量归并与争议对象。E8/VIB-44 已完成，E9 的停止规则、Judge 和最终报告另按子任务推进。

此自动入口适用于打开本仓库的会话；与该项目无关的空白会话没有自动定位仓库的上下文。换机器或创建全新 checkout 时，需要把这三份文件一并带过去。
