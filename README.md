# 工业设备故障树智能生成系统

针对一段工业文本，用户给出顶事件，系统基于 LightRAG 自动抽取实体与因果关系，构建知识图谱并生成故障树（支持与门 AND / 或门 OR）。

## 项目结构

```
.
├── backend/          # LightRAG 后端（FastAPI，入口 python -m lightrag.api.lightrag_server，端口 9621）
│   └── lightrag/     #   RAG / 知识图谱 / 故障树生成核心代码
├── frontend/         # React Web 管理界面（含内置 Vue 故障树编辑器 fault-tree-app）
├── frontend-vue/     # 早期独立 Vue 原型（fault-tree-ui，已停止演进，暂不部署）
├── docs/             # 学习文档、问题清单
├── Dockerfile        # 单镜像构建（前端 bun + 后端 uv，多阶段）
├── docker-compose.yml
└── railway.json      # Railway 部署配置（DOCKERFILE builder）
```

- **前端**：`frontend/` 是当前主界面，Vite 多入口构建（`main` React + `faultTree` Vue），产物输出到 `backend/lightrag/api/webui`，由后端以静态资源挂载在 `/webui`。
- **后端**：`backend/` 是 HKUDS/LightRAG 的分支，仅拆出了原 `lightrag_webui` 作为 `frontend/`，内部实现保持上游原样。

## 本地开发

### 后端

```bash
cd backend
# 首次：安装依赖（uv 或 conda + pip 均可）
uv sync --extra api --extra offline
# 或使用已有 conda 环境做可编辑安装：
#   uv pip install -e backend/   （在仓库根目录执行）

# 配置环境变量（复制 .env.example 为 .env 并填入 LLM / Embedding 密钥）
# 启动
python -m lightrag.api.lightrag_server   # 监听 0.0.0.0:9621
```

### 前端

```bash
cd frontend
bun install --frozen-lockfile
bun run dev          # 监听 5173，代理到后端 9621
```

构建生产资源（写入后端静态目录）：

```bash
cd frontend && bun run build
```

## 部署（Docker / Railway）

根目录 `Dockerfile` 用多阶段构建，产出包含后端 + 内置 Web 界面的单镜像；`railway.json` 已指定 DOCKERFILE builder 与 `/health` 健康检查。

```bash
docker compose up --build
```

需配置的环境变量见后端 `.env`（`LLM_BINDING_*`、`EMBEDDING_BINDING_*`、本地存储后端等）；部署时由 Railway 注入 `PORT`，数据目录挂载到 `/app/data` 以实现持久化。
