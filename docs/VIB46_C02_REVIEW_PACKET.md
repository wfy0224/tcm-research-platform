# VIB-46 C02 专家审阅材料

编制日期：2026-10-01。**C02 为 PROPOSED，未冻结，实际专家未签署；VIB-46 仍未完成**。本文是待填工作表，不创建 HumanReview 或发布知识。编制日期不是冻结或签署日期。

既有工程见 [VIB-46验收](VIB46_KNOWLEDGE_CANDIDATES_ACCEPTANCE.md)；synthetic/自动APPROVE非专家审核。[C01清单](../backend/fixtures/initial_corpus.json) 不含完整方剂，不得凭方名补造药味、剂量或煎服法。

## 负责人选择与来源冻结

来源：[PROPOSED清单](../backend/fixtures/c02_candidate/manifest.json)、[说明](../backend/fixtures/c02_candidate/README.md)、[权利通知](../backend/fixtures/c02_candidate/rights_notice.txt)、[固定HTML](../backend/fixtures/c02_candidate/upstream_revision_2607901.html)。候选：[桂枝湯](../backend/fixtures/c02_candidate/guizhi_tang.txt)、[桂枝加葛根湯](../backend/fixtures/c02_candidate/guizhi_jia_ge_gen_tang.txt)、[桂枝加附子湯](../backend/fixtures/c02_candidate/guizhi_jia_fu_zi_tang.txt)；范围待选。

负责人角色“测试人员”不等于实际专家身份。

| 决定项 | 待填写证据 | 状态 |
| --- | --- | --- |
| 数据负责人 | 实际人员/身份、确认记录 | 待填 |
| C02范围 | 方剂清单、完整原文及相邻条件上下文 | 待选择 |
| 对照底本 | 书名、版本、卷章/实体页或图像；未知保留 | 待选择 |
| 专家安排 | 原文、方剂/剂量、术语职责及实际人员 | 待指定 |
| 冻结决定 | 文件/canonical hash/范围/权利/确认者及实际时间 | PROPOSED |

冻结需留存固定URL/修订ID、原件字节SHA-256、卷章/边界/提取规则/遗漏重复检查、编码换行/canonical hash、作品声明/协议通知/署名与贡献历史/使用范围、底本逐项异文及精确修订定位；不足不冻结/批准，改字追加版本。

网页修订不证明底本一致，版权模板可能为取得时渲染；古籍公版不推及现代注释/译文/扫描，通知不代替正式权利判断。TXT页1为逻辑页，摘录段号不是条文号；实体页/年份/流派无依据为null。机器校验不自动冻结。

## 方剂逐字段核对

一方一表、一味一组。引用绑定精确EvidenceRevision及同源TextSegmentRevision、原文/hash/ `[start_offset,end_offset)`。offset按Python Unicode字符左闭右开，非字节/UTF-16单元。非null须引用；null不补值/引用。

| field_key（分别逐行填） | 候选值/null | quote_text | Evidence/片段修订、[start,end)、hash | basis/专家结论 |
| --- | --- | --- | --- | --- |
| original_name | 待填 | 待填 | 待填 | 原字变化须解释 |
| ingredients.0.original_name / amount_original / unit / processing | 每味按0、1、2…重复 | 待填 | 每字段单独记录 | 原药名/数量/单位/炮制逐字核对 |
| method | 完整煎服段 | 待填 | 多段逐条引用 | 原顺序换行连接须说明 |
| era / school | 无字段依据为null | 有值时填 | 有值时填 | 有值必填basis，源元数据不能替代 |
| indications / effects / dosage_form / preparation / cautions | 未知为null | 有值时填 | 各字段分别填 | 改写须basis，条件不删除 |
| ingredients.0.herb_id / amount_normalized / dose_ratio / role | 无依据为null | 有值时填 | 各字段分别填 | 有值必填basis；剂量列标准/版本/适用范围 |

`basis`不能仅写“已规范化”。规则复制原药名/剂量/单位/炮制/煎服段，不补现代绑定、角色/比例、剂型/治法/主治，不换算历史剂量。

共享/模糊/缺失剂量、替代/重复药味、数量不符、非法数字、未解析文字、条件/否定标题、跨结构会跳过整方。允许0命中，保留拒绝原文/原因，补规则或人工DRAFT；不得删药味造部分方剂，机械拒绝不代表方剂无效。

校订以 `create-formula --formula-id` 追加DRAFT，附 `--ingredient-spec` / `--field-sources`；旧修订/快照保留。旧待审版本0须追加新版1；旧已审对象不宣称达逐字段标准。字段键/门禁：[knowledge_formula_provenance.py](../backend/src/tcm_platform/knowledge_formula_provenance.py)。

## 术语裁定

| 原Concept/所选mention IDs | 原词/类型/时代/流派/上下文 | 裁定及新名称/类型 | basis与精确引用 | 已审对照Concept/引用 | 实际裁定者/结果 |
| --- | --- | --- | --- | --- | --- |
| 待填 | 未知保留null | NORMALIZE / HISTORICAL_SYNONYM / DISTINCT / UNRESOLVED，待选 | Evidence/片段修订、offset、原文/hash | 历史同义词必需 | 待指定/待审 |

不自动繁简、跨来源合并或扩展全局别名。`adjudicate-term`必填实际 `--actor` / `--basis` / `--sources`；`--mention`选特定语境，省略选全部。历史同义词须独立且REVIEWED的 `--related-concept`及精确对照Evidence，沿用对照名称/类型，保持独立身份及原时代/流派。UNRESOLVED保留原义/未知，不批准/入快照。裁定追加DRAFT，原记录不改，关系另校订。入口：[knowledge_terms.py](../backend/src/tcm_platform/knowledge_terms.py)。

## 操作顺序与证据

只用已验证Linux容器与独立测试库，不运行故障Windows Python/uv/Alembic或修改业务/预览库。正式验收导入/专家批准待冻结；独立 `*_test` 库可用PROPOSED原文验证DRAFT/快照排除，不自动APPROVE真实候选。

1. 冻结来源；C02不继承C01/预览出站授权，默认 `outbound_authorized=false`。
2. `show-import` / `show-segments`留存精确修订；SEGMENTED后 `extract-knowledge`，保留 `trace-extraction`版本/接受拒绝明细。
3. 专家对照底本、`trace-evidence`、`trace-knowledge formula_revision` / `concept`。`open-quality-issue`记录问题，BLOCKER未解决不批准。
4. **先审全部引用Evidence，再审方剂/概念**。实际决定用 `review-knowledge <kind> <ID> --reviewer … --decision APPROVE|REJECT --note …`分别留存HumanReview；不能冒充专家。
5. 批准复验字段/裁定/Evidence状态；保留失败ID/错误/无新增HumanReview证据，不直接改库绕门禁。
6. 隔离库 `snapshot-knowledge`留存KV/manifest/reference manifest/对象清单，已审纳入、草稿/拒绝排除、旧修订可追踪；创建/激活重验，快照不代表发布。

只读入口：[inspect_c02_rules.py](../backend/scripts/inspect_c02_rules.py)，Linux调用：

```powershell
docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/inspect_c02_rules.py fixtures/c02_candidate
```

该脚本报告生产解析/规则版本、原段/候选及 `database_writes=0`、`model_calls=0`，不创建草稿/升级审批；独立库工程验证可有写入。

| 验收项 | 待填实际记录 | 状态 |
| --- | --- | --- |
| 冻结/覆盖 | [v4扫描](acceptance-artifacts/vib46-c02/rules-v4.json) 3方全0；[v5扫描](acceptance-artifacts/vib46-c02/rules-v5.json) 各1候选 | PROPOSED；未冻结 |
| 字段/术语 | 每方表、裁定IDs、质量问题及解决依据 | 待专家 |
| Evidence先审 | EvidenceRevision/HumanReview IDs、真实reviewer/note | 待实际决定 |
| 方剂/概念审核 | 修订/独立HumanReview IDs、真实reviewer/note | 待实际决定 |
| 快照正反证 | 独立库/KV/manifest、纳入排除/失败门禁 | 待验；skip不算通过 |
| 工程验证 | `tcm_c02_extraction_cad7ff2c_test`，迁至0026；9相关文件175 passed、0 skipped（50.95s）；Ruff通过 | 3真实方仅DRAFT；位置/null、先审拒绝、快照排除、v4保留/v5重放通过；既有Alembic弃用提示 |

## 实际签署与并行边界

| 签署范围 | 实际人员/身份 | 实际日期 | 结论/记录位置 |
| --- | --- | --- | --- |
| 负责人选择/冻结 | 待填 | 待签署 | PROPOSED |
| 原文/字段/剂量/术语（各职责分别填写） | 待指定专家 | 待签署 | 待填 |

来源登记、只读校验/扫描、审阅表可并行。正式冻结→专家裁定→HumanReview→快照验收依次推进，不发明签字。VIB-48工程无需重做；真实C02/专家/VIB-68医学质量仍待验收。
