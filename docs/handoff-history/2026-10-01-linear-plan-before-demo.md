# 历史规划：2026-09-27 Linear 原计划

> 已于 2026-10-01 被客户演示优先计划替代。仅供追溯，不是执行队列。

# 完整开发流程与实施计划

本计划将已有交付、当前 V1 剩余工作及后续产品路线统一到一个 Linear 项目。当前开发范围仍为第一阶段 A 知识底座与第一阶段 B 理论研究；病例、临床方药和疗效规律属于后续阶段。计划基线日期：2026-09-27。

## 1 依据与核对边界

依据仓库中的《中医知识研究与临床推理平台\_需求规格说明书\_V1》《中医理论辅助研究工具\_V1\_系统总体设计说明书\_HLD》《中医知识研究与临床推理平台\_V1\_系统详细设计说明书\_LLD》，以及 README、代码、迁移、CI 和 Linear 既有记录。

源码：[tcm-research-platform](<https://github.com/wfy0224/tcm-research-platform>)。核对时本地分支 codex/evidence-audit，HEAD 为 afe47f2；存在 0012_debate、debate_service.py 及相关未提交修改。本次只制定计划和更新 Linear，不提交或改写现有源码、不迁移数据库、不调用模型，也未重新运行测试。既有测试通过记录是之前 Issue 的历史证据。

两段关联对话尚未读取：Codex chat 01a0e1b6-0692-7c53-9d97-847ecef4f13f 与 ChatGPT conversation 6ab7e3ae-8310-83e9-b137-117da1716a47。本次环境未提供 read_thread；没有依据标题推断其中的模型选择或其他决策。将补充核对纳入 [VIB-72 E11.1 需求追踪矩阵、设计差异与决策闭环](<https://linear.app/vibecoding-demo/issue/VIB-72/e111-%E9%9C%80%E6%B1%82%E8%BF%BD%E8%B8%AA%E7%9F%A9%E9%98%B5%E8%AE%BE%E8%AE%A1%E5%B7%AE%E5%BC%82%E4%B8%8E%E5%86%B3%E7%AD%96%E9%97%AD%E7%8E%AF>)；补充对话后如有差异，更新计划并保留决策记录。

## 2 当前进展

| 已有工作 | 状态与证据 | 尚不代表完成的范围 |
| -- | -- | -- |
| E0/E1 工程与运行基础 | [VIB-36 E0 工程骨架与运行环境](<https://linear.app/vibecoding-demo/issue/VIB-36/e0-%E5%B7%A5%E7%A8%8B%E9%AA%A8%E6%9E%B6%E4%B8%8E%E8%BF%90%E8%A1%8C%E7%8E%AF%E5%A2%83>)、[VIB-37 E1 知识底座与可追溯任务](<https://linear.app/vibecoding-demo/issue/VIB-37/e1-%E7%9F%A5%E8%AF%86%E5%BA%95%E5%BA%A7%E4%B8%8E%E5%8F%AF%E8%BF%BD%E6%BA%AF%E4%BB%BB%E5%8A%A1>) 已 Done；FastAPI/React/PG、CAS、EventLog、持久化 Job | 完整桌面生命周期、正式备份恢复、安全及安装交付 |
| E2/E3 来源与文本 | [VIB-38 E2 文献来源导入与解析](<https://linear.app/vibecoding-demo/issue/VIB-38/e2-%E6%96%87%E7%8C%AE%E6%9D%A5%E6%BA%90%E5%AF%BC%E5%85%A5%E4%B8%8E%E8%A7%A3%E6%9E%90>)、[VIB-39 E3 结构化文本分段与版本对齐](<https://linear.app/vibecoding-demo/issue/VIB-39/e3-%E7%BB%93%E6%9E%84%E5%8C%96%E6%96%87%E6%9C%AC%E5%88%86%E6%AE%B5%E4%B8%8E%E7%89%88%E6%9C%AC%E5%AF%B9%E9%BD%90>) 已 Done；TXT/DOCX/文本 PDF、层级分段、修订对齐 | OCR 执行、真实语料入库与古病案双表示 |
| E4/E5 知识与发布 | [VIB-40 E4 实体、概念、关系、方剂与证据建模](<https://linear.app/vibecoding-demo/issue/VIB-40/e4-%E5%AE%9E%E4%BD%93%E6%A6%82%E5%BF%B5%E5%85%B3%E7%B3%BB%E6%96%B9%E5%89%82%E4%B8%8E%E8%AF%81%E6%8D%AE%E5%BB%BA%E6%A8%A1>)、[VIB-41 E5 人工校订、质量问题与知识发布门禁](<https://linear.app/vibecoding-demo/issue/VIB-41/e5-%E4%BA%BA%E5%B7%A5%E6%A0%A1%E8%AE%A2%E8%B4%A8%E9%87%8F%E9%97%AE%E9%A2%98%E4%B8%8E%E7%9F%A5%E8%AF%86%E5%8F%91%E5%B8%83%E9%97%A8%E7%A6%81>) 已 Done；实体/关系/方剂/Evidence 草稿、审核质量门禁、知识快照与索引切换 | 自动候选抽取、完整校订 UI、结构查询与真恢复 |
| E6 检索 | [VIB-42 E6 全文、向量与混合检索](<https://linear.app/vibecoding-demo/issue/VIB-42/e6-%E5%85%A8%E6%96%87%E5%90%91%E9%87%8F%E4%B8%8E%E6%B7%B7%E5%90%88%E6%A3%80%E7%B4%A2>) 已 Done；Exact/FTS/Vector、云端重排、证据查看和评测框架 | 正式 Golden Set、结构/关系通道、断网降级和完整知识工作区 |
| E7 首轮研究 | [VIB-43 E7 研究任务运行时、Agent 合约与首轮独立研究](<https://linear.app/vibecoding-demo/issue/VIB-43/e7-%E7%A0%94%E7%A9%B6%E4%BB%BB%E5%8A%A1%E8%BF%90%E8%A1%8C%E6%97%B6agent-%E5%90%88%E7%BA%A6%E4%B8%8E%E9%A6%96%E8%BD%AE%E7%8B%AC%E7%AB%8B%E7%A0%94%E7%A9%B6>) 已 Done；冻结上下文、Planner、首轮隔离、租约恢复与控制 | Worker 尚在 FIRST_ROUND_COMPLETE 结束；完整研究报告未完成 |
| E8 审计纠错 | [VIB-44 E8 Claim 证据审计与质疑纠错闭环](<https://linear.app/vibecoding-demo/issue/VIB-44/e8-claim-%E8%AF%81%E6%8D%AE%E5%AE%A1%E8%AE%A1%E4%B8%8E%E8%B4%A8%E7%96%91%E7%BA%A0%E9%94%99%E9%97%AD%E7%8E%AF>) 进行中；afe47f2 实现追加式机械与语义审计 | Critic/再检索工作区改动待完成验证；Rebuttal 与 Worker 闭环待做 |

保留 E0–E7 的既有 Done 状态；新增任务承接设计要求的缺口，不将已有 Issue 重开或重复建设。M0 是工程交付基线，不是 Stage 1A/1B 整体验收。任务数量及父子任务数量不能直接换算完成百分比。

## 3 里程碑与退出条件

| 里程碑 | 交付及退出条件 |
| -- | -- |
| M0 已交付 E0–E7 | 归档 8 项既有完成记录及实现证据 |
| M1 知识底座补齐 | 真实语料/OCR 决策、候选抽取、古病案双表示、结构检索与校订版本，具备 AC-1A 后端能力 |
| M2 理论研究闭环 E8–E9 | 质疑→再检索→反驳→审计→争议→停止规则→Judge→结构化报告，含导出重试 |
| M3 API 与工作台 | 本地会话、业务 API、SSE 和知识/研究/任务/质量/审计备份/设置界面；核心流程无需 CLI |
| M4 运行可靠性 E10 | 真恢复、故障注入、安全、真实语料和模型评测、桌面安装升级通过 |
| M5 正式验收 E11 | AC-1A/1B 逐项留证；专家抽样、版本冻结、发布与交接完成 |
| M6 阶段 2A | 复用古病案、现代病例、身份分离、时间线和审计，AC-2A-01～06 |
| M7 阶段 2B | 多流派候选、可解释排序、独立风险门禁、医师确认与临床报告，AC-2B-01～08 |
| M8 阶段 3 | 随访与归因、单例假设、多例复现和规律治理，AC-3-01～08 |

## 4 执行顺序与关键依赖

核心研究路径：E7 → [VIB-44 E8 Claim 证据审计与质疑纠错闭环](<https://linear.app/vibecoding-demo/issue/VIB-44/e8-claim-%E8%AF%81%E6%8D%AE%E5%AE%A1%E8%AE%A1%E4%B8%8E%E8%B4%A8%E7%96%91%E7%BA%A0%E9%94%99%E9%97%AD%E7%8E%AF>) → [VIB-53 E9 争议、停止规则、Judge 与结构化报告](<https://linear.app/vibecoding-demo/issue/VIB-53/e9-%E4%BA%89%E8%AE%AE%E5%81%9C%E6%AD%A2%E8%A7%84%E5%88%99judge-%E4%B8%8E%E7%BB%93%E6%9E%84%E5%8C%96%E6%8A%A5%E5%91%8A>) → [VIB-65 E10 恢复、安全、性能、备份与桌面交付](<https://linear.app/vibecoding-demo/issue/VIB-65/e10-%E6%81%A2%E5%A4%8D%E5%AE%89%E5%85%A8%E6%80%A7%E8%83%BD%E5%A4%87%E4%BB%BD%E4%B8%8E%E6%A1%8C%E9%9D%A2%E4%BA%A4%E4%BB%98>) → [VIB-71 E11 Stage 1A/1B 正式验收与协议冻结](<https://linear.app/vibecoding-demo/issue/VIB-71/e11-stage-1a1b-%E6%AD%A3%E5%BC%8F%E9%AA%8C%E6%94%B6%E4%B8%8E%E5%8D%8F%E8%AE%AE%E5%86%BB%E7%BB%93>)。

产品交付同时依赖三条工作线：

1. 知识线：语料清单 → 抽取与古病案兼容 → 结构检索/校订修订 → 知识 API/UI → Stage 1A 验收。
2. 研究线：E8 → Dispute/StopEvaluator/人工中断 → Judge/报告 → 研究 API/UI → Stage 1B 验收。
3. 运行线：本地会话与外发策略 → 安全写 API；备份真恢复、全节点恢复、模型与性能评测 → 桌面交付 → 正式发布。

父任务的 blockedBy 表示整体完成门槛；准备性子任务按自身依赖可提前实施。例如 E11 下的追踪矩阵应现在启动，E10 的备份开发也不必等报告做完。

建议按以下交付批次推进，可按实际产能拆成多轮迭代，不把批次当作确定工期：

| 批次 | 重点 | 可评审成果 |
| -- | -- | -- |
| 当前批次 | 收尾 E8.1，开始语料盘点、本地会话/API 约定、模型治理、需求矩阵 | Critic/受限再检索提交，语料和接口合约，设计差异清单 |
| 下一批次 | Rebuttal 与 Worker 纠错闭环；知识抽取/校订/古病案；备份基础 | E8 演示、可审核知识与真恢复初测 |
| 闭环批次 | E9 争议/停止/人工处理/Judge/报告；知识 API 和界面 | 自动研究到结构化报告、知识工作区 |
| 产品批次 | 研究 API/SSE、研究工作区、任务/设置/审计备份页面 | 从导入到研究报告导出的产品 E2E |
| 加固批次 | 全链故障、安全与架构、Golden Set/模型资格/性能、桌面安装 | E10 验证记录、候选安装包、已知限制 |
| 发布批次 | AC-1A/1B、专家抽样、恢复演练、协议冻结与发布 | V1 发布包和交接文档 |
| 后续阶段 | 2A → 2B → 3，每阶段先设计再实现、评测、验收 | 分阶段批准的数据模型与产品能力 |

尚未给定开发人数、领域专家可用时间和上线日期，因此不编造日历、工作量或截止日；未擅自分配人员、Cycle 或 dueDate。建议每 1–2 周复盘依赖、验收证据和剩余工作量，再据实际吞吐确定排期。Linear 中 High 优先级用于当前关键路径与发布门槛；后续阶段默认 Backlog，不能挤占 V1。

## 5 每项任务的开发流程

1. **进入开发**：读取需求/设计引用、确认依赖和验收条件；复杂功能先明确 Domain/API/Agent Contract、状态转移和迁移方案。复用当前实现；差异记录在设计决策和追踪矩阵。
2. **实现**：按 Source → Knowledge/Evidence → Retrieval → Research/Debate/Audit → Judge/Report 依赖方向开发；业务对象与 Event 在事务内一致提交；外部模型调用不占长事务。
3. **验证**：按变更范围执行后端单元/真实 PostgreSQL 集成、strict 合约、迁移检查、前端构建和必要 E2E；涉及长任务、发布、外发或恢复时增加对应失败场景；不以模拟测试冒充真实模型效果。
4. **评审与集成**：记录提交/PR、设计或接口变化、迁移风险和测试证据；功能分支完成评审后集成，保持 CI 可重复。迁移前做快照，失败恢复不依赖破坏性 down migration。
5. **演示与关闭**：按验收条件演示，更新 README/设计差异/requirements.csv 和 Linear；只有验收证据齐全才 Done。父任务在所有必要交付完成后关闭。
6. **发布与维护**：形成 Release Manifest、备份与回退步骤、操作手册、已知问题；在真实语料和版本更新后做回归、专家抽样及影响说明。新模型、Prompt、知识与 Workflow 进入正式使用前重新过门禁。

## 6 模型与数据策略

当前代码已有硅基流动生成/Embedding/Rerank 路由，以及可选的 DeepSeek/百炼适配能力。本规划沿用已有接入基础，不根据尚未读到的模型推荐对话引入新供应商，不把 README 中历史“免费”描述视为未来定价保证，不发起任何付费调用。

[VIB-58 V1 模型网关治理、冻结策略与统一外发控制](<https://linear.app/vibecoding-demo/issue/VIB-58/v1-%E6%A8%A1%E5%9E%8B%E7%BD%91%E5%85%B3%E6%B2%BB%E7%90%86%E5%86%BB%E7%BB%93%E7%AD%96%E7%95%A5%E4%B8%8E%E7%BB%9F%E4%B8%80%E5%A4%96%E5%8F%91%E6%8E%A7%E5%88%B6>) 负责完整 ModelEndpoint/ModelVersion/ModelPolicy、冻结路由与外发策略；[VIB-68 E10.3 真实 Golden Set、模型资格与性能评测](<https://linear.app/vibecoding-demo/issue/VIB-68/e103-%E7%9C%9F%E5%AE%9E-golden-set%E6%A8%A1%E5%9E%8B%E8%B5%84%E6%A0%BC%E4%B8%8E%E6%80%A7%E8%83%BD%E8%AF%84%E6%B5%8B>) 负责按角色和真实样本确定正式模型资格、质量、时延与成本。协议通过不等于语义可靠；小模型曾扩写无证据解释这一历史问题应进入回归集。Embedding 维度和索引配置绑定版本；更换模型必须重建并验证相应索引，不能静默切换已有任务。

云端生成与本地知识可读可检索是不同能力：保留当前云端接入，同时实现断网的浏览/Exact/FTS/结构检索降级，不强制下载本地大模型。complete、embed 和 rerank 都受外发规则约束；未来真实病例身份默认不进入模型上下文。

初始语料与专家标注是交付依赖。扫描件出现时 OCR 升为必须完成；若首批不含扫描件，保留 OCR_REQUIRED 和人工处理路径并记录延期依据。检索准确率、召回率和模型效果阈值在真实基线后冻结，不杜撰百分比。

## 7 发布门槛

必须满足：非法 Evidence 引用率为 0；已发布关键证据可定位率为 100%；首轮隔离；Judge 不创造未经审计的新结论；合理争议可保留；旧报告和冻结任务不随新版本静默变化；已提交节点恢复不重复写业务对象；发布失败不切换 Active；事件哈希链可校验；备份可在临时环境真实恢复后安全切换。

性能使用 HLD 初始目标作为测量起点：十万级精确/关键词和结构查询 P95 ≤1s，混合检索不含远程模型 P95 ≤3s，Evidence 详情 P95 ≤500ms，创建任务 ≤500ms，暂停/取消请求响应 ≤1s，冷启动至基础知识可读目标 ≤15s。它们是待目标机器校准的工程目标，不是本次已测结果；远程调用时延应单独记录。

Stage 1A 验收由 [VIB-73 E11.2 Stage 1A 知识底座验收](<https://linear.app/vibecoding-demo/issue/VIB-73/e112-stage-1a-%E7%9F%A5%E8%AF%86%E5%BA%95%E5%BA%A7%E9%AA%8C%E6%94%B6>) 负责；Stage 1B 与发布由 [VIB-74 E11.3 Stage 1B 验收、V1 发布与交接](<https://linear.app/vibecoding-demo/issue/VIB-74/e113-stage-1b-%E9%AA%8C%E6%94%B6v1-%E5%8F%91%E5%B8%83%E4%B8%8E%E4%BA%A4%E6%8E%A5>) 负责。后续临床和疗效阶段必须先完成各自详细设计、数据权限及领域评审，再执行需求中对应 AC 门禁。

## 8 风险与待决事项

| 事项 | 当前处理 | 跟踪 |
| -- | -- | -- |
| 关联对话缺失 | 不推断其结论，补读后核对模型及范围决策 | [VIB-72 E11.1 需求追踪矩阵、设计差异与决策闭环](<https://linear.app/vibecoding-demo/issue/VIB-72/e111-%E9%9C%80%E6%B1%82%E8%BF%BD%E8%B8%AA%E7%9F%A9%E9%98%B5%E8%AE%BE%E8%AE%A1%E5%B7%AE%E5%BC%82%E4%B8%8E%E5%86%B3%E7%AD%96%E9%97%AD%E7%8E%AF>) |
| 真实语料/扫描件/授权未知 | 先盘点，决定 OCR 和导入范围 | [VIB-45 V1 初始语料清单、来源授权与 OCR 实施决策](<https://linear.app/vibecoding-demo/issue/VIB-45/v1-%E5%88%9D%E5%A7%8B%E8%AF%AD%E6%96%99%E6%B8%85%E5%8D%95%E6%9D%A5%E6%BA%90%E6%8E%88%E6%9D%83%E4%B8%8E-ocr-%E5%AE%9E%E6%96%BD%E5%86%B3%E7%AD%96>) |
| 原型与完整产品差距 | CLI 能力与 API/UI/桌面验收分开跟踪 | [VIB-59 V1 本地会话、权限边界与 API 通用合约](<https://linear.app/vibecoding-demo/issue/VIB-59/v1-%E6%9C%AC%E5%9C%B0%E4%BC%9A%E8%AF%9D%E6%9D%83%E9%99%90%E8%BE%B9%E7%95%8C%E4%B8%8E-api-%E9%80%9A%E7%94%A8%E5%90%88%E7%BA%A6>)、[VIB-70 E10.5 Desktop Supervisor、安装升级与降级运行](<https://linear.app/vibecoding-demo/issue/VIB-70/e105-desktop-supervisor%E5%AE%89%E8%A3%85%E5%8D%87%E7%BA%A7%E4%B8%8E%E9%99%8D%E7%BA%A7%E8%BF%90%E8%A1%8C>) |
| 云端接口与断网需求 | 统一外发策略，提供本地检索降级 | [VIB-58 V1 模型网关治理、冻结策略与统一外发控制](<https://linear.app/vibecoding-demo/issue/VIB-58/v1-%E6%A8%A1%E5%9E%8B%E7%BD%91%E5%85%B3%E6%B2%BB%E7%90%86%E5%86%BB%E7%BB%93%E7%AD%96%E7%95%A5%E4%B8%8E%E7%BB%9F%E4%B8%80%E5%A4%96%E5%8F%91%E6%8E%A7%E5%88%B6>)、[VIB-48 V1 结构与关系检索、查询规范化及断网降级](<https://linear.app/vibecoding-demo/issue/VIB-48/v1-%E7%BB%93%E6%9E%84%E4%B8%8E%E5%85%B3%E7%B3%BB%E6%A3%80%E7%B4%A2%E6%9F%A5%E8%AF%A2%E8%A7%84%E8%8C%83%E5%8C%96%E5%8F%8A%E6%96%AD%E7%BD%91%E9%99%8D%E7%BA%A7>) |
| 样例与正式研究质量 | 真实 Golden Set、反证集、专家抽样和版本化基线 | [VIB-68 E10.3 真实 Golden Set、模型资格与性能评测](<https://linear.app/vibecoding-demo/issue/VIB-68/e103-%E7%9C%9F%E5%AE%9E-golden-set%E6%A8%A1%E5%9E%8B%E8%B5%84%E6%A0%BC%E4%B8%8E%E6%80%A7%E8%83%BD%E8%AF%84%E6%B5%8B>) |
| 备份只有模型骨架 | 必须实际 restore，成功后才能标记可恢复 | [VIB-66 E10.1 加密备份、临时恢复验证与发布迁移快照](<https://linear.app/vibecoding-demo/issue/VIB-66/e101-%E5%8A%A0%E5%AF%86%E5%A4%87%E4%BB%BD%E4%B8%B4%E6%97%B6%E6%81%A2%E5%A4%8D%E9%AA%8C%E8%AF%81%E4%B8%8E%E5%8F%91%E5%B8%83%E8%BF%81%E7%A7%BB%E5%BF%AB%E7%85%A7>) |
| 需求附录与正文阶段划分不完全一致 | 本路线采用需求 3/15 总览；临床/疗效均不进入 V1 | [VIB-72 E11.1 需求追踪矩阵、设计差异与决策闭环](<https://linear.app/vibecoding-demo/issue/VIB-72/e111-%E9%9C%80%E6%B1%82%E8%BF%BD%E8%B8%AA%E7%9F%A9%E9%98%B5%E8%AE%BE%E8%AE%A1%E5%B7%AE%E5%BC%82%E4%B8%8E%E5%86%B3%E7%AD%96%E9%97%AD%E7%8E%AF>) |
| 未明确产能和发布日期 | 使用逻辑批次与依赖，待实际估算再定日期 | 项目计划复盘 |

## 9 可执行任务索引

本次补充 42 项（当前 V1 30 项，后续阶段 12 项），保留原有 9 项，共 51 项；父子任务同时计数。任务中已写明范围、依据、验收条件、优先级、状态、里程碑和阻塞依赖。

### M1 知识底座验收补齐

* [VIB-45 V1 初始语料清单、来源授权与 OCR 实施决策](<https://linear.app/vibecoding-demo/issue/VIB-45/v1-%E5%88%9D%E5%A7%8B%E8%AF%AD%E6%96%99%E6%B8%85%E5%8D%95%E6%9D%A5%E6%BA%90%E6%8E%88%E6%9D%83%E4%B8%8E-ocr-%E5%AE%9E%E6%96%BD%E5%86%B3%E7%AD%96>)
* [VIB-46 V1 知识候选抽取、术语规范与方剂字段补齐](<https://linear.app/vibecoding-demo/issue/VIB-46/v1-%E7%9F%A5%E8%AF%86%E5%80%99%E9%80%89%E6%8A%BD%E5%8F%96%E6%9C%AF%E8%AF%AD%E8%A7%84%E8%8C%83%E4%B8%8E%E6%96%B9%E5%89%82%E5%AD%97%E6%AE%B5%E8%A1%A5%E9%BD%90>)
* [VIB-47 V1 古病案文献与 CaseRecord 兼容对象](<https://linear.app/vibecoding-demo/issue/VIB-47/v1-%E5%8F%A4%E7%97%85%E6%A1%88%E6%96%87%E7%8C%AE%E4%B8%8E-caserecord-%E5%85%BC%E5%AE%B9%E5%AF%B9%E8%B1%A1>)
* [VIB-48 V1 结构与关系检索、查询规范化及断网降级](<https://linear.app/vibecoding-demo/issue/VIB-48/v1-%E7%BB%93%E6%9E%84%E4%B8%8E%E5%85%B3%E7%B3%BB%E6%A3%80%E7%B4%A2%E6%9F%A5%E8%AF%A2%E8%A7%84%E8%8C%83%E5%8C%96%E5%8F%8A%E6%96%AD%E7%BD%91%E9%99%8D%E7%BA%A7>)
* [VIB-49 V1 校订修订、版本比较与历史版本切换补齐](<https://linear.app/vibecoding-demo/issue/VIB-49/v1-%E6%A0%A1%E8%AE%A2%E4%BF%AE%E8%AE%A2%E7%89%88%E6%9C%AC%E6%AF%94%E8%BE%83%E4%B8%8E%E5%8E%86%E5%8F%B2%E7%89%88%E6%9C%AC%E5%88%87%E6%8D%A2%E8%A1%A5%E9%BD%90>)

### M2 理论研究闭环 E8–E9

* [VIB-50 E8.1 完成 Critic、EvidenceRequest 与受限再检索](<https://linear.app/vibecoding-demo/issue/VIB-50/e81-%E5%AE%8C%E6%88%90-criticevidencerequest-%E4%B8%8E%E5%8F%97%E9%99%90%E5%86%8D%E6%A3%80%E7%B4%A2>)
* [VIB-51 E8.2 Rebuttal 与追加式 Claim 修订及重新审计](<https://linear.app/vibecoding-demo/issue/VIB-51/e82-rebuttal-%E4%B8%8E%E8%BF%BD%E5%8A%A0%E5%BC%8F-claim-%E4%BF%AE%E8%AE%A2%E5%8F%8A%E9%87%8D%E6%96%B0%E5%AE%A1%E8%AE%A1>)
* [VIB-52 E8.3 Worker 接入纠错闭环与节点幂等验证](<https://linear.app/vibecoding-demo/issue/VIB-52/e83-worker-%E6%8E%A5%E5%85%A5%E7%BA%A0%E9%94%99%E9%97%AD%E7%8E%AF%E4%B8%8E%E8%8A%82%E7%82%B9%E5%B9%82%E7%AD%89%E9%AA%8C%E8%AF%81>)
* [VIB-53 E9 争议、停止规则、Judge 与结构化报告](<https://linear.app/vibecoding-demo/issue/VIB-53/e9-%E4%BA%89%E8%AE%AE%E5%81%9C%E6%AD%A2%E8%A7%84%E5%88%99judge-%E4%B8%8E%E7%BB%93%E6%9E%84%E5%8C%96%E6%8A%A5%E5%91%8A>)
* [VIB-54 E9.1 CanonicalClaim、Dispute 与 EvidenceGap](<https://linear.app/vibecoding-demo/issue/VIB-54/e91-canonicalclaimdispute-%E4%B8%8E-evidencegap>)
* [VIB-55 E9.2 确定性 StopEvaluator 与人工中断恢复](<https://linear.app/vibecoding-demo/issue/VIB-55/e92-%E7%A1%AE%E5%AE%9A%E6%80%A7-stopevaluator-%E4%B8%8E%E4%BA%BA%E5%B7%A5%E4%B8%AD%E6%96%AD%E6%81%A2%E5%A4%8D>)
* [VIB-56 E9.3 Judge 综合与不可变 Structured Report](<https://linear.app/vibecoding-demo/issue/VIB-56/e93-judge-%E7%BB%BC%E5%90%88%E4%B8%8E%E4%B8%8D%E5%8F%AF%E5%8F%98-structured-report>)
* [VIB-57 E9.4 Markdown 与 DOCX 报告导出及重试](<https://linear.app/vibecoding-demo/issue/VIB-57/e94-markdown-%E4%B8%8E-docx-%E6%8A%A5%E5%91%8A%E5%AF%BC%E5%87%BA%E5%8F%8A%E9%87%8D%E8%AF%95>)

### M3 API 与完整工作台

* [VIB-58 V1 模型网关治理、冻结策略与统一外发控制](<https://linear.app/vibecoding-demo/issue/VIB-58/v1-%E6%A8%A1%E5%9E%8B%E7%BD%91%E5%85%B3%E6%B2%BB%E7%90%86%E5%86%BB%E7%BB%93%E7%AD%96%E7%95%A5%E4%B8%8E%E7%BB%9F%E4%B8%80%E5%A4%96%E5%8F%91%E6%8E%A7%E5%88%B6>)
* [VIB-59 V1 本地会话、权限边界与 API 通用合约](<https://linear.app/vibecoding-demo/issue/VIB-59/v1-%E6%9C%AC%E5%9C%B0%E4%BC%9A%E8%AF%9D%E6%9D%83%E9%99%90%E8%BE%B9%E7%95%8C%E4%B8%8E-api-%E9%80%9A%E7%94%A8%E5%90%88%E7%BA%A6>)
* [VIB-60 V1 来源、知识、证据与版本质量 API](<https://linear.app/vibecoding-demo/issue/VIB-60/v1-%E6%9D%A5%E6%BA%90%E7%9F%A5%E8%AF%86%E8%AF%81%E6%8D%AE%E4%B8%8E%E7%89%88%E6%9C%AC%E8%B4%A8%E9%87%8F-api>)
* [VIB-61 V1 研究控制、详情查询与 SSE 事件 API](<https://linear.app/vibecoding-demo/issue/VIB-61/v1-%E7%A0%94%E7%A9%B6%E6%8E%A7%E5%88%B6%E8%AF%A6%E6%83%85%E6%9F%A5%E8%AF%A2%E4%B8%8E-sse-%E4%BA%8B%E4%BB%B6-api>)
* [VIB-62 V1 知识工作区与统一 Evidence Drawer](<https://linear.app/vibecoding-demo/issue/VIB-62/v1-%E7%9F%A5%E8%AF%86%E5%B7%A5%E4%BD%9C%E5%8C%BA%E4%B8%8E%E7%BB%9F%E4%B8%80-evidence-drawer>)
* [VIB-63 V1 理论研究工作区与完整辩论时间线](<https://linear.app/vibecoding-demo/issue/VIB-63/v1-%E7%90%86%E8%AE%BA%E7%A0%94%E7%A9%B6%E5%B7%A5%E4%BD%9C%E5%8C%BA%E4%B8%8E%E5%AE%8C%E6%95%B4%E8%BE%A9%E8%AE%BA%E6%97%B6%E9%97%B4%E7%BA%BF>)
* [VIB-64 V1 任务中心、审计备份和系统设置工作区](<https://linear.app/vibecoding-demo/issue/VIB-64/v1-%E4%BB%BB%E5%8A%A1%E4%B8%AD%E5%BF%83%E5%AE%A1%E8%AE%A1%E5%A4%87%E4%BB%BD%E5%92%8C%E7%B3%BB%E7%BB%9F%E8%AE%BE%E7%BD%AE%E5%B7%A5%E4%BD%9C%E5%8C%BA>)

### M4 运行可靠性与交付 E10

* [VIB-65 E10 恢复、安全、性能、备份与桌面交付](<https://linear.app/vibecoding-demo/issue/VIB-65/e10-%E6%81%A2%E5%A4%8D%E5%AE%89%E5%85%A8%E6%80%A7%E8%83%BD%E5%A4%87%E4%BB%BD%E4%B8%8E%E6%A1%8C%E9%9D%A2%E4%BA%A4%E4%BB%98>)
* [VIB-66 E10.1 加密备份、临时恢复验证与发布迁移快照](<https://linear.app/vibecoding-demo/issue/VIB-66/e101-%E5%8A%A0%E5%AF%86%E5%A4%87%E4%BB%BD%E4%B8%B4%E6%97%B6%E6%81%A2%E5%A4%8D%E9%AA%8C%E8%AF%81%E4%B8%8E%E5%8F%91%E5%B8%83%E8%BF%81%E7%A7%BB%E5%BF%AB%E7%85%A7>)
* [VIB-67 E10.2 全研究链 NodeExecution 与故障恢复演练](<https://linear.app/vibecoding-demo/issue/VIB-67/e102-%E5%85%A8%E7%A0%94%E7%A9%B6%E9%93%BE-nodeexecution-%E4%B8%8E%E6%95%85%E9%9A%9C%E6%81%A2%E5%A4%8D%E6%BC%94%E7%BB%83>)
* [VIB-68 E10.3 真实 Golden Set、模型资格与性能评测](<https://linear.app/vibecoding-demo/issue/VIB-68/e103-%E7%9C%9F%E5%AE%9E-golden-set%E6%A8%A1%E5%9E%8B%E8%B5%84%E6%A0%BC%E4%B8%8E%E6%80%A7%E8%83%BD%E8%AF%84%E6%B5%8B>)
* [VIB-69 E10.4 安全、审计完整性与架构边界检查](<https://linear.app/vibecoding-demo/issue/VIB-69/e104-%E5%AE%89%E5%85%A8%E5%AE%A1%E8%AE%A1%E5%AE%8C%E6%95%B4%E6%80%A7%E4%B8%8E%E6%9E%B6%E6%9E%84%E8%BE%B9%E7%95%8C%E6%A3%80%E6%9F%A5>)
* [VIB-70 E10.5 Desktop Supervisor、安装升级与降级运行](<https://linear.app/vibecoding-demo/issue/VIB-70/e105-desktop-supervisor%E5%AE%89%E8%A3%85%E5%8D%87%E7%BA%A7%E4%B8%8E%E9%99%8D%E7%BA%A7%E8%BF%90%E8%A1%8C>)

### M5 V1 验收与协议冻结 E11

* [VIB-71 E11 Stage 1A/1B 正式验收与协议冻结](<https://linear.app/vibecoding-demo/issue/VIB-71/e11-stage-1a1b-%E6%AD%A3%E5%BC%8F%E9%AA%8C%E6%94%B6%E4%B8%8E%E5%8D%8F%E8%AE%AE%E5%86%BB%E7%BB%93>)
* [VIB-72 E11.1 需求追踪矩阵、设计差异与决策闭环](<https://linear.app/vibecoding-demo/issue/VIB-72/e111-%E9%9C%80%E6%B1%82%E8%BF%BD%E8%B8%AA%E7%9F%A9%E9%98%B5%E8%AE%BE%E8%AE%A1%E5%B7%AE%E5%BC%82%E4%B8%8E%E5%86%B3%E7%AD%96%E9%97%AD%E7%8E%AF>)
* [VIB-73 E11.2 Stage 1A 知识底座验收](<https://linear.app/vibecoding-demo/issue/VIB-73/e112-stage-1a-%E7%9F%A5%E8%AF%86%E5%BA%95%E5%BA%A7%E9%AA%8C%E6%94%B6>)
* [VIB-74 E11.3 Stage 1B 验收、V1 发布与交接](<https://linear.app/vibecoding-demo/issue/VIB-74/e113-stage-1b-%E9%AA%8C%E6%94%B6v1-%E5%8F%91%E5%B8%83%E4%B8%8E%E4%BA%A4%E6%8E%A5>)

### M6 后续阶段 2A 病例工作区

* [VIB-75 阶段 2A 病例工作区与隐私边界](<https://linear.app/vibecoding-demo/issue/VIB-75/%E9%98%B6%E6%AE%B5-2a-%E7%97%85%E4%BE%8B%E5%B7%A5%E4%BD%9C%E5%8C%BA%E4%B8%8E%E9%9A%90%E7%A7%81%E8%BE%B9%E7%95%8C>)
* [VIB-76 2A.1 病例领域设计与古病案复用](<https://linear.app/vibecoding-demo/issue/VIB-76/2a1-%E7%97%85%E4%BE%8B%E9%A2%86%E5%9F%9F%E8%AE%BE%E8%AE%A1%E4%B8%8E%E5%8F%A4%E7%97%85%E6%A1%88%E5%A4%8D%E7%94%A8>)
* [VIB-77 2A.2 现代病例录入、就诊时间线与补充版本](<https://linear.app/vibecoding-demo/issue/VIB-77/2a2-%E7%8E%B0%E4%BB%A3%E7%97%85%E4%BE%8B%E5%BD%95%E5%85%A5%E5%B0%B1%E8%AF%8A%E6%97%B6%E9%97%B4%E7%BA%BF%E4%B8%8E%E8%A1%A5%E5%85%85%E7%89%88%E6%9C%AC>)
* [VIB-78 2A.3 身份分离、病例权限与阶段验收](<https://linear.app/vibecoding-demo/issue/VIB-78/2a3-%E8%BA%AB%E4%BB%BD%E5%88%86%E7%A6%BB%E7%97%85%E4%BE%8B%E6%9D%83%E9%99%90%E4%B8%8E%E9%98%B6%E6%AE%B5%E9%AA%8C%E6%94%B6>)

### M7 后续阶段 2B 临床推理与方药策略

* [VIB-79 阶段 2B 临床推理、方药策略与医师确认](<https://linear.app/vibecoding-demo/issue/VIB-79/%E9%98%B6%E6%AE%B5-2b-%E4%B8%B4%E5%BA%8A%E6%8E%A8%E7%90%86%E6%96%B9%E8%8D%AF%E7%AD%96%E7%95%A5%E4%B8%8E%E5%8C%BB%E5%B8%88%E7%A1%AE%E8%AE%A4>)
* [VIB-80 2B.1 多流派推理、MatchScore 与相似病案](<https://linear.app/vibecoding-demo/issue/VIB-80/2b1-%E5%A4%9A%E6%B5%81%E6%B4%BE%E6%8E%A8%E7%90%86matchscore-%E4%B8%8E%E7%9B%B8%E4%BC%BC%E7%97%85%E6%A1%88>)
* [VIB-81 2B.2 方药候选与独立风险门禁](<https://linear.app/vibecoding-demo/issue/VIB-81/2b2-%E6%96%B9%E8%8D%AF%E5%80%99%E9%80%89%E4%B8%8E%E7%8B%AC%E7%AB%8B%E9%A3%8E%E9%99%A9%E9%97%A8%E7%A6%81>)
* [VIB-82 2B.3 医师确认签名、临床报告与阶段验收](<https://linear.app/vibecoding-demo/issue/VIB-82/2b3-%E5%8C%BB%E5%B8%88%E7%A1%AE%E8%AE%A4%E7%AD%BE%E5%90%8D%E4%B8%B4%E5%BA%8A%E6%8A%A5%E5%91%8A%E4%B8%8E%E9%98%B6%E6%AE%B5%E9%AA%8C%E6%94%B6>)

### M8 后续阶段 3 疗效反馈与规律研究

* [VIB-83 阶段 3 疗效反馈、假设演进与规律研究](<https://linear.app/vibecoding-demo/issue/VIB-83/%E9%98%B6%E6%AE%B5-3-%E7%96%97%E6%95%88%E5%8F%8D%E9%A6%88%E5%81%87%E8%AE%BE%E6%BC%94%E8%BF%9B%E4%B8%8E%E8%A7%84%E5%BE%8B%E7%A0%94%E7%A9%B6>)
* [VIB-84 3.1 随访 Outcome 与疗效归因](<https://linear.app/vibecoding-demo/issue/VIB-84/31-%E9%9A%8F%E8%AE%BF-outcome-%E4%B8%8E%E7%96%97%E6%95%88%E5%BD%92%E5%9B%A0>)
* [VIB-85 3.2 单例假设、多例复现与证据评审](<https://linear.app/vibecoding-demo/issue/VIB-85/32-%E5%8D%95%E4%BE%8B%E5%81%87%E8%AE%BE%E5%A4%9A%E4%BE%8B%E5%A4%8D%E7%8E%B0%E4%B8%8E%E8%AF%81%E6%8D%AE%E8%AF%84%E5%AE%A1>)
* [VIB-86 3.3 规律治理、方药优化反馈与阶段验收](<https://linear.app/vibecoding-demo/issue/VIB-86/33-%E8%A7%84%E5%BE%8B%E6%B2%BB%E7%90%86%E6%96%B9%E8%8D%AF%E4%BC%98%E5%8C%96%E5%8F%8D%E9%A6%88%E4%B8%8E%E9%98%B6%E6%AE%B5%E9%AA%8C%E6%94%B6>)

当前可开始/继续的入口：[VIB-50 E8.1 完成 Critic、EvidenceRequest 与受限再检索](<https://linear.app/vibecoding-demo/issue/VIB-50/e81-%E5%AE%8C%E6%88%90-criticevidencerequest-%E4%B8%8E%E5%8F%97%E9%99%90%E5%86%8D%E6%A3%80%E7%B4%A2>)、[VIB-45 V1 初始语料清单、来源授权与 OCR 实施决策](<https://linear.app/vibecoding-demo/issue/VIB-45/v1-%E5%88%9D%E5%A7%8B%E8%AF%AD%E6%96%99%E6%B8%85%E5%8D%95%E6%9D%A5%E6%BA%90%E6%8E%88%E6%9D%83%E4%B8%8E-ocr-%E5%AE%9E%E6%96%BD%E5%86%B3%E7%AD%96>)、[VIB-59 V1 本地会话、权限边界与 API 通用合约](<https://linear.app/vibecoding-demo/issue/VIB-59/v1-%E6%9C%AC%E5%9C%B0%E4%BC%9A%E8%AF%9D%E6%9D%83%E9%99%90%E8%BE%B9%E7%95%8C%E4%B8%8E-api-%E9%80%9A%E7%94%A8%E5%90%88%E7%BA%A6>)、[VIB-58 V1 模型网关治理、冻结策略与统一外发控制](<https://linear.app/vibecoding-demo/issue/VIB-58/v1-%E6%A8%A1%E5%9E%8B%E7%BD%91%E5%85%B3%E6%B2%BB%E7%90%86%E5%86%BB%E7%BB%93%E7%AD%96%E7%95%A5%E4%B8%8E%E7%BB%9F%E4%B8%80%E5%A4%96%E5%8F%91%E6%8E%A7%E5%88%B6>)、[VIB-72 E11.1 需求追踪矩阵、设计差异与决策闭环](<https://linear.app/vibecoding-demo/issue/VIB-72/e111-%E9%9C%80%E6%B1%82%E8%BF%BD%E8%B8%AA%E7%9F%A9%E9%98%B5%E8%AE%BE%E8%AE%A1%E5%B7%AE%E5%BC%82%E4%B8%8E%E5%86%B3%E7%AD%96%E9%97%AD%E7%8E%AF>)。
