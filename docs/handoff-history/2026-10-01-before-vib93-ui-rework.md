# 开发交接

## 当前决策与实施入口

- 2026-10-01，分支 `codex/evidence-audit`，HEAD `7b27043`；此前 `442b88c`、`e3932f8`。本轮未提交，不把既有改动打包提交。
- 用户明确要求查看重排计划并开始开发，已从规划角色转入实施。主线继续 **D1导入能继续 → D2检索能使用 → D3真实研究能演示**。
- **VIB-87 工程验收通过，Linear Done；下一项 VIB-88**。VIB-93 仅落地 D1 禁用原因、表单和流程恢复的局部交互，整项仍 Todo。
- 当前清单：[DEVELOPMENT_BACKLOG](docs/DEVELOPMENT_BACKLOG.md)；范围与页面方向：[DEMO_FIRST_PLAN](docs/DEMO_FIRST_PLAN.md)。不回到旧 C02/治理优先路线。

## 本轮实现与代码入口

- `frontend/src/KnowledgeWorkspace.tsx`：导入、选段、草稿、人工核对的具体禁用原因；无证据返回原文，待核对证据可达入口，通过后自动选择；必填/选填明确。
- 来源修订和步骤在同标签刷新后恢复，切换资料重新加载正确证据范围；解析自动轮询，失败/OCR可打开新修订导入。
- 连续/同层级同类型/最多100段选择校验；保留服务端精确引用和人工审核边界。来源公开、解析完成与人工审核彼此独立。
- 同步操作锁阻止双击重复提交；修复解析完成后重复轮询刷新清空刚选段落的竞态。
- `frontend/src/api.ts`：字段位置映射与连接中断/连续范围说明。网络失败在当前表单旁展示并保留输入，便于重试。
- `frontend/src/knowledge.css`：禁用原因、焦点提示和窄屏；`frontend/package.json`：新增两项检查命令。
- 新检查：`frontend/scripts/check_import_guidance.mjs`、`check_api_errors.mjs`。详细验收：[VIB87记录](docs/VIB87_IMPORT_GUIDANCE_ACCEPTANCE.md)。

## 实际验证与剩余边界

- `npm run build` 通过：TypeScript与Vite。
- 真实API/解析Worker/Edge，独立 `tcm_vib62_vib87_test`：导入TXT→选原文→证据→人工核对→首条草稿通过。
- 缺文件/标题、无证据、待核对、草稿接口失败与重试、非连续选择、刷新、切换资料、损坏PDF、需OCR、双击仅一条草稿、375px全部通过。
- `node scripts/check_api_errors.mjs` 六类错误检查通过；保留18067服务的开发连接/刷新/新标签/凭据恢复/重连浏览器回归通过。
- `git diff --check` 通过。没有运行Windows Python/uv/Alembic；没有本轮后端pytest或真实模型调用；合成工程资料不等于真实文献/专家验收。
- 旧 `check_research_browser.mjs` 在 `bootstrap form` 超时：缺当前连接配置mock，仍依赖旧导航/文案。本轮未修改、未计为通过；完整研究页面验收归VIB-92/94。
- 未保存表单、核对说明、勾选不在刷新后恢复范围；已落库对象重新读取。真实资料分段质量、引用跳转、知识入库、云端检索、研究/导出和用户体验仍归VIB-88～94。

## 工作区、运行与同步

- 开始前已有大量前后端、C02候选、测试和规划改动；全部保留。本轮仅改上述前端、验收/计划/交接文件，未改既有后端。
- 保留开发服务 `http://127.0.0.1:18067/` 与 `tcm_vib62_workspace_test` 数据。本轮构建更新共享dist，刷新页面即可载入；未重启既有服务。
- 本轮临时测试使用18075/18076与 `tcm-vib87-forward`；结束时停止本轮启动器并移除该转发容器。隔离测试库和 `/tmp/tcm_vib62_vib87_test_store` 保留供复查。
- Linear VIB-87验收勾选、实施证据与Done已同步回读；其他Issue的状态/依赖保持重排计划，VIB-88下一项Todo。
- 被替代交接已归档：[实施前规划首页](docs/handoff-history/2026-10-01-before-vib87-implementation.md)。启动不读历史。

## 下一条具体操作

- 读取VIB-88最新验收与依赖；从实际资料定位“句子被拆开”的样例，比较原文件→解析文本→TextSegment自然段→检索片段→页面展示。
- 先查 `backend/src/tcm_platform` 的解析/分段入口与 `frontend/src/KnowledgeWorkspace.tsx`；建立多行/跨页/长段/标题列表样例，找到分裂层再修复。
- 如未明确用户文献，先用代表性TXT、DOCX、文本PDF复现；已有资料保留，不静默重写Evidence、修订或历史报告。
- 按VIB-93知识库布局同步改善阅读与整理；不要先做完整C02专家材料或恢复演示后治理工程。
- Windows故障运行时禁令继续有效；运行验证使用Linux独立测试库，skip不等于通过。真实模型外发和费用仍需相应授权，本轮未扩大此权限。
