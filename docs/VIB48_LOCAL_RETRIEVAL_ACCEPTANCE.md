# VIB-48 本地检索与模型故障降级验收

日期：2026-09-30。起点：`71d15a3`，分支 `codex/evidence-audit`。本轮属于 VIB-48 的工程增量，Issue 保持 In Progress。

工程提交：`2c0d282`；接续文档另行提交。Linear 简短工程验收已同步，评论 `a03d60ad-4e18-4ab9-b2e1-7bb77c405602`。包含内部提交/测试/实现细节的完整评论被自动审批拒绝，未外发；具体证据保留本地。

## 交付行为

- `search_published` 的 `embedder=None` 为明确本地模式：使用 Exact/FTS/Structured/Relation 和既有 RRF。保留原 query，NFKC 仅用于匹配；结果仍来自冻结 KV/Index/Scope 内的 REVIEWED 精确 EvidenceRevision。
- API 默认未授权外发时直接使用本地模式，不创建云客户端、不读取模型凭据。`mode=local` 即使同时传入外发同意也强制本地。
- 授权尝试云模型但缺密钥、凭据存储不可用或客户端配置无效时回退本地，并使用固定安全原因码。查询外发同意不能绕过当前/冻结模式、策略版本及来源授权；策略拒绝时没有远程模型调用。
- 向量调用发生传输、容量、熔断、超时或模型响应错误时回退本地，不继续请求重排。重排失败时保留已完成的向量/本地候选，以原融合得分排序；失败通道不标为已完成，rerank_score 保持 null。
- 新增模型错误类型用于区分可降级故障与数据库/审计故障。数据库、审计存储、来源越界、冻结模型/端点不一致仍报错；不将这些错误伪装成降级成功。完整双索引仍是已发布版本的检索门禁。
- 服务层模型故障降级需显式 `allow_model_fallback=True`；既有研究任务与 benchmark 未开启此选项，保持严格模型路径。
- 新 `GET /api/v1/retrieval/query` 返回原 query、规范 query、LOCAL/HYBRID/DEGRADED、原因码、通道和公开编号结果，空结果也返回状态。旧 `/search` 维持数组响应，使用同一本地/降级路径。
- 前端允许不勾选外发同意直接检索，显示本次模式、原因和通道；显示结构/关系中文名。证据详情直接使用本地响应里的原文、上下文与引用，不调用模型。后续错误清除旧降级状态。

## 实际验证

- 首轮新独立库 `tcm_vib48_local_fallback_initial_test`：**192 passed、0 skipped**，223.35 秒。
- 最终新独立库 `tcm_vib48_local_fallback_verified_test`：**200 passed、0 skipped**，173.89 秒，比本轮起点177条新增23条。新增内容含传输响应/超时错误分类、API 正常/故障通道、重排正常/策略拒绝；首轮与最终库均无失败。两条警告为现有 Starlette TestClient/httpx 和 Alembic path_separator 弃用提示。
- 首轮和最终脚本均完成新空库升级 0026、0026→0023→0026 往返、两次 `alembic check` 无差异，以及合成旧方剂/概念内容、状态、null 与版本0保留。无新增迁移或依赖；所有测试库保留。
- 完整后端、测试、迁移、脚本 Ruff：通过（`--no-cache --ignore EXE002`）。前端 TypeScript/Vite build：通过。
- `npm run check:research-browser`：隔离模拟 API + headless Edge 通过本地无同意查询（含原输入空白保留）、结构/关系标签、证据详情、缺密钥、重排故障、空结果状态、发布错误清理，以及既有研究创建→人工审核→报告导出与移动宽度检查。首次沙箱执行 CDP 连接关闭；正常权限重跑通过，无 Windows 应用程序错误弹窗。
- 浏览器使用模拟故障；后端模型调用使用假适配器/模拟 transport，并覆盖真实适配器的错误类型。未执行真实断网/远程供应商或 Windows Credential Manager 实机验收，不将工程模拟等同于生产网络或模型质量验收。

```powershell
docker exec -e PYTHONPATH=/workspace/backend/src -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python scripts/verify_knowledge_extraction.py --database tcm_vib48_local_fallback_recheck_test --full-suite
```

此脚本仅接受 `tcm_*_test`、固定 LOCAL_ONLY，不打印凭据、不删除旧库。有知识候选/引用时不降级；迁移往返使用新库。

## 剩余工作

VIB-48 的多样性、未发布高相关片段转 QualityIssue、范围内查询候选扩展完整验收仍待补。C02 仍未冻结；VIB-46 真实完整方剂/专家核对仍待补。没有真实云调用、模型切换、训练、付费、推送或部署；没有修改预览/业务库或 API 容器。工程合成结果不代表专家真值或 VIB-68 模型资格。
