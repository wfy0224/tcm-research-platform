# C02 方剂原文候选资料包（PROPOSED）

这是供测试人员与中医理论专家逐项核对的来源材料。尚未进入 `initial_corpus.json`、数据库、冻结知识版本或模型验收。`expert_review_status=PENDING`、`outbound_authorized=false`；数据负责人具体姓名、专家安排和实体书页码映射仍待确认。

## 已实际取得的证据

- 2026-10-01 通过 Node 原生 `fetch` 只读取得[维基文库《傷寒論》固定文章修订 2607901](https://zh.wikisource.org/w/index.php?title=%E5%82%B7%E5%AF%92%E8%AB%96&oldid=2607901)，HTTP 200；响应解码为 UTF-8 后保存为 `upstream_revision_2607901.html`。请求只含公开来源 URL，未发送内部文件、模型凭据或业务数据。
- 实际响应的 `RLCONF.wgRevisionId` 为整数 `2607901`。`source_url` 是作品入口；只有 `revision_url` 是指定固定修订，不能互换。没有用当前入口内容冒充固定修订。
- `oldid` 固定文章本身的修订；页面皮肤、模板及权利模板的渲染可能使用取得时的版本。本包归档的是此次实际响应，权利通知代表此次实际观察，不能推断为文章修订发生时的历史权利声明。
- 同章“辨太陽病脈證並治（上）第五”机械摘取桂枝湯方、桂枝加葛根湯方、桂枝加附子湯方，每方保留标题、药味剂量与完整煎服段落。仅限原文资料完整性候选，不作医学正确性认定。
- `rights_notice.txt` 来自同一 HTML 的作品 PD-old 通知和站点版权页脚：古代作品被标注为公有领域；站点文字另注明 CC BY-SA 4.0、可能附加条款及署名相关说明。通知中链接的[许可说明](https://creativecommons.org/licenses/by-sa/4.0/deed.zh)和[使用条款](https://foundation.wikimedia.org/wiki/Special:MyLanguage/Policy:Terms_of_Use)仅供负责人后续审阅，本包不把网页声明转化为项目法律审批。

## 文件与定位

| 文件 | 作用 |
| --- | --- |
| `manifest.json` | 版本、权利证据、状态、文件 SHA256 和摘录定位 |
| `upstream_revision_2607901.html` | 此次 HTTP 200 响应的 UTF-8 HTML 证据；不作为摘录 offset 基线 |
| `chapter_visible.txt` | 章节正文的确定性 HTML 文本抽取，作为所有摘录唯一定位基线 |
| `guizhi_tang.txt` | 桂枝湯方完整标题、药味剂量、煎服段落 |
| `guizhi_jia_ge_gen_tang.txt` | 桂枝加葛根湯方完整标题、药味剂量、煎服段落 |
| `guizhi_jia_fu_zi_tang.txt` | 桂枝加附子湯方完整标题、药味剂量、煎服段落 |
| `rights_notice.txt` | 此次实际页面的作品及站点权利通知文字 |
| `extract_candidate.ps1` | 从已归档 HTML 重新生成相同基线、摘录、通知及 manifest 的离线脚本 |

HTML 抽取明确限定为标题容器之后、下一章标题容器之前的章节正文。`br` 与关闭的 `p/dt/dd` 标签变为 LF，其余标签剥离，HTML 实体解码一次；既有文字与空白全部保留。所选章节没有 script/style。此规则构成可复现的可见正文文本基线，不是浏览器排版截图，也不把 HTML 标签计入文字 offset。

摘录以唯一 `dt` 标题及相随两个 `dd` 节点机械选取，是 `chapter_visible.txt` 的完整连续子串，不做正字、简繁转换、空白折叠或标点改写。原来源中的“麻黄”“去节”等混用字保留。生成文本以后仅允许 CRLF→LF，文件均 UTF-8 无 BOM。`source_start/source_end` 为从 0 开始的 Unicode 码点半开区间 `[start,end)`；不能按字节或 JavaScript UTF-16 下标使用。所有 artifact 哈希及 `text_sha256` 均在 CRLF→LF 后的 UTF-8 字节上计算。

离线重建（PowerShell 7）：

```powershell
& backend/fixtures/c02_candidate/extract_candidate.ps1
```

## 尚需审阅

上游页面同时标注未充分校对，并提示简繁转换可能产生错误。保留原貌只是证据要求，不意味着此版本已达到方剂真值标准。需指定数据负责人和专家，核对完整性、药味/剂量/炮制与可接受的原文疑点，填写可追溯的逐字段复核记录，并确认权利与底本/页码映射；批准前继续保持 PROPOSED。若需要校订，应保留本包原文，并按项目追加校订流程处理。

本包不包含药效、临床用途判断、真值标签、负责人代签或专家自动审批。规则扫描是否支持这些真实排版，属于单独的工程验证，不能替代专家复核。
