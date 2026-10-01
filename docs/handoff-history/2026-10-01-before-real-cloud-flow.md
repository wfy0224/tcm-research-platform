# 开发交接

## 当前状态与下一项

- 2026-10-01；分支 codex/evidence-audit，HEAD 7b27043（此前442b88c、e3932f8）。本轮未提交；已有前后端、模型配置等他人改动全部保留。
- 用户要求“继续修复核心流程问题”。本轮承接并完成VIB-89工程修复：引用→精确来源修订→长文完整范围高亮→返回原位置；上下文完整读取和失败重试。详情 docs/VIB89_CITATION_ACCEPTANCE.md。
- 真实已有大青龙汤检索1条→修订2阅读180～194、15段全部高亮→原证据返回，刷新/直接URL/390px布局通过；无重复导入/审核/发布/新启研究。
- VIB-87/88/89工程Done；VIB-89验收和状态已同步Linear。VIB-90/91/92未完成；VIB-93/94仍In Progress，真实研究报告全链未由本轮验收。
- 下一开发项VIB-90：补手工方剂编辑/核对入口和审核→可检索版本衔接，保留现有两方概念、证据与版本2。

## 来源、版本与研究停点

- 服务 http://127.0.0.1:18067，tcm_vib62_workspace_test，真实API/Worker，无模型替身；旧49123已不可用且服务退出，本轮重启会话23259仍运行，结束输入stop。
- 原来源“方剂学（麻黄汤与大青龙汤研究）”：SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350。修订2 SEGMENTED；旧修订/候选保留，未重解析历史。
- 麻黄汤逻辑段656、658、661、663、666、671、675、679（阅读157～164）；大青龙汤750、752、757、759、761、764、767、771、774、779、786、790、795、799、805（阅读180～194）。两证据已做操作者文本核对，非医学专家审核。
- 大青龙汤证据EV-01a0f68d-647a-78cf-8b60-1d51bd1adb64@1，来源修订2。两个名称按手工入口建概念OTHER，缺方剂类型限制，尚无结构化方剂/剂量字段。
- 版本2活动：24证据/3概念，0关系/药物/方剂；全文可用、向量不适用。发布JOB-01a0f68e-a58e-72af-985f-f9ddc11548f4完成，版本1保留。
- 研究RT-01a0f690-2bea-7fc1-aa32-347c177acf1b已创建，待开始，限定原来源；未勾外发。比较两方、区别三两/六两与9g/12g；不要重复创建。无本轮真实研究报告/导出。
- 同期其他工作修改启动器/模型目录/能力配置（workspace_model_config/catalog.mjs、research_capabilities.py等），已保留。本轮启动输出模型siliconflow/Qwen/Qwen3-8B、LOCAL_ONLY；旧“未配置TCM_RESEARCH_MODEL”已非当前判断依据。具体模型能力/策略待相关工作复验；本轮未改凭据或外发授权。

## 实际验证与剩余问题

- Linux既有tcm-vib54-py中新独立库tcm_demo_repairs_479d3a48_test：34 passed、0 skipped。含完整长上下文/旧修订/首末边界/历史摘要不变，以及原33项解析、分段、精确引用、审核、候选回归。一个现有Starlette/httpx弃用警告。
- npm run build、check_knowledge_selection.mjs、check_api_errors.mjs、Ruff、git diff --check通过。
- check_citation_boundaries.mjs：合成页面验证首中末/完整长上下文/同名多修订/长文未加载/子句/证据与段落503重试/目标缺失/返回旧阅读与报告任务标签，通过。合成报告只用于UI回归。
- check_citation_navigation.mjs：真实大青龙汤检索与上述定位/返回/刷新/手机检查通过；重载API确认完整上下文。已检查截图，证据 docs/acceptance-artifacts/vib89/。
- 先稳定复现落发布页，再修导航；额外修复同来源返回时generation互相失效导致空白。长上下文原1000字符摘要不改写，新增只读完整邻段字段。
- 未运行Windows Python/uv/Alembic；数据库集成用独立库，skip不等于通过。
- “待开始”却“执行状态：运行中”、能力文案、刷新研究需重选任务、质量页JSON归VIB-93；本轮仅保证引用往返保留已选任务/报告标签，不承诺整页刷新恢复研究选择。
- 手工无方剂类型归VIB-90；无正文搜索、质量警告摘要等仍未处理。VIB-91云端语义检索、VIB-92真实研究、VIB-94全链演示仍未验收。
- 原文三两(9g)/六两(12g)不静默改写，不把现代克数称为两倍；教材版次/版权/外发授权仍待核实。

## 实现入口与本轮改动

- 引用路由/展示：frontend/src/citation.ts、EvidenceDrawer.tsx、main.tsx；KnowledgeWorkspace.tsx原文定位/校验/高亮/返回位置，ResearchWorkspace.tsx报告阅读格式。knowledge.css与package.json增加引用样式和check:citations。
- API完整上下文：backend/src/tcm_platform/knowledge_api.py evidence_detail；只读精确历史来源修订的同层相邻段，保留冻结摘要。回归 backend/tests/test_knowledge_workflow_api.py。
- VIB-90：KnowledgeWorkspace.tsx DraftKind/草稿表单、knowledge_api.py方剂草稿/人工核对端点与既有版本发布服务。具体验收按docs/DEMO_FIRST_PLAN.md的D2.01及最新Linear读取。
- 新增引用验收文档、两支浏览器回归脚本和截图/结果；更新本页及DEVELOPMENT_BACKLOG.md。原当前页归档 docs/handoff-history/2026-10-01-before-vib89-citation-fixes.md。
- 既有C02/免码连接/UI/全文修复和同期模型配置改动未撤销；所有未提交内容保持原位。无提交、推送、部署。

## 下一条具体操作

- 开发“继续”：读取VIB-90验收，检查现有create_formula和方剂草稿接口，从KnowledgeWorkspace手工入口补结构化方剂及逐字段引用，先用独立合成数据回归；真实两方已有对象保留。
- 演示“继续”：先复验当前模型能力与外发条件，再重开既有RT-01a0f690-2bea-7fc1-aa32-347c177acf1b。条件满足才启动真实研究，不使用假模型或预制报告。
