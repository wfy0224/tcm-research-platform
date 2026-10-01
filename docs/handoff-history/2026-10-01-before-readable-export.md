# 开发交接

## 当前停点与下一步
- 2026-10-01，codex/evidence-audit，HEAD 7b27043；所有既有未提交改动保留，未提交/推送。
- 用户要求修复“有质疑不继续辩论／辩论完未生成报告”。已修多轮策略、准确失败状态、报告耗尽恢复与不可变修订；实际失败任务已COMPLETED，真实独立复核接受报告。
- 下一步：用同一分歧题目创建research-v3新任务，真实验证回应后的下一轮Critic与停止→报告→引用回跳；不要改写旧任务冻结max1或把本轮43项工程检查当作新多轮云端全链通过。
- VIB-92/93/94已同步本轮成果及验证边界，整体仍In Progress。VIB-90/91整书提取尚未整合通用UI。
- 用户要求真实云端、完整原文、实际质疑回应、自己的话回答和折叠原文；不能模拟业务数据补验收。

## 实际分歧任务已完成报告
- RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940 / JOB-01a0f7c4-c583-716b-a786-e407fb6c27ef 已COMPLETED。
- 题目检验“大青龙汤原方麻黄两倍→发汗强度必然两倍”，区分古制与教材括注克数、配伍及煎服口径；用户页面创建，限定1来源。
- 冻结generation_model=deepseek/deepseek-flash；沿用实际路由。48证据/9观点/18审计/5质疑/5回应；Judge7 HIGH_CONFIDENCE、2 UNRESOLVED保留。
- 旧任务冻结max_debate_rounds=1，保留STOP/ROUND_LIMIT；本轮修报告，未追加旧任务多轮辩论。
- 旧Writer/Reviewer rounds0～2 rejected原样保留。先恢复revision1 NEEDS_REVISION，标明综合回答未通过；这一步无新增模型调用。
- 页面“继续修订综合回答”真实执行round3 Writer/Reviewer；accepted=true、issues=[]，保存revision2 ACCEPTED，research-report/v3，四段综合回答。
- rev1 hash cfe74fb00cbade1c09872da87c2e5d8560eb36013c610bf3725cd4eb550c9296；rev2 hash 6234882bdcdecb0a0c02d4334bbd7166adc44250a88f26f7022a143b44eb607b。
- 页面已完成/回答/下载MD及DOCX通过；Word19页逐页查看无裁切乱码；2缺口仍写入报告。
- 证据docs/acceptance-artifacts/report-recovery/：revision-1/2.json、.md、.docx，completed-report.png、docx-preview-v2/、ACCEPTANCE.md。

## 本轮实现与验证
- stop_service.py：新WorkflowConfig max3/review_replies=true；有质疑回应后FOLLOWUP_REVIEW，直到独立Critic无质疑或预算耗尽。无质疑不捏造辩论；历史缺字段按max1/false回放。
- research_service.py新任务research-v3/critic-v3；debate_service.py冻结先前质疑/真实回应/缺口，Critic检查回应是否解决，不把REJECT当解决。
- report_narrative.py::ReportReviewExhausted专属异常；research_worker.py三稿耗尽保存NEEDS_REVISION报告并完成该次执行；真正基础设施失败仍重试。
- research_service.py::revise_research_report追加审计事件与有界3稿新修订；新起始稿号由EventLog.sequence_no确定，继承前次复核问题；幂等请求不重复起稿。
- judge_service.py/report_export.py/research_api.py/cli.py：不可变报告版本、report-export/v4、默认最新版本；待修订可查看导出，旧稿旧哈希不覆盖。
- models.py及0027_report_revisions.py：revision_no、unique(task,revision)，原不可变触发器保留；多稿时拒绝有损降级。
- ResearchWorkspace.tsx：job FAILED覆盖遗留ACTIVE；“保存已有研究报告”/“继续修订综合回答”与普通重试区分；失败提示准确、已有报告可用。
- 独立库tcm_debate_repair_6dca_test从实际库克隆并迁移0027；test_report_recovery_integration.py、test_debate_followup_integration.py、test_debate_stop_policy.py、test_job_failure_reason.py共43 passed/0 skipped。
- 恢复集成用实际旧检查点、外层事务回滚；模型/向量/重排若被调用即失败，不制造业务回复。
- check_real_debate_policy.py实际停止快照新规则回放：修前STOP/ROUND_LIMIT，修后CONTINUE/FOLLOWUP_REVIEW；旧冻结仍max1。
- node frontend/scripts/check_real_report_recovery.mjs两版本实际导出绿检；npm run build通过；涉及后端Ruff通过（仅忽略Windows挂载可执行位EXE002）。
- 原RT788哈希、rev1哈希及旧冻结max1真实只读检查通过。未运行新max3多轮云端全链，不宣称整体验收。

## 真实资料与此前基线
- 完整C:/Users/wangfeiyu/Downloads/方剂学.txt；SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350修订2，4211正文/843新增证据文本核对。
- 376最新方剂REVIEWED（233组成/141附方/2残缺），失败0；缺失剂量仍未知，非医学专家认证。
- KV4 READY/ACTIVE：1243证据/376方剂/3概念，125批真实向量索引；bge-m3+bge-reranker-v2-m3检索通过。
- index IB-e3e7a3fa3fb4d9784d036162b09a4b93；发布JOB-01a0f76a-5ded-7f06-9e2d-08923490bf07完成。
- 原RT-01a0f788-b1a8-7cee-9e52-7cee5d555a58完成research-report/v2；21证据/9观点/18审计/7高置信2条件；Critic0，无往返，最终去重引用1条原文。
- 原报告hash218664a5f307a02f13fe1838987ab824515e8067ed33c4477191b20791be0568未改变；旧v1 RT-01a0f73b-04e1-7c42-bd42-2c21c469f744保留。
- 原RT788证据docs/acceptance-artifacts/real-research-answer/不要覆盖；历史候选门禁/180s超时/紧凑复核输入等此前修复保留。

## 服务与约束
- 页面http://127.0.0.1:18067/?workspace=research，API18068；Node服务会话25694，非TTY/无stdin；停服务按scripts/serve_workspace.mjs精确匹配node进程。
- Linux tcm-vib54-py /workspace:ro，PYTHONPATH=/workspace/backend/src；实际库tcm_vib62_workspace_test；默认tcm_vib54_test旧schema，不拿它跑集成宣称通过。
- 测试库tcm_debate_repair_6dca_test；Postgres tcm-handoff-test，角色tcm_test，host.docker.internal:55432；dump /tmp/debate-repair-6dca.dump。
- 服务env TCM_OUTBOUND_MODE=CLOUD_ALLOWED、TCM_PUBLICATION_STRATEGY=hybrid-rrf-v1、TCM_MODEL_PROVIDER=TCM_RESEARCH_PROVIDER=siliconflow、TCM_RESEARCH_MODEL=deepseek-ai/DeepSeek-V3.2；实际执行按任务冻结路由，凭据继承禁止打印。
- Windows Python/uv/Alembic禁止重试错误弹窗入口；Python验证只用Linux Docker。DOCX helper tcm-docx-render内LibreOffice/Poppler/Noto CJK、/tmp/render_docx.py、repo只读。
- 既有未提交知识/研究/UI/文档改动全部保留；实际库迁移0027，新增报告版本及真实修订调用，未改写旧记录。
- 替代状态页归档docs/handoff-history/2026-10-01-before-multiround-repair.md；启动不读历史。
