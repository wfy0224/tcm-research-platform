# 质疑复查与报告恢复验收

2026-10-01，分支 codex/evidence-audit，基线 7b27043；未提交、未推送。

实际研究 RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940 原在三个报告草稿被拒绝后失败。保留原检查点，恢复 NEEDS_REVISION 报告，再通过页面继续修订，沿用冻结 deepseek/deepseek-flash 的真实模型调用。Writer/Reviewer round3 完成，accepted=true、issues=[]；任务和作业均 COMPLETED。

- revision1 hash：cfe74fb00cbade1c09872da87c2e5d8560eb36013c610bf3725cd4eb550c9296，原稿及拒绝原因保留。
- revision2 hash：6234882bdcdecb0a0c02d4334bbd7166adc44250a88f26f7022a143b44eb607b，ACCEPTED，四段综合回答。
- 真实48证据、9观点、18审计、5质疑和5回应保留。7高可信、2未解决问题，未因报告接受而抹去缺口。
- node frontend/scripts/check_real_report_recovery.mjs 两次实际读取和下载成功，产物 revision-1/2.json、.md、.docx。
- 页面截图 completed-report.png；任务已完成，研究回答已显示，MD/DOCX下载可用。
- Word 用Linux helper 的 LibreOffice及render_docx.py 渲染19页，逐页查看：中文正常，无裁切；附录从第3页开始，原文与实际研究记录保留。预览 docx-preview-v2/。

独立测试库 tcm_debate_repair_6dca_test 从实际现场克隆并迁移0027。四组共43 passed、0 skipped：test_report_recovery_integration.py、test_debate_followup_integration.py、test_debate_stop_policy.py、test_job_failure_reason.py。恢复集成使用真实已存业务记录、事务回滚；任何模型/向量/重排调用都会主动失败，未制造业务输出。

新任务默认 research-v3、max_debate_rounds=3、review_replies=true。工程验证先前5条回应、2个缺口进入下一Critic冻结输入，后续写入不修改旧输入；实际停止快照新规则回放由STOP/ROUND_LIMIT转为CONTINUE/FOLLOWUP_REVIEW。没有质疑不制造辩论，预算耗尽仍把缺口写入报告。旧任务冻结max1不变；本次未启动新max3任务的多轮真实云端研究，此项全链尚未验收。

前端构建、涉及后端Ruff通过（忽略Windows挂载可执行位EXE002）；实际只读核对旧RT788报告hash218664a5f307a02f13fe1838987ab824515e8067ed33c4477191b20791be0568和revision1 hash未改变。实际库迁移0027成功。Linear VIB-92/93/94已同步，整体In Progress。
