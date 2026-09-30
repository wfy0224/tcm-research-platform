# VIB-48 遗留环境验收补齐

日期：2026-09-30；启动 `2742ba6`，工程提交 `e36c9d7`。本次实际执行验收，不以更新计划替代运行结果。VIB-48/58简短结论已分别同步Linear评论 `29fd1bc2-675e-4bb7-98fb-a3403552e88e`、`cb62d1ab-d7b8-4053-bfb8-1b4c43e3ce0b`。

## 已完成

| 遗留项 | 实际执行及结果 | 证据 |
| --- | --- | --- |
| 真实 HTTP 后端与本地检索 | Uvicorn + HTTPX + PostgreSQL；固定公版C01首条原文，API导入幂等→生产解析/分段Worker→Evidence工程审核→发布Job/Worker→索引/激活→简体查询与精确原文/公开修订；通过 | [结果](acceptance-artifacts/vib48-offline/result.json) |
| 实际断网降级 | API验收容器只连接Docker internal网络，实际外部TCP连通探针失败；使用生产CloudEmbedder/urllib传输，不注入网络异常；3条失败调用落库，重试2次，服务降级后结果与本地完全相同。研究严格失败不入证据池，benchmark在网络/熔断错误下严格失败不生成指标 | 同上；独立库`tcm_vib48_offline_a797a044_test` |
| 真实后端检索浏览器 | 已构建前端→回环HTTP转发→生产API；默认本地、原文详情/修订、实际网络失败提示和证据可读、断网刷新、375px布局均通过 | [截图](acceptance-artifacts/vib48-offline/offline-evidence.png)；结果中的5条browser_checks |
| 真实供应商模型联调 | 既有SiliconFlow BGE-m3/BGE-reranker-v2-m3；C01首条原文在新独立库构建索引，查询向量和重排。**3次实际调用全部COMPLETED、0重试**；首位证据等于目标，索引READY、审计链通过 | [云调用结果](acceptance-artifacts/vib48-offline/cloud-result.json)；`tcm_vib48_cloud_acceptance_test` |
| 真实研究后端浏览器E2E | 既有独立`tcm_vib60_test`升级head；浏览器创建→暂停/恢复→真实Worker辩论→人工审核→续跑→报告→Markdown/DOCX实际下载→刷新→窄屏与SSE均通过。模型为固定替身，真实云调用0 | [研究结果](acceptance-artifacts/vib48-offline/research-result.json)；任务`RT-01a0f29f-a934-7a3b-9255-0e5827d72338` |
| Windows原生凭据实机 | PowerShell/.NET直接调用与生产适配器相同的CredReadW/CredWriteW/CredFree；Unicode字节、GENERIC/LOCAL_MACHINE、缺失返回1168及删除后缺失均通过；随机一次性测试target，无现有provider凭据读写，无原生Python启动 | [凭据结果](acceptance-artifacts/vib48-offline/windows-credential-result.json) |

断网索引构建仅使用固定测试向量；真实云模型联调另用专用数据库和真实供应商路由，两者不混淆。断网范围为专用测试容器，不称生产主机断网；没有断开用户电脑网络，也没有修改预览库或业务API容器。临时网络与relay均撤除，`tcm-vib54-py`恢复原bridge，`tcm-vib63-forward`恢复停止。

## 发现并修复的缺陷

首个真实HTTP验收在空库升级0026后失败：`main.py::SCHEMA_REVISION`仍为0023，健康检查误报`migration_required`，也阻止既有真实研究E2E入口启动。修正为0026，新增回归用例按Alembic实际head验证HTTP契约：修复前明确复现`migration_required != current`；修复后健康检查与相邻本地API **5 passed、0 skipped**（1.67秒）。首个回归夹具默认Host被回环门禁拒绝，改为127.0.0.1后复现正确缺陷，未放宽Host门禁。

失败库保留：`tcm_vib48_offline_e2e_test`（健康检查）；`tcm_vib48_offline_final_test`（浏览器错断言列表展示EV编号）；中间随机库（benchmark未给查询外发授权而先被门禁拒绝）。后两项是新验收脚本错误，已改为列表原文/详情编号，并显式授权隔离查询，未修改生产降级/权限逻辑。最终完整运行通过；先前已有完整后端241通过，本轮仅一处健康常量变更，运行相邻5条回归及真实E2E，没有重复无关全量测试/迁移往返/build。

Ruff检查src/tests/本轮Python脚本通过，Node语法通过，diff检查通过。既有弃用提示未处理。没有敏感输入/凭据写入仓库，实际密钥只按环境变量名注入专用Docker exec进程，未打印值。

## 仍不能宣告通过的验收

- **VIB-46真实C02/专家复核**：当前冻结语料只有29条非方剂C01。准确完整方剂摘录/来源修订/权利/哈希与专家标签缺失，不能用C01方名或合成药味补造。实际医学术语裁定仍需专家判断。
- **VIB-58 Windows Python适配器全链**：原生凭据API已通过；应用Python的ctypes/CLI适配器仍受既有0xc0000142/0xc06d007e运行时禁令约束。没有用其他Python入口/提权反复启动，不能把PowerShell原生API检查记作Python适配器通过。
- **VIB-68医学相关性/模型资格**：单条真实模型冒烟不代替专家Golden Set、阈值、召回/准确率或生成模型质量。没有切换8B生成模型。

VIB-48保持In Progress，原因现在是明确的真实语料/专家依赖，而不是将已经运行的真实HTTP/断网/供应商验收继续笼统列为待补。

## 复现入口

- 实际断网+检索浏览器：根目录`./backend/scripts/check_retrieval_offline_e2e.ps1`；使用已有测试容器，自动建立/恢复internal网络，新随机`tcm_vib48_offline_*_test`库保留。读现有dist，不重复build。
- Windows安全原生探针：`./backend/scripts/check_windows_credentials.ps1`；唯一随机target并清理。
- 真实模型：`check_knowledge_api_live.py --execute`，仅允许既有`tcm_vib60_live_test`或本次`tcm_vib48_cloud_acceptance_test`，guard仍验证隔离store/路由/密钥开关；实际调用需要明确授权，不默认重跑。当前库已有完整结果，重跑需考虑固定幂等键，不能覆盖后伪装首验。
- 真实研究浏览器：`node frontend/scripts/check_research_e2e.mjs`，需测试库当前head和回环relay与`research-api`别名可用；完成后关闭relay并撤除专用网络。
