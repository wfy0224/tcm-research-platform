# 开发交接

## 当前任务：页面配置模型、数据库保存（2026-10-03）
- 基线仍 d0f002e / codex/evidence-audit；已有未提交改动保留，本轮未提交、未部署。
- 新增 migration 0028_model_configuration、governance.model_configuration；model_configuration.py 初次导入旧 JSON/环境/Windows 凭据，后续 API/Worker/CLI 从 DB 读取。环境密钥导入保留 TCM_ALLOW_ENV_API_KEYS=1 限制。
- ModelSettings.tsx 新增提供商密码输入、向量/重排模型、阿里工作空间/区域；密钥留空保留，API 不回显；数据库 JSON 保存密钥，尚未应用层加密。db.py 隐藏 SQL 参数防止异常输出凭据。
- main.py schema head 改为0028；README 同步迁移说明。研究模型路由仍按任务冻结，已有任务不改模型。调整向量模型需重建索引。
- 实际验证：frontend npm run build 通过；本地 Docker daemon 不可用，没有运行 Windows Python，后端单元/迁移/独立DB及页面验收未验证；没有付费调用。
- 新增 test_model_configuration.py；test_cloud_models.py 使用离线配置替身适配 DB 读取。下一步启动安全 Linux 测试容器，运行配置/云适配器测试，并用独立测试库验证0028迁移、密钥不回显、空密钥保留及双进程配置一致；之后页面验收。生产部署尚未执行。
- 本任务无对应已确认 Issue，Linear 不可用待同步。此前付费调用限制继续有效。

## 保留的原停点（离线修稿链路已部署，真实报告未终验）
- 分支codex/evidence-audit，基线d0f002e；未提交、未推送。已有UI/部署/任务进度改动全部保留。
- 用户最初授权部署及重试，最新要求真实测试；后因连续调用成本要求赔钱。已承认成本控制问题，承诺不再发起任何付费模型调用，后续付费测试必须重新得到明确授权。不要自动重试或续跑云研究。
- 原任务RT-01a1001e-e294-7ab7-9ba2-e2005bee58cc；内部3e1ddfed-82be-5d24-8d0d-093afd5ca3ec；JOB-01a1001f-0ec8-7880-af07-3b34818e003a。
- 当前REPORT_REVIEW_REQUIRED；队列COMPLETED/attempts1/last_error=null；最新报告revision7 NEEDS_REVISION。最后一轮在暂停请求到达前已结束，暂停API返回research job cannot be paused；没有成功设PAUSED，当前control_state=ACTIVE但无运行队列。不得称研究完成或测试通过。
- 本次实际执行5个有界修订周期，Writer round6～20共15稿，模型Reviewer10稿均拒绝、程序Validator5稿失败。真实付费调用25次（15写作+10复核）；精确费用、余额和扣费金额未知。全部记录保存在REAL_REPORT_TEST.json；该文件model_calls还含此前历史调用，不能当作本轮调用计数。
- 最新修复report_narrative.py：恢复同冻结来源前后文/证据强度，写作与复核一致范围规则、明确完整JSON字段、实质拒绝与可选建议区分；程序校验错误保留已有内容反馈并跨周期恢复，原始草稿/独立ReportValidator持久记录保留，不伪造模型通过。
- 最新部署report_narrative.py SHA256 04c385582d9f809e41424c6cc6c1c286a14260ab3de85a94225ea5a6263f5cf1，备份.pre-targeted-revision-20261003；重建API/Worker。本轮0模型调用、未重试原研究。
- 本轮补修：把上一稿传给写作者并跨周期恢复，完整校验定位段落与引用；复核只接收本稿相关缺口/争议，增加逐段引用清单；新生成原样失败稿提前停止后续调用，保留原稿及反馈。原门禁未放宽，未修改历史稿或accepted状态。
- 冻结execution_context哈希仍0f9ffcabe70c2073d6b8c75b9f41619e3e2830b71f094db29ec6b31729f7236b；历史报告rev1/2原哈希保留，新rev3～7追加。恢复48条证据上下文，不修改冻结快照或引用正文。
- 之前debate_service.py角色类型约束已部署SHA abce564d26ed214d21f4b2164bec4afd621d635649b888795f2236d5e203863d；5真实回应通过。DeepSeek max_tokens393216已部署SHA c8a70ac6852bb2ab80f29f8e32b9addeb1ac8f126346797de145271aee069b5b；未补响应finish_reason诊断。
- SSH ubuntu@42.193.100.122，/opt/zhongyi；私钥C:/Users/wangfeiyu/.ssh/zhongyi_diagnose_ed25519保持加密，不输出私钥、不移除口令。密钥口令仅保存在本机，不进入仓库。

## 本轮验证与下一步
- Linux容器整批候选及部署后模块16项unittest通过，含真实第16/19/20稿离线重放。修复前缺上一稿2errors/错误定位1failure、重复调用1error/1failure、范围过滤1failure；0云调用、0生产DB写入。未跑独立DB集成；git diff --check通过。
- 浏览器Computer Use因无法确认Windows当前网址被工具停止；不绕过限制，网页验收未完成。
- 入口report_narrative.py、test_report_validation_feedback.py；证据server-rebuttal-contract/OFFLINE_REPAIR.md、OFFLINE_REPLAY.json、OFFLINE_REPAIR_VERIFICATION.json，付费失败历史REAL_REPORT_TEST.json保留。
- 下一步只做无费用检查：研究仍未获真实复核接受，新增修稿输入能否产出合规正文未云验。未经用户重新明确授权和预算上限，禁止重试/修订/恢复模型队列；不要以16工程回归宣称研究完成。
- 部署后API可达，DB connected/schema current/blob_store available；health按现有实现返回DEGRADED。原报告7版hash、冻结配置及历史40条报告模型调用均不变。
- VIB-92/93/94仍In Progress；Linear不可用待同步。历史首页归档docs/handoff-history/2026-10-03-before-offline-revision-repair.md。

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
