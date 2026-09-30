# VIB-48 来源与证据多样性工程验收

日期：2026-09-30；工程提交 `ffc70b7`，起点 `25047fc`，分支 `codex/evidence-audit`。C02 完整方剂仍未冻结，本阶段使用合成数据验证检索工程，不构造真实语料真值。

## 实现与边界

`retrieval_diversity.py` 实现 `source-context/v1`。各通道先按精确 EvidenceRevision ID 去重，再融合 RRF。Exact/FTS/Vector 的同分候选按修订 UUID 稳定排序。已发布的冻结 KV/Index/Scope 过滤保持原路径；多样性只调整已授权候选的顺序。

每轮选择的分数为 `relevance_credit / ((1 + source_count) * (1 + context_overlap))`。`source_count` 为此前已选同一 SourceDocument 的数量；`context_overlap` 为与此前已选同一 SourceRevision 证据逐项计算的段落交集比例之和，单项分母为两者中较小的引用段落数。两项独立相乘，避免来源重复数增大时稀释段落重叠的惩罚。这里的“上下文相近”仅指精确引用范围重叠，不用文本模糊相似推断异体字、时代或版本等价，也不将仅共享前后文的独立段落当成重复。

候选池截取前使用正数 RRF credit，多样性处理后保留 `min(100, max(limit * 3, 20))` 条，避免同源候选挤掉其他已召回来源。最终返回前再次应用同一规则；正常重排按供应商原分数排序，再以 `1 / (60 + rank)` 作为正数 credit，避免供应商分数为负或量纲差异改变惩罚方向。重排未完成时用 RRF credit。最相关候选保留首位，之后为软惩罚；不会强制每个来源占固定名额，没有校准过的质量/无结果阈值。

同修订多通道只产生一条结果，保留全部 matched_channels。不同 Evidence 身份即使引用相同段落也保留，只降低重复引用的优先级；单一来源仍可填满结果。返回的都是原精确修订，未替换成新版、未合并为新证据、未扩大来源范围。

每条服务及 API 结果新增 `diversity`：policy、relevance_rank、source_occurrence、context_overlap、selection_score。relevance_rank 是最终候选池按 RRF 或供应商重排排序时的名次；selection_score 是当次选择 credit，不是医学可信度或模型质量。原 retrieval_score/rerank_score 保留。API 的说明不含内部 UUID，旧 `/search` 数组外形保留；前端忽略此新增字段，尚未增加专门的排序说明 UI。

研究 EvidenceRetrievalEvent 继续记录实际最终名次、通道与精确修订；研究审计事件额外保存本次排名与说明。benchmark 保存策略版本及逐题精确排名/说明，原六项指标继续仅做数值汇总，既有历史记录不修改。无迁移或新依赖。

通道候选仍各自最多 300 条，最多五通道合并后仅批量读取段落来源信息；完整引用链校验只对至多 100 条最终候选执行。多样性不能恢复已被单通道上限裁掉的候选，也不能保证弱相关来源召回，后续候选扩展与真实 Golden Set 仍需独立验收。

## 实际验证

- 最终全新独立库 `tcm_vib48_diversity_final_test`：完整后端 **213 passed、0 skipped**（266.16秒），比起点200条新增13条，全部实际运行。
- 首库 `tcm_vib48_diversity_verified_test`：**212 passed、1 failed、0 skipped**（396.21秒）。单来源用例揭示加法惩罚稀释重叠上下文；修正为来源与重叠两项相乘，失败用例与3条算法用例 **4 passed、0 skipped**（6.86秒），随后最终新库完整通过。未降低验收断言。
- 两个新库均完成空库升级0026、0026→0023→0026往返和两次 `alembic check` 无差异；旧合成概念/方剂原文、状态、null与版本0保留。测试库均保留，未删除旧库。
- 全后端/测试/迁移/脚本 Ruff `--no-cache --ignore EXE002` 与 `git diff --check` 通过；前端 TypeScript/Vite build 通过。未改前端逻辑，未重跑浏览器；API说明和旧数组接口已由真实 TestClient/数据库集成验证。
- 全部 LOCAL_ONLY、合成工程验证，0次真实云调用；既有 Linux 运行容器和只读 backend 挂载。未运行原生 Windows Python/uv/Alembic，未触发程序错误弹窗，未修改预览/业务库或 API 容器。
- 简短验收已同步 Linear 评论 `3d9f12aa-a2a6-48f4-8909-35e64da67d3b`，仍 In Progress；详细内部工程证据保留本地。

复现命令（新库可复核空库升级和往返；已存在并含候选的库只升级及测试，不破坏其数据）：

```powershell
docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib48_diversity_recheck_test --full-suite
```

新增 `test_retrieval_diversity.py` 与 `test_retrieval_diversity_integration.py`，覆盖重叠段落、不同修订边界、弱相关来源软惩罚、同修订去重、多来源、超过旧候选池上限的重复引用、单来源填充、历史快照/替换修订、来源越界/空范围、本地与向量故障降级、负分重排/重排故障、API安全说明、研究实际排名与重放幂等、benchmark反证召回与排名持久化。

## 剩余验收

VIB-48 保持 In Progress。未发布高相关片段转 QualityIssue、查询候选扩展完整验收仍未实现；VIB-46 真实 C02/专家依赖保留。本阶段未执行真实模型质量评测、真实供应商断网或 Windows 凭据实机验证。
