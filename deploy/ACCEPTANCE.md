# Docker 部署验证记录

2026-10-02，本地 Docker Desktop Linux 引擎，Compose v5.5.0；项目 zhongyi-docker-check，独立命名卷、空库及回环端口 18079，与现有工作区隔离。

- 前后端镜像构建成功；后端 uv --frozen，前端 npm ci/TypeScript/Vite 成功。
- Compose config --quiet 通过；数据库健康，首次迁移至0027 head并退出0。
- Nginx 页面200，API代理通；一次性访问码兑换、本地Cookie会话及CSRF返回通过（未记录密钥）。
- 发现健康常量0026与迁移head不一致；改为0027后重新构建、启动：database=connected、schema=current、blob_store=available、state=DEGRADED。
- 重建同一独立库后二次迁移成功，API健康、辅助Worker轮询无任务运行正常。
- compileall因镜像非root用户不可写只读代码目录而失败，改用AST只读解析两个入口脚本通过；运行入口此前已通过启动验证。
- 测试容器和网络已down，未删除独立测试卷，未触碰现有服务、数据库或文件。

本轮0云调用，没有云研究、真实文献导入发布/导出全链、SSE浏览器验收、完整备份恢复或2c2g负载测试。镜像针对当前电脑架构，跨架构部署须重新构建。内存限额不表示已在2GB主机验证稳定。
