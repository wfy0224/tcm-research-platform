# 开发交接

## 当前停点
- 2026-10-01，分支 codex/evidence-audit，HEAD 7b27043；所有既有未提交改动保留，未提交/推送。
- 用户最后要求“记录任务。没token了”：停止继续开发和研究调用，本页为接续入口。
- 用户研究问题必须原样为：比较麻黄汤和大青龙汤，分析大青龙汤中麻黄用量为什么比麻黄汤多
- 用户要求真实云端、完整研究/实际质疑回应、全书方剂审核、通过无需原因、报告用自己的话回答且原文折叠。不能再拿模拟数据补验收。

## 真实资料与已完成事项
- 来源 SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350 修订2为真实约1 MB完整《方剂学.txt》，不是仅两方；原文件 C:/Users/wangfeiyu/Downloads/方剂学.txt。
- 4,211正文片段顺序覆盖，843条新增原文证据核对；376个最新方剂条目全部REVIEWED、失败0（233组成块、141附方、2组成残缺）。
- 柴葛解肌汤p333、三仁汤p3327组成残缺，药名仅据原文方解，剂量缺失保留未知。属于用户授权的文本核对，非医学专家认证。
- 方剂分页全量读取、默认最新修订、整份修订批量通过且note可省略，真实API376条复核通过；重放total0不重复审核。
- KV-000004 READY/ACTIVE：1243证据/376方剂/3概念；真实全文+云端向量索引125批构建成功，发布JOB-01a0f76a-5ded-7f06-9e2d-08923490bf07完成。
- index IB-e3e7a3fa3fb4d9784d036162b09a4b93；云检索bge-m3+bge-reranker-v2-m3已实际成功。索引块上限6000保留实书最长约4183字符。
- 原两证据任务 RT-01a0f73b-04e1-7c42-bd42-2c21c469f744完成，Critic0质疑/无Rebuttal，旧报告v1不可改写，不宣称完整往返辩论。

## 当前研究失败及下一条操作
- 当前准确一句话任务 RT-01a0f788-b1a8-7cee-9e52-7cee5d555a58 冻结KV4、workflow research-v2。
- 真实取回21条证据，含剂量说明与柯琴方论；Classicist已提交3观点，HistoricalScholar仍PENDING，Theorist PENDING，尚无审计/辩论/报告。
- JOB-01a0f788-b28f-72ee-8a1f-ba401705fba4 FAILED，attempts3；确定错误：ValueError: HistoricalScholar requires explicit source history metadata。
- 根因第二处门禁未修：backend/src/tcm_platform/research_service.py::submit_first_round_output，visible之后约585行，仅允许SourceDocument作者/时代等元数据存在，误拒绝正文明确引用医家方论的历史观点。
- 已移除research_runtime.execute_first_round仅因元数据缺失便跳过HistoricalScholar的捷径。真实模型已调用历史考证3次，但输出被上述门禁拒绝；不要把ModelInvocation成功等同观点提交成功。
- 下一条具体操作：修复submit_first_round_output历史门禁，使正文所载方论可进入候选，仍严格检查可见/已审核/冻结证据ID，再由语义审计限制史实推断；不要填造作者元数据。
- 修复后重启本机服务，用现有任务retry恢复检查点，勿重新创建任务/重做经典观点。再运行frontend/scripts/check_real_research_answer.mjs续跑。
- 辩论、综合回答与导出真实验收尚未完成；不得宣称成功。

## 本轮新增报告实现（尚待真实全链验证）
- 根因：judge_service.render_structured_report仅分组复制assertion_text，原来没有综合写作。
- 新report_narrative.py：ReportWriter用自己的话先回答核心问题，引用裁决后HIGH_CONFIDENCE/CONDITIONAL观点；ReportReviewer独立核对引用/事实/因果/剂量边界，最多3稿，未通过不保存最终报告。
- Writer/Reviewer真实模型调用、AgentRun检查点、冻结提示与版本已接入REPORTING；judge分类不改，旧冻结任务保持旧协议；新报告research-report/v2。
- API新增answer；ResearchReport正文展示综合回答，详细观点/审计与去重编号原文默认折叠；旧报告明确注明未生成综合回答。
- Markdown/DOCX导出先呈现回答，详细论证与过程为附录；Markdown附录折叠。未生成新任务最终文件，未做DOCX版面渲染验收。
- Planner/首轮提示v2：用户一句话、自动规划剂量口径/对照与开放问题，观点须以自己的话形成比较解释。
- 旧长问题任务RT-01a0f773-3445-7c68-bd35-6c56ba0761eb因语义审计误引ID失败，已取消。审计输入去掉易混淆的来源/片段ID，明确只复制evidence_revision_id。
- 一句话试验RT-01a0f784-e6a0-71d8-9ad5-2e752789aa8c已取消，因发现历史角色被跳过；现场保留cancelled-metadata-skip.json。

## 服务、验证与证据
- URL http://127.0.0.1:18067；Linux容器tcm-vib54-py、真实独立库tcm_vib62_workspace_test；Node PTY会话8779仍在服务，停止可写入stop。研究轮询会话42104已失败退出，无研究任务运行。
- 云配置：TCM_OUTBOUND_MODE=CLOUD_ALLOWED、TCM_PUBLICATION_STRATEGY=hybrid-rrf-v1、TCM_MODEL_PROVIDER=TCM_RESEARCH_PROVIDER=siliconflow、TCM_RESEARCH_MODEL=deepseek-ai/DeepSeek-V3.2。凭据继承已有环境，禁止打印。
- 未运行Windows Python/uv/Alembic（错误弹窗风险）；只使用既有Linux Docker Python。无新模拟业务数据或模型替身。
- 最新npm run build通过；涉及报告/运行/审计文件Ruff通过；git diff --check通过（仅CRLF提示）。新检查脚本已移除唯一unused import，未再次运行最终绿检。
- backend/scripts/check_real_report_answer.py对真实旧v1报告实际红检：report still only arranges copied assertions；须对新任务完成后绿检，核对真实角色调用/外发授权、跨任务引用拒绝、条件观点升级拒绝、旧报告未修改。
- frontend/scripts/check_real_research_answer.mjs真实API创建/恢复任务、进度、answer与MD/DOCX检查；默认模型未设置时明确选已有DeepSeek-V3.2条目，不修改用户默认。
- docs/acceptance-artifacts/real-research-answer/result.json为当前失败现场；full-fangji-review为376/4211覆盖证据；real-fangji-flow为旧真实云端与报告；full-fangji-research为前次失败现场。
- 用户IAB仍开研究页；完成新任务后选择RT788、验证正文回答/折叠原文，保存截图与真实导出再交接。
- VIB-90/91/92/93/94均In Progress，完整Issue标准未全部满足；整书脚本尚未整合为通用提取UI，VIB-92还需第二场景等验收。
- 上次交接存档docs/handoff-history/2026-10-01-before-report-narrative.md；不必启动时读历史。
