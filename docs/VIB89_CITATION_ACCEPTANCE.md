# VIB-89 引用定位与完整上下文修复

2026-10-01；分支 `codex/evidence-audit`，基线 `7b27043`。本轮未提交；已有改动、历史修订、证据与版本保留。

## 修复与原因

- 原 `EvidenceDrawer.onSource` 只传来源ID。相同来源会恢复旧发布标签和旧修订，阅读默认首50条。现在传递来源ID/修订和证据ID/修订，原文页强制打开，URL可恢复精确目标。
- 原文分页读取到全部引用段均存在，核对完整引用文本与证据一致后才高亮。句级引用也能定位；目标不存在、版本不一致或读取失败会显示错误和重试，不落到首段冒充成功。
- 引用导航不覆盖原阅读位置；返回恢复来源修订、标签、长文加载范围和焦点。研究组件在引用往返期间保留当前任务和报告标签。重载引用URL也能恢复目标。
- 回归发现同来源返回时，段落加载的generation使来源详情请求过期，留下空白。将来源请求与审核请求的generation分开，加入同来源跨修订往返回归。
- 历史证据保存的上下文为最多1000字符的摘要。详情API新增 `full_context_before/after` 和 `context_complete`，从证据绑定的不可变来源修订中按同层兄弟读取完整相邻原文；原保存的摘要、引用文本、校验和和证据修订均不改写。
- 检索、详情、阅读和报告使用一致的软换行阅读格式。已知逻辑段/章/页可读展示，内部路径与物理行映射收进详情。TXT/DOCX不把解析器虚拟页1显示成真实页码；PDF显示已有真实页码。
- 详情读取失败明确显示重试；失败时不把上下文显示为“无上文/下文”。旧API不带完整上下文字段时明确标为摘要。

## 实际验证

- 修复前 `node scripts/check_citation_navigation.mjs`：应进“来源与原文”，实际“质量与版本发布”，明确断言失败。
- 真实 `http://127.0.0.1:18067` / `tcm_vib62_workspace_test`：大青龙汤检索1条 → 精确证据 → 来源修订2的阅读180～194，15段全部高亮 → 返回相同证据详情。故意预存修订1/发布标签仍跳到修订2。刷新恢复、直接引用URL、390px无横向溢出通过。重载API后确认已提供完整上下文。
- 来源 `SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350`，证据 `EV-01a0f68d-647a-78cf-8b60-1d51bd1adb64@1`。未重复导入、审核、发布或开始研究；本輪0生成调用。
- `node scripts/check_citation_boundaries.mjs`：独立本地合成HTTP服务，篇首/中间/篇末、超过1000字符的上下文、同名来源、保存新修订时定位旧修订、未加载长文、子句、证据503重试、段落503重试、目标不存在、返回旧阅读位置、报告引用返回原任务/标签均通过。合成报告只用于UI回归，不充当真实研究成果。
- Linux既有 `tcm-vib54-py`，`backend/scripts/check_demo_repairs.py` 创建独立库 `tcm_demo_repairs_479d3a48_test`：**34 passed / 0 skipped**。新用例验证长上下文、篇首末边界、来源新修订出现后仍读取旧修订上下文，且历史摘要不变；原33项解析/分段/引用/审核/提取回归通过。一个现有Starlette/httpx弃用警告。
- 构建、知识选择检查、API错误检查和Ruff通过；`git diff --check`通过。未运行Windows Python/uv/Alembic。
- 页面工程截图已检查：1280×900原文高亮；390×844手机布局。证据目录 `docs/acceptance-artifacts/vib89/`：`fangji-citation.png`、`fangji-citation-mobile.png`、`real-result.json`、`contracts-result.json`；修复前失败文本保留。

## 入口、运行与边界

- 前端：`citation.ts`、`EvidenceDrawer.tsx`、`main.tsx`、`KnowledgeWorkspace.tsx`、`ResearchWorkspace.tsx`、`knowledge.css`。
- 后端：`knowledge_api.evidence_detail`；回归 `test_knowledge_workflow_api.py`。
- 前端复验：`npm run check:citations`（需要已有演示服务及上述证据）；合成回归可单独运行，不依赖演示数据库。
- 旧启动器会话49123已不可用，服务确认退出后已重启；本轮新会话23259，仍用原演示库。没有创建新业务版本。
- 同期发现其他工作区修改了模型启动器、模型目录/能力配置；已保留。本轮启动输出选择 `siliconflow/Qwen/Qwen3-8B`，`LOCAL_ONLY`；不能再沿用“未配置TCM_RESEARCH_MODEL”作为最新能力结论。模型可用性/外发条件由相关工作接续验证。本轮没有新启研究任务。
- VIB-89工程验收完成；真实研究任务尚无本轮报告/导出，VIB-92/94全链验收未由本轮完成。真实PDF阅读器/文件页打开不是本轮新增功能；系统内引用定位使用已有页码。
- 下一开发项VIB-90：补手工方剂入口及审核→可检索版本衔接，保留两方已有概念、证据和活动版本2。
