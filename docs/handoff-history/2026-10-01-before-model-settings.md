# 开发交接

## 当前状态与下一项

- 2026-10-01；分支 codex/evidence-audit，HEAD 7b27043；此前442b88c、e3932f8。未提交，全部既有前后端改动保留。
- 用户要求“继续演示核心流程并记录问题”。本轮只改文档、队列和交接，未修业务代码；详情 docs/VIB94_FANGJI_CONTINUED_DEMO.md。
- 修订2两方完整证据、操作者文本核对、两个概念名称审核、版本2本地发布和关键词检索通过。停在研究启动：未配置TCM_RESEARCH_MODEL，开始禁用，0云调用，无报告/导出。
- 引用回跳失败：检索详情打开来源落质量发布页；手动切原文后首段，无目标定位/高亮。下一开发项仍VIB-89，优先用本次已有证据复测。
- VIB-88工程Done；VIB-93 In Progress；VIB-94已实际演示，Linear In Progress，全链未验收。VIB-89仍Todo；VIB-90/91/92未完成。

## 来源、版本与停点

- 服务 http://127.0.0.1:18067，tcm_vib62_workspace_test，真实API/知识Worker，无模型替身。原服务退出后恢复成功；启动器会话49123仍运行，如需结束输入stop。
- 原来源“方剂学（麻黄汤与大青龙汤研究）”：SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350。修订2 SEGMENTED；旧修订/候选保留，未重复导入或改历史。
- 麻黄汤逻辑段656、658、661、663、666、671、675、679（阅读157～164）；大青龙汤750、752、757、759、761、764、767、771、774、779、786、790、795、799、805（阅读180～194）。两证据均通过操作者文本核对，非医学专家审核。
- 大青龙汤证据EV-01a0f68d-647a-78cf-8b60-1d51bd1adb64@1，来源修订2。两个名称按手工入口建概念OTHER，说明已记录缺方剂类型限制，未填结构化方剂/剂量字段。
- 版本2已活动：24证据/3概念（含此前已审内容），0关系/药物/方剂；全文可用、向量不适用、无模型调用。发布JOB-01a0f68e-a58e-72af-985f-f9ddc11548f4完成。版本1保留。
- 研究RT-01a0f690-2bea-7fc1-aa32-347c177acf1b已创建，待开始，限定原来源；未勾外发。问题要求比较两方、区别三两/六两与9g/12g。不要重复创建。
- 浏览器留在模型阻断处；刷新能恢复会话/任务列表，当前任务和详情标签需手动重选。

## 实际验证与问题

- 本轮npm run build、git diff --check通过。无业务代码变更，未重跑后端测试。Linux容器迁移启动成功；未运行Windows Python/uv/Alembic。
- 页面逐段阅读、完整证据/概念名称/核对保存/发布通过；两方选定范围与用户原文件逐字一致（忽略排版空白），source-fidelity.json两项true。
- 大青龙汤、麻黄汤、火星土壤矿物成分实际1/2/0条；重复大青龙汤仍1条修订2。未验证云端语义检索。
- 详情上下文正确：麻黄汤《伤寒论》→【附方】；大青龙汤《伤寒论》→【医案举例】。回跳失败，详情/检索仍带物理换行、技术定位字段。
- “待开始”却“执行状态：运行中”；无模型却文案称路由已配置；刷新需重选；手工无方剂类型；无正文搜索；质量页出现27条未入库匹配警告及JSON。D94-01～07及未诊断边界见记录。
- 原文件三两(9g)/六两(12g)是源记载，非解析错误；不静默改原文或把现代克数说成两倍。教材版次/版权/外发授权未核实。
- 证据目录 docs/acceptance-artifacts/vib94-fangji-continued/；无本轮研究执行/报告/导出，不以旧研究替代。
- 上轮独立库33 passed/0 skipped及真实隔离页面检查已通过，见docs/DEMO_BUGFIXES.md；本轮未重跑。

## 实现入口

- VIB-89：frontend/src/EvidenceDrawer.tsx的onSource只传sourceId；main.tsx导航、KnowledgeWorkspace.tsx需携带精确来源修订/段范围，强制原文页、按需加载/高亮，保存返回位置。
- VIB-93：ResearchWorkspace.tsx的CREATED/control_state ACTIVE展示、能力文案、task_id/标签恢复；知识质量页人可读摘要。
- VIB-90：补手工方剂编辑/核对入口，保留本轮概念名称与证据。
- 真研究：backend/scripts/serve_workspace_demo.py、frontend/scripts/serve_workspace.mjs仅配置TCM_RESEARCH_MODEL后启研究Worker。核对既有模型、来源授权/费用后继续已有任务，不用假模型或预制报告替代。
- 上轮全文修复：segmentation.py structure-resolver/v2、parsing.py source-parser/v3、segment_service.py、knowledge_service.py、knowledge_api.py、frontend/src/knowledgeSelection.ts，均在既有未提交内容中。

## 未提交与同步

- 本轮新增演示记录、截图/DOM/一致性结果和交接归档，更新DEVELOPMENT_BACKLOG.md及本页；未改运行配置/凭据。
- 既有C02/免码连接/UI/全文修复等改动全部保留。必要追溯才读历史。
- Linear VIB-94状态/证据和VIB-89复现已同步；其他归属保存在本地及VIB-94，没有标完成。
- 替代首页归档 docs/handoff-history/2026-10-01-before-core-demo-continued.md。

## 下一条具体操作

- 开发“继续”：先修VIB-89引用目标传递，用已有大青龙汤证据验证检索→修订2阅读180～194定位/高亮与返回，不重复入库。
- 演示“继续”：检查服务/模型配置，重开RT-01a0f690-2bea-7fc1-aa32-347c177acf1b；配置、授权和费用条件满足后再启动。目前唯一停点是已创建的待开始任务。
- Windows故障运行时禁令继续；数据库集成用独立测试库，skip不等于通过；未保存表单/选择不承诺刷新恢复。
