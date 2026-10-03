# 离线修稿链路修复（2026-10-03）

本轮新增模型调用：0。没有重试研究、没有改变原报告状态。

发现与修复：
- 下一稿仅收到意见，缺少上一稿正文；现在从最近复核/程序校验恢复原稿，并在稿间、修订周期之间传递previous_candidate。独立复核不接收上一稿或旧反馈。
- 程序校验只报首个泛化错误；现在一次报告所有可检测的段落问题及具体claim_id。结构错误保留全部字段位置，不重复转储长篇原稿。
- 复核带入不属于本稿引用的旧缺口与争议；现在模型可见输入保留相关意见、总体缺口和逐段引用清单。原有冻结检查点及报告均不改写。
- 收到原样失败稿仍重复付费复核；现在只对新生成的、与上一失败稿完全相同的草稿执行提前停止，保存程序拒绝及原反馈，不调用下一次复核或自动生成。已有缓存检查点不按此规则重写。

单命令反馈环：SSH容器内unittest执行backend/tests/test_report_validation_feedback.py，截获recorded_complete，使用OFFLINE_REPLAY.json中实际第16/19/20稿及冻结材料重建。没有模型请求，也没有生产数据库写入。

失败证据：修复前11项中2errors/1failure（上一稿缺失、错误无定位）；停止重复调用的回归修复前1error/1failure；范围过滤修复前1failure。整批候选16项通过，部署后的真实模块16项也通过。工程测试的假返回只验证状态机，不冒充真实研究通过；真实失败稿仍严格拒绝，不伪造accepted。

仅更新report_narrative.py，备份/opt/zhongyi/backend/src/tcm_platform/report_narrative.py.pre-targeted-revision-20261003；重建API/Worker。新SHA256：04c385582d9f809e41424c6cc6c1c286a14260ab3de85a94225ea5a6263f5cf1。

原任务仍REPORT_REVIEW_REQUIRED，revision7 NEEDS_REVISION；没有重新做付费模型复核，不能宣称用户研究已经成功。数据库集成、浏览器及导出未做本轮新增验收。接口/冻结配置/历史报告只读核对见OFFLINE_REPAIR_VERIFICATION.json。

下一步只做无费用检查；如需真实云端最终验收，必须先取得用户明确授权和预算上限。用户投诉的此前25次付费调用记录不变，退款权限不可用。

部署后只读核对：API可达，database=connected/schema=current/blob_store=available，state=DEGRADED（现有health实现的返回值，不宣称HEALTHY）。原任务报告7版哈希均不变，冻结配置不变，历史报告模型调用仍40条与本轮前一致。
