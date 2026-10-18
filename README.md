# 工业设备故障树智能生成系统

针对一段工业文本，用户给定顶事件，系统基于 **LightRAG** 自动抽取故障事件实体与因果关系，构建知识图谱，并生成带 **AND / OR 逻辑门** 的故障树（Fault Tree）。

项目同时是华为云 ICT 创新赛「智能体 + 知识工程」赛题的落地原型，围绕 **Nexent 集成、本体构建、证据可溯源** 三个方向演进。赛题与方向说明见 [`ict_docs/`](ict_docs/)，重构与选型方案见 [`project_docs/`](project_docs/)。

## 核心能力

- **故障因果抽取**：用 FTA（故障树分析）专用提示词从文本中抽取「故障事件」实体与「单一原因 / 多原因共同导致」两类因果关系。
- **知识图谱构建**：基于 LightRAG 的图存储（默认 NetworkX，可切换 Neo4j / Memgraph 等），支持实体与关系检索。
- **故障树生成**：从知识图谱子图构建 `TopEvent / IntermediateEvent / BasicEvent` 三层节点，并把 `resultsIn` 映射为 **OR 门**、`jointly_resultsIn` 映射为 **AND 门**。
- **结构校验**：对生成结果做结构完整性、层级合理性、逻辑关系、图谱一致性四类校验，可选 LLM 增强的修复建议。
- **可视化编辑**：内置 Vue 故障树编辑器，支持前端拖拽式查看与编辑。

## 工作原理

```
工业文本 ──▶ 实体/关系抽取（FTA 提示词）──▶ 知识图谱 ──▶ 故障树 payload ──▶ 结构校验 ──▶ 前端编辑器
             (backend/lightrag/fault_tree/prompts.py)   (builder.py)      (validation.py)   (fault-tree-app)
```

- 抽取与建图由 LightRAG 原生的实体关系流水线完成，提示词替换为 [`fault_tree/prompts.py`](backend/lightrag/fault_tree/prompts.py)。
- 故障树核心逻辑位于 [`backend/lightrag/fault_tree/`](backend/lightrag/fault_tree/)：`schemas.py`（数据模型）、`builder.py`（KG → 故障树）、`validation.py`（校验，暴露 `POST /fault-tree/validate`）。

## 项目结构

```
.
├── backend/            # LightRAG 后端（HKUDS/LightRAG 分支，FastAPI，端口 9621）
│   └── lightrag/fault_tree/   # 故障树抽取 / 构建 / 校验核心代码
├── frontend/           # 当前主界面：React + Vue 多入口（Vite）
│   └── src/fault-tree-app/    #   Vue 故障树编辑器
├── frontend-vue/       # 早期独立 Vue 原型（已停止演进，暂不部署）
├── ict_docs/           # 赛题、方向、部署方案
├── project_docs/       # 选型、重构方案、问题清单、学习文档、参考论文
├── 论文/               # 参考论文 PDF
├── Dockerfile          # 单镜像多阶段构建（前端 bun + 后端 uv）
├── docker-compose.yml
├── Makefile            # 常用命令入口
└── railway.json        # Railway 部署配置（DOCKERFILE builder）
```

- **前端**：`frontend/` 为当前主界面，Vite 多入口构建（`main` React + `faultTree` Vue），产物输出到 `backend/lightrag/api/webui`，由后端以静态资源挂载在 `/webui`。
- **后端**：`backend/` 是 HKUDS/LightRAG 的分支，仅拆出原 `lightrag_webui` 作为 `frontend/`，内部实现保持上游原样，另新增 `fault_tree` 故障树模块。

## 本地开发

### 环境要求

- Python 3.10+，推荐用 [uv](https://docs.astral.sh/uv/) 管理依赖
- [Bun](https://bun.sh)（前端包管理与构建）

### 后端

```bash
cd backend
# 首次安装依赖
uv sync --extra api --extra offline

# 配置环境变量：复制 env.example 为 .env，填入 LLM / Embedding 密钥
cp env.example .env

# 启动服务（监听 0.0.0.0:9621）
python -m lightrag.api.lightrag_server
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

> 根目录 `Makefile` 提供了快捷入口：`make install`、`make build`、`make dev-backend`、`make dev-frontend`、`make test`。

## 环境变量

后端配置通过 `backend/.env` 注入，主要项：

- `LLM_BINDING` / `LLM_BINDING_HOST` / `LLM_BINDING_API_KEY` / `LLM_MODEL`：LLM 与推理地址
- `EMBEDDING_BINDING` / `EMBEDDING_BINDING_HOST` / `EMBEDDING_BINDING_API_KEY` / `EMBEDDING_MODEL`：Embedding 模型
- `LIGHTRAG_GRAPH_STORAGE` / `LIGHTRAG_VECTOR_STORAGE` / `LIGHTRAG_KV_STORAGE`：存储后端（默认 NetworkX + NanoVectorDB + JSON KV）
- `POSTGRES_*` / `NEO4J_*`：可选的外部存储

完整变量清单见 [`backend/env.example`](backend/env.example)。

## 测试

```bash
# 后端（含故障树校验回归 / 业务用例）
cd backend && uv run pytest

# 前端
cd frontend && bun test                                   # 单元测试
cd frontend && node --test src/fault-tree-app/src/utils/validationState.test.js
cd frontend && bun run test:e2e:fault-tree                # Playwright 冒烟测试
```

## 部署

根目录 `Dockerfile` 用多阶段构建，产出「后端 + 内置 Web 界面」的单镜像；`railway.json` 已指定 DOCKERFILE builder 与 `/health` 健康检查。

```bash
docker compose up --build
```

部署时由 Railway 注入 `PORT`，数据目录挂载到 `/app/data` 以实现持久化；环境变量同样来自 `backend/.env`。

## 相关文档

- 赛题与方向：[`ict_docs/方向.md`](ict_docs/方向.md)、[`ict_docs/创新赛赛题.md`](ict_docs/创新赛赛题.md)
- 选型与重构：[`project_docs/Nexent重构初步方案.md`](project_docs/Nexent重构初步方案.md)、[`project_docs/AgentArts与Nexent选型及项目重构建议.md`](project_docs/AgentArts与Nexent选型及项目重构建议.md)
- 问题清单：[`project_docs/问题清单.md`](project_docs/问题清单.md)
