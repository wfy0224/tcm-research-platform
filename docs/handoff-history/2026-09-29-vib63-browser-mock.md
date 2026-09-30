# 开发交接

## 1 当前基线

- 2026-09-29，分支 `codex/evidence-audit`，HEAD `fabb6bf`（VIB-61 研究控制、详情与 SSE）。原有未跟踪 `AGENTS.md`、本文件及 `docs/` 均须保留；本轮新增未提交 `frontend/src/ResearchWorkspace.tsx`、`frontend/scripts/check_research_browser.mjs`，修改 `frontend/src/main.tsx`、`frontend/src/style.css`、`frontend/package.json`、`README.md`、`docs/DEVELOPMENT_BACKLOG.md`、`docs/REQUIREMENTS_TRACEABILITY.md`。
- 当前范围为 V1 知识底座与理论研究。VIB-60/61 本地和 Linear Done；VIB-49 本地已验收但 Linear 同步曾被审批拒绝；VIB-58 仅余 Windows Credential Manager Python 实机验证。VIB-63 当前本地 In Progress，Linear 仍 Backlog（本轮状态同步被拒绝）。

## 2 本轮 VIB-63 进度与验证

- 前端研究工作区已接入本地会话、研究问题与来源范围、任务列表、Summary/Claims/Debate/Evidence/Disputes/Report 六 Tab、Round/Claim 时间线、暂停/恢复/取消、人工审核、报告导出和下载。草稿与最终报告分开展示；控制按钮按 `allowed_actions` 启用；WAITING_HUMAN、失败与重试等待有持续提示。REST 为事实源，SSE 触发刷新，并每 5 秒轮询修复漏事件及导出状态。
- `npm run check:research-browser` 通过：本机 Edge 原生 CDP 连接隔离模拟 API，验证页面创建→人工审核→六 Tab / Round / Claim→报告导出与下载、`allowed_actions` 禁用及 375px 窄屏无横向溢出；无需 Playwright。独立 PostgreSQL 库 `tcm_vib60_test` 中 `test_research_api_creates_idempotent_task_and_serves_final_report`、`test_human_review_releases_lease_and_resumes_stop_stage_only` 各 1 passed。首次误连旧库 `tcm_vib54_test` 缺迁移列，改用指定测试库后通过。
- 浏览器与真实隔离后端/Worker 的同一流程 E2E 尚未执行，VIB-63 不能标 Done。会话未提供 Browser 插件，`web-access` Proxy 仍连不上浏览器；原生 CDP WebSocket 可操作临时 Edge，已用于上述可复现浏览器检查。Playwright 提权安装曾被审批拒绝，未安装。尝试清理最早的临时 Edge 配置目录时，递归删除命令被策略阻止；临时 Edge 进程已停止，目录可能仍位于系统 TEMP。
- 本轮尝试将 VIB-63 的 Linear 状态改为 In Progress，工具返回 `user rejected MCP tool call`；停止重试，待同步。未做真实云调用；未使用预览库。

## 3 下一条具体操作

- 下一步在独立测试库与假模型 Worker 上运行同一条浏览器→真实 API→Worker 的创建研究→人工处理→报告导出/下载流程。浏览器脚本 `npm run check:research-browser` 已覆盖模拟 API 的页面交互；可复用本机 Edge 原生 CDP。只有真实隔离链路通过后才把 VIB-63 标 Done。
- 完成 VIB-63 后按规定同步本地清单、追踪矩阵与 Linear；Linear 本轮状态写入被拒绝，不得绕过。VIB-62 仍受 VIB-46/48 阻断，VIB-46 依赖 VIB-45。

## 4 运行限制与入口

- Windows 原生 Python/uv/Alembic 曾触发应用程序错误弹窗，禁止换入口重试。后端验证用现有 `tcm-vib54-py` 只读 Linux 容器，显式设 `TCM_DATABASE_URL` 指向独立 `tcm_vib60_test`；skip 不算通过。`docker-api-1` 和 `tcm_preview_shanghanlun` 不作开发测试环境。
- 前端入口：`frontend/src/ResearchWorkspace.tsx`、`frontend/src/main.tsx`；API：`backend/src/tcm_platform/research_api.py`、`research_views.py`。验收清单：`docs/DEVELOPMENT_BACKLOG.md` VIB-63；追踪矩阵：`docs/REQUIREMENTS_TRACEABILITY.md`。
