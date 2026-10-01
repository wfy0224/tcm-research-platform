# 开发交接

## 1 当前基线与工作区

- 2026-09-30，codex/evidence-audit，工程基线 `e36c9d7`（实际环境验收与健康检查修复），本轮启动 `2742ba6`；查询扩展此前 `e7b0af0`。本轮验收/交接文档另提交，最终HEAD用git log核对。
- 并行开发启动前核对：代码/脚本/测试已提交e36c9d7；现存未提交内容均为该轮结果JSON、截图、backlog/需求矩阵/交接及归档，先提交为共同基线。无他人代码改动；未推送或部署。
- 默认每轮完成可验证阶段后仅提交本轮范围。旧首页归档docs/handoff-history/2026-09-30-before-live-acceptance.md，启动不读历史。
- 用户明确要求实际补验收；不能只更新计划或将未完成验收笼统标为阻塞、直接转新Issue。
- VIB-63/49/60/61 Done；VIB-46/48仍In Progress（真实C02/专家依赖），VIB-58仍In Progress（Windows Python适配器全链未验），VIB-45本地完成/旧详细外发待授权。
- 本轮Linear简短结论已同步：VIB-48评论29fd1bc2-675e-4bb7-98fb-a3403552e88e，VIB-58评论cb62d1ab-d7b8-4053-bfb8-1b4c43e3ce0b；完整内部证据留本地。

## 2 本轮实际完成的遗留验收

- 新真实HTTP+断网入口check_retrieval_offline_e2e.py/.ps1与前端driver：Uvicorn/HTTP/PostgreSQL、固定C01首条公版原文、API幂等导入/解析分段/工程审核/发布Worker/索引/本地简体查询与精确公开修订全部通过。
- API测试容器仅接Docker internal网络，实际外部TCP探针失败；生产CloudEmbedder/urllib真实网络失败，不注入异常。3条失败调用/重试审计，本地降级结果一致；研究严格失败不入池，benchmark网络/熔断严格失败无伪指标，审计链通过。
- Edge→真实后端：本地查询、原文详情/修订、实际断网提示/证据可读、刷新和375px通过。最终库tcm_vib48_offline_a797a044_test，JSON/截图在docs/acceptance-artifacts/vib48-offline/。断网索引用固定替身，不能称真实模型质量。
- 新独立tcm_vib48_cloud_acceptance_test：既有SiliconFlow BGE-m3与BGE-reranker-v2-m3 **3次真实调用全部COMPLETED、0重试**（2694/2394/1702ms），目标证据首位、索引READY、审计链通过。密钥只按变量名注入Docker exec，未打印/写仓库。单条冒烟不代表医学相关性/生成模型资格，未切8B模型。
- 既有tcm_vib60_test升级0026，真实研究Edge→HTTP/DB/Worker→暂停恢复/辩论/人工审核/续跑/报告/Markdown与DOCX实下载/SSE/刷新/375px全部通过；任务RT-01a0f29f-a934-7a3b-9255-0e5827d72338。固定生成替身，真实云调用0。
- Windows实机安全补验：PowerShell/.NET调用原生CredReadW/CredWriteW/CredFree与删除，随机一次性target的UTF-16LE、GENERIC/LOCAL_MACHINE、缺失1168与清理通过，未读写现有provider条目；没有启动Windows Python。Python ctypes/CLI适配器全链仍未验。
- 实测发现main.py::SCHEMA_REVISION仍0023，已迁到0026的库被误报migration_required，连真实研究E2E也会被阻断。修复为0026并加实际head回归：修复前复现，后健康与相邻本地API **5 passed、0 skipped**（1.67秒）。此前完整241通过保留为此前证据，本轮未重跑全量；Ruff/Node语法/diff/暂存diff通过。
- 失败验收库保留：tcm_vib48_offline_e2e_test健康常量；tcm_vib48_offline_final_test浏览器误断言列表EV编号；中间随机库benchmark漏单次授权。这些脚本预期已修正，未放宽门禁。最终全部流程通过。
- 文档docs/VIB48_LIVE_ENVIRONMENT_ACCEPTANCE.md及结果JSON/截图。临时网络/新relay已撤除，tcm-vib54-py回原bridge，tcm-vib63-forward回停止。未修改预览/业务库或docker-api-1；其unhealthy状态未修复。

## 3 仍缺的验收与下一条具体操作

- 已通过的真实HTTP/隔离断网/供应商/研究浏览器检查不再列待补，也不重复重跑。优先收尾VIB-46的真实C02与专家材料，不直接开VIB-47。
- 下一条操作：读fixtures/initial_corpus.json、VIB-46本地backlog及Linear最新记录，核对是否已有C02完整方剂准确摘录、固定来源修订/权利/哈希及专家安排。现仅29条非方剂C01，不能从方名补造药味/剂量。
- 若C02已具备，运行真实完整方剂抽取/逐字段引用/术语歧义/审核与检索验收，准备逐例校订清单，专家结果用实际输入；若仍缺，先准备可审阅来源摘录/冻结与验收材料，只请求确实不可替代的负责人/专家输入，不能拿合成测试标Done。
- VIB-58剩余的是Windows Python适配器实机全链，不是原生Credential Manager API。既有故障运行时禁令保持，不能为了闭环重试Python/uv/Alembic或其变体；需安全运行环境。已完成的PowerShell探针不冒充适配器验收。
- VIB-68承担专家Golden Set、医学相关性阈值和生成模型资格；3次BGE冒烟不替代它。真实语料依赖完成后再评估VIB-48 Done/VIB-62解除依赖。

## 4 保留的工程约束与增量流程

- local-exact-terms/v4保留旧批次，追加DRAFT与精确字符/字段来源，Evidence先审/知识后审，快照激活复验。explicit-orthography/v1有限表，不跨对象传播别名、不多跳；历史Evidence不以最新行替换，未知null保持。
- 检索每通道只返回冻结KV/Index/Scope内已审核/索引的精确Evidence。None用冻结来源，显式空Scope无结果/模型调用；未发布质量扫描仍原NFKC字面规则，不按字形扩展自动开问题。
- 默认未授权纯本地、不读凭据；服务故障降级显式开启，研究/benchmark严格失败。模型/端点/Scope/发布门禁及DB/审计故障不能降级绕过。
- 用户要求精简流程：只读当前交接/Git增量/相关Issue；不重新盘点全项目。按变化范围验证，未执行验收必须补，已通过相同检查不重复。无结构变更不重复迁移往返，无前端变更不重复build/模拟浏览器。此轮直接用现有dist。
- 安全验证只用既有Linux tcm-vib54-py与独立DB tcm-handoff-test，TCM_*_test数据库，PYTHONDONTWRITEBYTECODE=1，pytest禁缓存，Ruff --no-cache --ignore EXE002。不启动/修改docker-api-1/预览库。
- 复现断网：./backend/scripts/check_retrieval_offline_e2e.ps1（自动新随机测试库、内部网络/回环relay与finally恢复）。Windows原生探针check_windows_credentials.ps1随机target并清理。真实云验收不得无意义重复计费；check_knowledge_api_live.py默认只预检，--execute才调用，仅允许指定独立库。
