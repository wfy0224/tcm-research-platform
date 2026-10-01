# VIB-87 导入与证据草稿流程验收

日期：2026-10-01。基线：`codex/evidence-audit` / `7b27043` 加既有未提交改动。本轮仅归属下述导入引导修复，既有 C02、审核接口、开发免码连接和其他前后端改动均保留。

## 问题与修复

- 缺文件、缺标题等条件原来仅禁用按钮；新增按钮附近的具体原因、必填/选填标记、字段验证提示。
- 无证据和待核对证据在已审核下拉框里无选项；新增返回原文、核对待处理证据入口，核对通过后选择可用证据。保留真实人工核对，不自动标记审核。
- 证据尚未形成知识草稿时，不再引导直接发布；下一步引导填写知识名称。
- 不连续、混合层级/类型、超过 100 段的选择提供本地提示；服务端精确引用边界保持有效。
- 来源、修订和操作步骤在同一浏览器标签刷新后恢复；资料切换清空旧选择，重新加载对应范围。解析状态自行轮询，失败/需 OCR 提供作为新修订重新导入入口。
- 修复解析完成后的重复刷新可能清掉刚选段落的问题；同步操作锁防止同一操作重复提交。服务失败在对应表单旁显示，保留输入以便重试。

## 实际验证

环境：已有 Linux `tcm-vib54-py`，独立数据库 `tcm_vib62_vib87_test`，独立存储 `/tmp/tcm_vib62_vib87_test_store`，临时页面端口 18075、回环转发 18076。没有修改业务库、预览库或保留演示库。全部样本为合成工程资料，无真实模型调用、无真实文献/医学专家审核。

本轮结束已停止临时服务、移除本轮转发容器，库和样本保留。需要复查时，在 `frontend` 的一个终端启动隔离环境（先确认同名转发不存在、端口空闲）：

```powershell
$taskRuntimeIp = docker inspect tcm-vib54-py --format '{{.NetworkSettings.Networks.bridge.IPAddress}}'
docker run -d --name tcm-vib87-forward --publish 127.0.0.1:18076:18076 --mount 'type=bind,source=D:/DevelopProject/videcoding/zhongyi/backend,target=/workspace/backend,readonly' python:3.11-slim python /workspace/backend/scripts/serve_workspace_demo.py --forward --port 18076 --upstream-host $taskRuntimeIp
$env:TCM_WORKSPACE_PORT = '18075'
$env:TCM_WORKSPACE_API_PORT = '18076'
$env:TCM_WORKSPACE_DATABASE = 'tcm_vib62_vib87_test'
node scripts/serve_workspace.mjs
```

等待启动器报告 18075 地址后，在另一个终端执行检查；本流程使用合成资料，可以在保留隔离库内重复运行。结束后关闭临时启动器，并清理仅本轮的转发容器。

在 `frontend` 运行：

```powershell
npm run build
node scripts/check_import_guidance.mjs
node scripts/check_api_errors.mjs
node scripts/check_development_session_browser.mjs
```

首个浏览器检查在修复前明确失败：`missing-file reason must be visible beside disabled import`。最终检查直接驱动真实 API 与解析 Worker，所有业务写操作由页面提交：

| 检查 | 实际结果 |
| --- | --- |
| 缺文件、缺标题；填齐后按钮恢复 | 通过 |
| 新 TXT 导入→解析→无证据恢复入口→选择原文→建证据→填写核对说明→通过→建概念草稿 | 通过 |
| 待核对证据有处理入口；核对完成自动选中证据 | 通过 |
| 非连续选段禁用并显示文字原因 | 通过 |
| 阻断草稿接口后表单旁报错、保留输入，恢复网络后重新提交成功 | 通过 |
| 两次快速点击只创建一条知识草稿 | 通过 |
| 刷新恢复原资料与审核步骤；切换新资料不沿用原证据，切回后恢复正确范围 | 通过 |
| 损坏 PDF 明确解析失败；无文字 PDF 明确需要 OCR，均可打开新修订导入入口 | 通过 |
| 375px 窄屏无横向溢出 | 通过 |
| 共享 API 字段位置、连续范围、会话、冲突、503、连接中断六类错误 | 通过 |
| 保留开发服务连接、刷新、新标签、失效凭据、存储恢复、服务重连 | 通过 |
| TypeScript / Vite 构建 | 通过 |

浏览器测试脚本等待来源目录加载完成再操作，避免在初始化期间提前展开表单；轮询竞态修复已在最终代码下重新验证。

## 限制与接续

- `check_research_browser.mjs` 旧模拟回归尝试在 `bootstrap form` 超时；该脚本没有当前 `local-session/config` 模拟路由，仍依赖旧导航和旧文案。本轮未修改它，也未将其计为通过。研究页面的完整验收仍归 VIB-92/94。
- 当前验收证明导入与核对交互的工程闭环；真实资料分段质量、引用高亮、知识入库、云端检索、真实研究和用户体验签认分别由 VIB-88～94 承接。
- 不会恢复未提交的表单草稿、未保存的核对说明或勾选状态；已落库的资料、证据与知识草稿会重新读取。跨浏览器/跨设备恢复不是本任务验收范围。
- 下一实施项：VIB-88，先分层复现真实资料的换行/分页/自然段与检索切片差异，不预判模型能力，不重写历史证据修订。
