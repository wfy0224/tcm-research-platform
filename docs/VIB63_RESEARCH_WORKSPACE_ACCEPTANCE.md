# VIB-63 研究工作区验收

2026-09-30，分支 `codex/evidence-audit`，实施基线 `fabb6bf`。本项本地验收完成，实施提交 `ab755a2`；2026-09-30 用户授权同步后，Linear 已为 Done（回读确认）。包含详细内部实现、测试环境和提交明细的同步说明被自动审批拒绝；已成功同步简短验收结论，完整证据保留在本文件。

## 实际执行

Windows Edge 无界面浏览器通过 Node 静态资源服务及 HTTP 代理连接真实 Uvicorn API。API、数据库会话、研究 Worker、导出 Worker 和 SSE 均为项目实现；模型使用后端集成测试中的确定性 doubles。

- 数据库：既有独立 `tcm_vib60_test`，迁移 `0023_release_snapshot`，使用其中已发布并建立索引的测试知识。
- Python：既有 `python:3.11-slim` 容器 `tcm-vib54-py`，后端只读挂载；显式设置 `PYTHONPATH=/workspace/backend/src`。
- 浏览器/API：本机 `127.0.0.1:18064` / `127.0.0.1:18063`；临时 `tcm-vib63-forward` 仅发布回环端口。
- Store：`/tmp/tcm_vib63_browser_store`；不使用预览库或预览数据目录。
- 测试入口在正常 `start_research_task` 调用前注入 `mandatory_human_review=True`，由实际 StopEvaluator 生成待审事项；未伪造审核记录或改写冻结上下文。正常 HTTP API 未新增测试路由。
- 研究问题含每轮随机前缀，研究/导出 Worker 显式限定本轮 task/export；不会领取无关待执行任务。
- `LOCAL_ONLY`，清除进程内 API Key，禁用环境密钥读取，注入 FakeEmbedder/FakeReranker/DebateGenerator；没有真实云调用。

## 结果

`npm run check:research-e2e` 的构建通过；修正后的 `node scripts/check_research_e2e.mjs` 通过。最后一次成功任务：`RT-01a0f14b-384b-710e-bed9-b549d8a7a50f`。

| 门槛 | 实际证据 |
| --- | --- |
| 浏览器创建研究及来源范围 | 本地会话、CSRF、Origin 与幂等键经真实 API 校验；按来源公开编号选择，GET 返回同一来源 |
| 控制与 allowed_actions | CREATED 时暂停禁用；开始后暂停→恢复经 API 持久化；WAITING_HUMAN 时只允许 resolve_review |
| 六 Tab 与两种时间线 | Summary/Claims/Debate/Evidence/Disputes/Report；Round View/Claim View；实际 Critique→再检索→Rebuttal→追加 Claim→SEMANTIC 复审可查 |
| 草稿与最终报告 | 人工审核前 Report 显示未生成；实际 Worker 生成报告后展示原文证据 |
| 人工审核及恢复 | WAITING_HUMAN 持续提示；通过页面提交审核；恢复后首轮三个 AgentRun ID 不变 |
| 报告导出与下载 | 页面分别排队 Markdown/DOCX，真实导出 Worker 执行；点击下载链接保存文件；文件字节与带会话请求返回体相同；Markdown 含原文，DOCX 包含 word/document.xml |
| SSE 与持久化 | 收到 snapshot、waiting_human、human_review_resolved、report_saved 等真实事件；页面刷新后会话、任务、最终报告与下载入口可恢复 |
| 窄屏 | 375 × 812 下无横向溢出 |

独立数据库复核：任务、研究 Job、两种导出 Job 均 `COMPLETED`，审核 `RESOLVED`；审核说明“浏览器实链路审核完成”；研究 Job attempts=1；9 条假模型治理记录，远程 endpoint 数为 0；报告 schema=`research-report/v1`，hash=`262c2af71623080842f2f31b7197d34c92fa665d6f0356e24baa63829b603f71`。

回归：`npm run check:research-browser` 通过（含 TypeScript/Vite 构建）；独立库执行 `test_research_api_creates_idempotent_task_and_serves_final_report`、`test_human_review_releases_lease_and_resumes_stop_stage_only`，**2 passed、0 skipped**。新增 Python harness 和修改的集成测试 Ruff 通过；`git diff --check` 通过。未重跑完整后端套件，无新增迁移；既有 FastAPI/httpx 弃用警告仍存在。

回归曾因历史待执行导出任务失败：原用例的 `process_next_report_export()` 领取了其他任务。修正为按本次 API 返回的 Job 定位 export_id；保留已有队列内容，复跑两条用例通过。浏览器脚本还修正了同名来源选择、React 表单状态等待、实际 SEMANTIC 审计阶段及导出提交期间暂时 404 的等待条件。

## 复现

本入口面向本机既有测试容器与已发布测试知识；需 Node 22+ 和已安装 Edge，不需要 Playwright。Docker Desktop 运行后：

```powershell
docker start tcm-handoff-test tcm-vib54-py
```

首次建立回环转发容器（已存在时使用 `docker start tcm-vib63-forward`）：

```powershell
docker run -d --name tcm-vib63-forward --publish 127.0.0.1:18063:18063 --link tcm-vib54-py:research-api --mount 'type=bind,source=D:\DevelopProject\videcoding\zhongyi\backend,target=/workspace/backend,readonly' python:3.11-slim python /workspace/backend/scripts/serve_research_e2e.py --forward
```

```powershell
cd frontend
npm run check:research-e2e
```

脚本从既有测试容器连接串复用同一服务器的凭据，并显式切换至 `tcm_vib60_test`；拒绝非测试数据库配置。只读使用活动测试知识，不执行迁移或发布；未准备测试知识时失败而非 skip。脚本退出后关闭临时浏览器和本轮 API；用 `docker stop tcm-vib63-forward` 停止转发。失败尝试留下的测试任务和队列保留用于诊断。

真实模型语义质量由 VIB-68 验收，桌面密钥交接由 VIB-70 接线；本验收不代表 V1 发布门禁完成。
