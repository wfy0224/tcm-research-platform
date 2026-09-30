# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 `codex/evidence-audit`，HEAD `ab755a2`（VIB-63 真实隔离 E2E）；VIB-45/46 增量均未提交，未创建提交或部署。
- 本轮新增 `knowledge_formula_provenance.py`、迁移 `0025_formula_provenance.py`、`test_formula_provenance_integration.py`；修改 models/knowledge_service/knowledge_publish/CLI、候选复现脚本、候选集成测试和研究导出测试，以及 README/backlog/追踪矩阵/验收文档。
- 启动时已有 VIB-45 parsing/fixture/测试/验收与 VIB-46 extraction/0024 等未提交改动，均保留；原有 AGENTS.md、交接与历史目录保留。上一首页归档 `docs/handoff-history/2026-09-30-before-formula-field-provenance.md`。
- 当前范围 V1 知识底座与理论研究。VIB-63/49/60/61 本地及 Linear Done；VIB-45 本地验收完成，Linear 回读 Todo，旧具体验收同步仍待授权；VIB-46 本地实施中，本轮已同步 Linear In Progress，VIB-40 回读 Done。VIB-58 仍待 Windows 密钥实机验证。

## 2 VIB-46 当前交付与实际验证

- `extract_source_candidates` 使用 `local-exact-terms/v2`：仅 SEGMENTED 精确来源修订和最外层可引用片段，生成原词位置、条件原句、冻结时代/流派的 Evidence/EntityMention/Concept/明确命名 NAMED_AS 草稿；同批次同类型原词归并，不猜繁简/历史同义词、不跨来源合并。0024 批次/草稿/审计共用事务、行锁串行幂等，manifest 不可变。
- 新 `FormulaFieldSource` 保存修订字段或 `ingredients.<从0起序号>.<字段>`、精确 Evidence/片段修订、Unicode 左闭右开字符区间、字段值/原文/片段哈希快照、解释依据。必须属于所引 Evidence；无值不能登记引用，规范剂量/比例/角色/药物绑定/时代/流派需依据，原文变换亦需依据。相邻原文 span 可无损拼接，多片段解释保存多条依据；未知保持 null，不换算古代单位。
- CLI `create-formula --field-sources <JSON文件>` 原子登记，有效但不完整的 DRAFT 可保存；无效引用整笔回滚。APPROVE 先审 Evidence，再完整检查每个非 null 字段，失败不写 HumanReview/审核审计；快照与激活复验新版来源。`trace_knowledge` 返回逐字段引用和 provenance_version。
- 0025 将旧行标为版本0、新行默认1，禁止原位改版本；旧已审核修订保留原链，旧待审需追加新版本1。引用不可改删，父行锁阻止审核/快照后追加；已审核或进入任意 KV 的修订内容/药味/证据关联不可改删或移到其它修订，状态单独变更仍经审核服务处理。校订追加 DRAFT，旧版本不重写；有新版数据时迁移降级拒绝。
- 最终新库 `tcm_vib46_fields_verified_test` 完整后端 **113 passed、0 skipped**（65.73秒），含字段完整性、33条新增方剂专项、实际29条候选、既有研究/API/导出回归；迁移往返/旧数据保留/模型检查/Ruff/diff均通过。方剂字段工程增量完成，整个 VIB-46 仍在实施。
- 本轮首库 `tcm_vib46_fields_full_test` **110 passed、2 failed、0 skipped**（62.76秒），第二库 `tcm_vib46_fields_final_test` **112 passed、1 failed、0 skipped**（72.50秒）。新增方剂用例均通过；既有导出断言假定单行：Markdown 正确保留逐行引用标记，DOCX 正确保留 w:br 换行。只修测试的引用块比较和 XML 文本提取，生产渲染器不改；DOCX 导出定向 **1 passed**。两个失败库保留。
- 三个新库的空库升0024→合成旧草稿→0025、0025→0023→0025、两次 `alembic check` 均通过。旧草稿字段/状态保持、版本0且无补造引用；合成迁移探针 DRAFT 不参与快照。完整后端及脚本 Ruff 通过，diff 检查通过；只有既有 Starlette/httpx 弃用提示。
- 此前完整后端80条/专项16条属于上轮抽取验证；真实固定29条候选定位/冻结/草稿快照排除已在本轮全套重跑通过。实际语料不 APPROVE，合成文本不代表专家校订、正式剂量标准或模型质量。未跑前端/浏览器，无真实云调用，未改业务/预览库或 API。
- 详细边界与复现见 `docs/VIB46_KNOWLEDGE_CANDIDATES_ACCEPTANCE.md`；VIB-46 未完成，不标 Done。

## 3 下一条具体操作

- 继续 **VIB-46 术语歧义/历史同义词的可校订方案**。先读 backlog VIB-46 及验收文档未完成项，不回读历史。入口 `knowledge_extraction.py`、`ConceptTerm/EntityMention`、`knowledge_publish.py::supersede_reviewed_object` 与候选集成测试。
- 同一原词的不同类型/时代/流派保留独立候选身份、原词和精确提及；实现显式人工裁定及追加校订，复用已审核对象替换谱系，禁止按字符串相似度自动合并。工程种子词表不等于正式术语标准。
- 真实完整方剂候选和专项校订仍需负责人“测试人员”冻结 C02 同章方剂摘录、来源/权利说明/哈希并安排专家复核。C01 只有方名条文而无完整药味剂量和煎服，不能补造真值。古病案由 VIB-47 选定、Golden Set由 VIB-68 补齐。
- Linear：VIB-46 In Progress 与113条完整验证简短结论已同步（评论 `2441adf1-bde8-4575-ac6e-982a3e9aa1ad`）；VIB-45 先前具体验收评论被自动审批拒绝，未获对应明确授权前不重复外发。保留本地可接续记录。

## 4 运行限制与复现入口

- Windows 原生 Python/uv/Alembic 曾触发应用程序错误弹窗，禁止换入口或提权重试。本轮只用既有 Linux 容器 `tcm-vib54-py`；Docker 部分管道执行需要沙箱权限。`tcm-vib54-py`、`tcm-handoff-test` 已运行。
- 复现：`docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib46_fields_recheck_test --full-suite`。只接受 `tcm_*_test`、LOCAL_ONLY、不打印凭据、不删除旧库；已有抽取/新版方剂数据跳过降级，skip不等于通过。
- backend 只读挂载：pytest 禁缓存，PYTHONDONTWRITEBYTECODE=1；Ruff `--no-cache --ignore EXE002`（Windows绑定挂载权限误报）。新库用作迁移往返，旧队列/失败数据保留。
- 不启动或修改 `docker-api-1`、`tcm_preview_shanghanlun`。预览库仍未升0024/0025；新代码可能提示旧schema。`docker ps` 回读 API 原有 unhealthy，本轮没有修复或验证预览健康；`tcm-vib63-forward` 停止。
