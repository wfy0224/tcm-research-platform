# 服务器回应质疑类型约束修复（2026-10-03）

## 实际失败
- 服务器 `42.193.100.122`，项目 `/opt/zhongyi`，API/DB healthy，Worker running。
- 题目：所有与伤寒病症（恶寒或恶风，发热）相关的症候及对应方剂，按照症候从轻到重排列，分析比较各个方剂的药物组成的差别与原因。
- 最近失败研究 `RT-01a1001e-e294-7ab7-9ba2-e2005bee58cc`，内部 ID `3e1ddfed-82be-5d24-8d0d-093afd5ca3ec`。
- 队列 `JOB-01a1001f-0ec8-7880-af07-3b34818e003a`，FAILED，attempts=3。
- 数据库 last_error：`ValueError: revised Claim type is not allowed for its original role`。
- 三个首轮角色和 Critic 第2轮均 COMPLETED；Rebuttal 第2轮 PENDING。
- 五个修订目标：HistoricalScholar/HISTORICAL_FACT 两条、Theorist/THEORETICAL_INFERENCE 一条、Classicist/TEXTUAL_RELATION 一条、HistoricalScholar/LATER_INTERPRETATION 一条。
- 此前任务 `RT-01a10005-0050-7a81-a02f-5bc208a35510` 的失败为 invalid JSON，本轮未将它认定为同一原因或宣称已修复。

## 原因与修复
- Rebuttal 示例固定为 DIRECT_TEXT，却未告诉模型目标角色允许的类型；HistoricalScholar 和 Theorist 不允许 DIRECT_TEXT。
- 新提示词明确 allowed_claim_types，并删除固定 DIRECT_TEXT 示例，新 Rebuttal prompt_version 为 rebuttal-v2。
- 模型可见上下文逐条附加角色允许类型，并明确示例不能覆盖角色约束。旧冻结任务也能取得此约束，原 input_snapshot / frozen_prompts 不变。
- 保留 submit_rebuttal_output 的角色、来源、证据和原子提交校验，未自动改写模型观点类型。

## 实际验证
- 通过专用 SSH 密钥连接；服务器接受公钥。使用加密私钥连接，口令不进入仓库，未输出私钥。
- 生产容器只读运行 `backend/tests/test_rebuttal_contract.py`：修复前 1 failure / 3 subtest errors（allowed_claim_types 缺失）；修复候选在临时 Python 进程加载后 2 tests OK，覆盖三角色及旧冻结快照不变。
- 未写生产数据库，未调用模型，未修改服务器源码或容器文件。
- 已部署文件路径 `/app/backend/src/tcm_platform/debate_service.py`，修复前 SHA256 `2db31b0e8a78c2412b313eb44d6c3150da5347accff9574679fd682a9d4c5925`。
- git diff --check 通过。Windows Python/uv/Alembic 禁止入口未运行；本机 Docker daemon 当前不可用。

## 部署与真实恢复
- 用户明确批准部署及原任务重试，保留原模型路线。
- 原文件备份 `/opt/zhongyi/backend/src/tcm_platform/debate_service.py.pre-rebuttal-20261003`；更新唯一源文件后重建镜像，重启 API/Worker。
- 新文件 SHA256 `abce564d26ed214d21f4b2164bec4afd621d635649b888795f2236d5e203863d`。
- 新镜像中2项回归通过；真实5条目标类型约束通过；execution_context/input_snapshot 不变。
- 冻结配置 SHA256 `0f9ffcabe70c2073d6b8c75b9f41619e3e2830b71f094db29ec6b31729f7236b`。
- 使用现有 retry_research_task，idempotency_key=server-rebuttal-contract-20261003，恢复原任务，不直接改库或创建替代任务。
- 实际 Rebuttal 第2轮 COMPLETED，保存5回应；Critic 第3轮 COMPLETED，Rebuttal 第3轮 PENDING；任务 DEBATING，队列 RUNNING/attempts1，报告0。

## 当前边界
- 前次真实重试第3轮 Rebuttal 连续3次 invalid JSON，队列 FAILED/attempts3。不能宣称全链完成，未记录响应结束原因，截断诱因未确认。
- 自动审批拒绝过取消私钥口令及未限定的交互式 SSH shell，均未执行。采用加密密钥和具体限定命令完成部署。

## 用户指定输出上限调整（2026-10-03 13:39）
- 用户明确要求只改并重新部署，不重试、不观察研究结果。
- 只读确认原任务冻结模型为 deepseek/deepseek-flash。官方参数文档 https://api-docs.deepseek.com/api/create-chat-completion/ 的最大 max_tokens 为393216（384K）。
- cloud_models.py 将DeepSeek请求从2048设为393216；其他provider不变。撤回未部署的动态截断重试候选，仅保留上限调整。
- 原文件备份 /opt/zhongyi/backend/src/tcm_platform/cloud_models.py.pre-output-limit-20261003。
- 新文件SHA256 c8a70ac6852bb2ab80f29f8e32b9addeb1ac8f126346797de145271aee069b5b。
- 原文件指纹/无运行中任务检查、Python源编译、后端镜像构建及API/Worker重建启动成功，git diff --check通过。
- 本次0模型调用、0研究重试；未验证调大上限能否解决invalid JSON，未补齐响应诊断记录。下一步由用户操作页面重试。

## 用户反馈报告阶段失败后的只读核对
- 原任务当前REPORT_REVIEW_REQUIRED，队列COMPLETED/attempts3，Writer/Reviewer rounds0～5均已保存。
- 队列保留last_error：`ValueError: conditional Claims cannot become certain report findings`。实际门禁禁止段落kind=finding引用CONDITIONAL观点；这是本次报告阶段执行失败原因，与此前JSON失败不同。
- 自动重试当前已结束，报告仍未被复核接受。最近两轮复核中指出段落部分配伍/归因/排序标志超出其所引观点与quote_text范围，并要求明确条件性归因。
- 本轮只读查询，不改服务器、不调用模型、不自动重试；尚未修复Writer段落类型契约或引用越界。
