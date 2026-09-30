# 开发交接

## 1 当前基线与工作区

- 2026-09-30，分支 codex/evidence-audit，工程基线 86c6299（VIB-45/46 语料/候选/溯源/裁定，起点ab755a2）；接续文档另行提交，最新HEAD以git log核对。近期增量均已整理为本地Git提交，未推送或部署。
- 86c6299包含26个文件，3275行新增/44行删除：parsing/fixture、extraction/0024、formula provenance/0025、term resolution/0026、方剂规则、CLI/审核/模型、测试与复现脚本及README。
- 已有改动全部保留并纳入提交；AGENTS.md、交接及历史目录随文档提交。旧验证中的“未提交”为当时状态，当前代码以86c6299为准；上一首页归档 docs/handoff-history/2026-09-30-before-formula-candidate-extraction.md。
- 本轮提交前复查完整后端/脚本Ruff与暂存diff通过，代码与此前167条回归通过版本一致，未重复运行数据库回归。提交后工作区应干净，实际结果以git status --short核对。
- 范围 V1 知识底座与理论研究。VIB-63/49/60/61 本地及 Linear Done；VIB-46 In Progress，VIB-40 Done；VIB-45 本地完成，旧具体验收外发仍待授权；VIB-58 Windows 密钥实机待安全环境。

## 2 VIB-46 当前交付与实际验证

- extract_source_candidates 使用 local-exact-terms/v4，保留 v2/v3 冻结批次。仅 SEGMENTED 精确来源及最外层片段；原词多类型、冻结时代/流派和独立身份保留，歧义不可直接批准，不跨来源猜繁简/历史同义词。
- v4 新增完整方剂窄规则：行首明确“方名方”标题、全部原药味/明确剂量、括号炮制及数量吻合的“右/上×味”煎服段；同父节点/同类型连续片段可跨段，跨章节拒绝。共享/模糊剂量、替代/缺失药味、条件/否定标题、重复药名和未解析列表整方跳过。
- 原单位字符和剂量逐字保存，不换算；药物绑定/规范量/比例/角色等未知保持 null。完整煎服原文保留，跨段换行连接有引用依据，不推定剂型/禁忌/主治或方剂时代/流派；来源时代/流派仍在批次和精确源链。
- create_formula 内部 _session 复用逐字段来源验证，与方剂/Evidence/提及/关系/批次/审计同事务。manifest 返回 formula_count/formulas 和精确引用；trace 汇集方剂 Evidence，旧 manifest 兼容。全部先 DRAFT，Evidence 先审、方剂后审、审核后才入快照；并发重放仅创建一份。
- 既有 0025 字段/药味序号来源、Unicode区间、值/原文/哈希/解释及审核/快照/激活复验保持；旧已审核版本0沿原链，旧待审须追加版本1。新内容/药味/证据关联冻结，校订追加 DRAFT。
- 既有 knowledge_terms.py/0026 显式人工 NORMALIZE/HISTORICAL_SYNONYM/DISTINCT/UNRESOLVED，复制选定提及、新 DRAFT、原身份保留；历史同义词需已审对照及其精确引用，时代/流派沿原概念。未解决不能批准，快照/激活复验，裁定/来源/内容/词形/关联冻结；已发布替换/历史切回复用原谱系，关系须另校订。
- 最终新独立库 tcm_vib46_formula_candidates_verified_test 完整后端 **167 passed、0 skipped**（87.69秒），比前136条新增24条方剂规则+7条集成。含真实29条原文仍为0方剂、事务回滚、并发重放、跨段精确引用、未知保留、审核/快照、CLI、跨章节/来源及旧v3保留。
- 空库升0024→合成旧方剂/概念探针→0026，0026→0023→0026往返，两次 alembic check 无差异；旧内容/状态/null及方剂版本0保留，无补造裁定/引用。完整后端与脚本 Ruff、git diff --check通过；仅既有 Starlette/httpx 和 Alembic 配置弃用提示。
- 首库 tcm_vib46_formula_candidates_initial_test 专项97过1失（37.58秒）：条件“若用”前缀误识别标题，修复并补否定/条件/非法数字用例。首个完整库 tcm_vib46_formula_candidates_full_test 163过1失（85.78秒）：旧报告测试依赖选中来源无历史元数据，扩大已审夹具池后多出历史 Claim；明确该两类别专项的假模型历史角色弃答，生产研究代码保持。3座库和所有旧失败数据均保留。
- 真实语料未 APPROVE；合成文本/裁定不代表正式方剂、术语标准、专家复核或模型质量。C02未冻结。未改业务/预览库/API、未跑前端/浏览器/真实云模型，无训练或微调。
- 详情 docs/VIB46_KNOWLEDGE_CANDIDATES_ACCEPTANCE.md；Linear工程结论已同步（评论 9f5bf2e5-3311-4db2-9d87-fce24b940a5b），保持 In Progress。VIB-45旧具体验收曾被自动审批拒绝，未经对应授权不重复外发。

## 3 用户最新模型问题

- 用户问“8B能调教好吗，要不要换高级的”。已确认 README 的云端 Qwen/Qwen3-8B 联调路由及曾产生超原文解释的记录，不能将程序测试当作模型资格。
- 建议升级核心研究生成模型并做相同专家样本对照，8B可保留作低成本基线；官方硅基流动模型列表已核对现售强模型候选。没有切换配置或发起付费调用，也没有获得具体模型/预算授权。
- 正式资格仍归 VIB-68：无支持断言、引文忠实度、纠错/拒答、成本和时延同测。更强模型亦须专家样本验证，不承诺通过提示词把8B变成可靠专家。

## 4 下一条具体操作

- 先看 backend/fixtures/initial_corpus.json 是否新增负责人“测试人员”冻结的 C02（同章方剂固定摘录、来源/权利/哈希、专家复核安排）。若已有，按真实排版补保守规则和精确字段定位/校订，工程规则入口 knowledge_formula_extraction.py、knowledge_extraction.py 和新集成测试。
- C02仍未冻结时，不重跑合成验收或补造真实真值；直接承接 **VIB-48 本地 Structured/Relation 检索准备**。只读 backlog VIB-48及直接依赖、Linear最新状态，入口 backend/src/tcm_platform/retrieval.py、retrieval_benchmark.py、research_service.py及知识版本/关系模型。
- 先实现冻结KV/Scope内已发布概念/关系/方剂的保守结构候选→精确 Published EvidenceRevision，禁止扩大来源/回退未审草稿；用合成已审夹具验证版本与来源过滤。VIB-46未整体验收不阻止此准备，但不能提前宣告VIB-48完成；别名扩展须保持裁定范围。模型升级选择可并行准备无外发评测计划，实际付费比较需明确授权。
- 实际术语/方剂专家核对待补，古病案待VIB-47，真实Golden Set待VIB-68。

## 5 运行限制与复现

- Windows原生Python/uv/Alembic曾触发错误弹窗，禁止换入口或提权重试。本轮仅既有Linux容器tcm-vib54-py；Docker管道当前可用，tcm-vib54-py与tcm-handoff-test运行。
- 复现：docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib46_formula_candidates_recheck_test --full-suite。仅接受tcm_*_test、LOCAL_ONLY、不打印凭据/不删除旧库；有候选/字段/裁定数据不降级，迁移往返用新库。
- backend只读挂载：pytest禁缓存，PYTHONDONTWRITEBYTECODE=1；Ruff --no-cache --ignore EXE002（Windows挂载权限误报）。skip不等于通过。
- 不启动/修改docker-api-1或tcm_preview_shanghanlun；预览库仍未升0024/0025/0026，原API unhealthy本轮未修复/验收。tcm-vib63-forward仍停止。
