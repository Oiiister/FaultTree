# 华为云 Nexent 团队共享部署方案

## 0. 文档说明

**目的**：在华为云上部署**一套** Nexent 实例，让团队成员通过邀请码注册账号、加入同一租户与用户组，共同使用同一批智能体、知识库和模型配置。

**先读这一段（决定方案对错的关键）**：

邀请码不是离线口令，而是保存在实例数据库里的一条记录。注册时浏览器请求的是"这套实例"的后端，后端在自己的数据库里校验邀请码，并在自己的 Supabase 里创建账号。因此：

- 团队必须共用**一套**实例。每人各自本地部署一套，再互相发邀请码，永远不会成功，这与网络是否互通无关。
- 团队成员只需要浏览器、实例地址和邀请码，本地不需要部署任何东西。
- 反过来说，一旦共用同一套实例，邀请码、用户组、知识库、智能体天然互通。

**适用范围**：单台华为云 ECS + Docker Compose 部署，适合团队与小规模生产。需要高可用时走 CCE/Kubernetes，见附录 D。

**文档中的路径与变量名**均来自仓库 `deploy/` 目录下的实际脚本与 compose 文件；如果你部署的版本与此不同，以 `deploy/env/.env.example` 和 `deploy/docker/compose/` 为准。

---

## 1. 方案总览

### 1.1 访问链路

```
团队成员浏览器
   |  https://nexent.example.com  (443)
   v
华为云安全组  -->  ECS 上的 Nginx（TLS 终结）
                      |  proxy_pass http://127.0.0.1:3000
                      v
                 nexent-web（前端，3000）
                      |  内部 Docker 网络 nexent_network
                      v
   nexent-config(5010) / nexent-runtime(5014) / nexent-mcp(5011,5015)
   nexent-northbound(5013) / nexent-data-process(5012)
                      |
                      v
   nexent-postgresql  nexent-elasticsearch  nexent-redis  nexent-minio
   supabase-kong + supabase-auth + supabase-db-mini（认证与账号）
```

### 1.2 组件与端口

| 组件组 | 容器 | 作用 | 容器端口 | 生产环境对外 |
|---|---|---|---|---|
| infrastructure | nexent-postgresql | 业务库：租户、用户、用户组、邀请码、智能体、会话、知识库元数据 | 5432 | 否 |
| infrastructure | nexent-elasticsearch | 全文索引与向量检索 | 9200 | 否 |
| infrastructure | nexent-redis | 缓存、分布式锁、任务队列 | 6379 | 否 |
| infrastructure | nexent-minio | 对象存储：知识库原始文件、生成产物 | 9000 / 9001 | 否 |
| application | nexent-config | 配置与主 API，启动时执行 SQL 迁移 | 5010 | 否 |
| application | nexent-runtime | 智能体运行时，负责创建沙箱容器 | 5014 | 否 |
| application | nexent-mcp | MCP 工具与工具管理 | 5011 / 5015 | 否 |
| application | nexent-northbound | 北向 API（外部 A2A 集成） | 5013 | 可选 |
| application | nexent-web | Web 前端 | 3000 | 是（经 Nginx） |
| data-process | nexent-data-process | 文档解析、分片、向量化 | 5012 | 否 |
| supabase | supabase-kong / supabase-auth / supabase-db-mini | 用户认证、注册、登录 | 8000 / 9999 / 5436 | 否 |
| terminal（可选） | nexent-openssh-server | 智能体 SSH 终端工具 | 22 | 否 |
| monitoring（可选） | otel-collector 等 | 观测组件 | 4317/4318 等 | 否 |

### 1.3 端口发布规则（务必理解）

部署脚本按 `--port-policy` 选择不同的 compose 文件：

- `production` 使用 `deploy/docker/compose/docker-compose.prod.yml`，其中只发布 `3000:3000`（Web）和 `5013:5013`（北向 API）；Supabase 文件 `docker-compose-supabase.prod.yml` 不发布任何端口。
- `development` 使用 `docker-compose.yml`，会额外发布 ES(9210/9310)、PostgreSQL(5434)、Redis(6379)、MinIO(9010/9011) 以及各服务调试端口。

两条硬性要求：

1. 云上实例必须使用 `production`。`development` 只适合本机排障，绝不能在公网机器上使用。
2. 生产文件里的 `3000` 是硬编码的，不要直接修改 compose 文件（升级会被覆盖）。对外端口一律由 Nginx 和华为云安全组控制。

---

## 2. 资源规划

### 2.1 ECS 规格

| 项目 | 最低 | 推荐（团队 3～10 人） | 说明 |
|---|---|---|---|
| vCPU | 4 | 8 | 模型推理在外部，本地主要是服务与索引 |
| 内存 | 8 GiB | 16 GiB | 内存不足最先表现为 ES 或数据处理容器被杀 |
| 系统盘 | 40 GiB | 60 GiB | 承载 Docker 镜像与容器层 |
| 数据盘 | 40 GiB | 100 GiB 起 | 承载所有持久化数据，建议通用型 SSD 或超高 IO |
| 架构 | x86_64 | x86_64 或鲲鹏 ARM64 | 应用镜像同时提供两种架构 |
| 操作系统 | Ubuntu 22.04 LTS | Ubuntu 22.04 LTS | 脚本对 apt/Docker 安装最省事；openEuler/HCE 需改用 yum |
| 带宽 | 5 Mbps | 10 Mbps 或按流量计费 | 知识库上传大文件时带宽是瓶颈 |
| 域名 | 可选 | 强烈建议 | 邀请链接、认证回调、分享链接都依赖固定地址 |

### 2.2 内存分配参考（16 GiB）

| 用途 | 建议 |
|---|---|
| Elasticsearch 堆 | `ES_JAVA_OPTS="-Xms4g -Xmx4g"`；8 GiB 机器保持默认 `-Xms2g -Xmx2g` |
| 两个 PostgreSQL（业务库 + Supabase 认证库） | 共享缓冲各 512 MiB～1 GiB |
| Web（Node）+ 各 Python 服务 | 合计 2～4 GiB |
| Docker 沙箱 | 按并发数量估算；`lightweight` 为默认，`full` 更占空间，`disabled` 最省 |

### 2.3 容量估算

MinIO 保存知识库原始文件，Elasticsearch 保存分片文本与向量，两者叠加通常是原始文档体积的 2～4 倍。除此之外还要给 Elasticsearch 的磁盘水位留出余量，见 5.6。

---

## 3. 实施步骤

### 步骤 1：创建 ECS、数据盘与安全组

1. 购买 ECS：镜像选 Ubuntu 22.04 LTS，登录方式用密钥对，不要用密码登录；绑定弹性公网 IP。
2. 购买数据盘（EVS，通用型 SSD 或超高 IO）并挂载到该 ECS。
3. 配置安全组入方向规则，只放行必要端口：

| 端口 | 协议 | 来源 | 用途 |
|---|---|---|---|
| 22 | TCP | 管理员固定公网 IP 或跳板机 | SSH 运维，禁止 `0.0.0.0/0` |
| 443 | TCP | `0.0.0.0/0` | HTTPS 入口（经 Nginx） |
| 80 | TCP | `0.0.0.0/0` | 跳转到 HTTPS，也可不开 |
| 3000 | TCP | 管理员 IP 或内网 | 仅在尚未配置 Nginx 时临时开放 |
| 5013 | TCP | 需要对接 A2A 的来源 | 北向 API，可选，不用就别开 |

绝对不要放通的端口：5434 / 5436（PostgreSQL）、6379（Redis）、9200 / 9210 / 9300 / 9310（Elasticsearch）、9000 / 9001 / 9010 / 9011（MinIO）、8000 / 8443（Supabase Kong）、5555（Flower）、8265（Ray Dashboard）。这些服务只应在容器内网 `nexent_network` 中互通。

出方向需要放通，否则无法拉取镜像、无法调用外部模型 API。若必须经过代理，在 `deploy/env/.env` 中配置 `HTTP_PROXY` / `HTTPS_PROXY` / `NO_PROXY`。

### 步骤 2：主机初始化

```bash
# 1) Elasticsearch 必需的内核参数（不设置会导致 ES 启动失败）
sudo sysctl -w vm.max_map_count=262144
echo 'vm.max_map_count=262144' | sudo tee -a /etc/sysctl.conf
sudo sysctl -p

# 2) 挂载数据盘（示例盘符 /dev/vdb，请以实际为准）
sudo mkfs.ext4 /dev/vdb
sudo mkdir -p /data
echo '/dev/vdb /data ext4 defaults,noatime 0 0' | sudo tee -a /etc/fstab
sudo mount -a
df -h /data

# 3) 目录规划：数据、用户文件、备份、Docker 数据目录分开
sudo mkdir -p /data/nexent-data /data/nexent-user /data/nexent-backup /data/docker
```

安装 Docker 24+ 与 Compose v2（Ubuntu）：

```bash
sudo apt-get update
sudo apt-get install -y docker.io docker-compose-v2
sudo systemctl enable --now docker
```

把 Docker 数据目录放到数据盘，并配置华为云容器镜像服务（SWR）提供的镜像加速地址：

```bash
sudo mkdir -p /etc/docker
sudo tee /etc/docker/daemon.json >/dev/null <<'JSON'
{
  "data-root": "/data/docker",
  "registry-mirrors": ["https://<SWR 控制台提供的镜像加速地址>"],
  "log-driver": "json-file",
  "log-opts": { "max-size": "100m", "max-file": "3" }
}
JSON
sudo systemctl restart docker
docker info | grep -A1 "Docker Root Dir"
```

注意：镜像层和 Docker 命名卷（`nexent-agent-workspace`、`db-config` 等）默认落在 `/var/lib/docker`，也就是系统盘。如果 Docker 已经装好且已有数据，修改 `data-root` 前必须先停 Docker 并迁移 `/var/lib/docker`，否则旧镜像和容器会不可见。

### 步骤 3：获取代码

```bash
cd /data
git clone https://github.com/ModelEngine-Group/nexent.git
cd nexent
```

服务器无法访问公网镜像仓库时，使用 GitHub Actions 产出的离线部署包（`nexent-<version>-amd64.zip`），或先把镜像推送到华为云 SWR：

```bash
bash deploy.sh --push-images --image-registry-prefix swr.cn-north-4.myhuaweicloud.com/nexent docker
```

### 步骤 4：配置 deploy/env/.env

首次部署时脚本会从 `deploy/env/.env.example` 生成 `deploy/env/.env`，此后每次部署都保留已有值并追加新增变量。

必须修改的项（公网实例的默认值不可用）：

| 变量 | 建议值 | 说明 |
|---|---|---|
| `ROOT_DIR` | `/data/nexent-data` | 所有持久化数据的根目录，部署前确定，之后不要改 |
| `NEXENT_USER_DIR` | `/data/nexent-user` | 用户上传与生成文件的目录。默认是 `$HOME/nexent`；若把仓库克隆到 `/root/nexent` 会与该目录重合，建议显式指定 |
| `NEXENT_SUPER_ADMIN_PASSWORD` | 强密码 | 超级管理员 `suadmin@nexent.com` 的初始密码，默认 `Nexent@123` |
| `ELASTIC_PASSWORD` | 强密码 | Elasticsearch 密码 |
| `NEXENT_POSTGRES_PASSWORD` | 强密码 | 业务库密码 |
| `MINIO_ROOT_PASSWORD` | 强密码 | MinIO 管理密码 |
| `SUPABASE_POSTGRES_PASSWORD` | 强密码 | Supabase 认证库密码 |
| `DASHBOARD_PASSWORD` | 强密码 | Supabase 控制台密码 |

需要按公网域名调整的项：

```dotenv
SITE_URL=https://nexent.example.com
API_EXTERNAL_URL=https://nexent.example.com
OAUTH_CALLBACK_BASE_URL=https://nexent.example.com
SHARE_BASE_URL=https://nexent.example.com
# 仅在需要外部 A2A 客户端时才设置
NORTHBOUND_EXTERNAL_URL=https://nexent.example.com/api
```

与团队注册直接相关的项：

```dotenv
DISABLE_SIGNUP=false          # 必须为 false，否则注册入口被关闭
ENABLE_EMAIL_SIGNUP=true      # 允许邮箱注册
ENABLE_EMAIL_AUTOCONFIRM=true # 默认开启：注册不需要邮件服务器即可生效
```

可按团队规模调整的项：

| 变量 | 默认 | 说明 |
|---|---|---|
| `MAX_USERS_PER_TENANT` | 10000 | 超过配额注册会返回 429 |
| `MAX_GROUPS_PER_TENANT` | 1000 | 用户组上限 |
| `MAX_KNOWLEDGE_BASES_PER_USER` | 10 | 每人知识库数量 |
| `MAX_KNOWLEDGE_FILE_SIZE_MB` | 100 | 单文件上传上限，需与 Nginx `client_max_body_size` 对齐 |
| `FILE_UPLOAD_SIZE_LIMIT` | 10 | Web 端上传限制 |
| `RUNTIME_AGENT_ID_MAX_CONCURRENT_RUNS` | 50 | 同一智能体并发运行上限 |
| `RUNTIME_AGENT_THREAD_MAX_WORKERS` | 200 | 运行时线程池，多人并发时关注 |
| `ES_JAVA_OPTS` | `-Xms2g -Xmx2g` | Elasticsearch 堆，不超过物理内存 50% |

关于 `INVITE_CODE`：模板中的 `INVITE_CODE=nexent2025` 是历史遗留变量，当前代码中 `verify_invite_code` 已没有生产调用方，注册校验全部走数据库里的租户邀请码记录。既然实例要暴露在公网，把它改成随机值没有坏处，但它不是准入闸门——真正的闸门是租户管理员签发的邀请码。

关于自动生成的密钥：`MINIO_ACCESS_KEY`、`MINIO_SECRET_KEY`、`ELASTICSEARCH_API_KEY`、`JWT_SECRET` 等由部署脚本生成并写入 `.env`。不要手工改动 `JWT_SECRET`，它一旦变化，所有已登录用户的会话会立即失效。

### 步骤 5：执行部署

```bash
cd /data/nexent
bash deploy.sh docker \
  --components infrastructure,application,data-process,supabase \
  --port-policy production \
  --image-source mainland \
  --root-dir /data/nexent-data \
  --defaults
```

参数说明：

- `--components`：`supabase` 必须包含，它是注册、登录、租户与用户组的基础，缺了它邀请码流程走不通。
- `--port-policy production`：只发布 Web 与北向 API 端口。
- `--image-source mainland`：使用中国大陆镜像源；如果已把镜像推送到自有仓库，改用 `--image-registry-prefix`。
- `--root-dir`：把持久化数据放到数据盘。
- `--defaults`：非交互部署，复用已保存的 `deploy/docker/deploy.options`。首次部署想逐项确认可换成 `--config`。

部署完成后验证：

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker logs nexent-config --tail 50          # 确认 SQL 迁移执行成功
curl -I http://127.0.0.1:3000               # 期望 200 或 307
```

### 步骤 6：接入 HTTPS

两种做法，按你部署的版本选择。

A. 外挂 Nginx（当前版本可用，推荐）

在华为云 SSL 证书管理申请免费 DV 证书，下载 Nginx 格式，放到 ECS 上，然后配置：

```nginx
server {
    listen 80;
    server_name nexent.example.com;
    return 301 https://$host$request_uri;
}

server {
    listen 443 ssl;
    server_name nexent.example.com;

    ssl_certificate     /etc/nginx/ssl/nexent.crt;
    ssl_certificate_key /etc/nginx/ssl/nexent.key;

    # 需要不小于 MAX_KNOWLEDGE_FILE_SIZE_MB
    client_max_body_size 200m;

    location / {
        proxy_pass http://127.0.0.1:3000;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;      # 对话流式输出依赖 WebSocket
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        proxy_read_timeout 3600s;
        proxy_send_timeout 3600s;
    }
}
```

验证通过后，把安全组里的 3000 端口关闭，只保留 443。

B. 内置 Nginx（需要较新版本）

较新版本在部署时自带 Nginx 容器，可只用一条参数启用，HTTPS 走独立端口 3100，原 HTTP 3000 保持不变：

```bash
bash deploy.sh docker --defaults --https-mode custom \
  --https-cert-file /etc/nginx/ssl/nexent.crt \
  --https-key-file  /etc/nginx/ssl/nexent.key
```

启用后必须同步把 `SITE_URL` 改成 `https://nexent.example.com:3100`。部署前先确认你的版本支持该参数：在仓库根目录执行 `grep -rn "https-mode" deploy/`，没有输出说明不支持，而旧版本会静默忽略未知参数，不报错却也不生效。3100 不是标准端口，若希望用户不带端口访问，需要在华为云 ELB 上把 443 转发到 3100，或在宿主机做 iptables DNAT——安全组只能放行，不能做端口映射。

### 步骤 7：初始化管理员与租户

1. 浏览器打开 `http://<EIP>:3000`，配好 HTTPS 后改用域名。
2. 用 `suadmin@nexent.com` 登录，密码取部署终端输出或 `.env` 中的 `NEXENT_SUPER_ADMIN_PASSWORD`。
3. 进入「租户资源」，创建租户，再创建该租户的管理员账号。
4. 退出，用租户管理员账号登录。超级管理员只负责权限管理，不能开发智能体或建知识库。

角色说明：`SU`（超级管理员，仅权限管理）、`ADMIN`（租户管理员）、`DEV`（开发者）、`USER`（普通用户）、`ASSET_OWNER`（可选，默认关闭）。建议每位团队成员使用独立账号，不要共用。

### 步骤 8：开通团队访问（邀请码）

见第 4 章。

### 步骤 9：验收

- 团队成员能在自己的网络环境打开 HTTPS 地址并完成注册；
- 注册后能看到你共享的智能体与知识库；
- 知识库上传一个 10 MiB 左右的文档能正常解析；
- 连续多轮对话不中断，验证 WebSocket 与超时配置；
- `docker ps` 中所有容器状态为 healthy 或 Up；
- 数据盘占用、内存占用有监控（华为云 CES 或简单脚本）。

---

## 4. 团队访问与邀请码注册

### 4.1 准入模型

| 环节 | 由谁控制 | 说明 |
|---|---|---|
| 实例地址 | 部署方 | 谁拿到地址都能打开登录页 |
| 能否注册 | 租户管理员签发的邀请码 | 没有邀请码无法注册，这是唯一的准入闸门 |
| 注册后属于哪个租户与用户组 | 邀请码本身携带 | 由创建邀请码时选择的用户组决定 |
| 能用哪些资源 | 角色与用户组权限 | 同租户内按组共享智能体、知识库 |

因为注册不需要邮箱验证码（`ENABLE_EMAIL_AUTOCONFIRM=true`），邀请码的次数与有效期就是唯一防线，请按人数精确设置。

### 4.2 管理员操作

1. 用租户管理员账号登录，进入「租户资源」。
2. 先在「用户组」中建好团队用户组，例如 `team-core`。
3. 进入「邀请码」，点击新建，按下表填写字段后保存。
4. 把实例地址与邀请码一起发给成员。只发邀请码是最常见的沟通事故。

### 4.3 邀请码字段

| 字段 | 说明 | 建议 |
|---|---|---|
| `code_type` 类型 | `USER_INVITE` 普通用户、`DEV_INVITE` 开发者、`ADMIN_INVITE` 租户管理员（仅超管可建） | 一般选 `USER_INVITE` |
| `invitation_code` 邀请码 | 自定义，仅限大写字母与数字；留空则自动生成 | 留空自动生成更省事 |
| `capacity` 可用次数 | 默认 1，用满即失效 | 按实际人数设置，宁小勿大 |
| `group_ids` 用户组 | 注册后自动加入的用户组 | 选团队组 |
| `expiry_date` 有效期 | 到期后不可用 | 建议设置，例如 7 天 |

### 4.4 成员操作

1. 在浏览器打开管理员给的共享实例地址，不是自己的 localhost。
2. 点击注册，填写邮箱、密码、邀请码。
3. 密码要求：至少 8 位，且同时包含大写字母、小写字母和数字，否则会被拒绝。
4. 注册成功即自动登录，并且已经在指定的用户组中。

### 4.5 排障对照表

| 现象 | 最可能的原因 | 处理方式 |
|---|---|---|
| 提示"邀请码错误" | 成员打开的是他自己本地部署的页面 | 打开浏览器开发者工具，查看 `POST /api/user/signup` 的 host 是否为共享实例域名 |
| 提示"邀请码错误" | 邀请码已用满、已过期或状态不是 `IN_USE` | 在邀请码列表核对已用次数、容量与有效期 |
| 提示"邀请码错误" | 类型不匹配，例如用 `ADMIN_INVITE` 在普通注册入口使用 | 改用 `USER_INVITE` |
| 提示"请输入邀请码" | 注册表单未填邀请码 | 邀请码是必填项 |
| 注册返回 429 | 触达租户配额 | 调整 `.env` 中的 `MAX_*` 上限后重启 `nexent-config` |
| 注册成功但无法登录 | 未部署 `supabase` 组件或认证容器异常 | 检查 `supabase-auth`、`supabase-kong` 容器与 `.env` 中的 `DISABLE_SIGNUP`、`SITE_URL` |
| 页面能打开但操作报错 | Nginx 未正确转发 WebSocket | 检查 Nginx 的 `Upgrade`、`Connection` 头与超时设置 |

---

## 5. 数据库与存储注意事项（重点）

### 5.1 数据落盘位置总览

下表是恢复和扩容时唯一需要记住的清单。`$ROOT_DIR` 指 `.env` 中的 `ROOT_DIR`，本方案为 `/data/nexent-data`。

| 数据 | 宿主机路径 | 容器内路径 | 内容 | 丢失后果 |
|---|---|---|---|---|
| 业务 PostgreSQL | `$ROOT_DIR/postgresql/data` | `/var/lib/postgresql/data` | 租户、用户、用户组、邀请码、智能体配置、会话历史、知识库元数据 | 全部业务数据丢失 |
| Supabase PostgreSQL | `$ROOT_DIR/volumes/db/data` | `/var/lib/postgresql/data` | `auth.users`、`auth.identities`、会话等认证数据 | 所有人无法登录 |
| Elasticsearch | `$ROOT_DIR/elasticsearch` | `/usr/share/elasticsearch/data` | 知识库分片文本与向量索引 | 检索失效，文档需重新解析 |
| MinIO | `$ROOT_DIR/minio/data` | `/data` | 知识库原始文件、生成产物、预览文件 | 文件丢失，数据库仍有记录，形成脏数据 |
| Redis | `$ROOT_DIR/redis` | `/data` | 缓存、分布式锁、Celery 队列（AOF 持久化） | 可接受丢失；丢失后运行中的任务状态可能不一致 |
| 用户文件 | `NEXENT_USER_DIR`（默认 `$HOME/nexent`） | `/mnt/nexent` | 用户上传与生成的文件、工作目录 | 用户文件丢失 |
| 技能与配置 | `$ROOT_DIR` 下的 `skills`、`memory-provider-plugins`、`project-config`、`openssh-server/ssh-keys` | 多处 | 技能包、记忆插件、项目配置、SSH 密钥 | 部分功能不可用 |
| 日志 | `$ROOT_DIR/logs` | `/mnt/nexent-data/logs` | 服务日志 | 仅影响排查 |
| Docker 命名卷 | `/data/docker/volumes` 下的 `nexent-agent-workspace`、`db-config` | — | 沙箱工作区、Supabase 数据库配置 | 沙箱产物与数据库配置丢失 |
| Supabase 接口配置 | `$ROOT_DIR/volumes/api/kong.yml` 等 | — | Kong 路由、Pooler 配置 | 认证链路异常 |

### 5.2 一致性：必须一起备份的三件套

业务 PostgreSQL、Supabase PostgreSQL、MinIO 是同一个逻辑数据集，必须同时备份、同时恢复：

- 只恢复业务库：知识库有记录、文件却不存在；
- 只恢复 MinIO：文件存在、数据库里没有索引与权限记录；
- 只恢复其中一个 PostgreSQL：会出现有租户记录但没有认证用户，用户无法登录。

注意：认证数据位于独立的第二个 PostgreSQL 实例（容器 `supabase-db-mini`），不是业务库，两边要落在同一时间点。

### 5.3 冷备前必须停服务

PostgreSQL、Elasticsearch、MinIO 的数据目录不支持在线直接拷贝。运行中拷贝得到的是崩溃不一致的副本，典型后果是 PostgreSQL 启动报错或 Elasticsearch 分片损坏。

```bash
# 停掉全部 Nexent 与 Supabase 容器（最简可靠的方式）
docker ps --format '{{.Names}}' | grep -E '^(nexent-|supabase-)' | xargs -r docker stop

# 拷贝到独立位置，不要放在同一块盘
cp -a /data/nexent-data /data/nexent-backup/nexent-data-$(date +%F)
cp -a /data/nexent-user /data/nexent-backup/nexent-user-$(date +%F)

# 重新启动
cd /data/nexent && bash deploy.sh docker --defaults
```

### 5.4 逻辑备份（不停服务，可与快照互补）

```bash
# 业务库
docker exec nexent-postgresql pg_dump -U root -d nexent -Fc -f /tmp/nexent.dump
docker cp nexent-postgresql:/tmp/nexent.dump /data/nexent-backup/nexent-$(date +%F).dump

# 认证库（包含 roles、auth schema 等）
docker exec supabase-db-mini pg_dumpall -U postgres > /data/nexent-backup/supabase-$(date +%F).sql
```

逻辑备份期间数据库仍在写入，因此它覆盖不了 MinIO 中的文件对象；文件对象请用对象存储方式同步，见 5.8。

### 5.5 数据库主版本不可跨版本复用

- 业务库镜像为 `postgres:15-alpine`，国内源为 `docker.m.daocloud.io/postgres:15-alpine`；
- 认证库镜像为 `supabase/postgres:15.8.1.060`。

PostgreSQL 的数据目录不能跨主版本直接复用。升级镜像前必须先做逻辑 dump，升级后用同版本恢复，或保持镜像版本不变。Elasticsearch 同理，`8.x` 的索引不要跨大版本回滚。

### 5.6 Elasticsearch 单节点与磁盘水位

- 生产配置是单节点（`discovery.type: single-node`），没有副本，节点故障即检索不可用；
- 磁盘水位默认 `85% / 90% / 95%`，对应 `ES_DISK_WATERMARK_LOW/HIGH/FLOOD_STAGE`。数据盘使用率超过高水位会限制分片分配，到达 flood 水位后索引转为只读，表现为上传成功但检索不到、写入报错；
- 请给数据盘预留至少 30% 余量；需要放宽水位时，先扩盘再调参数，不要反过来；
- `ES_JAVA_OPTS` 的堆不要超过物理内存的 50%。

### 5.7 连接数与并发

默认 `max_connections` 为 100，而 `nexent-config`、`nexent-runtime`、`nexent-northbound`、`nexent-mcp`、`nexent-data-process` 各自持有连接池。团队人数多或并发对话高时，先观察再调整：

```bash
docker exec nexent-postgresql psql -U root -d nexent -c "SELECT count(*) FROM pg_stat_activity;"
docker exec nexent-postgresql psql -U root -d nexent -c "SHOW max_connections;"
```

优先通过 `.env` 中的 `RUNTIME_AGENT_ID_MAX_CONCURRENT_RUNS`、`RUNTIME_AGENT_THREAD_MAX_WORKERS` 控制并发，而不是无限放大数据库连接数。

### 5.8 备份策略建议

| 层次 | 手段 | 频率 | 说明 |
|---|---|---|---|
| 块级 | 华为云 EVS 快照或 CBR 备份策略 | 每天 1 次，保留 7～30 天 | 崩溃一致，PostgreSQL 通常可自动恢复；Elasticsearch 可能需重建索引 |
| 逻辑 | `pg_dump` 加 `pg_dumpall`（见 5.4） | 每天 1 次 | 可精确恢复到某个库，体积小 |
| 文件 | 把 `/data/nexent-data/minio/data` 同步到 OBS | 每天 1 次 | 用 `obsutil` 或兼容 S3 的工具做增量同步 |
| 配置 | 备份 `deploy/env/.env` 与 `NEXENT_USER_DIR` | 变更后 | `.env` 含各类密码与密钥，注意存放位置与权限 |

备份文件不要与数据放在同一块盘，也不要只放在同一台机器上。

恢复演练：至少完整演练一次业务库、认证库、MinIO 目录的三件套恢复，否则备份不具备可信度。恢复顺序建议为：先恢复两个 PostgreSQL 与 MinIO 数据目录，再启动容器，然后用 `nexent-config` 日志确认迁移无异常，最后登录验证。

### 5.9 数据盘扩容

```bash
# 先在华为云控制台对数据盘扩容，再在实例内扩展文件系统
# 若磁盘是整盘格式化（示例中 mkfs 直接作用在 /dev/vdb），只需：
sudo resize2fs /dev/vdb
# 若磁盘分了分区（/dev/vdb1），先扩容分区：
# sudo growpart /dev/vdb 1 && sudo resize2fs /dev/vdb1
df -h /data
```

扩容前先做一次快照。文件系统扩展完成后，如需放宽 Elasticsearch 水位，再修改 `.env` 中的 `ES_DISK_WATERMARK_*` 并重启 Elasticsearch。

### 5.10 密码的生效时机（容易踩坑）

- PostgreSQL、Elasticsearch：容器环境变量中的密码只在首次初始化时生效。部署完成后再改 `.env` 里的 `NEXENT_POSTGRES_PASSWORD` 或 `ELASTIC_PASSWORD`，数据库里的密码并不会跟着变，结果是服务连不上。正确做法是首次部署前就把密码定好；已部署后要改，必须进入容器修改数据库或 ES 中的实际密码，并同步 `.env`。
- MinIO：根账号密码在每次启动时读取环境变量，改 `.env` 后重启容器即可生效。
- `JWT_SECRET`：改动会使所有已登录会话失效，除非确有必要，不要改动。

### 5.11 数据库只在内网暴露

所有数据库与对象存储容器都只挂在 `nexent_network` 上，生产 compose 不发布它们的端口。任何时候都不要为了用客户端连接而把 5434、5436、6379、9200、9010 开放到公网。需要运维访问时用 SSH 隧道，并注意在 `production` 策略下宿主机本就没有发布这些端口，隧道需要先按需临时调整部署策略。

### 5.12 可选：用华为云托管数据库替代自建

理论上可以只部署 `application` 组件，把 `POSTGRES_HOST`、`ELASTICSEARCH_HOST`、`REDIS_URL`、`MINIO_ENDPOINT` 指向 RDS for PostgreSQL、CSS（Elasticsearch）、DCS（Redis）、OBS。但这条路径不在项目官方文档与测试覆盖范围内，需要自行验证：Elasticsearch 的安全认证与 API Key 创建流程、CSS 的版本兼容性、OBS 的 S3 兼容程度都会带来额外工作量。若追求高可用与免运维，优先考虑附录 D 的 Kubernetes/CCE 路线，而不是混搭托管中间件。

---

## 6. 安全基线

- 默认密码全部替换：超管密码、各类数据库密码、MinIO、Supabase 控制台；
- SSH 只允许密钥登录，安全组来源限制到固定 IP；
- 安全组遵循最小化原则，只放行 443，必要时加 22；
- 存储与数据库端口绝不对外；
- `suadmin` 只用于租户与权限管理，日常使用租户管理员账号；
- 容器挂载了宿主机的 `/var/run/docker.sock`，运行时与 MCP 需要它创建沙箱容器，这意味着容器内权限接近宿主机 root：只运行你信任的镜像，不要在这台机器上跑无关服务；
- 定期执行 `bash deploy.sh docker --defaults` 升级到新版本，包含安全修复；
- Supabase 控制台与监控组件默认只在容器内网，不要为方便而暴露。

---

## 7. 日常运维

### 7.1 状态与日志

```bash
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
docker stats --no-stream                        # 内存与 CPU 占用
docker logs nexent-config --tail 100            # 主服务
docker logs nexent-runtime --tail 100           # 运行时报错
du -sh /data/nexent-data/* /data/docker         # 各组件占用
```

容器日志使用 json-file 驱动并限制为 `max-size: 100m`、`max-file: 3`；应用日志同时落盘在 `$ROOT_DIR/logs`。

### 7.2 升级

```bash
# 1) 先备份，至少一次快照加逻辑备份
# 2) 拉新代码
cd /data/nexent && git pull
# 3) 重新部署，沿用保存的配置与数据目录
bash deploy.sh docker --defaults
# 4) 观察迁移与启动
docker logs -f nexent-config
```

数据库迁移由 `nexent-config` 启动时按 `NEXENT_SQL_STARTUP_MODE=migrate` 自动执行，脚本位于 `deploy/sql/migrations/`。不要手工修改 `deploy/sql/` 下已合并的 SQL 文件，也不要手工改 compose 文件，升级时都会被覆盖。

### 7.3 调整配额与并发

修改 `deploy/env/.env` 中的 `MAX_*`、`RUNTIME_*` 变量后，重启受影响的容器（`nexent-config`、`nexent-runtime`）即可，不需要重新部署整套。

### 7.4 卸载

```bash
bash uninstall.sh docker
```

卸载过程会询问是否删除持久化数据。默认不要删除；即使要重装，也先确认 `/data/nexent-data` 与 `/data/nexent-user` 已有备份。

---

## 8. 故障排查

| 现象 | 常见原因 | 处理 |
|---|---|---|
| Elasticsearch 启动失败，日志报 `max virtual memory areas vm.max_map_count [65530] is too low` | 未设置内核参数 | 执行步骤 2 中的 `vm.max_map_count=262144` |
| 容器被 OOM Kill | 内存不足，ES 堆过大或多组件叠加 | 降低 `ES_JAVA_OPTS`、关闭 monitoring 或 terminal 组件，或用 `--sandbox-mode disabled` |
| 上传成功但检索不到 | ES 到达磁盘水位，索引转为只读 | 扩盘或调整 `ES_DISK_WATERMARK_*`，然后确认索引恢复可写 |
| 页面能打开但对话无输出 | WebSocket 被代理切断 | 检查 Nginx 的 `Upgrade`、`Connection` 与 `proxy_read_timeout` |
| 注册返回 429 | 租户配额，用户数或知识库数超限 | 调整 `MAX_*` 后重启 `nexent-config` |
| 服务启动后连不上数据库 | 部署后修改了 PG 或 ES 密码，数据库内密码未同步 | 见 5.10，恢复原密码或进容器同步修改 |
| 磁盘快满 | MinIO 原始文件与 ES 索引同时增长 | 清理无用知识库，把文件同步到 OBS 后删除，再扩容数据盘 |
| 重新部署后数据看起来消失 | `ROOT_DIR` 被改动，指向了空目录 | 把旧目录内容拷到新路径，或在 `.env` 中改回原 `ROOT_DIR` |
| 日志报端口冲突 | 与宿主机上其他服务端口冲突 | 释放端口，或调整 `.env` 中对应端口变量 |

---

## 9. 上线检查清单

- [ ] ECS 规格不低于 8 vCPU / 16 GiB，数据盘已挂载到 `/data` 并写入 `/etc/fstab`
- [ ] `vm.max_map_count=262144` 已持久化
- [ ] Docker `data-root` 指向数据盘
- [ ] 安全组只放行 22（限制来源）与 443，其余端口全部关闭
- [ ] `.env` 中所有默认密码已替换为强密码
- [ ] `ROOT_DIR=/data/nexent-data`、`NEXENT_USER_DIR=/data/nexent-user` 在部署前设定
- [ ] 部署组件包含 `supabase`
- [ ] 端口策略为 `production`
- [ ] HTTPS 已配置，`SITE_URL`、`API_EXTERNAL_URL`、`SHARE_BASE_URL` 已改为公网地址
- [ ] `DISABLE_SIGNUP=false`、`ENABLE_EMAIL_SIGNUP=true`
- [ ] `suadmin` 已创建租户与租户管理员，日常使用租户管理员账号
- [ ] 团队用户组已建好，邀请码已签发并核对过次数与有效期
- [ ] 已完成一次业务库、认证库、MinIO 的备份并演练过恢复
- [ ] EVS 快照或 CBR 策略已开启

---

## 附录 A：完整命令速查

```bash
# 主机准备
sudo sysctl -w vm.max_map_count=262144
sudo mkfs.ext4 /dev/vdb && sudo mkdir -p /data
echo '/dev/vdb /data ext4 defaults,noatime 0 0' | sudo tee -a /etc/fstab && sudo mount -a
sudo mkdir -p /data/nexent-data /data/nexent-user /data/nexent-backup /data/docker

# Docker
sudo apt-get install -y docker.io docker-compose-v2
# 写入 /etc/docker/daemon.json（data-root 与 registry-mirrors）后：
sudo systemctl restart docker

# 部署
cd /data/nexent
bash deploy.sh docker \
  --components infrastructure,application,data-process,supabase \
  --port-policy production --image-source mainland \
  --root-dir /data/nexent-data --defaults

# 状态
docker ps --format 'table {{.Names}}\t{{.Status}}\t{{.Ports}}'
ss -ltnp | grep -E ':(3000|5013)\b'

# 停服冷备
docker ps --format '{{.Names}}' | grep -E '^(nexent-|supabase-)' | xargs -r docker stop
cp -a /data/nexent-data /data/nexent-backup/nexent-data-$(date +%F)
cp -a /data/nexent-user /data/nexent-backup/nexent-user-$(date +%F)
bash deploy.sh docker --defaults

# 逻辑备份
docker exec nexent-postgresql pg_dump -U root -d nexent -Fc -f /tmp/nexent.dump
docker cp nexent-postgresql:/tmp/nexent.dump /data/nexent-backup/nexent-$(date +%F).dump
docker exec supabase-db-mini pg_dumpall -U postgres > /data/nexent-backup/supabase-$(date +%F).sql

# 升级与卸载
git pull && bash deploy.sh docker --defaults
bash uninstall.sh docker
```

## 附录 B：.env 关键片段模板

```dotenv
# ---- 存储路径 ----
ROOT_DIR=/data/nexent-data
NEXENT_USER_DIR=/data/nexent-user

# ---- 凭证（首次部署前设定，部署后修改不会同步到数据库）----
NEXENT_SUPER_ADMIN_PASSWORD=<强密码>
ELASTIC_PASSWORD=<强密码>
NEXENT_POSTGRES_PASSWORD=<强密码>
MINIO_ROOT_PASSWORD=<强密码>
SUPABASE_POSTGRES_PASSWORD=<强密码>
DASHBOARD_PASSWORD=<强密码>

# ---- 公网地址 ----
SITE_URL=https://nexent.example.com
API_EXTERNAL_URL=https://nexent.example.com
OAUTH_CALLBACK_BASE_URL=https://nexent.example.com
SHARE_BASE_URL=https://nexent.example.com

# ---- 注册开关 ----
DISABLE_SIGNUP=false
ENABLE_EMAIL_SIGNUP=true
ENABLE_EMAIL_AUTOCONFIRM=true

# ---- Elasticsearch ----
ES_JAVA_OPTS="-Xms4g -Xmx4g"
ES_DISK_WATERMARK_LOW=85%
ES_DISK_WATERMARK_HIGH=90%
ES_DISK_WATERMARK_FLOOD_STAGE=95%

# ---- 团队配额与并发 ----
MAX_USERS_PER_TENANT=10000
MAX_GROUPS_PER_TENANT=1000
MAX_KNOWLEDGE_BASES_PER_USER=10
MAX_KNOWLEDGE_FILE_SIZE_MB=100
FILE_UPLOAD_SIZE_LIMIT=10
RUNTIME_AGENT_ID_MAX_CONCURRENT_RUNS=50
RUNTIME_AGENT_THREAD_MAX_WORKERS=200
```

## 附录 C：Nginx 站点配置

见步骤 6 的 A 方案。三个要点重复一次：`client_max_body_size` 不小于 `MAX_KNOWLEDGE_FILE_SIZE_MB`；必须保留 WebSocket 的 `Upgrade` 与 `Connection` 头；`proxy_read_timeout` 要足够长，否则流式输出会被中断。

## 附录 D：Kubernetes 与 CCE 路线简述

需要高可用、弹性伸缩或托管运维时走华为云 CCE，集群版本 1.24 以上，推荐 1.28 以上：

```bash
# 先确认集群存储类，CCE 常见为 csi-disk
kubectl get sc

# 镜像需先推送到 SWR
bash deploy.sh --push-images --image-registry-prefix swr.cn-north-4.myhuaweicloud.com/nexent k8s

bash deploy.sh k8s \
  --persistence-mode dynamic --storage-class csi-disk \
  --image-registry-prefix swr.cn-north-4.myhuaweicloud.com/nexent \
  --defaults
```

Kubernetes 会先部署 `nexent-infrastructure`（ES、PostgreSQL、Redis、MinIO），待基础组件与 Elasticsearch API Key 就绪后再部署应用侧 `nexent`。生产模式下内部服务使用 ClusterIP，仅暴露入口；对外访问建议使用华为云 ELB 加 Ingress。数据持久化依赖 StorageClass（EVS），备份策略需单独配置云硬盘快照。

若部署的版本自带内置 HTTPS 能力，Kubernetes 侧对应 NodePort 31000，可通过 `NEXENT_HTTPS_PORT` 调整，前提同样是先确认版本支持。
