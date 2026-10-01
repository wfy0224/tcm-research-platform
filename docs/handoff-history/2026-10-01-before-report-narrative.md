# 开发交接

## 当前状态
- 2026-10-01，分支 codex/evidence-audit，HEAD 7b27043；本轮未提交，既有全部未提交内容保留。
- 用户要求继续核心流程、真实云端模型、完整研究，拒绝模拟业务数据；随后明确要求整份方剂审核通过，以及批量审核无需逐项填写通过原因、报告结论优先和原文折叠。
- 来源 SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350 修订2：真实约1 MB《方剂学》；4,211正文片段全部覆盖，843条新增完整顺序证据文本核对通过。
- 已核对376个最新方剂条目：233组成块、141附方、2组成残缺条目，失败0。2条残缺是柴葛解肌汤、三仁汤，药名仅据方解，缺失剂量仍未知；非医学专家审核。
- 实际API分页复核376条全部REVIEWED；通过不填note的批量接口重放返回total0，不重复写审核。
- 云端版本3已READY/活动，24证据/3概念；版本4已有1243证据/376方剂/3概念，真实全文/向量索引READY且已激活，发布首次成功。发布JOB-01a0f76a-5ded-7f06-9e2d-08923490bf07。
- 原两证据小范围任务 RT-01a0f73b-04e1-7c42-bd42-2c21c469f744 已真实完成并导出，但Critic返回0质疑、无Rebuttal，不宣称完成往返辩论。
- 重跑试验RT-01a0f766-a5a0-73ff-9857-2f5d1231f088因浏览器脚本发布等待条件过早误选旧版本3，已取消并保留记录。脚本已要求快照数量匹配整本预览后才继续。
- 当前完整书研究RT-01a0f773-3445-7c68-bd35-6c56ba0761eb已启动，冻结版本4；脚本会话73662持续运行。不得重用已取消试验或修改旧冻结报告。

## 服务及验证
- URL http://127.0.0.1:18067，既有Linux容器 tcm-vib54-py，真实工作区库tcm_vib62_workspace_test；Node PTY会话51734，结束可输入stop。
- 云端配置：TCM_OUTBOUND_MODE=CLOUD_ALLOWED，TCM_PUBLICATION_STRATEGY=hybrid-rrf-v1，TCM_MODEL_PROVIDER=TCM_RESEARCH_PROVIDER=siliconflow，TCM_RESEARCH_MODEL=deepseek-ai/DeepSeek-V3.2。凭据来自已有环境，不打印。
- 新增启动器转发检索配置；已真实验证bge-m3向量+bge-reranker-v2-m3云端重排，旧本地配置和历史版本保留。
- 修复worker没有初始化冻结任务的真实检索客户端；增加失败重试API/按钮、任务刷新恢复、实时审计计数；同任务恢复检查点成功。
- Critic输入新增冻结研究问题、子问题、观点理由、来源范围，提示覆盖剂量双口径、问题完整性和因果边界，并保存review_summary。真实旧任务捕获输入绿检通过。
- 376方剂引用按原文和Unicode字符位置校验，原方剂量未换算；结构化缺字段保留null。跨段药名/原文重复药物被保留，旧已核对修订不覆盖。
- 建索引单条上限4,000→6,000字符：实书最长约4,183含上下文；保持完整引用，无截断。须以版本4真实供应商调用确认。
- npm run build、涉及11个Python文件Ruff（忽略Windows挂载EXE002）、git diff --check通过。未运行Windows Python/uv/Alembic，无新模拟业务数据。
- 旧真实报告UI已验证：结论优先、相关表述折叠保留、证据编号去重并默认折叠；报告查看隐藏完成任务的冗余控制，已完成执行状态显示已结束。
- DOCX已生成真实文件，OOXML可验证；尚无版面渲染验收，不宣称PDF/排版通过。

## 实现和证据
- backend knowledge_api/publish/worker：手工方剂逐字段出处、完整发布预览、幂等准备快照、构建后显式激活、批量审核、分页offset、最新方剂修订列表。
- frontend FormulaEditor/KnowledgeWorkspace：方剂手工核对、整份修订通过按钮、通过无需原因、分页全量读取；ResearchReport：结论优先、证据去重折叠；ResearchWorkspace：进度/重试/恢复/辩论审查说明。
- backend/scripts/review_fangji_corpus.py：实书云端字面提取、精确字段出处和用户授权文本审核，可缓存续跑；cover_fangji_corpus.py：全文按顺序覆盖并核对，不依答案选证据。
- docs/acceptance-artifacts/full-fangji-review：formulas.json/coverage.json/api-verification.json，376/376方剂、4211/4211片段、843原文证据。
- docs/acceptance-artifacts/real-fangji-flow：原24证据版本云端检索、旧小范围报告及MD/DOCX；full-fangji-research：当前整书重跑现场。
- VIB-90/91/92/93/94仍In Progress，未完成全部Issue验收；需同步本轮全量审核和真实研究证据至Linear与backlog。
- 上一交接已归档docs/handoff-history/2026-10-01-before-real-cloud-flow.md。

## 下一条操作
- 轮询会话38836或版本4发布任务，版本4已READY/活动。研究运行中每60秒内说明阶段与实际证据/审计/质疑/回应数量。
- 确认新任务冻结版本4且来源范围仅目标整书；检查是否取得总论剂量和其他对照材料，真实Critic/Rebuttal执行，处理实际失败或待审。
- 完成报告/导出真实浏览器检查，保存报告与截图；更新本页（≤100行、8 KB）、backlog和Linear，再按实际结果交接。禁止用模拟数据弥补研究失败。
