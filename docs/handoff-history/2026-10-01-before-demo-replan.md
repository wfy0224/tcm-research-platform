# 开发交接

## 1 当前基线与工作区

- 2026-10-01，分支 `codex/evidence-audit`，启动与当前 HEAD `7b27043`；此前 `442b88c`、`e3932f8`。本轮明确任务：开发环境取消手填本机访问码，已实现并验证。
- 启动前已有未提交 `.gitignore`、`backend/src/tcm_platform/main.py`、`frontend/src/main.tsx`、`frontend/src/style.css`；已有未跟踪 `check_workspace_demo.py`、`serve_workspace.mjs`、`EvidenceDrawer.tsx`、`api.ts`。全部保留，未覆盖或回退。
- 本轮改动尚未提交：config/local_auth/main 的开发会话、前端连接/启动器/package scripts、开发会话后端与浏览器验证入口、README/backlog/本交接及旧首页归档。main.py/main.tsx/serve_workspace.mjs 与既有界面增量重叠，提交前按归属整理，不能把此前改动冒充本轮成果；未推送或部署。
- 旧首页存于 `docs/handoff-history/2026-10-01-before-development-auto-session.md`；启动不用读历史。

## 2 当前完成结果与运行入口

- `Settings.development_auto_session` 对应 `TCM_DEVELOPMENT_AUTO_SESSION`，通用默认 false。`GET /api/v1/local-session/config` 返回模式；`POST /api/v1/local-session/development` 开启时建立真实 Cookie/CSRF/权限会话，关闭返回404。正式一次性 bootstrap 保留。
- `local_auth.py::development_local_session` 使用随机会话 Cookie 派生可恢复 CSRF，复用有效开发会话；新标签页不会使旧标签页失效，过期/撤销会话重建。Host/Origin/业务 CSRF/权限/审计不绕过，不涉及云外发授权。
- `frontend/src/main.tsx::SessionConnection` 按配置自动连接，刷新/新标签页/丢失或陈旧 CSRF 自动恢复。服务暂不可用显示重连按钮，不要求码；正式模式保留码输入。
- `serve_workspace.mjs` 不再要求 `TCM_DEMO_BOOTSTRAP`；`serve_workspace_demo.py` 自动开启开发会话，不再读取首行码。`frontend` 中 `npm run dev:workspace` 可构建并启动；单用 Vite 需为其对应后端显式配置该开关。
- 当前已后台运行 Node PID **43752**，页面 `http://127.0.0.1:18067/`；既有 Linux `tcm-vib54-py` 内 API/Workers，经既有 `tcm-vib62-workspace-forward` 的回环18068转发。复用 `tcm_vib62_workspace_test` 和已有文件/研究报告；未启动或改动 docker-api-1/业务库/预览库。
- 启动日志 `backend/data/workspace-dev.stdout.log`、`workspace-dev.stderr.log`（ignored）。Codex 浏览器打开请求已排队。若已有页面运行，刷新；端口停了则用上述启动命令，不要再生成或寻找访问码。

## 3 本轮实际验证

- Linux 新独立 `tcm_development_session_6f7cede1_test` 迁到0026：`tests/test_development_session.py`、`test_local_api_integration.py`、`test_research_capabilities.py`、`test_job_failure_reason.py` 共 **52 passed、0 skipped**（2.28秒），一条既有 Starlette/httpx 弃用警告。入口 `backend/scripts/check_development_session.py` 每次新建独立测试库。
- 验证开关关闭、无码连接、Cookie/CSRF、Origin/Host拒绝、权限、重复会话、过期/撤销后重建与正式一次性码流程；没有数据库模型/迁移改动。
- 最终实际无头 Edge→HTTP/DB 验证：首次自动连接、刷新、双标签页、CSRF缓存丢失及陈旧恢复、375px无码、服务配置请求被阻断后重连；知识来源与研究任务GET均200，旧标签页POST通过鉴权进入422必填校验，无业务数据写入。0次真实模型调用。
- 浏览器复验 `frontend` 中 `npm run check:development-session`，要求18067实际服务已运行；无头Edge独立profile退出后清理，不操作用户浏览器。
- 最终 TypeScript/Vite build、相关后端 Ruff（--no-cache --ignore EXE002）、Node语法与git diff --check通过。未重复全量后端、旧研究流程或模型质量验收。
- 未启动故障 Windows Python/uv/Alembic。容器/后台服务/无头Edge所需沙箱升级已获允许。

## 4 仍缺事项与下一条具体操作

- 本次开发连接任务完成；VIB-70桌面Supervisor仍Backlog，不以开发自动连接替代正式桌面交付。backlog对应小节已记增量，Linear未同步（本轮没有外发授权）；不因该增量变更其他Issue状态。
- 若用户继续测试页面，先承接其反馈。若仅说继续开发：先核对Git增量与本交接，再读 `fixtures/initial_corpus.json` 及backlog VIB-46，核对C02完整方剂摘录/来源修订/权利/哈希和专家安排；当前仅29条非方剂C01，不从方名补造药味剂量。
- 若C02缺失，准备可审阅来源摘录、冻结与验收材料，仅请求不可替代的负责人/专家输入。VIB-46/48仍需真实C02/专家；VIB-68承担Golden Set、医学相关性与生成模型资格，既有BGE冒烟不替代它。
- VIB-58只剩Windows Python凭据适配器实机全链；原生PowerShell API探针已通过。故障运行时禁令保持，不能改入口或提权重试以闭环。
- 开发代码与此前界面增量仍混在工作区，后续阶段提交前只纳入确认归属的改动，先保留已有代码/数据。

## 5 必要工程约束

- 安全验证用既有Linux `tcm-vib54-py`、`tcm-handoff-test` 和独立 `TCM_*_test` 库，`PYTHONDONTWRITEBYTECODE=1`，pytest禁缓存，Ruff --no-cache --ignore EXE002；不启动/修改docker-api-1/预览库。
- 默认未授权纯本地、不读模型凭据；研究/benchmark严格失败。开发免码不改变外发授权、模型设置、Scope、审核/发布门禁及DB/审计失败行为。
- Evidence/知识保留精确来源修订，校订追加DRAFT，未知null不补造；查询限定冻结KV/Index/Scope，历史Evidence不以最新行替换；字形/别名不跨身份或多跳传播。
- 用户要求精简：当前交接/Git增量/相关Issue按需读；只验证变化与必要回归，已通过相同检查不重复，真实模型不无意义重复计费。
