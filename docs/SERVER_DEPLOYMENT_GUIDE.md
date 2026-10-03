# 服务器部署手册

适用基线：2026-10-02，提交 `d0f002e`，后端迁移至 `0027_report_revisions`。本机未提交的 UI 美化不包含在该提交中；交付时应另行提交并锁定实际发布提交。本文依据仓库代码核对，尚未在新服务器执行部署验收。

## 1. 部署范围

当前可采用 Linux 单机、单管理员、SSH 隧道方式运行知识库与研究工作区。API 强制回环 Host，所有会话属于 local-owner；没有公网账号登录和多租户权限隔离。不能把本手册当作公网多人生产部署方案。

服务器运行 PostgreSQL 16 + pgvector、FastAPI、研究 Worker、辅助队列 Worker 和 Nginx 静态前端。浏览器通过 SSH 隧道访问同源页面及 API。数据库、API、网页端口均只绑定 127.0.0.1；外部仅开放受控 SSH。无需 GPU，模型通过云端 API 调用。

以下命令在 Linux Bash 执行，使用 `/opt/zhongyi` 存放代码、`/var/lib/zhongyi` 存放文件。示例容量起点为 4 核、8 GB 内存及 50 GB SSD，实际空间随原文、索引、报告和备份增长；这不是压力测试结论。需预先安装 Git、Docker Compose、Python 3.11+、uv、Node.js 20+、npm、Nginx，确认服务器能访问所选模型端点。安装工具版本由运维环境管理。

## 2. 代码与依赖

将经审核的仓库复制到 `/opt/zhongyi`，或从实际仓库地址克隆；本仓库没有提供公开克隆地址。固定发布提交，禁止直接使用持续变动的分支作为发布版本。

```bash
cd /opt/zhongyi
git checkout <已审核的发布提交>
git status --short
sudo useradd --system --home /var/lib/zhongyi --shell /usr/sbin/nologin tcm
sudo install -d -o tcm -g tcm -m 700 /var/lib/zhongyi
cd backend
uv sync --frozen --no-dev
cd ../frontend
npm ci
npm run build
sudo install -d /var/www/zhongyi
sudo cp -a dist/. /var/www/zhongyi/
```

后端虚拟环境必须能由 tcm 用户读取执行。后续 systemd 示例使用其绝对路径，无需后台运行 uv。不要使用 `dev:workspace` 启动器部署服务器，它依赖本机专用测试容器和数据库。

## 3. 独立数据库

不要原样使用根目录开发 Compose 的弱密码和开发数据卷。新建 `/etc/zhongyi/compose.yaml`（目录权限 700），内容如下：

```yaml
services:
  db:
    image: pgvector/pgvector:pg16
    restart: unless-stopped
    environment:
      POSTGRES_DB: tcm_platform
      POSTGRES_USER: tcm
      POSTGRES_PASSWORD: ${POSTGRES_PASSWORD:?set POSTGRES_PASSWORD}
    ports:
      - "127.0.0.1:5432:5432"
    volumes:
      - postgres_data:/var/lib/postgresql/data
    healthcheck:
      test: ["CMD-SHELL", "pg_isready -U tcm -d tcm_platform"]
      interval: 5s
      timeout: 3s
      retries: 10
volumes:
  postgres_data:
```

在该目录创建 `.env`，写入 `POSTGRES_PASSWORD=<随机强密码>`，权限 600；禁止提交 Git。密码如含 URL 保留字符，连接串中须百分号编码。记录实际镜像摘要，以便后续复现部署。

```bash
cd /etc/zhongyi
sudo docker compose up -d db
sudo docker compose ps
sudo docker compose exec -T db pg_isready -U tcm -d tcm_platform
```

## 4. 运行配置与迁移

创建 `/etc/zhongyi/runtime.env`，所有示例占位符须替换，权限 root:root / 600。该文件采用同时可被 Bash source 和 systemd EnvironmentFile 读取的简单 KEY=value 格式；字符串需要时用单引号，不写 export，不做变量展开。

```ini
TCM_DATABASE_URL='postgresql+psycopg://tcm:替换为URL编码密码@127.0.0.1:5432/tcm_platform'
TCM_DATA_ROOT=/var/lib/zhongyi
TCM_LOCAL_ALLOWED_ORIGINS=http://127.0.0.1:18067
TCM_DEVELOPMENT_AUTO_SESSION=false
TCM_SECURE_SESSION_COOKIE=false
TCM_BOOTSTRAP_TTL_SECONDS=300
TCM_OUTBOUND_MODE=LOCAL_ONLY
TCM_MODEL_PROVIDER=siliconflow
TCM_EMBEDDING_MODEL=BAAI/bge-m3
TCM_RERANK_MODEL=BAAI/bge-reranker-v2-m3
TCM_RESEARCH_PROVIDER=siliconflow
TCM_RESEARCH_MODEL=deepseek-ai/DeepSeek-V3.2
```

HTTP 仅在回环和加密 SSH 隧道内使用，所以示例 Cookie 不设 Secure。不要将这项设置套用到公网 HTTPS。

仅本地检索无需云密钥。云研究和发布需要另外配置凭据：当前凭据存储只实现 Windows Credential Manager，Linux 上没有对应生产凭据适配器。现有环境变量回退要求 `TCM_ALLOW_ENV_API_KEYS=1`，仓库将其定位于隔离开发容器；在服务器试运行中若采用该方式，须由运维明确接受该限制，将 `SILICONFLOW_API_KEY`（或 DeepSeek 路由的 `DEEPSEEK_API_KEY`）通过受限环境注入 API 和 Worker。不要输出密钥，也不要把密钥放在命令参数、仓库或截图里。正式生产应先实现服务器凭据管理适配。

启用云调用时同时设置 `TCM_OUTBOUND_MODE=CLOUD_ALLOWED`。这不会替代来源 PUBLIC/外发授权和用户对研究问题或检索词的外发同意。页面选择的 provider/model 必须与可用凭据一致；已启动任务的路由被冻结。

在 root 管理终端加载配置并迁移（服务启动前执行）：

```bash
set -a
source /etc/zhongyi/runtime.env
set +a
cd /opt/zhongyi/backend
.venv/bin/alembic upgrade head
.venv/bin/alembic current
```

确认版本为发布提交的迁移 head；本基线 head 是 0027。API 不会自动建表。空库不会自动带入本机的方剂学原文、知识版本或报告。

## 5. systemd 服务

创建 `/etc/systemd/system/tcm-api.service`：

```ini
[Unit]
Description=TCM API
After=network-online.target docker.service
Wants=network-online.target
[Service]
User=tcm
Group=tcm
WorkingDirectory=/opt/zhongyi/backend
EnvironmentFile=/etc/zhongyi/runtime.env
EnvironmentFile=-/etc/zhongyi/bootstrap.env
ExecStart=/opt/zhongyi/backend/.venv/bin/uvicorn tcm_platform.main:app --host 127.0.0.1 --port 8000 --workers 1
Restart=on-failure
RestartSec=5
UMask=0077
[Install]
WantedBy=multi-user.target
```

创建 `tcm-research.service`，使用同样的 Unit、User、Group、WorkingDirectory、runtime.env、Restart、UMask 和 Install；不读取 bootstrap.env，将 Description 和 ExecStart 改为：

```ini
Description=TCM research worker
ExecStart=/opt/zhongyi/backend/.venv/bin/python -m tcm_platform.cli run-research-worker --worker-id server-research-1 --poll-seconds 2
```

来源解析、分段、知识发布和报告导出目前只有单次 CLI 入口，需额外轮询。创建 `/opt/zhongyi/ops/queue-worker.sh`：

```bash
#!/bin/bash
set -u
cd /opt/zhongyi/backend || exit 1
while true; do
  for job in parse-next segment-next publish-next run-report-export-next; do
    if ! .venv/bin/python -m tcm_platform.cli "$job"; then
      printf 'queue command failed: %s\n' "$job" >&2
    fi
  done
  sleep 2
done
```

赋予执行权限。创建 `tcm-queues.service`，沿用研究服务配置，将 ExecStart 改为 `/opt/zhongyi/ops/queue-worker.sh`。这是运维轮询包装，需监控退出码和 Job 失败原因；不能因为进程存活就认定业务成功。

```bash
sudo systemctl daemon-reload
sudo systemctl enable --now tcm-api tcm-research tcm-queues
sudo systemctl status tcm-api tcm-research tcm-queues
```

本机 LOCAL_ONLY 无凭据时，研究 Worker 可能在创建云客户端时失败；未启用云研究的部署仅启动 API/辅助队列，配置云研究后再启动研究 Worker。云端不可用时知识发布任务也不能完成。

## 6. 前端与 SSH 访问

Nginx 配置 `/etc/nginx/conf.d/zhongyi.conf`：

```nginx
server {
    listen 127.0.0.1:18067;
    server_name 127.0.0.1;
    root /var/www/zhongyi;
    index index.html;
    client_max_body_size 140m;
    location /api/ {
        proxy_pass http://127.0.0.1:8000;
        proxy_set_header Host 127.0.0.1:8000;
        proxy_http_version 1.1;
        proxy_set_header Connection "";
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 900s;
    }
    location / {
        try_files $uri $uri/ /index.html;
    }
}
```

代理保留 `/api/` 路径和浏览器 Origin；关闭缓冲支持研究 SSE。140m 为 100 MiB 原文件的 Base64 JSON 留出空间，不改变应用自身导入上限。

```bash
sudo nginx -t
sudo systemctl reload nginx
curl --fail http://127.0.0.1:18067/api/v1/system/health
```

在用户电脑执行并保持终端运行：

```powershell
ssh -N -o ExitOnForwardFailure=yes -L 127.0.0.1:18067:127.0.0.1:18067 <SSH用户>@<服务器地址>
```

打开 `http://127.0.0.1:18067/`，不要改用 localhost。本机端口冲突时选另一端口，并同步修改服务器 `TCM_LOCAL_ALLOWED_ORIGINS`、重启 API；SSH 本地端口与浏览器 Origin 必须一致。

## 7. 首次登录与重新登录

每次需要新会话时在服务器 root 管理终端生成一次性访问码：

```bash
umask 077
bootstrap_code=$(openssl rand -hex 32)
printf 'TCM_BOOTSTRAP_SECRET=%s\n' "$bootstrap_code" > /etc/zhongyi/bootstrap.env
systemctl restart tcm-api
printf '%s\n' "$bootstrap_code"
unset bootstrap_code
```

通过自己的 SSH 终端取得访问码，5 分钟内填入页面连接框。访问码只能兑换一次；API 使用单进程避免启动密钥语义不一致。会话默认 8 小时，新标签页没有原标签页的 CSRF 缓存，可能需要新会话。生成新码需重启 API，会短暂中断连接，应安排操作窗口。完成兑换后可删除 bootstrap.env；下次重新生成。不要将访问码输出采集到公共日志。

## 8. 数据初始化或迁移

新库：从页面导入真实授权文献；辅助 Worker 解析与分段；核对候选、原文引用与人工审核，创建知识版本并发布。云发布成功激活 KV/Index 后才可开始研究。不得导入模拟业务数据充当验收。

迁移已有工作区：必须迁移对应数据库和整个 `TCM_DATA_ROOT`，包括内容寻址原文、索引工件、导出及模型设置。只复制代码不会恢复知识库，只复制数据库会丢失原文/报告文件。用第 10 节的一致性备份流程，在新库恢复后执行 `alembic upgrade head`，再启动服务。本机专用测试库名称不作为服务器生产库名称；不要把测试库配置复制过去。

迁移后确认活动 KV/Index、来源数量、引用定位和文件哈希，保留旧环境到恢复验收完成。不要为迁移无故重建向量索引：重建会产生真实云调用，并且已冻结任务仍依赖旧索引。模型设置文件是候选列表，不证明模型可用；密钥需单独重新注入。

## 9. 部署验收与排错

逐项记录实际结果和发布提交；未执行项目标为未验证：

- `alembic current` 为 head，数据库扩展 vector 可用。
- API 健康响应中数据库、schema、blob_store 无故障；当前 state=DEGRADED 可能是既有健康逻辑，不能据此断言整套业务通过。健康常量已对齐 0027；迁移仍以 Alembic head 为准。
- 通过 SSH 页面兑换访问码，刷新同一标签页可恢复会话，业务写入没有 Origin/CSRF 错误。
- 导入一份真实授权文献，解析/分段任务成功，原文可打开且定位准确。
- 已审核知识成功发布并可检索；从证据跳回来源，核对精确修订与原文。
- 获得云调用授权后创建真实研究任务，观察 Worker、SSE 和最终报告；研究完成后 Markdown/DOCX 均能实际下载打开。
- 重启服务后活动知识与历史任务仍可访问；在隔离恢复环境完成数据库+文件恢复演练。

常见问题：403 LOOPBACK_REQUIRED 检查代理 Host；ORIGIN_DENIED 检查浏览器端口与允许 Origin；BOOTSTRAP_UNAVAILABLE 检查启动码注入；INVALID_BOOTSTRAP 检查是否过期/已兑换；任务长期排队检查对应 Worker；模型凭据错误检查 API 与 Worker 环境是否一致；报告导出排队检查辅助 Worker。不要通过开启开发自动登录来绕过正式连接问题。

```bash
sudo journalctl -u tcm-api -u tcm-research -u tcm-queues --since '30 minutes ago'
sudo docker compose -f /etc/zhongyi/compose.yaml ps
```

查看日志时不要输出环境文件或进程完整环境。数据库测试必须使用独立测试库，skip 不等于通过。本机 Windows Python/uv 曾触发应用程序错误，不能用其验证；本文 Linux 命令未在本轮执行。

## 10. 备份、恢复与升级

一致性备份：进入维护窗口，停止所有应用写入和 Worker；数据库保持运行。同时保存数据库、完整数据目录、发布提交、迁移版本、镜像摘要和非密钥配置。示例在服务器 root Bash 执行：

```bash
systemctl stop tcm-api tcm-research tcm-queues
backup_dir=/var/backups/zhongyi/$(date +%Y%m%d-%H%M%S)
install -d -m 700 "$backup_dir"
cd /etc/zhongyi
docker compose exec -T db pg_dump -U tcm -d tcm_platform -Fc > "$backup_dir/database.dump"
tar -C /var/lib -czf "$backup_dir/data.tar.gz" zhongyi
sha256sum "$backup_dir/database.dump" "$backup_dir/data.tar.gz" > "$backup_dir/SHA256SUMS"
systemctl start tcm-api tcm-research tcm-queues
```

逐条确认退出码；任何一步失败都不要把该备份登记为成功。云功能未启用时只恢复此前实际运行的服务。备份应加密并复制到独立存储；凭据通过单独的秘密管理渠道备份，不与普通工件混存。

恢复到隔离服务器或新空库：先校验 SHA256SUMS，再以 PG16/pgvector 建空库，通过 `pg_restore --exit-on-error --no-owner --no-privileges -U tcm -d tcm_platform` 恢复 dump，将 data.tar.gz 恢复到 `/var/lib` 并确保 tcm 权限；恢复对应代码，运行迁移并执行第 9 节验收。恢复时应用服务保持停止，不覆盖仍在运行的数据库/文件。整套备份恢复演练完成前，不宣称具备灾难恢复能力。

升级：固定新提交 → 构建并检查依赖 → 维护窗口一致性备份 → 停服务 → 迁移 → 更新静态文件 → 启动与验收。迁移失败保持维护状态，排查后恢复同一备份；不要盲目 alembic downgrade。代码回退不等于数据回退，需确认 schema 兼容性。知识活动版本可通过 Release Snapshot 切回，但它不能替代数据库与文件备份。

## 11. 公网生产部署前的缺口

需要另行实现并验收：服务器账号认证与权限隔离、服务器凭据存储、适配远程 HTTPS 的 Host/Origin/会话策略、长期登录与访问码交接、受监控的统一 Worker 调度、容量/并发测试和自动备份恢复。反向代理强行改写 Host 并暴露公网，会把本机管理员能力暴露到远程，不构成这些能力的实现。
