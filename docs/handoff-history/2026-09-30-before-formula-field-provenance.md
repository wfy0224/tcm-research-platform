# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 `codex/evidence-audit`，HEAD `ab755a2`（VIB-63 真实隔离 E2E）；VIB-45 与本轮 VIB-46 增量均未提交。
- 本轮修改 `README.md`、`backend/src/tcm_platform/{cli,knowledge_service,models}.py`，新增 `knowledge_extraction.py`、迁移 `0024_knowledge_extraction.py`、`scripts/verify_knowledge_extraction.py`、两个 extraction 测试文件与 `docs/VIB46_KNOWLEDGE_CANDIDATES_ACCEPTANCE.md`；原位更新 backlog、追踪矩阵和本文件。
- 启动时已有 VIB-45 的 parsing/fixture/测试/验收文档，以及 backlog、追踪矩阵、`VIB63_RESEARCH_WORKSPACE_ACCEPTANCE.md` 改动，均保留；原有未跟踪 `AGENTS.md`、本文件、历史目录保留。上一首页归档 `docs/handoff-history/2026-09-30-before-vib46.md`。
- 当前范围 V1 知识底座与理论研究。VIB-63/49/60/61 本地及 Linear Done；VIB-45 本地验收完成，Linear 同步待具体验收内容授权；VIB-46 本地实施中，Linear 本轮回读 Backlog，依赖 VIB-40 Done。本轮只回读 Linear，没有外发；VIB-58 仍待 Windows Credential Manager 实机验证。

## 2 VIB-46 当前交付与实际验证

- `knowledge_extraction.py::extract_source_candidates` 和 CLI `extract-knowledge`/`trace-extraction`：只受理已 SEGMENTED 精确来源修订，使用 `local-exact-terms/v2` 工程种子词表，保留原词字符位置及条件原句；生成 Evidence/EntityMention/Concept/明确命名 NAMED_AS Relation 草稿，保留冻结时代/流派。只在同批次归并同类型原词，不猜测繁简或历史同义词、不跨来源合并。
- 仅抽取最外层可引用片段，避免段落与句子重复；`0024_knowledge_extraction` 固定来源修订+规则版本唯一、行锁串行重放，批次/草稿/审计共用事务，失败全部回滚，批次 UPDATE/DELETE 被数据库拒绝。manifest DRAFT 表示创建时状态，当前审核以业务行和 HumanReview 为准。
- 方剂 CLI 暴露完整 IngredientSpec JSON 和 method/dosage_form/preparation/cautions；原剂量与规范值分别保留、未知 null，不换算古代单位；原 formula-id 追加新 DRAFT，旧修订不动。当前方剂字段只引用整段 FormulaEvidence，逐字段位置/规范化依据尚未完成。
- 新独立 `tcm_vib46_final_test` 空库升级0024、0024→0023→0024及 `alembic check` 无差异，专项 **16 passed、0 skipped**；新独立 `tcm_vib46_full_test` 同样迁移验证，完整后端 **80 passed、0 skipped**（48.69秒，1条既有 Starlette/httpx 弃用提示）。完整后端 Ruff与脚本通过，`git diff --check`通过。
- 真实固定29条原文候选位置/原句、元数据冻结、草稿不入快照、活动指针不变和未补造完整方剂通过；只审核独立合成测试文本/方剂，未对实际语料 APPROVE，不代表专家校订或模型质量。无真实云调用，未重跑前端/浏览器，未修改业务/预览库或 API。
- 首次专项13过2失败：同时抽取段落和句子导致29条计为80范围、关系重复；修正最外层范围并升持久化规则v2，加入方剂CLI用例后在新库16条和全后端80条通过。失败v1数据保留于 `tcm_vib46_test`，不删除或重写。
- 复现命令与全部边界见 `docs/VIB46_KNOWLEDGE_CANDIDATES_ACCEPTANCE.md`；VIB-46 **未完成，不标Done**。

## 3 下一条具体操作

- 继续 **VIB-46 方剂逐字段溯源与审核校验**。先读验收文档“未完成项”及 backlog VIB-46，无需回读历史归档。入口 `knowledge_service.py::create_formula/trace_knowledge`、`knowledge_publish.py::review_object`、`FormulaRevision/FormulaIngredient`、CLI 和 `test_knowledge_extraction_integration.py`。
- 为修订字段和 ingredient sequence/字段保存精确片段修订及字符区间；检查片段属于所引 Evidence，规范剂量/角色等解释保存依据，缺失/越界引用不得通过审核；未知保持null，旧已发布修订不原位重写。先用合成方剂覆盖门禁和追加校订，再补真实来源验收。
- 术语歧义/历史同义词的可校订方案仍待补，现有种子词表不是正式术语标准，不按字符串相似度自动合并。
- 真实完整方剂候选与专项校订还需负责人“测试人员”冻结 C02 同章方剂摘录、来源/权利说明/哈希并安排复核；C01有方名条文而无完整药味剂量、煎服，不能补造真值。古病案另由VIB-47选定，专家Golden Set由VIB-68补齐。
- Linear待同步：VIB-46当前实施进度和简短验证结论；VIB-45先前具体验收评论被自动审批拒绝，内容包括纯文本范围/负责人、PDF逐页阻塞、20 passed及专家校订边界。对应明确授权前不重复外发。保持本地可接续记录。

## 4 运行限制与复现入口

- Windows原生Python/uv/Alembic曾触发错误弹窗，禁止换入口或提权重试。后端仅用既有Linux容器 `tcm-vib54-py`，显式 `PYTHONPATH=/workspace/backend/src`；Docker读取/执行需要沙箱权限。`tcm-vib54-py`、`tcm-handoff-test`已运行。
- 复现：`docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib46_recheck_test --full-suite`。只接受 `tcm_*_test`，LOCAL_ONLY且不打印凭据；新库验迁移往返，含冻结批次的旧库跳过回退，skip不等于通过。
- backend挂载只读：pytest禁缓存、PYTHONDONTWRITEBYTECODE=1；Ruff `--no-cache --ignore EXE002`（Windows绑定挂载权限误报）。不使用默认 `tcm_vib54_test`；新测试库/失败数据保留，不清除旧队列。
- 不启动或修改 `docker-api-1`、`tcm_preview_shanghanlun`。预览库仍未升级0024，新代码下schema检查可能提示旧版；本轮未验证预览健康。既有临时浏览器/API已退出，`tcm-vib63-forward`停止。