# 真实报告测试（2026-10-03）

结果：**未通过**。原任务RT-01a1001e-e294-7ab7-9ba2-e2005bee58cc，最后REPORT_REVIEW_REQUIRED、队列COMPLETED、无last_error；report revision7 NEEDS_REVISION。

本次5次有界修订，round6～20共15个真实Writer、10个真实Reviewer、5个程序Validator；全部未获接受。15写作+10复核为25次付费模型调用，金额未知；JSON内model_calls包括更早历史调用，不是本轮账单。

发现并修复：模型输入丢弃已冻结证据上下文；写作与复核范围规则不一致；程序校验覆盖先前内容复核反馈；旧冻结提示输出字段易遗漏kind。新增同源上下文、共享范围/归因规则、实质拒绝标准、完整JSON字段约束和跨稿跨周期反馈保留。程序门禁和独立模型复核没有绕过。

最新部署report_narrative.py SHA256：67d3e7d7403a34189546fac4cef73c8f7ecd67bc1b4912b565f6a83a9200fbc2。Linux容器8项工程回归通过；构建并重启API/Worker。未跑独立数据库集成，未通过整体验收。

round19内容反馈7条，新增程序错误后round20收到8条，证明保留修复真实生效；round20仍误用finding引用CONDITIONAL，程序拒绝。round18的上下文归因、引用覆盖和审计理由一致性仍需排查。不能把队列COMPLETED当报告成功。

冻结context哈希0f9ffcabe70c2073d6b8c75b9f41619e3e2830b71f094db29ec6b31729f7236b保持。rev1/2历史哈希保留，rev3～7追加。详见REAL_REPORT_TEST.json（原草稿、每轮意见、调用token_usage和历史报告）。

用户投诉连续调用费用后立即请求暂停；最后周期在请求到达前已结束，API返回research job cannot be paused，未设PAUSED。没有继续的测试队列；不再发起付费调用，后续必须重新取得明确授权。

浏览器测试因工具无法确认Windows当前网址停止，没有绕过；页面验收未完成。
