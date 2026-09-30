# VIB-46 知识候选增量验证（2026-09-30）

承接 `ab755a2`，保留已有 VIB-45 等改动；工程代码已归入 `86c6299`，完整后端167 passed、0 skipped。VIB-46 **本地实施中，未达到完整验收**；Linear 回读 In Progress，VIB-40 已为 Done，VIB-45 本地完成但远端具体验收同步仍待授权。没有模型调用或部署。下列“已交付入口/实际验证/复现”为前一轮抽取增量记录；最新方剂逐字段和术语裁定接续结果见后节。历史段落的“未提交”和HEAD描述保留当时验证背景，当前工程提交以本段为准。

## 已交付入口

- `knowledge_extraction.py::extract_source_candidates`、CLI `extract-knowledge <source_revision_id>`：仅受理 SEGMENTED 来源修订。本地规则 `local-exact-terms/v2` 查找工程种子词表中的原词，生成 Evidence、EntityMention、Concept 和 Relation 待审草稿。
- `trace-extraction <extraction_id>`：冻结原词、Python Unicode 字符区间（左闭右开）、片段修订 ID/哈希/结构定位、精确 EvidenceRevision 及关系完整原句。引文沿既有链回到不可替换的来源修订。页 1 仍是逻辑页，不是书籍实体页。
- `0024_knowledge_extraction`：同一来源修订与规则版本唯一。来源修订行锁串行化并发重放；批次、既有草稿服务和哈希链审计共用事务，任何异常整体回滚；数据库触发器拒绝修改或删除批次。批次 manifest 的 DRAFT 表示创建时状态，当前审核状态以知识对象和 HumanReview 为准。
- 只处理最外层可引用片段，保留整段条件上下文，避免段落和句子子片段重复抽取。概念只在同一批次内按原词和类型归并，并关联每次出现位置和对应 Evidence；使用 SourceRevision.metadata_snapshot 的时代/流派，不读后来变化的 SourceDocument 字段。未知字段保持 null，不做跨来源归并、繁简转换或历史同义词判定。
- 关系仅抽取同句中明确命名的 `NAMED_AS`，保存完整原句；没有推断临床治疗关系。术语/关系都是待专家核对的候选；词表覆盖、语义召回和准确率未评测。
- `create-formula` 新增 `--method`、`--dosage-form`、`--preparation`、`--cautions` 和完整 `--ingredient-spec` JSON 输入；可登记原剂量/规范值/单位/比例/角色/炮制/药物引用。使用原 `--formula-id` 追加新 DRAFT，旧修订与冻结快照保留；原 Evidence 未审核时不能批准方剂。

## 实际验证

- 既有只读 Linux 容器 `tcm-vib54-py`，显式当前 `PYTHONPATH`，`LOCAL_ONLY`，禁止写缓存；未运行 Windows 原生 Python/uv/Alembic，未触发应用程序错误弹窗。
- 新建独立 `tcm_vib46_final_test`：空库升级至 0024，0024→0023→0024 往返及两次 `alembic check` 无差异；专项 **16 passed、0 skipped**。
- 新建独立 `tcm_vib46_full_test`：相同空库及迁移验证；完整后端 **80 passed、0 skipped**（48.69 秒），一条既有 Starlette/httpx 弃用提示。不是前端或浏览器验收。
- 实际固定 29 条《傷寒論》原文：段落与句子不重复，实体字符区间精确，每个关系原句可回原文；原词保持唯一 PREFERRED，不补造 ALIAS；改变 SourceDocument 元数据后候选仍保留冻结“漢”及未知流派；不创建 FormulaRevision；候选和未审核 Evidence 排除于知识快照，活动指针不变。实际语料未进行 APPROVE。
- 合成样本：故障回滚所有草稿与审计后可重试；两个线程重放同一批次只产生一份记录；不同来源/时代/流派不混合；批次不可变；未分段及不存在来源拒绝。方剂 CLI 验证完整输入、未知规范剂量、Evidence 先审门禁、已审核旧修订入快照、新修订仍 DRAFT。合成样本的 APPROVE 不代表实际语料专家审核。
- 完整后端 Ruff `src tests migrations` 及复现脚本通过（`--no-cache --ignore EXE002`，仅忽略 Windows 绑定挂载权限误报）；`git diff --check` 通过。
- 首次专项 **13 passed、2 failed**：抽取同时处理了段落和句子子片段，29 条被计为 80 个候选范围，单句关系重复生成。改为最外层可引用片段，持久化规则升为 v2；旧 v1 失败数据保留于 `tcm_vib46_test`，不重写、不删除。随后加入方剂 CLI 用例，在新库最终专项16条及完整80条均通过。
- 没有修改 `docker-api-1`、业务库或预览库，也没有自动把它们升级到 0024；默认 API schema 检查在预览库未迁移时可能提示旧版。本轮不将预览健康当作验证证据。

## 复现

脚本只接受 `tcm_*_test` 名称，不删除数据库；沿用容器现有连接凭据，仅替换数据库名称且不打印连接串。有冻结批次的测试库不会回退迁移，应使用新名称复验往返。

```powershell
docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib46_final_test
docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib46_recheck_test --full-suite
docker exec -w /workspace/backend tcm-vib54-py ruff check --no-cache --ignore EXE002 src tests migrations scripts/verify_knowledge_extraction.py
```

## 方剂逐字段溯源接续（2026-09-30）

本次增量在上述未提交工作区上实施，HEAD 仍为 `ab755a2`。新增 `0025_formula_provenance`、逐字段来源服务和 `--field-sources`；最终验证结果见本节末尾。

- 引用键为修订字段名或 `ingredients.<从0开始的序号>.<字段名>`。每条记录绑定精确 EvidenceRevision、TextSegmentRevision、Unicode 字符区间、字段值快照和原文；规范剂量、比例、角色、药物绑定、时代/流派必须有解释依据，其他字段若与引用文本不同也需依据。未知 null 保持未知。
- 可以保存部分引用的 DRAFT；已提供的无效引用在创建时拒绝。APPROVE 在同一事务内检查所有非 null 字段引用完整，失败不写 HumanReview 或审核审计。新方剂在快照创建、版本激活时重新校验。
- 已有修订标记 `provenance_version=0`，新增为 1。旧已审核修订沿原链保留，不宣称它们已达到逐字段标准；旧待审草稿必须追加带完整引用的新修订。发布内容与来源不可原位更改，校订追加 DRAFT。
- 本轮合成文本只用于工程门禁，不代替真实方剂、剂量标准或专家意见；真实 C01 仍不生成缺失药味剂量的方剂。
- `verify_knowledge_extraction.py` 在新库先升 0024、插入合成旧草稿，再升 0025、回退 0023、重升 0025；断言旧字段/状态不变、版本为 0、无补造引用。该无药味/证据的合成旧 DRAFT 仅是迁移探针，不参与知识快照。旧审核兼容用例的模拟行及临时触发器状态全部在外层事务回滚。
- 首次新库 `tcm_vib46_fields_full_test` 完整回归 **110 passed、2 failed、0 skipped**（62.76 秒）：方剂专项均通过；两条既有报告导出断言只接受单行原文。多片段引文正确输出成逐行 `> ` 的 Markdown 引用块，最小两行复现证实原文和换行均保留。修正两条测试断言以验证完整引用块，DOCX 原文检查保留；未修改生产报告渲染器或篡改单段语料。失败库保留。
- 第二个新库 `tcm_vib46_fields_final_test` 加入父修订/药味/证据关联冻结专项，完整回归 **112 passed、1 failed、0 skipped**（72.50 秒）：Markdown 断言已通过；DOCX 文本提取只遍历 `w:t`，忽略实际保存换行的 `w:br`，导致多行引文断言失败。提取器保留换行节点后，该导出用例定向 **1 passed**（3.02 秒）；生产 DOCX 渲染器保持原实现。该库也保留。
- 最终新库 `tcm_vib46_fields_verified_test` 完整后端 **113 passed、0 skipped**（65.73 秒，1 条既有 Starlette/httpx 弃用提示），含 **33 条新增方剂专项**和实际29条候选/既有知识发布及研究 API/导出回归。旧数据迁移保留、0025→0023→0025 往返和两次 `alembic check` 无差异；完整后端及脚本 Ruff 通过，`git diff --check` 通过。先前失败库和最终测试数据全部保留。
- 新迁移已直接验过引用、父修订、药味、证据关联的冻结（包括移动到其它修订）、禁止版本降级和审核后新增药味；无快照时服务仍允许明确 REJECT，已批准内容继续冻结。新快照和版本激活均复验逐字段来源，旧版0已审核对象保持兼容。未更新预览库/API，未重跑前端/浏览器或真实云模型。

## 完整方剂候选接续（2026-09-30）

- 本轮回读 Linear VIB-46 仍 In Progress；`initial_corpus.json` 仅有 C01 非方剂文本，FORMULA_TEXT 仍明确排除，C02 未冻结。新增文本均明确标为合成，不改真实语料，不自动 APPROVE 真实候选。
- 新 `knowledge_formula_extraction.py::scan_formula_candidates` 和 `local-exact-terms/v4` 只接受行首明确“方名方”标题、完整药味列表以及“右/上×味”计数吻合的煎服段。方名须以湯/汤/散/丸/飲/饮/方结尾；药味可用分号、顿号或换行分隔，每项须有明确原剂量。支持常见正整数及尾半、兩/两/錢/钱/分/升/合/枚/斤/銖/铢原单位、括号炮制原文；不换算、不补现代药物绑定或历史同义词。
- 共享剂量、缺失/模糊剂量、替代药物、数量不吻合、重复药名、条件/否定标题、混合/畸形数字及未解析列表文字均跳过整方；不丢掉未知药味后创建部分方剂。煎服段须有明确水制备前缀和服用文字，原段含条件/禁忌时完整保留，不另行推定剂型、治法、主治或禁忌字段。仅为窄规则工程覆盖，尚未验证真实排版的召回。
- 同源最外层可引用片段按连续同父节点/同类型分组，跨结构节点不拼方。字段记录精确 Unicode 区间、片段修订及哈希；多段煎服以原顺序换行连接，引用附连接依据。批次时代/流派保留冻结源值；方剂对应字段保持 null，源元数据不代替字段论据。
- `create_formula` 增加内部 `_session`，抽取复用已有逐字段验证，Formula/Evidence/实体/关系/批次及审计原子提交。新增 manifest `formula_count`/`formulas`（精确方剂修订、字段、药味、引用），trace 汇集方剂 Evidence；同源同规则并发重放仅创建一份，旧 v2/v3 批次及旧 trace 兼容保留。没有新 schema 迁移。
- 新增24条纯规则、7条数据库集成，涵盖 Unicode 原文/未知字段、跨段完整引用、先审 Evidence、草稿快照排除/批准后入快照、字段/批次审计失败整体回滚、并发重放、v3 保留、跨来源身份隔离、CLI 和跨章节拒绝；实际29条 C01 断言仍为0方剂。
- 首库 `tcm_vib46_formula_candidates_initial_test` 专项 **97 passed、1 failed、0 skipped**（37.58秒）：条件前缀“若用”误收进标题。修正标题词义门禁，补否定/条件与非法数字用例。
- 首个完整库 `tcm_vib46_formula_candidates_full_test` **163 passed、1 failed、0 skipped**（85.78秒）：旧 `test_report_distinguishes_unsupported_and_conditional_claims` 依赖所选来源无历史元数据。扩大已审夹具池后历史角色可正常产生第三条 Claim；明确该两类别专项的假模型对历史角色弃答，不改变生产研究代码或放宽计数断言。
- 最终新库 `tcm_vib46_formula_candidates_verified_test` 完整后端 **167 passed、0 skipped**（87.69秒）。空库升0024、旧方剂/概念探针保留后升0026、0026→0023→0026往返及两次 `alembic check` 无差异。Ruff（无缓存，仅忽略Windows挂载权限 EXE002）与 diff检查通过。仅既有 Starlette/httpx 与 Alembic 配置弃用提示。以上3库及既有失败数据保留。
- 未改业务/预览库、API 或模型默认路由，未执行 Windows 原生 Python、前端/浏览器或真实云调用。用户提出8B是否升级，已核对 README 的 `Qwen/Qwen3-8B` 云端联调及超原文解释记录；建议更强生成模型对照评测，但本轮未训练/微调、切换或验证模型语义质量，正式资格仍归 VIB-68。

## 未完成项与下一步

1. **完整方剂候选工程已补齐，真实验收仍待补**：v4 规则与同事务逐字段草稿已实现并通过167条完整后端回归，详见末节。先检查 `fixtures/initial_corpus.json` 中 C02 冻结状态；来源冻结后按真实排版逐例补定位/保守规则和专项校订，不从 C01 方名推造药味。未冻结时可推进 VIB-48 本地结构/关系检索准备；VIB-46 整体验收保持未完成。
2. 术语歧义与历史同义词工程方案已交付，但种子词表和合成人工裁定不等于正式术语标准；实际歧义、历史语境和同义词仍需术语专家核对，没有语义质量评测或自动字符串合并。
3. 真实完整方剂验收需负责人“测试人员”冻结 C02 同章方剂摘录、来源修订/权利说明/哈希并安排专项校订。C01 有方名及条文，但不具备完整药味剂量和煎服文本，不能为缺失字段补造真值。v4 合成工程测试不等于真实语料验收。
4. VIB-46 保持实施中；本地清单与矩阵记录当前证据，Linear 本轮已同步136条完整回归的工程结论（评论 `2ebeb7c4-1ec0-490c-832c-e2ca71151906`），保持 In Progress。此前113条结论亦保留；VIB-45 先前具体验收评论被自动审批拒绝，未获对应明确授权前不重复外发。

## 术语歧义与历史同义词接续（2026-09-30）

- `local-exact-terms/v3` 支持一个原词对应多种类型，在同一字符范围生成独立概念/提及；按原词、类型、冻结时代和流派保留身份，跨来源批次不归并。多类型歧义标为 `AMBIGUOUS_DRAFT`，概念有不可降级的 `requires_term_resolution` 标记，直接 APPROVE 拒绝；命名关系跳过有歧义端点。默认工程词表未扩充临床语义标签，旧 v2 批次不重写。
- 新 `knowledge_terms.py::adjudicate_term` / CLI `adjudicate-term` 记录 NORMALIZE、HISTORICAL_SYNONYM、DISTINCT 或 UNRESOLVED。必须显式提供校订者、解释依据和精确 Evidence/片段修订及 Unicode 引用范围。可选择部分原提及来区分同原词的不同语境；生成新的 DRAFT 概念和复制提及，原身份/位置/审核状态保留。时代/流派沿用原概念，包括 null。
- 历史同义词必须明确指定已审核的对照概念，并引用对照 Evidence 的精确范围。新概念采用其名称/类型，但保留独立身份和原时代/流派；保存对照名称/类型/时代/流派快照，原词以 scoped HISTORICAL 词形保存。原提及、解释引文和对照引文全部进入新概念 Evidence 链；没有全局别名扩展、字符串相似度合并或审核自动通过。
- `trace-knowledge concept` 返回词形范围、解释、裁定者、复制与原提及、精确原文/哈希和对照快照。APPROVE 先审所引 Evidence，再验证裁定；UNRESOLVED 不能批准，即使绕过服务改状态，知识快照和版本激活仍拒绝。已发布校订在审核后使用既有 `supersede_reviewed_object` 谱系，新版选择新概念，旧版保留旧行，可切回原版本；关系引用仍须另行校订。
- `0026_term_resolution` 的数据库触发器冻结裁定、被裁定来源及新概念内容、词形、证据关联和提及；已审核或进入任意知识版本的概念内容/关联同样冻结，禁止旧提及重绑及位置改写。状态仍由审核服务单独处理。后续裁定继续追加 DRAFT，不改原记录；存在裁定或歧义标记数据时拒绝迁移降级。
- 首轮新独立库 `tcm_vib46_terms_initial_test` 迁移往返、模型检查通过，候选/方剂/知识发布/术语专项 **70 passed、0 skipped**（34.47 秒）。其后补强历史同义词精确对照证据，并增加版本激活复验和有数据降级拒绝用例。
- 最终新独立库 `tcm_vib46_terms_full_test` 完整后端 **136 passed、0 skipped**（76.36 秒），比此前113条新增 **22 条术语集成专项 + 1 条多类型扫描测试**。覆盖歧义候选门禁、选择提及、Unicode 原词位置、未知保留、跨时代/流派历史同义词、无效来源和审计故障整体回滚、并发人工提案、不可变内容/关联、已发布替换/激活/历史切回和 CLI。实际固定29条原文候选回归仍通过，实际语料未 APPROVE。
- 新库先升0024，插入合成旧方剂/旧概念 DRAFT 探针，再升0026、0026→0023→0026往返；两次 `alembic check` 无差异。旧概念名称、类型、时代/流派 null 和 DRAFT 保持，标记为 false且无补造裁定；旧方剂版本0和字段保持。完整后端及脚本 Ruff 通过；仅既有 Starlette/httpx 及 Alembic 旧配置分隔符弃用提示。未更新预览/业务库或 API，未跑前端/浏览器/真实云模型。
