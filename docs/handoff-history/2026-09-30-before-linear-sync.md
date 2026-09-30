# 开发交接

## 1 当前基线

- 2026-09-30，分支 `codex/evidence-audit`，HEAD `ab755a2`（VIB-63 研究工作区与真实隔离 E2E）。工作区、验收脚本、README、清单与追踪矩阵已提交；没有未提交代码改动。原有未跟踪 `AGENTS.md`、本文件及其余 `docs/` 保留；旧首页移至 `docs/handoff-history/2026-09-29-vib63-browser-mock.md`。
- 当前范围为 V1 知识底座与理论研究。VIB-60/61 本地和 Linear Done；VIB-63 本地 Done，2026-09-30 读取 Linear 仍 Backlog（此前写入被拒绝，未绕过或重试）。VIB-49 已本地验收，Linear 待同步；VIB-58 仅余 Windows Credential Manager 实机验证。

## 2 VIB-63 交付与实际验证

- 六 Tab、Round/Claim 时间线、研究创建与来源范围、allowed_actions 控制、WAITING_HUMAN/失败提示、人工审核、最终报告与 Markdown/DOCX 下载已接线；草稿与最终报告分开。REST 为事实源，SSE 触发刷新，5 秒轮询修复漏事件及导出状态。
- 真实隔离 E2E 通过：本机 Edge→真实 Uvicorn/API→假模型研究 Worker→人工审核→恢复→导出 Worker→两种文件实际浏览器下载；含按钮限制、暂停/恢复、六 Tab、质疑/再检索/反驳/修订/SEMANTIC 复审、真实 SSE、页面刷新恢复及 375px 无横向溢出。审核恢复保留首轮三个 AgentRun；最终任务 `RT-01a0f14b-384b-710e-bed9-b549d8a7a50f`，任务/导出 Job COMPLETED，审核 RESOLVED；9 条假模型治理记录，远程 endpoint 为 0，0 次真实云调用。
- `npm run check:research-browser`（含 TypeScript/Vite 构建）通过；独立 `tcm_vib60_test` 的研究 API→报告导出与人工审核→恢复两条集成用例 **2 passed、0 skipped**；新增 harness 与修改测试 Ruff 通过；`git diff --check`、暂存差异检查通过。本轮未重跑完整后端套件，无新增迁移。FastAPI/httpx 弃用警告仍存在。
- 回归曾领取旧队列中的无关导出而失败：改为按本次 API 返回的 Job 定位 export_id，再跑两条用例通过。E2E 修正同名来源选择、React 状态等待、实际审计阶段及入队期间 404 等待。失败尝试留下的独立库测试任务与队列保留，未删除业务数据。
- 详见 `docs/VIB63_RESEARCH_WORKSPACE_ACCEPTANCE.md`，含结果、报告哈希与复现命令。清单和追踪矩阵本地 Done；Linear 待明确允许后的同步。

## 3 下一条具体操作

- 下一项承接 **VIB-45 初始语料清单、来源授权与 OCR 实施决策**。本轮读取最新 Linear：Todo，依赖 VIB-38；VIB-62 受 VIB-46/48 阻断，VIB-46/47/48 需先推进语料主线。先读清单 VIB-45、`backend/fixtures/README.md`、`backend/scripts/prepare_shanghanlun_preview.py`、`backend/tests/test_source_import_integration.py` 与 `test_parsing.py` 中 OCR_REQUIRED 用例；盘点《傷寒論》29 条公版原文的来源、版本、授权、格式和页码能力，形成首批语料候选清单及 OCR 决策依据，不虚构数据负责人或专家确认。
- 先完成无需外部输入的清单与 OCR_REQUIRED 不误发布验证；首批范围、数据负责人或扫描件需求确实无法从资料确定时，呈现具体候选后再请求关键输入。设计依据按需查 LLD 附录 C/需求 3.2。
- VIB-63/VIB-49 的 Linear 写入此前被拒绝，不得因“继续”绕过；不阻止本地开发与交接。

## 4 运行限制与入口

- Windows 原生 Python/uv/Alembic 曾触发错误弹窗，禁止换入口重试。后端验证使用既有只读 Linux 容器 `tcm-vib54-py`，显式 `PYTHONPATH=/workspace/backend/src`；容器内已安装包较旧，不设路径会误用旧代码。显式选择独立 `tcm_vib60_test`，不要使用默认连接的 `tcm_vib54_test`，skip 不算通过。
- Docker Desktop 本轮由用户手动启动；`tcm-handoff-test`、`tcm-vib54-py` 已运行。新建的 `tcm-vib63-forward` 已停止，复跑前 `docker start tcm-vib63-forward`。E2E 临时浏览器和 API 已退出；无需启动预览 API。`docker-api-1`、`tcm_preview_shanghanlun` 不作开发测试环境。
- 前端：`frontend/src/ResearchWorkspace.tsx`；E2E：`frontend/scripts/check_research_e2e.mjs`、`backend/scripts/serve_research_e2e.py`（只在测试容器运行，要求显式 TCM_E2E_DATABASE）；API：`research_api.py`、`research_views.py`；回归：`backend/tests/test_research_integration.py`。
- E2E 固定 LOCAL_ONLY 和注入假模型；在正常 start 服务入口冻结 mandatory_human_review 后交给真实 Worker。它不修改生产 API 合约，不代表真实模型质量、桌面密钥交接或 V1 发布门禁完成。
