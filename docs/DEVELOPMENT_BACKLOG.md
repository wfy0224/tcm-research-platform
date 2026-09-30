# 开发任务与验收清单

**2026-09-30 最新顺序**：VIB-45 本地完成（Linear 旧详细验收待授权同步）；VIB-46 方剂候选工程已补齐，真实 C02 与专家核对待补，仍 In Progress。VIB-48 结构/关系、本地降级/UI、多样性、质量分流及有限繁简/异体/自身历史别名查询扩展工程已实现，最新完整后端 **241 passed、0 failed、0 skipped**，Ruff/diff通过；无结构变更，未重复迁移往返，无前端变更，未重跑build/浏览器。本地及Linear仍 In Progress，真实依赖与VIB-68相关性评测保留。用户纠正接续顺序：先逐项补完VIB-46/48可执行的真实后端/本地环境验收，明确C02/专家/Windows环境及云调用的具体阻塞后再进入VIB-47；未执行验收不因流程精简而跳过。VIB-63/49/60/61 Done；VIB-62仍受VIB-46/48阻断，VIB-58 Windows密钥实机待安全环境。最新提交见根交接；以下早期进度为历史记录。

最新同步：VIB-59 本地会话与 API 通用合约已提交 `7ed5368` 并通过隔离验证；`0019_local_session_api` 往返迁移、`alembic check`、后端 51 passed、0 skipped、Ruff、前端构建均通过。Linear 最终状态见 VIB-59 小节。桌面壳接线待 VIB-70，来源与研究命令路由待 VIB-60/61，网页报告工作台待 VIB-63。此前 E9 基线提交为 `86e3a5d`。

接续更新：2026-09-28，VIB-54 已通过隔离库验收：`0015` 从 0014 升级、回退、再升级，`alembic check` 无差异；官方 Python 容器使用项目声明的 `psycopg` 驱动，完整后端 **38 passed、0 skipped**；Ruff 在 Windows 只读挂载下忽略 EXE002 误报后通过，`git diff --check` 通过。重复归并、冲突、缺口、原/修订 Claim 保留、时代/流派边界和重放用例均执行；真实模型质量不在此验收范围。下一项 VIB-55。

接续更新：2026-09-28，VIB-54 已在 Linear 置为 In Progress。工作区新增 CanonicalClaim/Member、Dispute、EvidenceGap 模型及 `0015` 迁移，Worker 在首轮审计后和辩论结束时增量规范化，CLI 可重放；新增重复断言、矛盾、缺口、来源时代/流派边界及幂等用例。`git diff --check` 已通过。**0015 迁移、后端测试和 Ruff 尚未完成验证**：自动审批拒绝了将整个仓库挂载给现有第三方 Linux 镜像的测试命令；Windows Python/uv 入口按本机错误弹窗规则禁止重试。VIB-54 不宣告完成；取得可信隔离运行环境后先跑迁移、检查差异、知识发布与研究集成及完整回归，再同步验收。

接续更新：2026-09-28，E8 父任务 VIB-44 及子任务 VIB-50/51/52 已在 Linear Done。VIB-52 提交 `a7fda2f` 将一轮审计、质疑、受限再检索、反驳与修订审计接入 Worker；独立 PostgreSQL 测试库升至 `0014`，`alembic check` 无差异，完整后端 35 passed、0 skipped，Ruff 通过。Linux 测试容器使用 `psycopg2`，项目声明的 `psycopg` 仍需在后续运行环境复核；Fake 模型测试不代表真实模型质量。下一项为 E9 的 VIB-54 CanonicalClaim/Dispute/EvidenceGap，先读 VIB-53 父任务。原“未提交代码”表述属于规划时背景。

本文件是 2026-09-27 的开发计划快照，供无法访问 Linear 的接手会话使用。先读仓库根目录的 [开发交接入口](../DEVELOPMENT_HANDOFF.md)，再按 Issue 阅读本文件对应小节。执行前以最新源码、验证结果和 Linear 为准；状态不是永久事实。

[Linear 完整计划](https://linear.app/vibecoding-demo/document/完整开发流程与实施计划-2026-09-27-43cfca6e9aba)

## 阶段与顺序

当前仅交付 Stage 1A 知识底座和 Stage 1B 理论研究。主线 E8 → E9 → E10 → E11；知识完善、本地会话、模型治理、备份等准备工作按各自依赖提前推进。父任务依赖表示整体验收门槛，不阻止准备性子任务按自身条件启动。

| 里程碑 | 出口 |
| --- | --- |
| M0 已交付工程基线 E0–E7 | 归档已完成的工程、知识底座、检索与首轮研究交付。Done 只表示各 Issue 已声明范围完成，不代表 Stage 1A/1B 整体验收。 |
| M1 知识底座验收补齐 | 补齐真实语料与 OCR 决策、候选抽取、古病案兼容对象、结构检索及知识修订。出口：具备 AC-1A-01～08 的后端能力；完整验收在 M5。 |
| M2 理论研究闭环 E8–E9 | Critic→EvidenceRequest→再检索→Rebuttal→Audit→Dispute→StopEvaluator→Judge→Structured Report；出口：全程可追溯，首轮草稿不充当最终报告。 |
| M3 API 与完整工作台 | 本地会话、版本化 API、SSE、知识与研究工作区、任务中心、版本质量、审计备份和设置；出口：用户无需 CLI 完成 V1 核心流程。 |
| M4 运行可靠性与交付 E10 | 真实备份恢复、全链路故障恢复、安全与架构约束、真实语料评测、桌面运行和安装包。出口：发布硬门禁通过并保存证据。 |
| M5 V1 验收与协议冻结 E11 | Stage 1A/1B 验收矩阵、专家抽样、迁移/恢复演练、Knowledge/Agent/Workflow v1 冻结、发布与交接。 |
| M6 后续阶段 2A 病例工作区 | V1 发布后再进入详细设计和实施。复用古病案、现代病例与时间线、身份分离和病例权限；AC-2A-01～06。 |
| M7 后续阶段 2B 临床推理与方药策略 | 依赖 2A 和临床领域评审。多流派候选、可解释排序、独立风险门禁、方药策略、医师确认与报告；AC-2B-01～08。 |
| M8 后续阶段 3 疗效反馈与规律研究 | 依赖 2B 验收及可用治疗结局。随访、归因、单例假设、多例验证、规律版本与人工审批；AC-3-01～08。 |

执行批次：E8/E9 已交付 → VIB-58 外发治理验收与知识补齐 → 知识 API/UI → 研究 API/SSE 和工作台 → E10 验证与桌面交付 → E11 验收发布 → 2A/2B/3。批次不是承诺工期；人力、日历和截止日尚未确认。

## 全量任务索引

共 51 项，包含父任务；状态以各 Issue 小节和 Linear 为准，旧汇总计数不再用于估算剩余轮次。新增计划项共 42 项，其中当前 V1 30 项、后续阶段 12 项。计数不能换算真实完成百分比。

| Issue | 内容 | 快照状态 | 父任务 | 里程碑 |
| --- | --- | --- | --- | --- |
| [VIB-36](https://linear.app/vibecoding-demo/issue/VIB-36/e0-工程骨架与运行环境) | E0 工程骨架与运行环境 | Done | — | M0 已交付工程基线 E0–E7 |
| [VIB-37](https://linear.app/vibecoding-demo/issue/VIB-37/e1-知识底座与可追溯任务) | E1 知识底座与可追溯任务 | Done | — | M0 已交付工程基线 E0–E7 |
| [VIB-38](https://linear.app/vibecoding-demo/issue/VIB-38/e2-文献来源导入与解析) | E2 文献来源导入与解析 | Done | — | M0 已交付工程基线 E0–E7 |
| [VIB-39](https://linear.app/vibecoding-demo/issue/VIB-39/e3-结构化文本分段与版本对齐) | E3 结构化文本分段与版本对齐 | Done | — | M0 已交付工程基线 E0–E7 |
| [VIB-40](https://linear.app/vibecoding-demo/issue/VIB-40/e4-实体概念关系方剂与证据建模) | E4 实体、概念、关系、方剂与证据建模 | Done | — | M0 已交付工程基线 E0–E7 |
| [VIB-41](https://linear.app/vibecoding-demo/issue/VIB-41/e5-人工校订质量问题与知识发布门禁) | E5 人工校订、质量问题与知识发布门禁 | Done | — | M0 已交付工程基线 E0–E7 |
| [VIB-42](https://linear.app/vibecoding-demo/issue/VIB-42/e6-全文向量与混合检索) | E6 全文、向量与混合检索 | Done | — | M0 已交付工程基线 E0–E7 |
| [VIB-43](https://linear.app/vibecoding-demo/issue/VIB-43/e7-研究任务运行时agent-合约与首轮独立研究) | E7 研究任务运行时、Agent 合约与首轮独立研究 | Done | — | M0 已交付工程基线 E0–E7 |
| [VIB-44](https://linear.app/vibecoding-demo/issue/VIB-44/e8-claim-证据审计与质疑纠错闭环) | E8 Claim 证据审计与质疑纠错闭环 | Done | — | M2 理论研究闭环 E8–E9 |
| [VIB-45](https://linear.app/vibecoding-demo/issue/VIB-45/v1-初始语料清单来源授权与-ocr-实施决策) | V1 初始语料清单、来源授权与 OCR 实施决策 | Todo | — | M1 知识底座验收补齐 |
| [VIB-46](https://linear.app/vibecoding-demo/issue/VIB-46/v1-知识候选抽取术语规范与方剂字段补齐) | V1 知识候选抽取、术语规范与方剂字段补齐 | In Progress | — | M1 知识底座验收补齐 |
| [VIB-47](https://linear.app/vibecoding-demo/issue/VIB-47/v1-古病案文献与-caserecord-兼容对象) | V1 古病案文献与 CaseRecord 兼容对象 | Backlog | — | M1 知识底座验收补齐 |
| [VIB-48](https://linear.app/vibecoding-demo/issue/VIB-48/v1-结构与关系检索查询规范化及断网降级) | V1 结构与关系检索、查询规范化及断网降级 | In Progress | — | M1 知识底座验收补齐 |
| [VIB-49](https://linear.app/vibecoding-demo/issue/VIB-49/v1-校订修订版本比较与历史版本切换补齐) | V1 校订修订、版本比较与历史版本切换补齐 | Done（本地及 Linear） | — | M1 知识底座验收补齐 |
| [VIB-50](https://linear.app/vibecoding-demo/issue/VIB-50/e81-完成-criticevidencerequest-与受限再检索) | E8.1 完成 Critic、EvidenceRequest 与受限再检索 | Done | VIB-44 | M2 理论研究闭环 E8–E9 |
| [VIB-51](https://linear.app/vibecoding-demo/issue/VIB-51/e82-rebuttal-与追加式-claim-修订及重新审计) | E8.2 Rebuttal 与追加式 Claim 修订及重新审计 | Done | VIB-44 | M2 理论研究闭环 E8–E9 |
| [VIB-52](https://linear.app/vibecoding-demo/issue/VIB-52/e83-worker-接入纠错闭环与节点幂等验证) | E8.3 Worker 接入纠错闭环与节点幂等验证 | Done | VIB-44 | M2 理论研究闭环 E8–E9 |
| [VIB-53](https://linear.app/vibecoding-demo/issue/VIB-53/e9-争议停止规则judge-与结构化报告) | E9 争议、停止规则、Judge 与结构化报告 | Done | — | M2 理论研究闭环 E8–E9 |
| [VIB-54](https://linear.app/vibecoding-demo/issue/VIB-54/e91-canonicalclaimdispute-与-evidencegap) | E9.1 CanonicalClaim、Dispute 与 EvidenceGap | Done | VIB-53 | M2 理论研究闭环 E8–E9 |
| [VIB-55](https://linear.app/vibecoding-demo/issue/VIB-55/e92-确定性-stopevaluator-与人工中断恢复) | E9.2 确定性 StopEvaluator 与人工中断恢复 | Done | VIB-53 | M2 理论研究闭环 E8–E9 |
| [VIB-56](https://linear.app/vibecoding-demo/issue/VIB-56/e93-judge-综合与不可变-structured-report) | E9.3 Judge 综合与不可变 Structured Report | Done | VIB-53 | M2 理论研究闭环 E8–E9 |
| [VIB-57](https://linear.app/vibecoding-demo/issue/VIB-57/e94-markdown-与-docx-报告导出及重试) | E9.4 Markdown 与 DOCX 报告导出及重试 | Done | VIB-53 | M2 理论研究闭环 E8–E9 |
| [VIB-58](https://linear.app/vibecoding-demo/issue/VIB-58/v1-模型网关治理冻结策略与统一外发控制) | V1 模型网关治理、冻结策略与统一外发控制 | In Progress | — | M3 API 与完整工作台 |
| [VIB-59](https://linear.app/vibecoding-demo/issue/VIB-59/v1-本地会话权限边界与-api-通用合约) | V1 本地会话、权限边界与 API 通用合约 | Done | — | M3 API 与完整工作台 |
| [VIB-60](https://linear.app/vibecoding-demo/issue/VIB-60/v1-来源知识证据与版本质量-api) | V1 来源、知识、证据与版本质量 API | Done | — | M3 API 与完整工作台 |
| [VIB-61](https://linear.app/vibecoding-demo/issue/VIB-61/v1-研究控制详情查询与-sse-事件-api) | V1 研究控制、详情查询与 SSE 事件 API | Done | — | M3 API 与完整工作台 |
| [VIB-62](https://linear.app/vibecoding-demo/issue/VIB-62/v1-知识工作区与统一-evidence-drawer) | V1 知识工作区与统一 Evidence Drawer | Backlog | — | M3 API 与完整工作台 |
| [VIB-63](https://linear.app/vibecoding-demo/issue/VIB-63/v1-理论研究工作区与完整辩论时间线) | V1 理论研究工作区与完整辩论时间线 | Done（本地及 Linear） | — | M3 API 与完整工作台 |
| [VIB-64](https://linear.app/vibecoding-demo/issue/VIB-64/v1-任务中心审计备份和系统设置工作区) | V1 任务中心、审计备份和系统设置工作区 | Backlog | — | M3 API 与完整工作台 |
| [VIB-65](https://linear.app/vibecoding-demo/issue/VIB-65/e10-恢复安全性能备份与桌面交付) | E10 恢复、安全、性能、备份与桌面交付 | Backlog | — | M4 运行可靠性与交付 E10 |
| [VIB-66](https://linear.app/vibecoding-demo/issue/VIB-66/e101-加密备份临时恢复验证与发布迁移快照) | E10.1 加密备份、临时恢复验证与发布迁移快照 | Backlog | VIB-65 | M4 运行可靠性与交付 E10 |
| [VIB-67](https://linear.app/vibecoding-demo/issue/VIB-67/e102-全研究链-nodeexecution-与故障恢复演练) | E10.2 全研究链 NodeExecution 与故障恢复演练 | Backlog | VIB-65 | M4 运行可靠性与交付 E10 |
| [VIB-68](https://linear.app/vibecoding-demo/issue/VIB-68/e103-真实-golden-set模型资格与性能评测) | E10.3 真实 Golden Set、模型资格与性能评测 | Backlog | VIB-65 | M4 运行可靠性与交付 E10 |
| [VIB-69](https://linear.app/vibecoding-demo/issue/VIB-69/e104-安全审计完整性与架构边界检查) | E10.4 安全、审计完整性与架构边界检查 | Backlog | VIB-65 | M4 运行可靠性与交付 E10 |
| [VIB-70](https://linear.app/vibecoding-demo/issue/VIB-70/e105-desktop-supervisor安装升级与降级运行) | E10.5 Desktop Supervisor、安装升级与降级运行 | Backlog | VIB-65 | M4 运行可靠性与交付 E10 |
| [VIB-71](https://linear.app/vibecoding-demo/issue/VIB-71/e11-stage-1a1b-正式验收与协议冻结) | E11 Stage 1A/1B 正式验收与协议冻结 | Backlog | — | M5 V1 验收与协议冻结 E11 |
| [VIB-72](https://linear.app/vibecoding-demo/issue/VIB-72/e111-需求追踪矩阵设计差异与决策闭环) | E11.1 需求追踪矩阵、设计差异与决策闭环 | Todo | VIB-71 | M5 V1 验收与协议冻结 E11 |
| [VIB-73](https://linear.app/vibecoding-demo/issue/VIB-73/e112-stage-1a-知识底座验收) | E11.2 Stage 1A 知识底座验收 | Backlog | VIB-71 | M5 V1 验收与协议冻结 E11 |
| [VIB-74](https://linear.app/vibecoding-demo/issue/VIB-74/e113-stage-1b-验收v1-发布与交接) | E11.3 Stage 1B 验收、V1 发布与交接 | Backlog | VIB-71 | M5 V1 验收与协议冻结 E11 |
| [VIB-75](https://linear.app/vibecoding-demo/issue/VIB-75/阶段-2a-病例工作区与隐私边界) | 阶段 2A 病例工作区与隐私边界 | Backlog | — | M6 后续阶段 2A 病例工作区 |
| [VIB-76](https://linear.app/vibecoding-demo/issue/VIB-76/2a1-病例领域设计与古病案复用) | 2A.1 病例领域设计与古病案复用 | Backlog | VIB-75 | M6 后续阶段 2A 病例工作区 |
| [VIB-77](https://linear.app/vibecoding-demo/issue/VIB-77/2a2-现代病例录入就诊时间线与补充版本) | 2A.2 现代病例录入、就诊时间线与补充版本 | Backlog | VIB-75 | M6 后续阶段 2A 病例工作区 |
| [VIB-78](https://linear.app/vibecoding-demo/issue/VIB-78/2a3-身份分离病例权限与阶段验收) | 2A.3 身份分离、病例权限与阶段验收 | Backlog | VIB-75 | M6 后续阶段 2A 病例工作区 |
| [VIB-79](https://linear.app/vibecoding-demo/issue/VIB-79/阶段-2b-临床推理方药策略与医师确认) | 阶段 2B 临床推理、方药策略与医师确认 | Backlog | — | M7 后续阶段 2B 临床推理与方药策略 |
| [VIB-80](https://linear.app/vibecoding-demo/issue/VIB-80/2b1-多流派推理matchscore-与相似病案) | 2B.1 多流派推理、MatchScore 与相似病案 | Backlog | VIB-79 | M7 后续阶段 2B 临床推理与方药策略 |
| [VIB-81](https://linear.app/vibecoding-demo/issue/VIB-81/2b2-方药候选与独立风险门禁) | 2B.2 方药候选与独立风险门禁 | Backlog | VIB-79 | M7 后续阶段 2B 临床推理与方药策略 |
| [VIB-82](https://linear.app/vibecoding-demo/issue/VIB-82/2b3-医师确认签名临床报告与阶段验收) | 2B.3 医师确认签名、临床报告与阶段验收 | Backlog | VIB-79 | M7 后续阶段 2B 临床推理与方药策略 |
| [VIB-83](https://linear.app/vibecoding-demo/issue/VIB-83/阶段-3-疗效反馈假设演进与规律研究) | 阶段 3 疗效反馈、假设演进与规律研究 | Backlog | — | M8 后续阶段 3 疗效反馈与规律研究 |
| [VIB-84](https://linear.app/vibecoding-demo/issue/VIB-84/31-随访-outcome-与疗效归因) | 3.1 随访 Outcome 与疗效归因 | Backlog | VIB-83 | M8 后续阶段 3 疗效反馈与规律研究 |
| [VIB-85](https://linear.app/vibecoding-demo/issue/VIB-85/32-单例假设多例复现与证据评审) | 3.2 单例假设、多例复现与证据评审 | Backlog | VIB-83 | M8 后续阶段 3 疗效反馈与规律研究 |
| [VIB-86](https://linear.app/vibecoding-demo/issue/VIB-86/33-规律治理方药优化反馈与阶段验收) | 3.3 规律治理、方药优化反馈与阶段验收 | Backlog | VIB-83 | M8 后续阶段 3 疗效反馈与规律研究 |

## 当前与后续任务的实施说明

以下范围、依赖、验收来自已写入 Linear 的规划。每项完成后附实际提交、测试及验收证据；准备性任务不因所属父任务尚未完成而自动阻塞。

**E8 父任务验收追踪**：VIB-44 对应 AC-1B-03/04，审计基线 `afe47f2`、Critic/再检索 `7921585`、Rebuttal/修订 `e326916`、Worker 串联 `a7fda2f`。VIB-50/51/52 均 Done；完整后端测试 35 passed、0 skipped，迁移 `0014` 的升级、回退及模型检查通过。E9 的争议、停止规则、Judge 和报告不属于 E8 完成范围。

### VIB-45 V1 初始语料清单、来源授权与 OCR 实施决策

- Linear：[VIB-45](https://linear.app/vibecoding-demo/issue/VIB-45/v1-初始语料清单来源授权与-ocr-实施决策)；本地完成，Linear 待同步；优先级：High。
- 父任务：无；依赖：VIB-38。
- 设计依据：LLD 附录 C；需求 3.2、AC-1A-01。

**范围与已有基础**：已有 TXT/DOCX/文本 PDF 导入；扫描 PDF 仅标记 OCR_REQUIRED。盘点典籍、版本、历史元数据、格式、授权及公开/敏感级别，形成真实验收样本。

**完成标准**：明确首批语料及数据负责人；含扫描件时实现 OCR Job、页码定位、置信度与人工复核；不含扫描件时记录延期依据并验证 OCR_REQUIRED 不误发布。

**2026-09-30 验收**：用户确认纯文本首批、OCR 延后，数据负责人角色为“测试人员”。`initial_corpus.json` 固定《傷寒論》修订 2607901 的 29 条非方剂文本、LF 哈希、来源/权利通知、公开级别、未知刊年/流派及逻辑页边界，默认无云出站授权。解析器 v2 将含任一无文字页的 PDF 整体阻塞为 OCR_REQUIRED，防止文字封面掩盖扫描正文；零页 PDF 拒绝。实际29条导入/逐条引用溯源与未审核草稿排除、无文字及混合 PDF 无分段/证据且不进入知识快照、原文件保留、活动指针不变，独立库专项 **20 passed、0 skipped**，Ruff（忽略绑定挂载权限误报 EXE002）及 diff 检查通过。本轮工程增量已归入提交 `86c6299`。完整证据见 `docs/VIB45_INITIAL_CORPUS_ACCEPTANCE.md`；不代表专家校订或 OCR 质量验收。

### VIB-46 V1 知识候选抽取、术语规范与方剂字段补齐

- Linear：[VIB-46](https://linear.app/vibecoding-demo/issue/VIB-46/v1-知识候选抽取术语规范与方剂字段补齐)；本地实施中，Linear 已同步 In Progress（2026-09-30）；优先级：High。
- 父任务：无；依赖：VIB-45、VIB-40。
- 设计依据：需求 3.2、AC-1A-02/04；LLD 4–5。

**范围与已有基础**：复用 E4 已有实体、概念、关系、药物、方剂和 Evidence 草稿模型，补自动候选抽取及术语/时代/流派歧义处理。

**完成标准**：抽取结果先进入待审草稿；每个实体/关系/方剂字段可回原文；剂量原文与规范值、炮制、剂型、煎服和禁忌可校订；模糊信息保持未知；审核后才进入知识快照。

**语料接续约束**：VIB-45 已冻结的29条仅能支撑非方剂原文候选与定位验证。先实现候选草稿、未知字段保留和审核门禁；真实完整方剂验收需“测试人员”选定同章方剂固定摘录、保存权利依据并安排专项校订，不能以现有预览自动 APPROVE 代替专家确认。依赖 VIB-40 本轮 Linear 回读为 Done。

**2026-09-30 实施增量（工程提交 `86c6299`）**：`knowledge_extraction.py` 和 CLI `extract-knowledge`/`trace-extraction` 使用本地 `local-exact-terms/v2`，从最外层可引用片段生成精确原词位置、概念和明确命名关系草稿；保存来源修订冻结的时代/流派，未知不补造，仅同批次同类型原词归并。`0024_knowledge_extraction` 以来源修订+规则版本唯一和行锁实现并发幂等，批次/草稿/审计原子提交，批次数据库不可变。方剂 CLI 暴露完整药味 JSON、剂型、炮制、煎服和禁忌输入，校订追加新 DRAFT。真实29条候选位置与未审核快照排除、元数据冻结、故障回滚和并发重放、合成方剂字段/追加修订及先审 Evidence 门禁通过；新独立库专项 **16 passed、0 skipped**、完整后端 **80 passed、0 skipped**，空库升级/0024往返、`alembic check`、Ruff 和 diff 检查通过。详情 `docs/VIB46_KNOWLEDGE_CANDIDATES_ACCEPTANCE.md`。**未完成**：方剂字段现只溯源整段 Evidence，逐字段字符引用/规范化依据及审核校验、术语歧义校订和真实完整方剂候选/专家校订仍待补；VIB-46 不标 Done。未修改预览/业务库，无真实云调用，Linear 本轮仅回读。

**2026-09-30 逐字段接续（工程提交 `86c6299`）**：新增 `0025_formula_provenance` 和 `FormulaFieldSource`，用字段/药味序号保存精确 Evidence/片段修订、Unicode 区间、字段值/原文/哈希及规范解释依据。有效但不完整草稿可保存；无效引用创建整体回滚，APPROVE 必须每个非 null 字段有依据，快照和激活复验。旧已审核版本0保留，旧待审需追加新修订；审核/快照后内容、药味、证据关联和引用冻结，禁止版本标记降级。CLI `--field-sources` 和 trace 已接入。最终新独立库完整后端 **113 passed、0 skipped**（33条新增方剂专项），旧数据保留/0025往返/模型检查/Ruff/diff通过。两轮失败分别110过2失、112过1失，均为既有导出测试未识别多行 Markdown/Word 换行；修正测试后通过，生产渲染器保持原实现，失败数据保留。方剂逐字段工程增量完成，**术语歧义校订、真实完整方剂候选和专家校订仍未完成，VIB-46 不标 Done**。下一步同一原词的多类型/时代/流派独立候选与显式人工裁定；不按字符串相似度归并。未改预览/业务库或 API、未跑前端/真实云模型。

**2026-09-30 术语裁定接续（工程提交 `86c6299`）**：`local-exact-terms/v3` 支持同原词多类型独立候选与歧义审核门禁，保留冻结时代/流派、原词和精确位置，不从歧义端点生成命名关系。新增 `0026_term_resolution`、`knowledge_terms.py` 和 CLI `adjudicate-term`，显式人工规范/历史同义词/独立含义/仍未知裁定生成新 DRAFT，复制选定原提及而不重绑旧行；需校订者、解释和精确引用，历史同义词另需已审核对照及其精确证据。审核/快照/激活复验，UNRESOLVED 禁止批准；裁定和概念内容/词形/证据/提及冻结，校订复用已发布对象替换谱系和历史切回。新独立库完整后端 **136 passed、0 skipped**（新增22条术语集成+1条扫描），0026→0023→0026往返、旧概念/方剂保留、模型检查/Ruff/diff通过。工程增量完成，**真实完整方剂候选、实际术语专家核对和专项校订仍未完成，VIB-46 不标 Done**。下一步保守完整方剂候选和逐字段草稿，C02 未冻结时只做合成工程验证；不从 C01 补造药味真值。未改预览/业务库/API，无真实云调用。

**2026-09-30 完整方剂候选接续（工程提交 `86c6299`）**：`local-exact-terms/v4` 新增 `knowledge_formula_extraction.py`，识别同父节点/同类型连续片段中明确“方名方”标题、完整原药味/剂量、括号炮制及计数吻合的“右/上×味”煎服段。共享/模糊剂量、条件/否定标题、替代/缺失药味及未解析列表整方跳过；剂量不换算，单位原样，药物绑定/规范量/比例/角色等保持 null，不推定方剂时代/流派。复用 `create_formula(_session=...)` 与逐字段来源门禁，方剂/Evidence/提及/批次/审计同事务；跨段原文连接有依据，旧 v2/v3 批次保留，新批次返回 formulas 与 formula_count。新增24条规则和7条集成用例，最终新库完整后端 **167 passed、0 skipped**（87.69秒），0026→0023→0026往返、旧字段/状态保留及模型检查通过。首轮97过1失修正条件标题；首个完整库163过1失为旧报告测试默认历史角色弃答的夹具依赖，明确该测试只生成它要验证的两个角色后通过，生产研究代码保持。C02 仍未冻结，全部为合成工程验收，真实29条不生成方剂；VIB-46 保持 In Progress，真实语料和专家验收仍待补。

### VIB-47 V1 古病案文献与 CaseRecord 兼容对象

- Linear：[VIB-47](https://linear.app/vibecoding-demo/issue/VIB-47/v1-古病案文献与-caserecord-兼容对象)；状态：Backlog；优先级：High。
- 父任务：无；依赖：VIB-45、VIB-39、VIB-40。
- 设计依据：AC-1A-05；LLD 18.1；需求 2.5。

**范围与已有基础**：当前代码未见 CaseRecord。仅建立古病案文献到兼容病例对象的映射，为 Stage 2A 复用做准备。

**完成标准**：同一古病案只导入一次；Source/Text/Evidence 精确修订与 CaseRecord 双表示关联；修订影响可查；V1 不开放现代临床诊疗界面或推理。

### VIB-48 V1 结构与关系检索、查询规范化及断网降级

**2026-09-30 查询候选扩展阶段（工程提交 `e7b0af0`）**：`retrieval_query.py` 的 `explicit-orthography/v1` 用有限明确字符组支持表内繁简、混合字形及羣/群、峯/峰；歧义简化字和未列字形保持原样，不推断医学等价。Exact使用NFKC字形键，FTS仅在字符/二元词内OR字形、词间AND，不重写冻结索引或扩展整句组合；Structured/Relation匹配自身词形/方剂字段，历史别名只沿用自身已裁定锚点，不传播比较身份词形。内部结果、研究审计及benchmark保留原query/规则/实际排名。冻结KV/Index/Scope、精确历史Evidence、未裁定/未知、同名多类型/时代、模型门禁、本地/显式降级与研究/benchmark严格失败覆盖。首专项4过5失0skip（四处既有行为测试预期及较/較映射遗漏），修正后同库6条集成通过、2条规则单测通过、方剂扩展用例通过；最终全新独立库完整后端 **241 passed、0 failed、0 skipped**（366.14秒，新增8条测试），Ruff/diff通过。没有迁移、依赖或前端改动，未重复迁移往返/build/浏览器，0次真实云调用。质量分流仍按原NFKC字面规则，字形扩展不自动触发问题。详情 [查询扩展验收](VIB48_QUERY_EXPANSION_ACCEPTANCE.md)。**本阶段工程完成，VIB-48仍 In Progress**：VIB-46真实C02/专家依赖未完成，真实模型/生产断网/Windows凭据实机与VIB-68医学相关性验收仍保留。后续按增量流程验证变化涉及的范围。

**2026-09-30 未发布内容质量分流接续（工程提交 `74beabe`）**：新增本地 `unpublished-exact/v1`，只扫描冻结 KV/Index 中已索引的精确 SourceRevision 与来源 Scope 交集；Evidence/关系断言/最外层可引用片段匹配查询全文，概念自身词形、药物词形及方剂原名/药味匹配查询内完整词形。生成可定位 WARNING QualityIssue，保留原 query、首次版本/任务、精确引用/哈希；不把候选加入结果或模型输入，不自动审核，也不声称已校准医学高相关阈值。已发布身份、拒绝目标排除；按规则/目标跨查询/版本/解决/豁免去重，目标锁保证并发幂等，整批问题与审计同事务，失败直接传播；每次新增至多100个目标，已有问题在截取前排除，不阻塞后续候选。旧版发布/新版草稿、同来源新修订和其他来源、人工门禁、本地/降级/严格失败、原子回滚、API/研究池及外层片段去重覆盖。首完整库227过1失0skip，失败为新审计测试 UUID 与字符串字段比较；修正后专项 **18 passed、0 skipped**，再补2条原始片段用例，最终另一全新独立库完整后端 **233 passed、0 failed、0 skipped**（327.57秒），两库迁移往返/旧数据保留/模型检查、完整Ruff/diff通过。无新迁移/依赖，0次真实云调用；本轮未改前端、未重跑build/浏览器。简短验收同步Linear评论 `5b90b9d7-ce2b-4a21-84a3-b44aa736c3c3`。详情 [质量分流验收](VIB48_QUALITY_TRIAGE_ACCEPTANCE.md)。**仍 In Progress**：查询候选扩展完整验收、VIB-46真实C02/专家依赖未完成；相关性阈值/真实Golden Set待VIB-68。

**2026-09-30 来源/证据多样性接续（工程提交 `ffc70b7`）**：`source-context/v1` 在 RRF 候选截取前及最终排序两处对来源重复与同 SourceRevision 精确引用段落重叠分别施加软惩罚；同修订多通道去重，不合并不同证据身份，单来源可填满结果。成功重排按名次正数 credit 排序，避免负分/供应商量纲影响；本地与显式故障降级沿用同一规则。API新增安全排序说明，研究审计/benchmark保存策略及实际精确排名。首次完整回归212过1失0skip，新单来源用例揭示加法惩罚稀释重复上下文；改为两项相乘，失败用例及3条算法用例 **4 passed、0 skipped**；最终另一座全新独立库完整后端 **213 passed、0 skipped**（266.16秒），两库迁移往返/模型检查/旧数据保留、完整Ruff/diff、前端build通过；无新迁移或依赖，0次真实云调用。简短验收已同步Linear评论 `3d9f12aa-a2a6-48f4-8909-35e64da67d3b`。详情 [多样性验收](VIB48_DIVERSITY_ACCEPTANCE.md)。**仍 In Progress**：未发布高相关片段转QualityIssue、查询候选扩展完整验收及VIB-46真实C02/专家依赖未完成。

**2026-09-30 本地/降级接续（工程提交 `2c0d282`）**：默认未授权查询走本地 Exact/FTS/Structured/Relation，不创建云客户端或读取密钥；授权尝试云调用时缺密钥、凭据不可用、配置无效、策略禁止、向量/重排故障返回安全原因码。向量故障回退本地，重排故障保留已完成候选按RRF排序；数据库/审计故障、越界Scope、冻结模型/端点不一致与不完整发布索引仍拒绝。服务需显式开启故障降级；研究和benchmark保持原严格路径。新增 `/retrieval/query` 状态响应，旧 `/search` 数组合约保留；UI无外发同意可检索，显示模式/原因/通道，证据详情只用本地精确引用。最终新独立库 **200 passed、0 skipped**（173.89秒），新增23条；首库192过0失0skip，补8条后最终通过。新库迁移往返/旧数据保留/模型检查、完整Ruff/diff、前端build、隔离模拟浏览器（本地查询/详情/缺密钥/重排故障/空结果/发布错误/研究回归/375px）通过。详见 [专项验收](VIB48_LOCAL_RETRIEVAL_ACCEPTANCE.md)。简短结论已同步Linear评论 `a03d60ad-4e18-4ab9-b2e1-7bb77c405602`；完整内部工程细节外发被自动审批拒绝，保留本地。**仍 In Progress**：多样性、未发布高相关片段转QualityIssue及查询候选扩展完整验收未完成；无真实模型/生产断网/Windows凭据实机验证，VIB-46真实C02/专家依赖保留。下一项来源/证据多样性；未改预览/业务库/API容器，无付费、推送或部署。

- Linear：[VIB-48](https://linear.app/vibecoding-demo/issue/VIB-48/v1-结构与关系检索查询规范化及断网降级)；状态：In Progress（2026-09-30 本地及 Linear 同步）；优先级：High。
- 父任务：无；依赖：VIB-42、VIB-46。
- 设计依据：LLD 9、16.3；AC-1A-07。

**范围与已有基础**：E6 已实现 Exact/FTS/Vector、云端重排。补 Structured/Relation、多样性、繁简/异体/历史别名候选及本地降级。

**完成标准**：所有通道解析为 Published EvidenceRevision；Scope 不扩大；未发布高相关片段转 QualityIssue；保留原 query；无密钥/断网时本地 Exact/FTS/结构查询和证据浏览仍可用，UI 明示降级。

**2026-09-30 结构/关系工程准备（提交 `c9bc6f6`，起点 `e852c48`）**：新增 `retrieval_structured.py`，将冻结KV/Index/Scope内已审核概念、关系、关系端点及方剂修订解析到该版本已审核/已索引的精确 EvidenceRevision；接入RRF和研究池通道记录。概念仅用自身词形和相同历史元数据，裁定仅用自身提及锚点；方剂按原名/药味及字段引用，不用可变当前名称，不替换历史Evidence。显式空Scope返回空结果且无模型调用；服务结果保留原query/NFKC查询，benchmark固定版本。新独立库完整后端 **177 passed、0 skipped**（115.25秒），新增10条集成；空库迁移往返、模型检查、完整Ruff和diff检查通过。首轮175过1失为新方剂夹具缺服用说明，补齐夹具后通过，生产方剂规则未改。详情 `docs/VIB48_STRUCTURED_RETRIEVAL_ACCEPTANCE.md`，Linear评论 `533b394a-dbc2-4924-83ad-70340e6bb71f`。**未完成**：无密钥/断网本地降级和UI提示、多样性、未发布高相关内容QualityIssue及查询扩展完整验收；VIB-48保持In Progress，VIB-46真实C02/专家核对仍待补。无真实云调用，未改预览/业务库/API，未跑前端/浏览器。

### VIB-49 V1 校订修订、版本比较与历史版本切换补齐

- Linear：[VIB-49](https://linear.app/vibecoding-demo/issue/VIB-49/v1-校订修订版本比较与历史版本切换补齐)；本地验收及 Linear：Done（2026-09-30 用户授权后同步）；优先级：High。
- 父任务：无；依赖：VIB-41。
- 设计依据：AC-1A-06/08；LLD 14.3。

**范围与已有基础**：E5 已有审核、QualityIssue、快照与双索引发布门禁；补完整校订修订和受控切回已有可用版本的业务流程。

**完成标准**：修改已发布对象产生新 Revision；差异和引用影响可见；旧研究任务仍固定旧版本；切换前校验目标 KV/Index 可用并记录审计；发布失败保留旧 Active；与备份快照联动。

**2026-09-28 增量**：提交 `9ad9e2f`。`compare_knowledge_versions` 现展示同一 Evidence/Formula 身份下的修订替换，并列出旧 Evidence 被哪些知识对象引用及其是否仍在目标版本。历史版本激活前复核目标快照、索引片段和对应向量是否完整；激活事件记录原 KV/Index 及是否切回历史版本。集成用例验证成功切回、缺向量时拒绝切换且原 Active 保留，以及 Evidence 修订的引用影响。独立库完整后端 **61 passed、0 skipped**，Ruff、diff 检查通过。**尚未完成**：已发布 Concept/Relation/Herb 的追加修订流程、引用影响处理和可用备份快照关联；旧研究任务固定版本也需专项验收，因此保持 In Progress。

**引用一致性发现**：现有快照会选最新已审核 EvidenceRevision，但仍收入引用旧修订的已审核 Concept 等对象。尝试在激活时直接拒绝这种情况，完整回归因既有测试数据的旧引用而失败（60 passed、1 failed）；该未提交试验已撤回，恢复后完整回归重新为 61 passed。下一步需先设计可执行的知识对象追加修订/替换与引用迁移，再加发布门禁，不能仅加拒绝条件使既有版本无法继续发布。

**2026-09-29 追加修订进度**：提交 `729b212`，迁移 `0021_knowledge_supersession` 新增 Concept/Relation/Herb 已审核对象间的不可变替换谱系，CLI `supersede-knowledge` 登记新旧修订。新 KV 排除被替换的旧对象，旧 KV 仍保留旧行并可切回；比较结果展示修订身份和编号。新替换对象引用缺失的 Evidence、关系仍指向被替换概念、方剂仍指向被替换药物时，快照拒绝创建。概念与关系的实际校订、失败修复、激活与切回链路通过集成测试。独立库完整后端 **61 passed、0 skipped**，Ruff、diff、迁移 0020→0021→0020→0021 与 `alembic check` 通过。独立预览库在校验备份后升级 0021，5173 健康接口 `schema=current`。**仍未完成**：旧数据中跨 Evidence 修订的引用全量一致性、真实 Backup/Release Snapshot 联动和旧研究任务冻结版本专项验收，保持 In Progress。

**2026-09-29 待验证增量**：工作区新增 `0022_reference_manifest`，为新 KV 冻结已审核知识对象引用的历史 EvidenceRevision 记录和哈希；引用只用于溯源，当前检索索引仍仅收当前 Evidence。激活时比对冻结记录与清单，版本比较显示历史引用增减。集成用例已扩展到含旧引用版本的实际激活与切回。首次迁移执行因 Alembic 版本号过长回滚，缩短标识后自动审批因额度限制拒绝 Docker 验证；**0022 迁移、测试、预览库更新均未通过**，旧版 61 passed 不适用于这批改动。真实备份关联和旧研究任务冻结专项验收仍待做，VIB-49 保持 In Progress。

**2026-09-29 0022 验证结果**：提交 `ad41f6a`。自动审批恢复后，隔离迁移库完成 0021→0022→0021→0022，`alembic check` 无差异；专项用例验证含旧引用版本激活、索引只返回新 Evidence，以及旧研究任务仍从冻结 KV/Index 得到旧 Evidence。完整后端 **61 passed、0 skipped**，Ruff 和 diff 检查通过。预览库先保存 464405 字节备份并核对容器内外 SHA256 `17deac2f577a54c1141cfbf2173735590e4735c6c44c9d437aa5fa53b235bd88`，然后迁移至 0022；重启 API 后 5173 代理健康 `schema=current`。LLD 14.4 的 Release Snapshot 是发布/迁移快速恢复点，Portable Backup 属后续 VIB-66；当前只有备份文件和 `BackupRecord` 骨架，尚无可核验发布快照工件与 KV/Index 关联，VIB-49 保持 In Progress。

**2026-09-29 本地验收**：提交 `0c3a714`，迁移 `0023_release_snapshot` 自动将已有活动版本切换前后的 KV/Index 与清单哈希写入不可变 CAS 工件，并将 Release Snapshot ID 写入激活审计。CLI `restore-release-snapshot` 对工件哈希、活动指针和旧版本双索引重新验关后原子切回；工件缺失或目标索引受损时保留原 Active。全新隔离库完整后端 **61 passed、0 skipped**，迁移库 0022→0023→0022→0023、`alembic check`、Ruff、diff 检查通过。预览库先备份 467297 字节、SHA256 `426ca71c0ece4326060fecda54d5e36a0d4ac1e7ed4462307c1da639b0da2078`（容器内外一致），再升级 0023；5173 健康接口 `schema=current`。VIB-49 的本机快速回退验收完成；该快照依赖原数据库和索引，完整加密 Portable Backup/灾难恢复归 VIB-66。当时 Linear 同步被自动审批拒绝；2026-09-30 用户明确授权后已同步 Done 和简短验收结论。

### VIB-50 E8.1 完成 Critic、EvidenceRequest 与受限再检索

- Linear：[VIB-50](https://linear.app/vibecoding-demo/issue/VIB-50/e81-完成-criticevidencerequest-与受限再检索)；状态：Done（2026-09-28 验收后同步）；优先级：High。
- 父任务：VIB-44；依赖：VIB-43。
- 设计依据：LLD 7.3、8；AC-1B-03。

**范围与已有基础**：工作区存在未提交 debate_service.py、0012 迁移和 Critique/EvidenceRequest/Rebuttal 模型；未将这些改动视为已验收。

**完成标准**：质疑指向具体 Claim；仅 EvidenceRequest 驱动再检索；Scope/版本/可见集合约束生效；保存检索来源事件；重复执行不重复写入；迁移及集成测试通过并形成提交。

**验收追踪**：AC-1B-03；提交 `7921585`；`test_research_worker_resumes_from_frozen_task_and_checkpoints` 覆盖 Claim 定向质疑、冻结 Scope、来源事件及重复检索。2026-09-28 在独立测试库随知识发布测试运行，7 passed、0 skipped；新库 `0011→0013` 升级及 `alembic check` 通过。测试驱动为 `psycopg2`。

### VIB-51 E8.2 Rebuttal 与追加式 Claim 修订及重新审计

- Linear：[VIB-51](https://linear.app/vibecoding-demo/issue/VIB-51/e82-rebuttal-与追加式-claim-修订及重新审计)；状态：Done（2026-09-28 验收后同步）；优先级：High。
- 父任务：VIB-44；依赖：VIB-50。
- 设计依据：LLD 4.5、7.4、8；AC-1B-03/04。

**范围与已有基础**：在质疑和新证据基础上处理 ACCEPT/PARTIAL_ACCEPT/REJECT/REVISE；复用已有机械与语义审计。

**完成标准**：Rebuttal 关联原 Critique；REVISE 生成新 Claim revision，旧记录保留；新 Claim 重新审计；池外证据整份拒绝；NOT_VERIFIABLE 不解释为 FALSE。

**验收追踪**：AC-1B-03/04；提交 `e326916`；同一研究链集成用例覆盖四种 Rebuttal action、池外证据整份拒绝、追加 Claim 与旧 Claim 保留、机械/语义重新审计、`NOT_VERIFIABLE` 与失败恢复。2026-09-28 在独立测试库随知识发布测试运行，7 passed、0 skipped；新库 `0011→0013` 升级及 `alembic check` 通过；后端 `ruff check src tests migrations` 通过。测试驱动为 `psycopg2`，真实模型语义质量留给 VIB-68。

### VIB-52 E8.3 Worker 接入纠错闭环与节点幂等验证

- Linear：[VIB-52](https://linear.app/vibecoding-demo/issue/VIB-52/e83-worker-接入纠错闭环与节点幂等验证)；状态：Done（2026-09-28 验收后同步）；优先级：High。
- 父任务：VIB-44；依赖：VIB-51。
- 设计依据：LLD 7、11、17 E8。

**范围与已有基础**：现有 Worker 正常路径在 FIRST_ROUND_COMPLETE 停止；把 E8 服务接入持久化节点执行与检查点。

**完成标准**：无需手工 CLI 串节点即可完成一轮质疑/再检索/反驳/审计；暂停取消安全点、失租丢弃、重试与增量修订验证通过；非法模型输出无部分提交；补齐 README 和可回放样例。

**验收追踪**：AC-1B-03/04；提交 `a7fda2f`；`test_worker_completes_audited_debate_without_manual_cli_steps` 及同文件故障用例覆盖完整轮次、原/修订 Claim 审计、节点检查点、暂停取消、失租/generation 变化、非法输出与重试不重复对象。迁移 `0014` 在两座隔离测试库升级，第二库回退再升级，`alembic check` 无差异；完整后端 35 passed、0 skipped；Ruff 与 diff 检查通过。README 记录可回放测试入口。测试驱动为 `psycopg2`，真实模型语义质量留给 VIB-68。

### VIB-53 E9 争议、停止规则、Judge 与结构化报告

- Linear：[VIB-53](https://linear.app/vibecoding-demo/issue/VIB-53/e9-争议停止规则judge-与结构化报告)；状态：Done；优先级：High。
- 父任务：无；依赖：VIB-44。
- 设计依据：LLD 17 E9；AC-1B-05～08。

**范围与已有基础**：承接 E8，建立正式理论研究端到端闭环。

**完成标准**：子任务完成；从研究问题到结构化报告自动执行；合理争议保留；Judge 不新增未审计事实；报告与冻结上下文可回放。

**验收追踪**：VIB-54/55/56/57 均已完成并同步 Linear；Worker 自动闭环、停止与争议保留、受约束 Judge、不可变 StructuredReport 和独立报告 Artifact 分别见四个子任务。最终迁移 `0018`，完整后端 48 passed、0 skipped；真实模型语义质量与网页研究工作台分别待 VIB-68 与 VIB-61/63。

### VIB-54 E9.1 CanonicalClaim、Dispute 与 EvidenceGap

- Linear：[VIB-54](https://linear.app/vibecoding-demo/issue/VIB-54/e91-canonicalclaimdispute-与-evidencegap)；状态：Done；优先级：High。
- 父任务：VIB-53；依赖：VIB-51。
- 设计依据：LLD 7.3、7.6；AC-1B-05。

**范围与已有基础**：对首轮和修订 Claim 增量规范化，依据审计结果形成竞争解释和证据缺口。

**完成标准**：归并不抹掉原 Claim、时代或流派差异；冲突样本产生 Dispute；保存正反证据和未解决缺口；不以多数票合并争议。

**验收追踪**：`claim_normalization.py` 使用断言类型、空白规范化文本和精确 SourceRevision 的时代/流派快照构造保守的重复归并键；原 Claim 与修订保留，Member 关联最新 AuditResult。审计明确矛盾及 Critic 的 `CONTRADICTION` 形成 Dispute；不充分/不可验证/缺证/检索无结果形成 EvidenceGap；未审反证保持缺口，不冒充验证结果。新审计结果将旧争议/缺口标为 `SUPERSEDED`，Worker 两个节点与 `normalize-claims` CLI 可幂等重放。AC-1B-05 对应迁移 `0015`、`test_claim_normalization.py` 和研究集成用例；两座独立数据库完成升级/回退/再升级与模型差异检查，完整后端 38 passed、0 skipped，Ruff（忽略 Windows 挂载 EXE002 误报）与 diff 检查通过。跨断言隐含冲突不自动猜测，保留为后续明确关系输入。

### VIB-55 E9.2 确定性 StopEvaluator 与人工中断恢复

- Linear：[VIB-55](https://linear.app/vibecoding-demo/issue/VIB-55/e92-确定性-stopevaluator-与人工中断恢复)；状态：Done；优先级：High。
- 父任务：VIB-53；依赖：VIB-54、VIB-52。
- 设计依据：LLD 7.3/7.5、11.4。

**范围与已有基础**：将轮次上限、停止条件与 HumanReviewRequest 纳入冻结 WorkflowConfig。

**完成标准**：停止依据可记录和复算；不使用模型自信或多数票；WAITING_HUMAN 保存 interrupted/resume stage 和原因并释放租约；人工处理后从正确阶段继续；首轮不重复执行。

**验收追踪**：`0016_stop_review` 将停止判断快照、冻结策略、人工复核请求和中断/恢复阶段落库。`stop_service.py` 只依据最新 AuditResult、当前轮 Critique、Dispute/EvidenceGap 与 WorkflowConfig 判断，保存输入哈希和决策，快照可独立重算；Critic/Rebuttal 可按冻结上限继续多轮。Worker 在 `WAITING_HUMAN` 原子完成 Job 并释放租约，CLI 记录人工处理后重排同一 Job，从 `STOP_EVALUATION` 恢复，不重跑首轮。两座隔离库升级 0016，其中迁移库回退/再升级；`alembic check` 无差异，完整后端 **40 passed、0 skipped**，Ruff 与 `git diff --check` 通过。Fake 模型只验证状态与约束，不代表真实模型质量。

### VIB-56 E9.3 Judge 综合与不可变 Structured Report

- Linear：[VIB-56](https://linear.app/vibecoding-demo/issue/VIB-56/e93-judge-综合与不可变-structured-report)；状态：Done；优先级：High。
- 父任务：VIB-53；依赖：VIB-55。
- 设计依据：LLD 7.6；AC-1B-06/08。

**范围与已有基础**：Judge 消费经审计 Active Claims、AuditResult、Dispute、已验证 Evidence 与 EvidenceGap；ReportGenerator 只渲染结构化综合。

**完成标准**：报告区分高可信、条件性、争议、未支持和未解决；禁止自由检索/新建 Evidence 或 Claim；结论到原文全链可追溯；结构化报告成功落库后才完成任务；旧报告不随新知识版本变化。

**验收追踪**：`0017_judge_report` 新增 ResearchSynthesis 与 StructuredReport，数据库触发器拒绝更新/删除。`judge_service.py` 从冻结知识版本中构造仅含最新已审计 Active Claim、AuditResult、开放 Dispute/EvidenceGap 和已审核 EvidenceRevision 的 Judge 快照；模型只能对每条 Claim 选择允许的分类与审计/争议/缺口理由 ID，不能创建新断言或证据。ReportGenerator 纯函数复制断言、正反证据及原文定位到五类结构化报告；Worker 在报告与 Job 完成同一事务后才将任务置 `COMPLETED`。无 Claim、非法 Judge 输出、报告落库失败重试、旧报告不随活动知识版本指针变化与数据库不可变性有集成用例。隔离库升级 0017，另一库 0016→0017→0016→0017；`alembic check` 无差异，完整后端 **45 passed、0 skipped**，Ruff 与 `git diff --check` 通过。真实云模型质量待 VIB-68，Markdown/DOCX 导出待 VIB-57。

### VIB-57 E9.4 Markdown 与 DOCX 报告导出及重试

- Linear：[VIB-57](https://linear.app/vibecoding-demo/issue/VIB-57/e94-markdown-与-docx-报告导出及重试)；状态：Done；优先级：Medium。
- 父任务：VIB-53；依赖：VIB-56。
- 设计依据：需求 3.3；LLD 7.6、14。

**范围与已有基础**：以结构化报告生成摘要、证据、争议、限制和可展开的完整研究过程。

**完成标准**：导出为独立派生 Job/Artifact；失败不使研究失败；重复导出可追踪格式与版本；DOCX 引用和分页经渲染检查；支持深链接与引用复制。

**验收追踪**：提交 `86e3a5d`。迁移 `0018_report_export` 记录 ReportExport 与独立 Job、Artifact、格式、渲染版本和导出时冻结的研究过程快照；同一报告/格式/版本幂等，失败和达到最大次数后可重排，研究任务保持 `COMPLETED`。Markdown/DOCX 共享事实大纲，展示五类结论、审计、争议/限制、完整研究过程和原文证据；内部锚点跳转、可复制来源修订/片段定位。CLI 可排队、处理、查看和保存文件。集成用例覆盖链接、原文、重试、数据库登记失败回滚、无断言报告；两座隔离库升级 0018，第二库 0017→0018→0017→0018；`alembic check` 无差异，完整后端 **48 passed、0 skipped**，Ruff 与 diff 检查通过。Word 将样本 DOCX 实际渲染为 4 页并逐页检查无截断和重叠。AC-1B-08 的后端报告导出可追踪；网页报告展示和下载 API 待 VIB-61/63，真实模型质量待 VIB-68。

### VIB-58 V1 模型网关治理、冻结策略与统一外发控制

- Linear：[VIB-58](https://linear.app/vibecoding-demo/issue/VIB-58/v1-模型网关治理冻结策略与统一外发控制)；状态：In Progress；优先级：High。
- 父任务：无；依赖：VIB-43。
- 设计依据：LLD 5.3、8、10；HLD 6.3。

**范围与已有基础**：复用现有云端生成/向量/重排适配器和 ModelInvocation，补 Endpoint/Version/Policy、Prompt/Workflow/检索配置版本及 OutboundPolicy。不在本任务中自行更换默认模型或调用付费模型。

**完成标准**：complete/embed/rerank 全部受数据级别、来源授权与冻结策略控制；LOCAL_ONLY/显式授权禁止被 fallback 绕过；密钥使用 OS Keychain；输入过长不静默截断；限流/熔断与两类重试分离；调用记录脱敏；正式模型资格由评测确定。

**2026-09-28 实现进度**：提交 `ba69cab`。`0020_outbound_source_policy` 为旧来源设 RESTRICTED/未授权默认值；索引和研究任务冻结模式、来源范围、策略/模型/Prompt，complete/embed/rerank 前检查来源授权并在调用前复核。查询词、研究问题要求单次显式同意，网页检索已接入。云模型适配器限制端点、请求/响应大小、并发/频率和熔断；传输重试与 JSON 格式重试分开，ModelInvocation 仅记录哈希、版本、状态与计数。Windows 密钥通过 Credential Manager 存取，无新增依赖；隔离开发容器的环境变量需显式开关。隔离 PostgreSQL 完整测试 **59 passed、0 skipped**，空库迁移升级/回退/再升级及 `alembic check` 通过。**待验收**：Windows Credential Manager 实机读写、既有预览库迁移与重建索引、治理后真实检索链路；这些未执行，因此保持 In Progress。正式模型质量资格属于 VIB-68。

**2026-09-28 治理后预览验收**：提交 `295f2f9` 为预览脚本增加已激活索引的来源授权复核，并用假 WinAPI 验证密钥包装器的指针调用协议。独立预览库先备份，再由 `0019` 升至 `0020`；固定公版来源核对后登记 `PUBLIC` 和显式授权，旧索引重建为冻结 `CLOUD_ALLOWED`、端点及 `outbound-policy/v1` 的活动索引。5173 代理下真实云检索 7/7 正向检查通过，六个目标条文均排在前 2 位；ModelInvocation 的 embed/rerank 成功记录含策略版本、输入和输出哈希、重试数。完整后端 **61 passed、0 skipped**，Ruff 通过。无关胰岛素问题仍返回 5 个候选，正式质量与拒答阈值属于 VIB-68。**仅余 Windows Credential Manager 的 Python 实机读写未验证**：本机 Python/uv/Alembic 会触发应用程序错误，不能为补验收再启动同一运行时；VIB-58 保持 In Progress。

### VIB-59 V1 本地会话、权限边界与 API 通用合约

- Linear：[VIB-59](https://linear.app/vibecoding-demo/issue/VIB-59/v1-本地会话权限边界与-api-通用合约)；状态：Done；优先级：High。
- 父任务：无；依赖：VIB-36。
- 设计依据：LLD 5、6、12.1/12.4。

**范围与已有基础**：当前 API 仅 health 和检索。先完成 loopback 会话和命令边界，再开放来源导入与业务写操作。

**完成标准**：bootstrap→HttpOnly session；精确 Origin/CSRF；服务层 actor/能力检查；public ID、strict DTO、错误码、Idempotency-Key、ETag/If-Match；长任务 202；API/Agent/DB 引用边界验证。

**验收追踪**：提交 `7ed5368`。`0019_local_session_api` 增加一次性启动授权、持久会话和 Job 公开编号。API 限定回环 Host，命令检查精确 Origin；会话 Cookie 为 HttpOnly/SameSite=Strict，CSRF token 只在 bootstrap 响应返回，撤销需 ETag/If-Match。`api_contract.py` 提供能力校验、公开编号解析、幂等 Job 与 202/Location、统一错误；任务查询和检索响应不直接输出数据库修订 UUID。CLI/Agent 仍保留内部精确修订引用。两座隔离库升级 0019，第二库 0018→0019→0018→0019；`alembic check` 无差异，完整后端 **51 passed、0 skipped**，Ruff、前端构建、diff 检查通过。需求对应关系见 [需求追踪矩阵](REQUIREMENTS_TRACEABILITY.md)。桌面主进程密钥注入属于 VIB-70，来源/研究写路由分别属于 VIB-60/61；当前 202 是已测试的通用响应契约，业务端到端 202 待这些路由接入。

### VIB-60 V1 来源、知识、证据与版本质量 API

- Linear：[VIB-60](https://linear.app/vibecoding-demo/issue/VIB-60/v1-来源知识证据与版本质量-api)；本地与 Linear：Done，验收评论已同步；优先级：High。
- 父任务：无；依赖：VIB-59、VIB-49。
- 设计依据：LLD 12.2；AC-1A-01/06/08。

**范围与已有基础**：将已有 CLI 业务服务通过受控 API 暴露，覆盖导入、解析/分段、草稿校订、审核、质量问题、发布、索引、比较切换与 Evidence batch/detail。

**完成标准**：写接口复用应用服务；导入和发布返回 Job；Published 不可覆盖 PATCH；证据原文/上下文/版本定位可查；失败与并发冲突可恢复。

**2026-09-29 已提交增量 `410b854`**：`knowledge_api.py` 复用现有来源/知识/发布服务，开放来源导入与修订分段、Evidence 草稿和 batch/detail、Concept/Relation/Herb/Formula 草稿与详情、人工审核、质量问题及报告、版本快照/比较/切换。只接受公开编号加修订号，不开放覆盖已发布对象的 PATCH；V1 API 拒绝现代患者病例导入。`knowledge_worker.py` 消费发布 Job，校验冻结模型路由，复用索引和激活门禁，故障后保留旧活动 KV/Index 并可重试。全新隔离库从空库迁移到 0023，完整后端 **62 passed、0 skipped**；专项测试还验证会话/CSRF、阻断质量问题、发布幂等、假模型故障后的重试与活动版本保持。Ruff 和 `git diff --check` 通过。当时未发起真实云调用，后续验收结果见下段；模型效果、成本与性能的正式资格归 VIB-68。

**真实模型联调准备 `024a184`**：`backend/scripts/check_knowledge_api_live.py` 只允许独立 `tcm_vib60_live_test` 和专用临时数据目录；默认仅预检，不写库或调用模型，显式 `--execute` 才执行公版单条原文的真实向量/重排链路。独立库已迁移到 0023；假占位密钥预检返回 `real_calls: 0`，来源表当时仍为空。脚本 Ruff 与 diff 检查通过；真实调用获用户授权后执行，结果见下段。

**2026-09-29 本地验收**：用户授权真实调用后，在独立 `tcm_vib60_live_test` 用公版《傷寒論》一条原文执行 HTTP 导入→解析/分段→Evidence 审核→快照→发布 Job/Worker→真实检索。`KV-000001` 与 FTS/向量索引均 READY，Job COMPLETED，检索第一条命中预期 Evidence；ModelInvocation 有 2 条 embed、1 条 rerank，均 COMPLETED，含 `outbound-policy/v1`、策略哈希与输出哈希，传输重试数 0。未改预览库。补提交 `3955e2c` 验证同一导入键不同内容、同一版本不同发布配置均返回 409；最终完整隔离库回归 **62 passed、0 skipped**，Ruff 通过。本地 VIB-60 验收通过；该单条原文冒烟只验证连接与业务链路，不代表 VIB-68 的模型效果、成本和性能资格，也不代表桌面/生产部署完成。

### VIB-61 V1 研究控制、详情查询与 SSE 事件 API

- Linear：[VIB-61](https://linear.app/vibecoding-demo/issue/VIB-61/v1-研究控制详情查询与-sse-事件-api)；状态：Done；优先级：High。
- 父任务：无；依赖：VIB-59、VIB-56。
- 设计依据：LLD 12.2/12.3。

**范围与已有基础**：提供 task create/start/pause/resume/cancel、Claims/Audits/Debate/Disputes/Report/HumanReview 和任务事件接口，可按 E8/E9 分段交付。

**完成标准**：REST 是事实源；allowed_actions 由服务端计算；SSE 仅传轻量 ID且支持 Last-Event-ID；重连先取快照；不流式暴露未校验模型 token；控制请求幂等。

**已提交增量**：`cadb7c8` 增加任务创建/启动、状态与 allowed_actions、最终报告查询、导出访问的 HTTP 路由；隔离库与假模型 API→Worker→报告/导出集成测试通过，完整后端 **60 passed、0 skipped**，Ruff 通过。

**2026-09-29 最终验收**：提交 `fabb6bf`。研究 API 接入暂停/恢复/取消、人工审核决议、Claims/Audits/Debate/Disputes/证据缺口/停止评估详情，并以公开引用投影取代内部 UUID；SSE 先发快照指针、支持 Last-Event-ID 回放，只发送公开任务 ID 与已提交的任务事件类型。暂停/恢复的事务性请求哈希覆盖首次空操作，阻止旧键跨状态重放；创建态可取消，人工审核同决议重放安全。用户恢复 Docker Desktop 后，在现有只读 Linux 容器、独立 `tcm_vib60_test`（迁移 `0023_release_snapshot`）完成**最终完整后端 62 passed、0 skipped**，包括新增幂等断言；Ruff 与 `git diff --check` 通过。Linear 已同步 Done 和验收证据。未触发真实云调用；模型语义质量受 VIB-68 单独验收。

### VIB-62 V1 知识工作区与统一 Evidence Drawer

- Linear：[VIB-62](https://linear.app/vibecoding-demo/issue/VIB-62/v1-知识工作区与统一-evidence-drawer)；状态：Backlog；优先级：High。
- 父任务：无；依赖：VIB-60、VIB-46、VIB-48。
- 设计依据：LLD 13.3/13.4；AC-1A。

**范围与已有基础**：扩展现有只读检索页，形成来源树/原文/知识与校订三栏工作区，加入导入、版本质量、检索过滤和审核操作。

**完成标准**：大树/长列表可用；原文与规范文本、Quote 与 Context 分开；相似度不标为可信度；证据组件跨页面复用且支持深链接；导入→校订→审核→发布→检索 E2E 通过。

### VIB-63 V1 理论研究工作区与完整辩论时间线

- Linear：[VIB-63](https://linear.app/vibecoding-demo/issue/VIB-63/v1-理论研究工作区与完整辩论时间线)；状态：Done（2026-09-30 本地验收并同步 Linear）；优先级：High。
- 父任务：无；依赖：VIB-61、VIB-57。
- 设计依据：LLD 13.5/13.6；AC-1B-07/08。

**范围与已有基础**：提供研究范围表单和 Summary/Claims/Debate/Evidence/Disputes/Report 六 Tab，支持 Round View/Claim View。

**完成标准**：首轮待审草稿与最终报告明确区分；质疑→反驳→修订→审计可追踪；控制按钮服从 allowed_actions；WAITING_HUMAN/失败有持续提示；创建研究→人工处理→报告导出 E2E 通过。

2026-09-30 验收：研究工作区提供本地会话、来源范围、任务列表、六 Tab、Round/Claim 时间线、allowed_actions 控制、人工审核及报告下载。`npm run check:research-browser` 的模拟 API 回归通过；`check_research_e2e.mjs` 在独立 `tcm_vib60_test` 中通过浏览器→真实 Uvicorn/API→假模型研究 Worker→人工审核→恢复→Markdown/DOCX 导出 Worker→实际浏览器下载、真实 SSE、页面刷新恢复及 375px 窄屏检查。最终任务 `RT-01a0f14b-384b-710e-bed9-b549d8a7a50f`，任务/导出完成、审核已解决，0 次真实模型调用。两条相关后端集成用例 **2 passed、0 skipped**，构建、Ruff、diff 检查通过。修正集成用例按本次 Job 定位 export，避免既有待执行队列干扰。详见 [验收与复现记录](VIB63_RESEARCH_WORKSPACE_ACCEPTANCE.md)。2026-09-30 用户明确授权后同步 Linear Done，并读取确认；详细内部证据的外发被自动审批拒绝，已同步不含内部环境和提交明细的验收结论，完整证据保留本地。

### VIB-64 V1 任务中心、审计备份和系统设置工作区

- Linear：[VIB-64](https://linear.app/vibecoding-demo/issue/VIB-64/v1-任务中心审计备份和系统设置工作区)；状态：Backlog；优先级：Medium。
- 父任务：无；依赖：VIB-59、VIB-58、VIB-66。
- 设计依据：LLD 12.2、13.1/13.6。

**范围与已有基础**：补齐任务/重试、版本质量、审计日志、备份恢复与模型设置导航；V1 不显示临床和疗效入口。

**完成标准**：备份恢复必须经过验证流程；模型设置显示数据外发范围和可用能力；DEGRADED/发布失败持续提示；核心业务数据不落 localStorage/IndexedDB；设置变更不影响已冻结任务。

### VIB-65 E10 恢复、安全、性能、备份与桌面交付

- Linear：[VIB-65](https://linear.app/vibecoding-demo/issue/VIB-65/e10-恢复安全性能备份与桌面交付)；状态：Backlog；优先级：High。
- 父任务：无；依赖：VIB-53、VIB-47、VIB-48、VIB-49。
- 设计依据：LLD 15–17 E10；HLD 6。

**范围与已有基础**：完成发布前非功能验收，覆盖 CLI 原型之外的可靠运行和可安装交付。

**完成标准**：备份真恢复、故障注入、安全与性能评测和安装升级全部通过；保留目标机器、数据、版本与测试结果；不以样例成功替代发布门禁。

### VIB-66 E10.1 加密备份、临时恢复验证与发布迁移快照

- Linear：[VIB-66](https://linear.app/vibecoding-demo/issue/VIB-66/e101-加密备份临时恢复验证与发布迁移快照)；状态：Backlog；优先级：High。
- 父任务：VIB-65；依赖：VIB-37、VIB-49。
- 设计依据：LLD 14.4、15.2；AC-1A-06；HLD 6.13。

**范围与已有基础**：当前有 BackupRecord 骨架，未见完整备份恢复服务。实现 pg_dump+CAS+Manifest、VERIFY、临时数据库/data generation 恢复和 live 切换。

**完成标准**：恢复 Source/Text/Evidence/Claim/Audit/Version/EventLog；哈希/引用/smoke 校验通过后切换；密钥值不入备份；失败不伤 live；验证换机恢复、发布前与迁移前快照；拒绝路径穿越与异常归档。

### VIB-67 E10.2 全研究链 NodeExecution 与故障恢复演练

- Linear：[VIB-67](https://linear.app/vibecoding-demo/issue/VIB-67/e102-全研究链-nodeexecution-与故障恢复演练)；状态：Backlog；优先级：High。
- 父任务：VIB-65；依赖：VIB-56、VIB-57、VIB-52。
- 设计依据：LLD 7.2、11；HLD 6.13。

**范围与已有基础**：将已有租约、心跳和首轮恢复扩展到 E8/E9、导入、发布与导出，并核对 NodeExecution/Checkpoint/领域提交一致性。

**完成标准**：逐节点 crash、断网、超时、失租、重启、取消及重复请求测试；先 reconcile 后重跑；旧 generation 结果丢弃；已完成节点不重复业务对象；外部调用不持长 DB 事务；资源并发有界。

### VIB-68 E10.3 真实 Golden Set、模型资格与性能评测

- Linear：[VIB-68](https://linear.app/vibecoding-demo/issue/VIB-68/e103-真实-golden-set模型资格与性能评测)；状态：Backlog；优先级：High。
- 父任务：VIB-65；依赖：VIB-45、VIB-48、VIB-56、VIB-58。
- 设计依据：LLD 9.7、15.3；HLD 6.12/6.14。

**范围与已有基础**：扩充已有检索评测框架，建立人工标注的真实语料、反证、歧义和错误引用研究集；模型角色资格、成本与时延同测。

**2026-09-28 初步真实模型联调（不改变 Backlog 状态）**：固定维基文库《傷寒論》修订 `2607901` 的太阳病上篇 29 条非方剂原文，独立 `tcm_preview_shanghanlun` 库用真实硅基流动 `bge-m3` 建索引，并经真实重排模型通过 5173 代理检索。开发者初选的 6 个目标条文问题均在前 3 条命中（5 个第 1）；用户截图的“太阳病”查询亦返回真实结果。**无关的现代胰岛素问题仍返回 5 条候选**，说明尚无校准过的“无结果”门槛。来源转写和自动审批未经过本项目专家复核，查询标签也非独立专家 Golden Set；本项正式验收依赖的反证/歧义/拒答、统计指标和模型资格仍未完成。原自动回归库固定假向量只验证程序逻辑，不计入真实模型质量证据。语料来源和初步证据见 `backend/fixtures/README.md`。

**完成标准**：记录 Precision/Recall/MRR/nDCG/反证召回/证据解析率；评估无支持 Claim、纠错率和证据增益；按 Prompt/Model/Workflow/KV/Index 版本保存；目标机器十万级数据校准 P95；阈值基于基线和专家样本冻结，不凭空设准确率。

### VIB-69 E10.4 安全、审计完整性与架构边界检查

- Linear：[VIB-69](https://linear.app/vibecoding-demo/issue/VIB-69/e104-安全审计完整性与架构边界检查)；状态：Backlog；优先级：High。
- 父任务：VIB-65；依赖：VIB-59、VIB-58、VIB-66、VIB-56。
- 设计依据：LLD 3/6/8/14/15.3；HLD 6.13。

**范围与已有基础**：补齐来源/备份文件攻击面、Prompt Injection、外发/密钥泄漏、本地 CSRF/Origin 及导入依赖方向检查。

**完成标准**：恶意文件/Zip Bomb/路径穿越被拦截；证据中的指令不获工具权限；Agent/Router/Worker 不绕过应用边界写库；事件哈希链可校验；非法引用跨 API/Agent/DB 拦截；正式配置无开发默认凭据。

### VIB-70 E10.5 Desktop Supervisor、安装升级与降级运行

- Linear：[VIB-70](https://linear.app/vibecoding-demo/issue/VIB-70/e105-desktop-supervisor安装升级与降级运行)；状态：Backlog；优先级：High。
- 父任务：VIB-65；依赖：VIB-59、VIB-62、VIB-63、VIB-64、VIB-66、VIB-67。
- 设计依据：LLD 16；需求 2.1。

**范围与已有基础**：按设计实现 Electron 或等价桌面壳，管理 PostgreSQL/API/Worker 生命周期与本地会话；形成 Release Manifest 和目标平台安装包。

**完成标准**：单实例、数据目录与磁盘检查、迁移快照、恢复扫描、正确 READY/DEGRADED；优雅停止和异常恢复；断网可浏览与本地检索；干净机器安装、升级/失败恢复、启动性能、数据保留测试通过。

### VIB-71 E11 Stage 1A/1B 正式验收与协议冻结

- Linear：[VIB-71](https://linear.app/vibecoding-demo/issue/VIB-71/e11-stage-1a1b-正式验收与协议冻结)；状态：Backlog；优先级：High。
- 父任务：无；依赖：VIB-65、VIB-62、VIB-63、VIB-64。
- 设计依据：LLD 18；需求 15.1/15.2。

**范围与已有基础**：以真实语料和完整产品执行阶段验收，冻结知识、Agent、工作流及发布兼容协议。

**完成标准**：全部 AC-1A/1B 有实现/测试/版本/审计证据；阻断缺陷清零；专家抽样、恢复演练和发布说明完成；不得用 E0–E7 Done 数量推算整体验收。

### VIB-72 E11.1 需求追踪矩阵、设计差异与决策闭环

- Linear：[VIB-72](https://linear.app/vibecoding-demo/issue/VIB-72/e111-需求追踪矩阵设计差异与决策闭环)；状态：Todo；优先级：High。
- 父任务：VIB-71；依赖：无。
- 设计依据：LLD 18.3、附录 C；需求 18.7。

**范围与已有基础**：建立 docs/traceability/requirements.csv，映射需求→设计→Issue→API/Contract→测试→版本→审计点；收敛 OCR/模型/性能及文档间阶段划分差异。

**完成标准**：每项功能至少一个验收证据；代码与 README/设计差异有明确状态；保留两段关联对话待核对项，不从标题推断选型；后续疗效阶段按需求 3/15 阶段总览解释并记录决策。

### VIB-73 E11.2 Stage 1A 知识底座验收

- Linear：[VIB-73](https://linear.app/vibecoding-demo/issue/VIB-73/e112-stage-1a-知识底座验收)；状态：Backlog；优先级：High。
- 父任务：VIB-71；依赖：VIB-72、VIB-46、VIB-47、VIB-48、VIB-49、VIB-62、VIB-66、VIB-68、VIB-69。
- 设计依据：LLD 18.1；需求 15.1。

**范围与已有基础**：逐项执行 AC-1A-01～08：真实来源、对象溯源、引用门禁、方剂字段、古病案双表示、版本与恢复、检索、质量报告。

**完成标准**：留存可复现数据和操作记录；不存在 Evidence 引用率 0；已发布关键引用可定位率 100%；真恢复及版本切换通过；所有阻断问题关闭。

### VIB-74 E11.3 Stage 1B 验收、V1 发布与交接

- Linear：[VIB-74](https://linear.app/vibecoding-demo/issue/VIB-74/e113-stage-1b-验收v1-发布与交接)；状态：Backlog；优先级：High。
- 父任务：VIB-71；依赖：VIB-73、VIB-56、VIB-57、VIB-63、VIB-64、VIB-67、VIB-68、VIB-69、VIB-70。
- 设计依据：LLD 18.2；需求 15.2。

**范围与已有基础**：逐项执行 AC-1B-01～08，专家抽查结论到原文，形成安装包、操作/恢复手册、发布说明和已知限制。

**完成标准**：合理争议不强制共识；Judge 无未审计新结论；历史报告可回放；Stage 1A、故障/安全/性能与桌面门禁通过；冻结 Knowledge/Agent/Workflow v1 和 API/备份兼容性；记录正式发布与回退步骤。

### VIB-75 阶段 2A 病例工作区与隐私边界

- Linear：[VIB-75](https://linear.app/vibecoding-demo/issue/VIB-75/阶段-2a-病例工作区与隐私边界)；状态：Backlog；优先级：Medium。
- 父任务：无；依赖：VIB-71。
- 设计依据：需求 3.4、15.3。

**范围与已有基础**：后续路线，当前不实施。V1 验收后先完成 2A 详细设计与数据策略。

**完成标准**：AC-2A-01～06；古病案无重复导入、现代病例完整、身份分离、未知不补造、导出版本有审计。

### VIB-76 2A.1 病例领域设计与古病案复用

- Linear：[VIB-76](https://linear.app/vibecoding-demo/issue/VIB-76/2a1-病例领域设计与古病案复用)；状态：Backlog；优先级：Medium。
- 父任务：VIB-75；依赖：VIB-71、VIB-47。
- 设计依据：AC-2A-01/05。

**范围与已有基础**：定义 PatientIdentity/CaseRecord/Encounter/Observation、字段字典、缺失/未知与冲突语义，复用 V1 古病案关联。

**完成标准**：评审 2A LLD、迁移和 API；相同古病案不重复导入；历史修订可追溯；缺失值不由模型擅自补全。

### VIB-77 2A.2 现代病例录入、就诊时间线与补充版本

- Linear：[VIB-77](https://linear.app/vibecoding-demo/issue/VIB-77/2a2-现代病例录入就诊时间线与补充版本)；状态：Backlog；优先级：Medium。
- 父任务：VIB-75；依赖：VIB-76。
- 设计依据：AC-2A-02/04/06。

**范围与已有基础**：病例、四诊、病程、检查、既往/用药/过敏史、附件与补充记录。

**完成标准**：结构化病例可保存和检索；时间线正确；追加修订、差异和导出有审计；病例用户流程端到端通过。

### VIB-78 2A.3 身份分离、病例权限与阶段验收

- Linear：[VIB-78](https://linear.app/vibecoding-demo/issue/VIB-78/2a3-身份分离病例权限与阶段验收)；状态：Backlog；优先级：High。
- 父任务：VIB-75；依赖：VIB-76、VIB-77、VIB-58。
- 设计依据：需求 13.3；AC-2A-03/06。

**范围与已有基础**：将身份信息与临床内容隔离，定义访问、脱敏、导出删除和留痕策略。

**完成标准**：真实身份默认不进入 Agent/远程模型；权限在服务端；删除兼顾历史审计；使用获授权数据完成 AC-2A-01～06 与安全评审。

### VIB-79 阶段 2B 临床推理、方药策略与医师确认

- Linear：[VIB-79](https://linear.app/vibecoding-demo/issue/VIB-79/阶段-2b-临床推理方药策略与医师确认)；状态：Backlog；优先级：Medium。
- 父任务：无；依赖：VIB-75。
- 设计依据：需求 3.5、15.4。

**范围与已有基础**：后续路线，依赖 2A 验收及领域专家参与；以现行需求为范围，具体临床规则另行审定。

**完成标准**：AC-2B-01～08；报告含正反证据和不确定性；风险门禁独立；处方必须医师确认并留痕。

### VIB-80 2B.1 多流派推理、MatchScore 与相似病案

- Linear：[VIB-80](https://linear.app/vibecoding-demo/issue/VIB-80/2b1-多流派推理matchscore-与相似病案)；状态：Backlog；优先级：Medium。
- 父任务：VIB-79；依赖：VIB-78。
- 设计依据：AC-2B-01～04。

**范围与已有基础**：定义临床 Agent 协议，归纳主症/病程，独立产生证候、病机、不典型点和相似病案，保留正反证据。

**完成标准**：至少两流派独立候选可比较；MatchScore 分项和权重可解释；冲突与缺失信息不抹平；回归集由专家标注。

### VIB-81 2B.2 方药候选与独立风险门禁

- Linear：[VIB-81](https://linear.app/vibecoding-demo/issue/VIB-81/2b2-方药候选与独立风险门禁)；状态：Backlog；优先级：High。
- 父任务：VIB-79；依赖：VIB-80。
- 设计依据：AC-2B-05/06。

**范围与已有基础**：组成/剂量/比例/炮制/剂型/煎服/疗程/加减候选与规则版本，覆盖需求指定的禁忌、过敏及高风险人群检查。

**完成标准**：执行处方、候选策略、研究假设分开；PASS/WARN/BLOCK 独立于模型评分；危险候选不能绕过；规则及数据来源经领域评审；完整正反场景回归通过。

### VIB-82 2B.3 医师确认签名、临床报告与阶段验收

- Linear：[VIB-82](https://linear.app/vibecoding-demo/issue/VIB-82/2b3-医师确认签名临床报告与阶段验收)；状态：Backlog；优先级：High。
- 父任务：VIB-79；依赖：VIB-80、VIB-81。
- 设计依据：AC-2B-07/08；需求 14、15.4。

**范围与已有基础**：医师可确认、修改、合并、拒绝候选，保留差异、签名、处方版本和报告。

**完成标准**：全链追溯到病例/知识/规则/模型版本；完整辩论可展开；高风险门禁和专家盲评通过；AC-2B-01～08 留存证据。

### VIB-83 阶段 3 疗效反馈、假设演进与规律研究

- Linear：[VIB-83](https://linear.app/vibecoding-demo/issue/VIB-83/阶段-3-疗效反馈假设演进与规律研究)；状态：Backlog；优先级：Medium。
- 父任务：无；依赖：VIB-79。
- 设计依据：需求 3.6、15.5。

**范围与已有基础**：后续路线，依赖 2B 验收和有质量的治疗结局，不自动训练模型或改临床规则。

**完成标准**：AC-3-01～08；疗效可归因，单例只成假设，多例证据可升级也可推翻；更新需人工审核。

### VIB-84 3.1 随访 Outcome 与疗效归因

- Linear：[VIB-84](https://linear.app/vibecoding-demo/issue/VIB-84/31-随访-outcome-与疗效归因)；状态：Backlog；优先级：Medium。
- 父任务：VIB-83；依赖：VIB-82。
- 设计依据：AC-3-01～03。

**范围与已有基础**：手工录入症状/舌脉/检查变化、不良反应、停药原因，关联病例、辨证、处方、剂量剂型疗程。

**完成标准**：时间线和来源明确；归因记录病机、剂量、剂型、病程、体质、依从性及自然波动等候选，保留反证和不确定性。

### VIB-85 3.2 单例假设、多例复现与证据评审

- Linear：[VIB-85](https://linear.app/vibecoding-demo/issue/VIB-85/32-单例假设多例复现与证据评审)；状态：Backlog；优先级：Medium。
- 父任务：VIB-83；依赖：VIB-84。
- 设计依据：AC-3-04/05；需求 14.4。

**范围与已有基础**：建立 HYPOTHESIS→PROVISIONAL/CONFIRMED 等版本化流程，明确适用范围、反例和样本质量。

**完成标准**：单例不升级为已确认规律；多例复现、正反证据和跨流派评审后才转换状态；时间切分/独立验证防止重复计数和过拟合。

### VIB-86 3.3 规律治理、方药优化反馈与阶段验收

- Linear：[VIB-86](https://linear.app/vibecoding-demo/issue/VIB-86/33-规律治理方药优化反馈与阶段验收)；状态：Backlog；优先级：Medium。
- 父任务：VIB-83；依赖：VIB-85。
- 设计依据：AC-3-06～08。

**范围与已有基础**：规律与典籍/教材/指南分层；支持冻结、降级、废弃、推翻和回滚；方药优化仍需医师确认。

**完成标准**：人工审核所有规则更新；不自动改模型权重；版本变更和影响可查；AC-3-01～08 完成专家与回归验收。

## 发布验证口径

- AC-1A-01～08：真实来源与定位、实体方剂证据、引用拦截、方剂结构查询、古病案双表示、修订发布与真恢复、检索、质量报告。
- AC-1B-01～08：问题规划、首轮隔离、质疑和追加式修订、五类审计、合理争议、Judge 分层报告、摘要与展开、关键结论到原文溯源。
- 硬门禁：无效 Evidence 引用率 0、关键发布引用可定位率 100%、失租结果丢弃、恢复不重复业务对象、发布失败不切换 Active、历史报告不静默变化、EventLog 可校验、Backup 真恢复。
- Benchmark：Precision/Recall/MRR/nDCG、反证召回、证据解析、无支持 Claim、纠错效果、时延和成本。先建立真实标注基线再定正式阈值。
- HLD 初始性能目标待目标机器校准：十万级 Exact/FTS/结构查询 P95 ≤1s；混合检索不含远程模型 P95 ≤3s；Evidence 详情 P95 ≤500ms；任务创建 ≤500ms；暂停/取消请求响应 ≤1s；基础知识可读冷启动目标 ≤15s。这些不是本次测试结果。

## 尚待明确

关联对话尚未读取、首批语料与授权/OCR 比例、正式模型资格、目标机器性能阈值、领域专家与开发产能。模型历史价格描述不视为现价；语义效果需专家样本验证。需求正文与附录的阶段差异由 VIB-72 记录，当前采用需求第 3/15 章的 2A → 2B → 3 划分。
