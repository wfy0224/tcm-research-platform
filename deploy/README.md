# Docker 部署

打包数据库、自动迁移、API、静态前端和串行 Worker。适用于单管理员 SSH 访问，未提供公网多人认证。2c2g 配置内存限额并串行运行重任务，但未完成该规格负载测试；建议增加 Swap，整书任务仍可能超过限额。

## 首次启动

服务器安装 Docker Engine 和 Compose，将代码上传后，在仓库根目录执行（Linux Bash）：

```bash
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
# 编辑 .env，将 POSTGRES_PASSWORD 改为随机十六进制强密码
docker compose -f deploy/compose.yaml up -d --build
docker compose -f deploy/compose.yaml ps -a
docker compose -f deploy/compose.yaml exec api cat /run/tcm-bootstrap/code
```

最后一条读取访问码，不写容器日志。API 启动后 5 分钟内在页面兑换，只能使用一次。过期或新标签页需要重新登录时，restart api 后重新读取。迁移容器 Exited 0 是正常状态。

用户电脑执行并保持 SSH 终端运行：

```bash
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18067:127.0.0.1:18067 用户@服务器
```

打开 http://127.0.0.1:18067，填入访问码。不要用 localhost。更改 TCM_WEB_PORT 时同步更改 SSH 两侧端口和网页地址。只暴露回环网页端口，数据库与 API 不映射宿主端口。

## 云模型

默认 LOCAL_ONLY，不运行研究队列。云研究编辑 deploy/.env：

```ini
TCM_OUTBOUND_MODE=CLOUD_ALLOWED
SILICONFLOW_API_KEY=实际密钥
TCM_RESEARCH_PROVIDER=siliconflow
TCM_RESEARCH_MODEL=deepseek-ai/DeepSeek-V3.2
```

DeepSeek 官方研究路由改为 provider=deepseek、model=deepseek-flash，并填写 DEEPSEEK_API_KEY；向量发布仍需硅基流动密钥。页面选择的路由须与凭据一致。执行 `docker compose -f deploy/compose.yaml up -d` 更新环境，再读取新访问码。

容器启用既有环境凭据回退，Linux 尚无生产秘密管理适配器。密钥保存于权限 600 的 .env，Docker 管理员能读取容器环境；不要分享 config/inspect 输出，或提交 .env。来源外发授权和问题外发同意仍需完成；配置云模型不会替代它们。

## 常用操作

```bash
docker compose -f deploy/compose.yaml logs --tail 100 api worker
docker stats
docker compose -f deploy/compose.yaml restart api
docker compose -f deploy/compose.yaml stop
docker compose -f deploy/compose.yaml start
```

API 每次启动生成新码。数据保存在 postgres_data/app_data 命名卷；不执行 down -v，它会删除数据。首次空库没有本机文献、知识或研究任务。迁移须同时恢复数据库和整个文件目录。

Worker 顺序轮询解析、分段、发布、导出及研究；长研究期间其他队列等待。单任务内部模型并发仍由业务实现控制。内存不足时检查 OOMKilled，不能把容器重启当作任务完成。

## 在电脑构建，服务器免构建

同 CPU 架构电脑执行，首次需要联网拉取镜像与依赖：

```bash
docker compose -f deploy/compose.yaml build
docker pull pgvector/pgvector:pg16
docker image save -o zhongyi-images.tar zhongyi-backend:local zhongyi-web:latest pgvector/pgvector:pg16
```

将镜像文件及 deploy 目录（不带密钥 .env）传到服务器。在服务器新建目录，把 deploy 放在其中，再执行：

```bash
docker load -i zhongyi-images.tar
cp deploy/.env.example deploy/.env
chmod 600 deploy/.env
# 编辑密码和模型配置
docker compose -f deploy/compose.yaml up -d --no-build
```

异构电脑需按目标平台重新构建。预构建镜像方案服务器无需安装 Python、Node 或 Nginx。

## 备份与升级

维护窗口停止应用，保持数据库运行。用新的备份目录，逐条确认命令成功；失败备份不能登记为成功：

```bash
docker compose -f deploy/compose.yaml stop web api worker
mkdir -m 700 backup
docker compose -f deploy/compose.yaml exec -T db pg_dump -U tcm -d tcm_platform -Fc > backup/database.dump
docker compose -f deploy/compose.yaml run --rm --no-deps -T migrate tar -C /data -czf - . > backup/data.tar.gz
sha256sum backup/database.dump backup/data.tar.gz > backup/SHA256SUMS
docker compose -f deploy/compose.yaml start api worker web
```

备份应加密另存。恢复到新空库时用 pg_restore，同时恢复 app_data 并确保 uid 10001 可读写，然后迁移、启动、验收。完整流程见 docs/SERVER_DEPLOYMENT_GUIDE.md。

升级前备份并停应用，build 镜像后 run --rm migrate，确认成功再 up -d。回退镜像不等于数据回退，需检查 schema 兼容性。

验收包括迁移、访问码连接、真实文献导入分段、原文定位、发布检索、授权后的真实研究和报告下载、重启持久性及备份恢复。HTTP 健康不代表业务验收通过。
