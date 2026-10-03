# 开发交接

## 当前停点与下一步
- 2026-10-02，codex/evidence-audit；基线d0f002e，父提交7b27043。本轮UI美化未提交，之前累计开发已本地提交、未推送。
- 用户本轮指定“美化一下ui”：已完成青绿暖白主题、阅读排版、导航/任务/引用样式及响应式布局；本地18067服务可刷新查看。
- 下一步：用同一分歧题目创建research-v3新任务，真实验证回应后的下一轮Critic、停止及报告；旧任务冻结max1不可改。新max3真实云端全链尚未运行，不把前轮43项工程测试或本轮展示验收当作该路径通过。
- VIB-92/93/94已同步本轮结果及边界，整体仍In Progress；VIB-90/91整书提取尚未整合通用UI。
- 用户要求真实云端、完整原文、实际质疑回应、自己的话回答、折叠原文；禁止模拟业务数据补验收。

## 本轮UI美化
- frontend/src/theme.css为统一主题入口，main.tsx在组件样式后引入；仅样式变化，无业务数据/研究流程修改。
- 深青侧栏、暖白卡片、中文衬线标题/原文、报告留白及引用按钮；统一选中态、输入焦点、模型设置按钮；保留引用高亮与减少动态效果偏好。
- 真实本地服务、独立无头Edge：1440/390px三个工作区无横向溢出，两种宽度报告引用均展开；已查看桌面知识库/研究和手机研究截图。构建通过，无新云端模型调用。
- 证据docs/acceptance-artifacts/ui-refresh/：6张页面截图、layout-check.json、ACCEPTANCE.md。未重跑后端集成，本轮不构成新多轮云端研究验收。
- 未提交：main.tsx、theme.css、本页、前页归档和ui-refresh验收文件。下一项仍为上方新research-v3真实多轮验收。
## 本轮报告可读性与引用修复
- report_export.py：report-export/v6；导出可见正文去除内部UUID、hash、运行/知识/索引编号及指纹；用报告内观点、证据、质疑、回应、缺口编号和内部链接，保留来源名称/修订/位置。Word书签/MD锚点承载关系。
- 原文Quote及研究回答未改；审计文字局部“证据1/2”展示改为“引用材料”避免混淆。旧复核issue里的观点ID映射为报告序号，仅改导出展示。
- research_api.py::_public_evidence添加citation_number，页面与导出编号一致。ResearchReport.tsx依据点击preventDefault，replaceState保留hash，主动展开/聚焦/滚动/高亮；支持返回引用、重复点击、键盘与初始深链接，原文按编号排列。
- 原因：原生hash触发main.tsx全局popstate恢复来源阅读scroll=0，且未展开details；只修改报告局部点击，保留来源导航。research.css目标scroll-margin-top90防固定导航遮住标题。
- 三个实际任务/四个保存报告版本只读检查通过：可见UUID/hash0，65/63/30/22个内部链接全部有目标，原文4/4/1/2条保留，保存报告hash不变；backend/scripts/check_real_readable_report.py及export-check.json。
- 实际接受稿MD/DOCX重新下载；Word经Linux LibreOffice/Noto CJK渲染19页，v6每页已查看，无裁切乱码溢出。中间v5导出/预览保留，不交付中间文件。
- 真实浏览器：依据1/2/4及详细论证3均展开聚焦高亮；重复点击、Enter、返回引用、刷新hash2通过，目标top约90px。
- 依据2→证据详情→打开来源文献：来源修订2/逻辑段180～194共15段定位高亮→返回报告通过；再次点击依据2正确。
- npm run build、相关两后端模块及只读脚本Ruff(--no-cache/忽略EXE002)、git diff --check通过。本轮无新研究模型调用；实际导出任务已生成v6文件。
- 证据docs/acceptance-artifacts/readable-report/：revision-2.json/.md/.docx、export-check.json、citation-jump.png、docx-preview-v6/、ACCEPTANCE.md。不要覆盖此前report-recovery或real-research-answer/。

## 实际分歧任务与前轮修复
- RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940 / JOB-01a0f7c4-c583-716b-a786-e407fb6c27ef均COMPLETED；题目检验“大青龙原方麻黄两倍→发汗必然两倍”，限定1来源。
- 冻结deepseek/deepseek-flash；48证据/9观点/18审计/5质疑/5回应，Judge7 HIGH_CONFIDENCE/2 UNRESOLVED；旧冻结max_debate_rounds=1，STOP/ROUND_LIMIT保留。
- 原Writer/Reviewer rounds0～2 rejected不覆盖；先恢复rev1 NEEDS_REVISION，再页面继续修订真实round3 accepted=true、issues=[]，新增research-report/v3 rev2 ACCEPTED四段回答。
- rev1 hash cfe74fb00cbade1c09872da87c2e5d8560eb36013c610bf3725cd4eb550c9296；rev2 hash 6234882bdcdecb0a0c02d4334bbd7166adc44250a88f26f7022a143b44eb607b均未改变。
- stop_service.py/research_service.py/debate_service.py：新research-v3/critic-v3最多3轮、review_replies=true、冻结先前质疑回应缺口，FOLLOWUP_REVIEW；旧缺字段按max1/false回放。
- report_narrative.py/research_worker.py三稿耗尽保存NEEDS_REVISION，真正设施失败仍重试；research_service.py::revise_research_report追加有界新稿和审计事件，幂等不重复；0027_report_revisions.py不可变修订、默认最新导出、禁止有损降级。
- ResearchWorkspace.tsx准确FAILED状态，保存已有研究报告/继续修订综合回答与重试区分。前轮独立库43 passed/0 skipped；新多轮实际快照规则回放通过，尚未实际新多轮云端链。
- 前轮证据docs/acceptance-artifacts/report-recovery/ACCEPTANCE.md及rev1/2文件、completed-report.png、docx-preview-v2/保留。

## 真实知识基线
- 完整C:/Users/wangfeiyu/Downloads/方剂学.txt；SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350修订2，4211正文/843新增证据文本核对。
- 376最新方剂REVIEWED（233组成/141附方/2残缺），失败0；缺失剂量未知，不是医学专家认证。
- KV4 READY/ACTIVE：1243证据/376方剂/3概念，125批真实向量索引；bge-m3/bge-reranker-v2-m3检索通过。
- index IB-e3e7a3fa3fb4d9784d036162b09a4b93；发布JOB-01a0f76a-5ded-7f06-9e2d-08923490bf07完成。
- RT-01a0f788-b1a8-7cee-9e52-7cee5d555a58已完成；21证据/9观点/18审计/7高置信2条件、Critic0，无往返；3段综合回答/1条去重原文，hash218664a5f307a02f13fe1838987ab824515e8067ed33c4477191b20791be0568不变。旧v1 RT-01a0f73b-04e1-7c42-bd42-2c21c469f744保留。

## 服务、验证约束与接续入口
- 页面http://127.0.0.1:18067/?workspace=research，API18068；Node会话3712，非TTY/无stdin。停服务仅匹配scripts/serve_workspace.mjs的node进程。
- Linux tcm-vib54-py /workspace:ro，PYTHONPATH=/workspace/backend/src；实际库tcm_vib62_workspace_test。默认tcm_vib54_test旧schema，禁止拿它跑集成宣称通过。
- 前轮独立库tcm_debate_repair_6dca_test；Postgres tcm-handoff-test、tcm_test、host.docker.internal:55432；dump /tmp/debate-repair-6dca.dump。
- 服务env：TCM_OUTBOUND_MODE=CLOUD_ALLOWED、TCM_PUBLICATION_STRATEGY=hybrid-rrf-v1、TCM_MODEL_PROVIDER=TCM_RESEARCH_PROVIDER=siliconflow、TCM_RESEARCH_MODEL=deepseek-ai/DeepSeek-V3.2；实际调用按任务冻结路由。继承凭据禁止打印。
- Windows Python/uv/Alembic错误弹窗入口禁止重试；Python只用Linux Docker。DOCX helper tcm-docx-render含LibreOffice/Poppler/Noto CJK、/tmp/render_docx.py、repo只读。
- 用户要求提交变更：全部累计前后端、迁移、验证脚本、验收及交接记录随本次本地提交保存；Word临时锁文件由.gitignore排除，运行数据仍忽略。暂存代码/文档diff检查通过；两个原始文献fixture自带尾空白保留，不改写来源；没有新模型调用或重跑已通过测试。提交前页归档docs/handoff-history/2026-10-02-before-commit.md，启动不读历史。

## 服务器部署手册（2026-10-02）
- 新增 docs/SERVER_DEPLOYMENT_GUIDE.md 及 README 入口：SSH 单管理员部署、Worker、备份及凭据缺口；仅代码核对，未实际部署。
- 本轮文档未提交，保留此前 UI 未提交改动；基线仍 d0f002e，下一开发任务仍为顶部 research-v3 真实多轮验收。
