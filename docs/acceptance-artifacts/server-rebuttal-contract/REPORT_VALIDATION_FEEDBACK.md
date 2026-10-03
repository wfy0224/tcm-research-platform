# 报告程序校验反馈修复（2026-10-03）

- 用户要求修复报告内容校验失败没有反馈给写作模型的断路，并重新部署；未自动重新运行用户研究。
- 实际错误：conditional Claims cannot become certain report findings。
- report_narrative.py 现在保存原草稿，程序校验不通过建立明确的 ReportValidator 记录（program/report-validator-v1），带具体修改意见进入下一稿。没有调用模型或伪造模型复核结果。
- 条件观点引用、越界引用、缺引用、重复引用、段落结构错误均进入同一有界修订循环；真实网络/授权/租约等故障仍抛给 Worker。
- 模型可见输入补齐 finding/explanation/boundary 契约，旧冻结任务/草稿检查点不改写。三稿耗尽仍保存明确待修订报告，不能宣称全部回答必然通过。
- 最新程序校验结果可被待修订报告读取；结构损坏的原稿仅保留在 AgentRun，不能作为正文段落渲染。正式结论仍需真正的模型独立复核接受。
- backend/tests/test_report_validation_feedback.py：修复前4测试中3错误，准确重现条件finding/结构校验越过反馈；候选修复后4 passed，包含传输故障保持原有重试。
- 测试为模拟模型响应的工程回归，0云调用/0生产数据库写入，不计为真实研究报告验收。没有数据库集成验收。
- 服务器旧文件SHA256 5dc5b65de665778074a43a9cd1e5aa062a1a04a186dfab01742e1b1cd50be39e；备份 /opt/zhongyi/backend/src/tcm_platform/report_narrative.py.pre-validation-feedback-20261003。
- 新文件SHA256 0e3a86a7bc21be34c4da279c0c0d32d95bea3d21124a345a5a6e845c20741c06。
- 部署前无RUNNING后台任务，源码编译/镜像构建、API及Worker重建启动通过；git diff --check通过。
- 当前报告仍沿用先前保存版本；本次未自动重试、未观察研究结果。用户后续从页面继续修订时应用新流程。
