# 开发交接

## 当前停点（2026-10-03）
- 分支 codex/evidence-audit；基线 d0f002e，父提交 7b27043；本轮未提交、未推送。已有 UI/部署/任务进度改动保留。
- 用户指定服务器研究失败排查，已批准备份、部署 debate_service.py 修复及重试原任务。
- 服务器 ubuntu@42.193.100.122，项目 /opt/zhongyi；专用 SSH 私钥 C:/Users/wangfeiyu/.ssh/zhongyi_diagnose_ed25519。不要输出私钥。新密钥因 Windows 参数转义被设了两个引号的口令；用该口令连接，仍加密，不移除口令。
- 最近失败 RT-01a1001e-e294-7ab7-9ba2-e2005bee58cc；内部 ID 3e1ddfed-82be-5d24-8d0d-093afd5ca3ec；JOB-01a1001f-0ec8-7880-af07-3b34818e003a。
- last_error 为 revised Claim type is not allowed for its original role；固定 DIRECT_TEXT 示例未说明历史/理论角色类型约束。更早任务 invalid JSON 是不同失败，未宣称本轮修复。
- 修复：Rebuttal 提示词说明 allowed_claim_types；模型可见输入逐目标附加允许类型及 revision_contract，覆盖旧冻结任务；新 prompt_version=rebuttal-v2。原角色/证据校验与冻结快照不变。
- 已备份服务器 /opt/zhongyi/backend/src/tcm_platform/debate_service.py.pre-rebuttal-20261003；已重建后端镜像、重启 API/Worker。部署新文件 SHA256 abce564d26ed214d21f4b2164bec4afd621d635649b888795f2236d5e203863d。
- 用户部署后操作原任务；最新只读核对：任务REPORT_REVIEW_REQUIRED，队列COMPLETED/attempts3；ReportWriter/Reviewer rounds0～5已保存。队列last_error保留conditional Claims cannot become certain report findings（条件观点被写成确定finding）；当前并非仍在等待重试。复核仍拒绝部分越界/误引，完整报告尚未接受。
- 用户最新要求只改+重新部署，不重试、不观察。cloud_models.py已将DeepSeek请求max_tokens从2048设为官方最大393216（384K）；其他provider不变。冻结路由deepseek/deepseek-flash。官方参数 https://api-docs.deepseek.com/api/create-chat-completion/ 。
- cloud_models.py服务器备份 /opt/zhongyi/backend/src/tcm_platform/cloud_models.py.pre-output-limit-20261003；部署新文件SHA256 c8a70ac6852bb2ab80f29f8e32b9addeb1ac8f126346797de145271aee069b5b。无模型调用或研究重试。
- 本轮用户要求“修”：report_narrative.py已将程序内容/结构校验失败接入自动修稿，保存原草稿及独立ReportValidator记录，不冒充模型复核。补齐模型可见段落契约，冻结快照不变；三稿耗尽仍明确待修订，真实设施错误仍Worker重试。
- 已部署report_narrative.py，备份后缀.pre-validation-feedback-20261003；新SHA256 0e3a86a7bc21be34c4da279c0c0d32d95bea3d21124a345a5a6e845c20741c06。4工程回归：修复前3errors，候选后全通过；镜像构建/API及Worker启动完成。没有云调用、研究重试或数据库集成。
- 下一步：用户继续修订原报告时验证模型是否根据具体校验/复核反馈改稿；此前只改部署、不自动研究的要求仍保留。证据docs/acceptance-artifacts/server-rebuttal-contract/REPORT_VALIDATION_FEEDBACK.md。输出上限已393216，响应诊断仍未补齐；冻结配置hash0f9ffcabe70c2073d6b8c75b9f41619e3e2830b71f094db29ec6b31729f7236b保留。

## 本轮验证与入口
- backend/src/tcm_platform/debate_service.py；backend/tests/test_rebuttal_contract.py；证据 docs/acceptance-artifacts/server-rebuttal-contract/ACCEPTANCE.md。
- 服务器 Linux 容器：修复前测试 1 failure/3角色子测试错误；临时进程候选及部署后均2 tests OK；真实5目标上下文约束通过，冻结快照不变。无测试数据库写入或测试模型调用；原任务重试为真实云调用。
- git diff --check 通过；Windows Python/uv/Alembic禁止入口未运行，本机 Docker daemon 当前不可用。未跑数据库集成测试；skip 不等于通过。
- 自动审批拒绝过取消私钥口令与未限定的交互式远程 shell；均未执行。改用加密密钥和具体限定 SSH 命令，部署/重试已有用户明确批准。
- VIB-92/93/94保持 In Progress；Linear 本轮待同步（未发现可用工具）。仍需报告端实际验收。

## 保留的本地开发与真实基线
- 之前 UI 美化：theme.css 青绿暖白/阅读/响应式，main.tsx 引入；真实1440/390px检查和构建通过，证据 docs/acceptance-artifacts/ui-refresh/。未提交。
- knowledge_api.py 新增最近后台任务/向量进度接口；JobsPanel.tsx 挂知识库质量页；接口200、向量133/133、api healthy、服务器前端构建通过，浏览器尚未验收。旧 publication_job 文案/JobResponse 进度仍未改。
- deploy/、.dockerignore、README 与服务器手册未提交；空库部署、迁移0027、网页/代理/访问码/CSRF已验，0云调用；2核2G负载尚未验。
- 完整方剂学.txt：来源 SRC-01a0f5ce-fd1e-761e-bb62-0e354f91a350 修订2，4211正文/843新增证据核对；376方剂REVIEWED（非医学认证），KV4 READY/ACTIVE，1243证据/376方剂/3概念。
- 向量 index IB-e3e7a3fa3fb4d9784d036162b09a4b93；125批真实向量，bge-m3/bge-reranker-v2-m3检索通过。
- 旧分歧任务 RT-01a0f7c4-ab9c-767d-ad0a-bd59b05bc940 COMPLETED；冻结 deepseek/deepseek-flash/max1；rev2 ACCEPTED，hash 6234882bdcdecb0a0c02d4334bbd7166adc44250a88f26f7022a143b44eb607b 保留。独立库43 passed/0 skipped仅前轮工程验收。
- research-v3/critic-v3 新任务最多3轮、review_replies=true；旧缺字段按max1/false。三稿耗尽保存NEEDS_REVISION，允许有界修订；0027不可变报告修订。当前服务器原任务的真实多轮运行正在补验，尚未完整通过。
- report-export/v6正文使用报告内编号/链接，去除内部UUID/hash；原文保留。三个实际任务四个版本、引用回跳和19页Word已验，证据 readable-report/、report-recovery/、real-research-answer/。

## 开发环境约束
- 用户要求真实云端、完整原文、实际质疑回应、自己的话回答、折叠原文；禁止模拟业务数据补验收。
- 本地页面127.0.0.1:18067，API18068；原Node会话3712。仅按 scripts/serve_workspace.mjs 匹配停服务，不批量杀进程。
- 历史 Linux tcm-vib54-py /workspace:ro；实际开发库 tcm_vib62_workspace_test；默认 tcm_vib54_test 旧schema禁止拿来宣称通过。前轮独立库 tcm_debate_repair_6dca_test。
- 服务 CLOUD_ALLOWED、hybrid-rrf-v1；模型按任务冻结路由；凭据禁止输出。DOCX只用Linux渲染。
- 被替代当前页完整保存在 docs/handoff-history/2026-10-03-before-server-rebuttal.md；新会话启动不读历史，仅具体追溯时按需读取。
