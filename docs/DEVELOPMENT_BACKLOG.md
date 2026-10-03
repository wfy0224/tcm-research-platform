# 当前开发任务队列

更新：2026-10-01。用户决定：先客户演示核心流程，完整工程验收后移。已开始实施；VIB-87 工程验收通过；用户再次反馈 UI 后，VIB-88 全文分段与完整引文修复已通过工程验收；VIB-93 的耗时反馈和审核负担已处理，研究与报告布局仍待完成。详细范围、交互要求和验收见 [客户演示优先计划](DEMO_FIRST_PLAN.md)。

## 第一优先：D1 导入能继续

| Issue | 工作 | 状态 / 优先级 | 前置 |
| --- | --- | --- | --- |
| [VIB-87](https://linear.app/vibecoding-demo/issue/VIB-87/d101-导入后下一步禁用原因与证据草稿闭环) | 导入后下一步、禁用原因与证据草稿闭环 | Done / Urgent | 无未完成前置 |
| [VIB-88](https://linear.app/vibecoding-demo/issue/VIB-88/d102-完整段落阅读与句子被拆开的解析修复) | 完整段落阅读与句子被拆开的解析修复 | Done / Urgent | 无未完成前置 |
| [VIB-89](https://linear.app/vibecoding-demo/issue/VIB-89/d103-上下文完整展示与引用跳转高亮) | 上下文完整展示与引用跳转高亮 | Done / High | VIB-88 |
| [VIB-93](https://linear.app/vibecoding-demo/issue/VIB-93/d1ui-核心工作台页面划分操作布局与视觉统一) | 核心工作台页面划分、操作布局与视觉统一 | In Progress / High | 无未完成前置 |

## 第二优先：D2 检索能使用

| Issue | 工作 | 状态 / 优先级 | 前置 |
| --- | --- | --- | --- |
| [VIB-90](https://linear.app/vibecoding-demo/issue/VIB-90/d201-知识整理到可检索版本的一体化衔接) | 知识整理到可检索版本的一体化衔接 | In Progress / High | VIB-87、VIB-89 |
| [VIB-91](https://linear.app/vibecoding-demo/issue/VIB-91/d202-云端检索可用性与本地检索能力澄清) | 云端检索可用性与本地检索能力澄清 | In Progress / High | VIB-90 |

## 第三优先：D3 真实研究能演示

| Issue | 工作 | 状态 / 优先级 | 前置 |
| --- | --- | --- | --- |
| [VIB-92](https://linear.app/vibecoding-demo/issue/VIB-92/d301-真实研究问题到可追溯报告的页面闭环) | 真实研究问题到可追溯报告的页面闭环 | In Progress / High | VIB-91 |
| [VIB-94](https://linear.app/vibecoding-demo/issue/VIB-94/d302-客户演示脚本与核心流程联合验收) | 客户演示脚本与核心流程联合验收 | In Progress / High | VIB-92、VIB-93 |

VIB-87 验收见 [导入与证据草稿流程验收](VIB87_IMPORT_GUIDANCE_ACCEPTANCE.md)。真实 API/Worker 与浏览器工程验证通过；合成资料，0 次真实模型调用，用户体验结论仍单独记录。VIB-93 已实施共用导航、知识库阅读/导入/审核布局并实际检查截图；研究和报告仍有剩余，整项 In Progress，见 [界面重做记录](VIB93_UI_REWORK.md)。

2026-10-01 完整《方剂学.txt》演示未通过：上传/解析/提取完成，但句中截断、父子段重复，选择麻黄汤逻辑段 565～586 的 22 条父段后仍无法创建完整证据。VIB-88 修复须同时验证连续完整引文可创建；VIB-93 需处理耗时反馈与逐条必填审核说明负担；VIB-94 全流程未验收。实际步骤和截图见 [真实文献演示停点](VIB94_FANGJI_DEMO.md)，原失败证据保留。

2026-10-01 已修复上述演示阻断：连续混合类型正文精确引用、软换行与分页续句、阅读父子重复、耗时提示、批量审核与失败恢复、导入后勾选被滞后刷新清空。独立库33项后端检查通过；真实API/Worker页面验证完整方剂学导入和麻黄汤完整证据创建通过。原演示来源已新增修订2，修订1及其候选保留；本轮无真实医学审核/发布/研究调用。VIB-88工程完成，VIB-93和VIB-94仍有剩余，见 [全文演示问题修复](DEMO_BUGFIXES.md)。

2026-10-01 用户要求继续演示：修订2两方8段/15段完整引用创建、操作者文本核对、两个概念名称审核和版本2本地发布通过；与原文件文字一致（忽略排版空白）。大青龙汤/麻黄汤/无关查询实际1/2/0条，重复目标查询一致。引用回跳失败（落质量发布页，原文首段，无高亮），VIB-89待修；手工入口无方剂类型（VIB-90），状态矛盾/刷新需重选任务/质量页JSON等归VIB-93。研究任务已创建，未配置TCM_RESEARCH_MODEL导致启动禁用；0云调用，无报告/导出，VIB-92未验收。VIB-94已实际开始演示，置In Progress但全链未通过；已同步Linear VIB-94/VIB-89。详见 [核心流程接续演示与问题清单](VIB94_FANGJI_CONTINUED_DEMO.md)。

2026-10-01 VIB-89工程验收完成：精确来源/证据修订导航、长文引用全文校验与高亮、刷新恢复、返回原阅读与报告位置、完整相邻上下文与失败重试通过。真实已有大青龙汤检索→修订2阅读180～194的15段高亮→原证据返回通过；独立库34 passed / 0 skipped，合成页面边界/历史修订/长文/子句/失败恢复/报告往返回归通过。未重建文献或发布版本，未新启模型研究；真实研究报告全链仍待验收。记录见 [引用定位验收](VIB89_CITATION_ACCEPTANCE.md)。下一开发项VIB-90。

VIB-62为知识工作区父任务，Todo / High；VIB-87～90为其子任务。已移除VIB-46/48整体完成对VIB-62的阻塞，保留关联和VIB-60既有接口依赖。正式知识验收VIB-73的完整依赖不删。

## 演示后：知识覆盖、运行质量与正式交付

以下均Backlog / Medium，新增VIB-94前置，原正式验收和其他依赖保留。

| Issue | 工作 | 主线如何复用 |
| --- | --- | --- |
| [VIB-45](https://linear.app/vibecoding-demo/issue/VIB-45/v1-初始语料清单来源授权与-ocr-实施决策) | V1 初始语料清单、来源授权与 OCR 实施决策 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-46](https://linear.app/vibecoding-demo/issue/VIB-46/v1-知识候选抽取术语规范与方剂字段补齐) | V1 知识候选抽取、术语规范与方剂字段补齐 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-47](https://linear.app/vibecoding-demo/issue/VIB-47/v1-古病案文献与-caserecord-兼容对象) | V1 古病案文献与 CaseRecord 兼容对象 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-48](https://linear.app/vibecoding-demo/issue/VIB-48/v1-结构与关系检索查询规范化及断网降级) | V1 结构与关系检索、查询规范化及断网降级 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-58](https://linear.app/vibecoding-demo/issue/VIB-58/v1-模型网关治理冻结策略与统一外发控制) | V1 模型网关治理、冻结策略与统一外发控制 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-64](https://linear.app/vibecoding-demo/issue/VIB-64/v1-任务中心审计备份和系统设置工作区) | V1 任务中心、审计备份和系统设置工作区 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-65](https://linear.app/vibecoding-demo/issue/VIB-65/e10-恢复安全性能备份与桌面交付) | E10 恢复、安全、性能、备份与桌面交付 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-66](https://linear.app/vibecoding-demo/issue/VIB-66/e101-加密备份临时恢复验证与发布迁移快照) | E10.1 加密备份、临时恢复验证与发布迁移快照 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-67](https://linear.app/vibecoding-demo/issue/VIB-67/e102-全研究链-nodeexecution-与故障恢复演练) | E10.2 全研究链 NodeExecution 与故障恢复演练 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-68](https://linear.app/vibecoding-demo/issue/VIB-68/e103-真实-golden-set模型资格与性能评测) | E10.3 真实 Golden Set、模型资格与性能评测 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-69](https://linear.app/vibecoding-demo/issue/VIB-69/e104-安全审计完整性与架构边界检查) | E10.4 安全、审计完整性与架构边界检查 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-70](https://linear.app/vibecoding-demo/issue/VIB-70/e105-desktop-supervisor安装升级与降级运行) | E10.5 Desktop Supervisor、安装升级与降级运行 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-71](https://linear.app/vibecoding-demo/issue/VIB-71/e11-stage-1a1b-正式验收与协议冻结) | E11 Stage 1A/1B 正式验收与协议冻结 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-72](https://linear.app/vibecoding-demo/issue/VIB-72/e111-需求追踪矩阵设计差异与决策闭环) | E11.1 需求追踪矩阵、设计差异与决策闭环 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-73](https://linear.app/vibecoding-demo/issue/VIB-73/e112-stage-1a-知识底座验收) | E11.2 Stage 1A 知识底座验收 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |
| [VIB-74](https://linear.app/vibecoding-demo/issue/VIB-74/e113-stage-1b-验收v1-发布与交接) | E11.3 Stage 1B 验收、V1 发布与交接 | 已有能力继续复用；直接阻断演示的小缺口归入对应D任务 |

恢复顺序：必要知识覆盖和真实质量评测→可靠性/备份/安全→桌面安装交付→正式Stage 1A/1B验收。演示不是正式发布，也不是医学/临床质量认证。

## 后续产品阶段

VIB-75～86全部Backlog / Low；保留2A→2B→3依赖，并增加VIB-94前置。病例、处方和疗效不进入本次演示。

- [VIB-75](https://linear.app/vibecoding-demo/issue/VIB-75/阶段-2a-病例工作区与隐私边界)：阶段 2A 病例工作区与隐私边界
- [VIB-76](https://linear.app/vibecoding-demo/issue/VIB-76/2a1-病例领域设计与古病案复用)：2A.1 病例领域设计与古病案复用
- [VIB-77](https://linear.app/vibecoding-demo/issue/VIB-77/2a2-现代病例录入就诊时间线与补充版本)：2A.2 现代病例录入、就诊时间线与补充版本
- [VIB-78](https://linear.app/vibecoding-demo/issue/VIB-78/2a3-身份分离病例权限与阶段验收)：2A.3 身份分离、病例权限与阶段验收
- [VIB-79](https://linear.app/vibecoding-demo/issue/VIB-79/阶段-2b-临床推理方药策略与医师确认)：阶段 2B 临床推理、方药策略与医师确认
- [VIB-80](https://linear.app/vibecoding-demo/issue/VIB-80/2b1-多流派推理matchscore-与相似病案)：2B.1 多流派推理、MatchScore 与相似病案
- [VIB-81](https://linear.app/vibecoding-demo/issue/VIB-81/2b2-方药候选与独立风险门禁)：2B.2 方药候选与独立风险门禁
- [VIB-82](https://linear.app/vibecoding-demo/issue/VIB-82/2b3-医师确认签名临床报告与阶段验收)：2B.3 医师确认签名、临床报告与阶段验收
- [VIB-83](https://linear.app/vibecoding-demo/issue/VIB-83/阶段-3-疗效反馈假设演进与规律研究)：阶段 3 疗效反馈、假设演进与规律研究
- [VIB-84](https://linear.app/vibecoding-demo/issue/VIB-84/31-随访-outcome-与疗效归因)：3.1 随访 Outcome 与疗效归因
- [VIB-85](https://linear.app/vibecoding-demo/issue/VIB-85/32-单例假设多例复现与证据评审)：3.2 单例假设、多例复现与证据评审
- [VIB-86](https://linear.app/vibecoding-demo/issue/VIB-86/33-规律治理方药优化反馈与阶段验收)：3.3 规律治理、方药优化反馈与阶段验收

## 已有完成记录与历史依据

已Done的VIB-36～44、49～57、59～61、63保留；不因新规划撤销或重做。VIB-63既有验收使用假模型，真实研究增量由VIB-92负责。

原任务完整范围、历史验收和设计依据见 [重排前清单](handoff-history/2026-10-01-backlog-before-demo-replan.md)。此归档不是执行队列；只有追溯具体任务才读取。当前各旧任务的实际状态以本页和Linear最新记录为准，不使用归档状态接续。

## 接续规则

- VIB-87、VIB-88 工程完成；下一项承接 VIB-89 原文上下文、引用回跳与高亮，VIB-93 随核心流程继续落地。
- 不按旧编号、旧评论、历史In Progress或归档中的“下一步”启动旧工程。
- 每批以用户路径实际验证，记录通过/失败/未验证，不用Done数量推算整体完成。
- 本轮已运行构建、导入页面闭环、API 错误检查和开发连接回归；研究旧模拟脚本超时未计通过。同步与下一步见根交接。

2026-10-01真实云端与整书核对增量：修订2全部4211正文片段、843新增原文证据核对；376最新方剂全部REVIEWED（233组成/141附方/2残缺），缺失仍未知，非医学专家认证。KV4 READY/ACTIVE：1243证据/376方剂/3概念，125批真实云端向量索引完成；bge-m3/bge-reranker-v2-m3实际检索通过。VIB-90/91整体仍In Progress，整书脚本尚未整合通用提取UI。

2026-10-01 VIB-92/93/94真实报告恢复：修历史候选仅元数据门禁、生成超时180s、独立复核紧凑输入与刷新遗留错误。原问题RT-01a0f788-b1a8-7cee-9e52-7cee5d555a58 / JOB-01a0f788-b28f-72ee-8a1f-ba401705fba4已COMPLETED，KV4/21证据/9观点/18审计/7高置信2条件，6稿5拒后真实接受3段综合回答。页面折叠与MD/DOCX export/v3导出通过，Word经LibreOffice渲染11页逐页检查。真实门禁回滚/报告引用边界/旧报告不变检查、传输15单测、构建/Ruff通过；集成旧schema/旧fixture失败不计通过。角色调用累计1513545ms、664726tokens，成本未知。Critic0质疑/0回应且最终仅引用去重后1条大青龙汤原文，不能宣称完整辩论或整体验收。证据 docs/acceptance-artifacts/real-research-answer/。

2026-10-01用户分歧场景已修复：RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940 / JOB-01a0f7c4-c583-716b-a786-e407fb6c27ef 均COMPLETED，保留48证据/9观点/18审计/5质疑/5回应、7高置信2未解决。三稿耗尽后保存明确NEEDS_REVISION报告，再由页面继续修订，沿用冻结deepseek/deepseek-flash真实Writer/Reviewer round3 accepted=true、issues=[]；新增research-report/v3 revision2 ACCEPTED，旧稿旧检查点不覆盖。准确FAILED状态、可用报告恢复、有界新稿修订、0027不可变报告版本及最新导出已落地。MD/DOCX导出与页面已完成验证；Word19页逐页检查。独立克隆库43 passed/0 skipped，构建/Ruff与旧报告哈希通过。新research-v3默认最多3轮，质疑回应后Critic复查，含冻结往返/缺口；旧任务max1不变，新max3多轮真实云端全链未执行，下一步验证该路径与新报告引用回跳。证据见[报告恢复验收](acceptance-artifacts/report-recovery/ACCEPTANCE.md)。VIB-92/93/94保持In Progress并已同步Linear。
2026-10-01 报告可读性与依据跳转修复：report-export/v6 的实际MD/DOCX已重新生成，正文去除内部UUID、哈希和运行/知识/索引编号，改用本报告内观点、证据、质疑、回应、缺口编号与有效链接；保留完整原文和研究回答。三个实际任务的四个报告版本只读检查通过，可见ID/哈希0，65/63/30/22个内部链接全部有目标，已存报告哈希未变化。实际接受稿Word19页逐页检查。页面依据1～4点击均展开、聚焦、高亮，重复点击、键盘Enter、返回引用及刷新深链接通过；定位标题约90px避免固定导航遮挡。构建、相关Ruff、diff检查通过。本轮无新增研究模型调用，新max3真实多轮全链仍待执行；VIB-92/93/94保持In Progress。证据见[报告可读性与跳转验收](acceptance-artifacts/readable-report/ACCEPTANCE.md)。

2026-10-03 VIB-92/94服务器交叉辩论失败修复：原任务 RT-01a1001e-e294-7ab7-9ba2-e2005bee58cc 的 Rebuttal 修订类型被原角色门禁拒绝；补齐逐目标 allowed_claim_types 和明确修订契约，旧冻结快照保留。部署前失败测试和部署后2项回归/5真实目标上下文校验通过，用户批准后已部署并重试原任务，实际第2轮5回应和第3轮Critic已完成，后续回应与报告仍在运行，未宣称全链通过。更早 invalid JSON 失败未归为同因。Linear本轮待同步；证据见[服务器回应类型约束修复](acceptance-artifacts/server-rebuttal-contract/ACCEPTANCE.md)。

2026-10-03 用户指定只改并重新部署：确认原任务冻结 deepseek/deepseek-flash，将其 max_tokens 从2048设为官方最大393216（384K）。备份 cloud_models.py、镜像构建及API/Worker重启完成；0模型调用，未重试、未监测研究，JSON失败是否解决尚未验证。VIB-92/94仍In Progress；Linear待同步。

2026-10-03 VIB-92/94报告校验反馈断路已修并部署：程序内容/结构不合规保存原稿及独立ReportValidator，将具体意见交下一稿；正式模型复核仍必需，设施故障仍重试。4回归修复前3errors/候选全通过；0云调用，原报告尚未重新实际修订，不宣称全链通过；证据server-rebuttal-contract/REPORT_VALIDATION_FEEDBACK.md，Linear待同步。

2026-10-03 VIB-92/94真实测试未通过：原任务5次有界修订、15Writer/10Reviewer/5程序Validator，最新rev7 NEEDS_REVISION。上下文/报告契约/反馈保留已部署，8工程回归通过；原报告仍未获复核接受，不能宣称交付。用户投诉连续付费调用后停止进一步模型调用；无运行测试队列，后续云测试必须重新明确授权。证据server-rebuttal-contract/REAL_REPORT_TEST.md及JSON；Linear待同步。

2026-10-03 VIB-92/94离线修稿链路已修部署：上一稿传递、全错误定位、相关缺口/争议过滤、相同失败稿提前停止；16回归及真实失败稿重放通过，0模型调用/0生产DB写入，原报告rev7仍未通过。不得宣称真实研究验收完成，后续付费云验必须重新明确授权及预算。证据server-rebuttal-contract/OFFLINE_REPAIR.md；Linear待同步。

2026-10-03 用户指定服务器模型配置改造：研究页模型设置新增API密钥/向量/重排配置，数据库governance.model_configuration（0028）保存并首次导入旧配置。服务器镜像与迁移完成；独立库保存/空密钥保留/不回显/重连持久性检查通过，线上GET200及CSRF保存验证通过，0付费模型调用。视觉验收及完整pytest未执行，Linear待同步。
