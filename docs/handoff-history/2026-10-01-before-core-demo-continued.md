# 开发交接

## 当前状态与下一项

- 2026-10-01，分支 codex/evidence-audit，HEAD 7b27043；此前442b88c、e3932f8。本轮未提交，全部既有前后端改动保留。
- 用户要求先修上次全文演示问题。本轮已修复断句/阅读重复、完整连续引用被拒、耗时反馈、逐条审核负担，并修掉滞后刷新清空勾选和新修订表单丢失来源/授权信息。
- VIB-88 工程验收完成、Linear Done；VIB-93仍 In Progress（研究内部/报告及剩余状态）；VIB-94全流程未验收。本轮记录 docs/DEMO_BUGFIXES.md，原失败记录 docs/VIB94_FANGJI_DEMO.md 保留。
- 下一项：VIB-89 上下文完整展示、引用回跳和高亮。若用户继续演示，使用原来源修订2，按页面核对→发布→检索→研究，不跳过实际审核。

## 原演示来源和运行状态

- 原入口 http://127.0.0.1:18067/?workspace=knowledge 已重载最新前后端，仍用 tcm_vib62_workspace_test、真实 API/Worker，没有切换库。
- 原来源“方剂学（麻黄汤与大青龙汤研究）”：SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350。
- 通过页面完整导入原998793字节文件为修订2，已 SEGMENTED，首段“经过长期”连续阅读通过。旧修订1和候选保留；抽查旧修订前500条文本/身份/定位JSON与操作前一致。没有静默修改历史证据。
- 用户旧标签会保存修订1；刷新后在来源修订下拉框选择修订2。新修订未自动提取、审核或发布，没有本轮真实研究/医学审核/模型调用。
- 本輪原服务启动器会话33136（tty）；正常结束可输入stop。18075/18076隔离服务已停止，tcm-demo-repairs-forward已移除，测试库和文件保留。

## 本轮实现入口

- backend/src/tcm_platform/segmentation.py：structure-resolver/v2；长中文未完句识别排版换行，短古文/标题/列表保留；跨页位置和物理行映射；句末引号跟随原句；正文上下文按相邻正文生成。
- parsing.py：source-parser/v3；DOCX真实段落起始行单独记录；segment_service.py读取该元数据，旧文件兼容。
- knowledge_service.py：允许连续同父节点正文混合CLAUSE/PARAGRAPH等；检查全部兄弟段，禁止漏掉不同类型中间正文、父子混选和跨修订。
- knowledge_api.py：segments新增view=reading，分页前排除子句（默认all兼容）；来源详情返回既有外发授权理由供新修订回填。
- frontend/src/knowledgeSelection.ts：连续范围与中文软换行展示；KnowledgeWorkspace.tsx默认完整段落，结构子句按需展开，保留物理文本详情。
- 操作真实阶段/耗时提示随滚动可见；批量审核处理明确勾选对象，共用说明，逐条保留门禁与审计；通过选填说明，拒绝必填；中途失败保留已保存结果和待保存选择/说明。
- 资料/修订/模式/显式刷新才清空选择；同范围解析状态迟到不重置。新修订预填来源类型、元数据和授权信息，文件输入重置。

## 实际验证

- 修复前断句复现失败；四项分段回归3failed/1passed；真实旧565～586段只读查询确认22个正文类型混合。
- Linux tcm-vib54-py，最终独立库tcm_demo_repairs_328bde58_test：33 passed、0 skipped。覆盖TXT/DOCX/PDF、分页、长段、引号、短古文/标题列表、解析文件往返、版本对齐、混合连续引用/漏段拒绝、阅读分页、知识溯源与提取回归。一个现有Starlette/httpx弃用警告。
- npm run build、node scripts/check_knowledge_selection.mjs、npm run check:api-errors通过；git diff --check通过。Ruff --no-cache --ignore EXE002通过（Windows挂载执行位差异）。
- frontend/scripts/check_demo_repairs.mjs：真实API/Worker、独立tcm_vib62_demo_repairs_test；合成3条混合正文→完整证据→批量审核第二条503→1条已保存/1条保留说明→重试→知识草稿审核通过。通过空说明、提取计时、窄屏检查通过。
- 同脚本完整方剂学导入→连续阅读→页面加载定位麻黄汤→从组成到附方前完整引用草稿创建通过。真实材料保持DRAFT，未发布或研究。
- 重跑页面曾两次发现导入后勾选变0，failure.png/failure-state.txt保留为修复前证据；范围加载缓存修复后重跑通过。
- 实际查看1280×900阅读/提取和390×844审核截图：docs/acceptance-artifacts/demo-repairs/。
- repair_fangji_revision.mjs通过原页面创建修订2，并再次执行确认不会重复导入。未运行Windows Python/uv/Alembic。

## 未提交改动与同步

- 本轮新增/修改上述后端/前端、backend/tests/test_demo_repairs.py、test_knowledge_workflow_api.py、backend/scripts/check_demo_repairs.py及两个前端检查/修订脚本、修复记录与交接；既有C02/免码连接/UI等未提交内容保留。
- Linear VIB-88 Done，VIB-93/VIB-94已同步实际证据与未完成边界；本地任务队列已更新。
- 替代首页归档 docs/handoff-history/2026-10-01-before-demo-bugfixes.md。启动不读历史。

## 下一条具体操作

- 读取VIB-89对应验收，检查frontend/src/EvidenceDrawer.tsx及后端证据详情/上下文接口，让研究或检索引用可跳回来源修订的精确原文并高亮，同时保留阅读位置。
- VIB-93研究/报告布局继续随功能实施；VIB-94须真实核对与完整研究后再验收，不能由本轮独立草稿创建代替。
- Windows故障运行时禁令继续；数据库集成必须独立测试库，skip不等于通过。未保存表单/说明/勾选不承诺刷新恢复。
