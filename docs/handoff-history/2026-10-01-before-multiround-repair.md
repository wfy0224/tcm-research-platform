# 开发交接

## 当前停点与下一步
- 2026-10-01，分支 codex/evidence-audit，HEAD 7b27043；既有未提交改动全部保留，未提交/推送。
- 用户先问辩论为何只有说明，随后自行用建议题目创建新研究；最后截图问“何意味”。已查明新任务报告三稿复核未通过，前面实际5质疑/5回应完整保留。
- 下一条具体操作：查看新任务 ReportWriter/ReportReviewer 三轮真实检查点，修复报告对原方总量/每服量和古今剂量口径的表达、复核反馈收敛与耗尽后的可恢复策略；不要无限重试或降低审计标准。
- 同时修复 ResearchWorkspace.tsx 执行状态：job FAILED 时不能显示 control_state ACTIVE 的“运行中”；REPORTING 为失败时所处阶段，非仍在生成。当前通用“重试失败步骤”在三稿耗尽时不会推进。
- 用户要求真实云端与实际往返辩论、完整原文、自己的话回答、原文折叠；不能用模拟业务数据补验收。保留两个真实任务及全部检查点，不改写已完成报告。

## 真实资料与知识版本
- 来源 SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350 修订2为约1 MB完整《方剂学.txt》；原文件 C:/Users/wangfeiyu/Downloads/方剂学.txt。
- 4211正文片段、843条新增原文证据文本核对，376个最新方剂全部REVIEWED、失败0（233组成、141附方、2残缺）。柴葛解肌汤p333/三仁汤p3327缺失剂量仍未知；非医学专家认证。
- KV-000004 READY/ACTIVE：1243证据/376方剂/3概念；125批真实云端向量索引，bge-m3+bge-reranker-v2-m3检索成功。
- index IB-e3e7a3fa3fb4d9784d036162b09a4b93；发布 JOB-01a0f76a-5ded-7f06-9e2d-08923490bf07 完成。最长索引块约4183字符，上限6000。

## 原准确问题已完成报告，但未形成往返辩论
- 问题原样：比较麻黄汤和大青龙汤，分析大青龙汤中麻黄用量为什么比麻黄汤多
- RT-01a0f788-b1a8-7cee-9e52-7cee5d555a58 / JOB-01a0f788-b28f-72ee-8a1f-ba401705fba4 已COMPLETED，冻结KV4/research-v2。
- 21真实证据，Classicist/HistoricalScholar/Theorist各3观点；9机械+9语义审计，7高置信/2条件观点。Critic 0质疑/0回应，NO_CRITIQUES停止，不宣称完整辩论。
- 原失败 HistoricalScholar requires explicit source history metadata 已修：正文明确方论可提交候选，保留角色可见/任务池/冻结版本/REVIEWED限制，再由语义审计判断。
- ReportWriter 6稿、5次拒绝后 ReportReviewer 接受，research-report/v2 三段综合回答；所有最终观点去重后仅引用1条大青龙汤原文，非完整比较语料辩论验收。
- 报告哈希 218664a5f307a02f13fe1838987ab824515e8067ed33c4477191b20791be0568；旧v1 RT-01a0f73b-04e1-7c42-bd42-2c21c469f744 内容保持不变。
- 真实角色调用累计1513545ms，prompt649590/completion15136/total664726 tokens（含失败重试）；成本未提供，保留null。

## 用户新题目：实际辩论已产生，报告未通过
- 问题：比较麻黄汤和大青龙汤，检验“大青龙汤原方麻黄用量是麻黄汤的两倍，因此发汗强度也必然是两倍”这一推断是否成立。区分古制剂量与教材括注克数，并分析两方配伍差异对该推断的影响。
- RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940 / JOB-01a0f7c4-c583-716b-a786-e407fb6c27ef；用户从页面创建，冻结已有知识，限定1来源。
- 实际48原文证据/3角色各3观点/9机械+9语义审计/5质疑/5回应；Judge 7 HIGH_CONFIDENCE、2 UNRESOLVED。
- task.status REPORTING/control_state ACTIVE，job FAILED/attempts3；last_error：ValueError: report narrative did not pass independent review after three drafts。
- ReportWriter/Reviewer rounds0～2均保存；三次accepted=false，无最终报告。本次只读诊断，未retry、未新增模型调用。
- Reviewer指出：将“不可推算古今换算标准”延伸为方间剂量比较限制；原方总量/每服量口径未清；边界段煎出量与分服次数引用不足。有反馈来回改变（先要求删煎服边界，后要求补），需依据实际输入与原文判定，不能自动认定复核都正确。
- 可先通过页面“辩论过程”看完整5条往返；第二分歧场景尚无合格最终报告，VIB-92/94继续In Progress。
- 追加核对：新任务停止原因为ROUND_LIMIT，冻结max_debate_rounds=1；5质疑回应后仍有2个open_gap，却因轮次上限进入报告。未进行下一轮Critic复查，需修多轮与缺口停止策略。

## 本轮实现入口与验证
- research_service.py::submit_first_round_output：修历史元数据门禁；check_real_history_gate.py 用真实证据外层事务回滚验证，不留下测试观点。
- config.py/cloud_models.py：生成请求默认180s（30～600可配置），embedding/rerank90s；workspace_model_config.mjs传入配置。test_cloud_models.py 15 passed。
- report_narrative.py：紧凑 report-narrative-input/v2 保留原文/审计/可用结论，Reviewer仅看被引用观点且不看Writer反馈；旧检查点兼容，旧协议耗尽可追加一次有界紧凑三稿恢复。新任务已用紧凑协议，三稿耗尽后重试不会产生新稿。
- ResearchWorkspace.tsx：刷新错误独立，成功刷新清除旧连接错误；页面状态矛盾仍待修。
- report_export.py export/v3：DOCX附录另起一页、标题outline level便于折叠；旧报告不改，新renderer另缓存。
- check_real_research_answer.mjs 复用原RT788并retry检查点，完成后仅重新导出；不要拿该脚本启动或覆盖新题目现场。
- check_real_report_answer.py真实报告/授权/跨任务引用拒绝/条件升级拒绝/旧报告不变绿检；check_real_report_inputs.py检查原文与引用保留、Reviewer无反馈。
- 前端构建、涉及文件Ruff、git diff --check通过；默认旧库集成失败于缺data_level，独立克隆迁移后同用例失败于旧fixture冻结外发授权，均不计通过/skip。
- 真实页面综合回答/折叠论证/去重原文与导出已检查；中文DOCX export/v3 LibreOffice渲染11页逐页查看，无裁切或乱码；后续引用回跳仍需新报告场景复验。
- 证据目录 docs/acceptance-artifacts/real-research-answer/：result.json、report.json、report.md、report.docx、report-check.json、history-gate-check.json、narrative-input-check.json、docx-preview-v3/。这些属于原RT788，新RT7c4诊断不可覆盖。

## 服务与约束
- URL http://127.0.0.1:18067，API18068；Linux tcm-vib54-py、真实库 tcm_vib62_workspace_test；默认容器库 tcm_vib54_test 为旧schema。
- Node后台服务会话5458（非TTY，stdin关闭）；需停时按 scripts/serve_workspace.mjs 精确匹配node进程，不依赖write_stdin。
- 云配置 TCM_OUTBOUND_MODE=CLOUD_ALLOWED、TCM_PUBLICATION_STRATEGY=hybrid-rrf-v1、TCM_MODEL_PROVIDER=TCM_RESEARCH_PROVIDER=siliconflow、TCM_RESEARCH_MODEL=deepseek-ai/DeepSeek-V3.2；凭据继承环境，禁止打印。
- Windows Python/uv/Alembic禁止重试错误弹窗入口。验证只用Linux Docker Python；DOCX辅助容器tcm-docx-render内安装LibreOffice/Poppler/Noto CJK，repo只读挂载。
- 未提交改动涵盖此前导入/分段/知识提取/审核/检索/模型设置/研究/报告/UI及文档；本轮新增真实检查脚本与报告恢复修改，与既有内容共同保留。
- Linear VIB-92/93/94已同步原任务完成及辩论未通过边界；本次新任务诊断也应同步。VIB-90/91/92/93/94整体均In Progress，整书提取尚未整合通用UI。
- 上一状态页归档 docs/handoff-history/2026-10-01-before-history-gate-recovery.md；启动不读历史。
