# VIB-45 初始语料与 OCR 决策验收

日期：2026-09-30。实施起点：`ab755a2`；工程提交：`86c6299`（与VIB-46验证增量一并提交）。首批盘点、来源依据、负责人、OCR 延期和不误发布专项已完成；不代表专家校订或 V1 整体验收完成。

## 首批范围与责任

用户在本次会话明确选择“先用文本，OCR 延后”，并指定数据负责人角色为“测试人员”。该角色负责维护语料清单、保存来源和权利依据、确认扩充范围、安排专家复核；没有虚构具体姓名或专家签字。

机器可读登记：`backend/fixtures/initial_corpus.json`。它是工程验收清单，既不自动导入/发布，也不赋予云出站授权。首批仅包含以下已存档样本；后两项是候选方向，尚未取得验收样本。

| 编号/用途 | 典籍与范围 | 版本/历史元数据 | 格式与定位 | 权利/公开级别 | 当前处理 |
| --- | --- | --- | --- | --- | --- |
| C01 首批工程样本 | 《傷寒論》卷第二·辨太陽病脈證並治（上）第五，29 条非方剂原文 | 上游称宋本；漢張仲景著、宋林億等校；数字修订 2607901；确切实体底本、刊年和流派未知 | UTF-8 TXT；固定章节、摘录段落及校验和；无实体页码映射 | 上游作品 PD-old；PUBLIC；登记默认禁止云出站 | 可验证导入、分段与草稿溯源；项目专家复核待办 |
| C02 VIB-46 方剂扩充候选 | 同章桂枝汤等方剂原文 | 沿用同一来源方向，但须取得固定修订摘录和对照底本 | 拟文本；份数、哈希、条文与页码未冻结 | 权利说明需随选定摘录保存；不能继承 C01 的云授权 | 未纳入首批；负责人选定并安排方剂专项校订 |
| C03 VIB-47 古病案候选 | 由负责人选定古病案文献和具体篇目 | 典籍、作者、年代、版本、刊年、流派尚未确定 | 格式与数量待定 | 授权与公开级别未知 | 未纳入首批；不能用 C01 证明 CaseRecord 兼容验收 |

三份项目设计 DOCX 是设计依据，不是中医原始语料；现代病人资料不在本次范围。C01 不具备药味、剂量、炮制、煎服等完整方剂原文，不能为 VIB-46/VIB-68 的对应验收补造真值。

## 来源和授权依据

- [作品页面](https://zh.wikisource.org/wiki/傷寒論) 本轮读到的页尾引用修订为 `2607901`，与已有 fixture 来源记录一致。页面标注古代作品公有领域，并提示转繁与校订不足；原文第五至十四章和方剂的校订状态不同。这里只保存依据，不宣布专家已复核。
- [固定修订及贡献者历史入口](https://zh.wikisource.org/w/index.php?title=傷寒論&oldid=2607901)、[站点版权说明](https://zh.wikisource.org/wiki/Wikisource:版权信息)：古代原作权利状态和数字贡献/校订的协议说明分别登记；保留张仲景、林亿等历史责任信息、维基文库来源和贡献历史链接、版本及协议通知。现代注释、出版排版或另取扫描件需另查权利依据。本轮没有新取扫描文件，也未发布到外部。
- 已有机械摘录仅统一 CRLF→LF，不改写文本，UTF-8 SHA-256 为 `65b83255eeb4f4e300301b1e144e758e0cf38e559d92f227372c9c586a11c4c4`；29 条逐条分段和引用一致性已验证。固定修订 URL 本轮直接打开失败，正常作品页的修订标识可读；没有宣称重新取得完整原始 wikitext 或对照扫描底本。
- TXT/当前 DOCX 解析的页 1 是逻辑容器；C01 用章节、摘录序号、原文哈希和精确修订定位，不能把摘录序号当通行本条号，不能把逻辑页 1 当宋本实体页。网页历史是数字编辑史，不是书籍刊印史。未知字段保留 null。

## OCR 决策与门禁

按 LLD 附录 C，初始语料含扫描件才将 OCR 列为 P0；本次用户已确认纯文本，因此延期 OCR Job、模型选择、置信度和人工逐页复核实现。引入扫描件前必须重新冻结范围并补齐这些能力以及物理页码映射，不能通过自动 APPROVE 绕过。

`source-parser/v2` 检查每个 PDF 页：任一页没有可提取文字（包括混合文件和空白页）时整份文件进入 `OCR_REQUIRED`，错误列出页号。真正空白页也先交人工确认；当前没有“跳过已确认空白页”功能。零页 PDF 以 `EMPTY_TEXT` 拒绝。全文字 PDF 保留逐页页号；已有旧修订不被重写或重新发布。现有文字层可能错误，非空判断不代表质量合格，仍需专家复核。

等待 OCR 的文件保留 ORIGINAL，PARSE 步骤 BLOCKED，无 Parsed Artifact、后续分段任务、TextSegmentRevision 或 EvidenceRevision；创建新知识快照只收入已有已审核测试证据，等待 OCR 的来源被排除，活动指针不改变。首批实际 29 条原文只生成 DRAFT，未审核证据也不进入快照。测试中 APPROVE 的全部是另外创建的合成文本，不是 C01 专家审核。

## 实际验证与复现

- 既有 Linux 容器 `tcm-vib54-py`，只读挂载当前 backend；新建独立 `tcm_vib45_test`，已有迁移从空库升至 `0023_release_snapshot`，无新增迁移。禁用云出站 `LOCAL_ONLY`。
- 解析、来源导入、首批实际语料、OCR 快照排除、分段单元与集成：**20 passed、0 skipped**。合成无文字 PDF/混合 PDF 验证边界，不是扫描件 OCR 质量测试。
- Ruff 针对修改的四个 Python 文件通过（`--no-cache --ignore EXE002`；Windows 只读绑定挂载呈可执行权限，忽略该权限误报）。`git diff --check` 通过。未重跑完整后端/浏览器套件，无真实云模型调用，未更改预览/业务数据库。
- 首次运行 14 passed、4 failed：来源导入测试留下分段任务，后续用例误领不属于本例的队列任务；新增测试按本次 import_job 的幂等键调用真实 `acquire_job`，保留真实租约、分段与提交逻辑。随后 19 passed、1 failed 为测试把 JSON 定位 dict 当作 set key，改为规范 JSON 序列化。最终上述 20 条全过，失败数据保留在独立测试库，未清除旧队列。

PowerShell 复现（独立库已创建并迁移；沿用容器环境凭据且不打印连接串）：

```powershell
docker exec -e PYTHONPATH=/workspace/backend/src -e TCM_OUTBOUND_MODE=LOCAL_ONLY -e PYTHONDONTWRITEBYTECODE=1 -w /workspace/backend tcm-vib54-py python -c 'import os; from sqlalchemy.engine import make_url; os.environ["TCM_DATABASE_URL"]=make_url(os.environ["TCM_DATABASE_URL"]).set(database="tcm_vib45_test").render_as_string(hide_password=False); import pytest; raise SystemExit(pytest.main(["-q","-p","no:cacheprovider","tests/test_parsing.py","tests/test_source_import_integration.py","tests/test_initial_corpus_integration.py","tests/test_segmentation.py","tests/test_segmentation_integration.py"]))'
docker exec -w /workspace/backend tcm-vib54-py ruff check --no-cache --ignore EXE002 src/tcm_platform/parsing.py tests/pdf_samples.py tests/test_parsing.py tests/test_initial_corpus_integration.py
```

下一项 VIB-46 先实施可追溯候选抽取草稿、原文定位和未知字段保留。完整方剂真实验收需负责人选定 C02 固定摘录并安排校订；古病案选定由 VIB-47 补齐，正式 Golden Set 与专家标签由 VIB-68 补齐。
