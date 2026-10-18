# 后端结构说明

本文档说明 `backend/` 目录下每个文件的职责与组织方式。后端 = **LightRAG 分支（上游 HKUDS/LightRAG）** + **自研故障树模块**，是一个 FastAPI 服务，入口：

```bash
python -m lightrag.api.lightrag_server   # 监听 0.0.0.0:9621（读取 PORT 环境变量）
```

---

## 1. 总览

| 层次 | 目录 | 职责 |
|---|---|---|
| 服务入口 | `lightrag/api/` | FastAPI 应用、路由、鉴权、配置解析 |
| 故障树模块（自研） | `lightrag/fault_tree/` | 故障树抽取提示词、数据模型、图谱→故障树构建、结构校验 |
| RAG 核心（上游） | `lightrag/lightrag.py`、`operate.py`、`base.py` 等 | 文档插入、实体/关系抽取、图谱存储、检索问答 |
| LLM 后端 | `lightrag/llm/` | 各家大模型 / 嵌入模型适配（本项目只用 `openai`） |
| 存储后端 | `lightrag/kg/` | 图 / 向量 / KV / 文档状态存储（本项目只用本地 4 个） |
| 工具 | `lightrag/tools/`、`scripts/` | CLI 工具、故障树校验脚本 |
| 测试 | `tests/` | pytest 测试 |

**技术栈**：Python ≥3.10、FastAPI、Pydantic v2、NetworkX、NanoVectorDB；依赖由 `uv` 管理（`pyproject.toml`）。

**实际运行配置**（来自 `.env`，见 `/health` 返回）：LLM = `openai` 兼容（SiliconFlow / DeepSeek-V3.2），Embedding = `BAAI/bge-m3`，存储 = `JsonKVStorage` + `JsonDocStatusStorage` + `NetworkXStorage` + `NanoVectorDBStorage`。

---

## 2. 启动流程（端到端）

```
python -m lightrag.api.lightrag_server
        │
        ▼
lightrag/api/lightrag_server.py::main()
        │  1. 解析命令行参数
        │  2. 读取 backend/.env（load_dotenv，工作目录需为 backend/）
        │  3. runtime_validation.py 校验运行时环境
        ▼
lightrag/api/config.py
        │  根据 env 解析 LLM / Embedding / 各存储后端，构造实例
        ▼
实例化 lightrag.LightRAG（核心引擎，见 lightrag/lightrag.py）
        │
        ▼
挂载路由（路由工厂模式，每个都返回 APIRouter）：
        ├─ create_query_routes(rag, ...)        → /query/*   （含 /query/fault-tree-json）
        ├─ create_graph_routes(rag, ...)        → /graph/*   （含 /graph/fault-tree/export）
        ├─ document_routes                       → /documents/*
        ├─ create_fault_tree_validation_routes   → /fault-tree/validate
        └─ OllamaAPI                             → /api/* （Ollama 兼容接口）
        │
        ▼
挂载静态 WebUI（backend/lightrag/api/webui，前端构建产物）→ /webui
        │
        ▼
uvicorn 启动，/health 健康检查
```

---

## 3. 顶层文件（`backend/` 根目录）

| 文件 / 目录 | 作用 |
|---|---|
| `.env` | 真实运行配置（**含 API Key，已 gitignore，切勿提交**）。从 `env.example` 复制而来 |
| `env.example` | 环境变量模板（所有可配置项 + 注释），`.env` 的样板 |
| `config.ini.example` | `config.ini` 的示例（LightRAG 早期配置文件，当前以 `.env` 为主） |
| `pyproject.toml` | 包定义（`lightrag-hku`）、依赖、可选 extra、入口脚本、pytest/ruff 配置 |
| `setup.py` | setuptools 兼容入口（委托给 `pyproject.toml`） |
| `uv.lock` | uv 锁文件，锁定依赖版本 |
| `MANIFEST.in` | 打包清单（含 `lightrag/api/webui/**`、`api/static/**`） |
| `Makefile` | 常用命令：`install` / `build` / `dev-backend` / `dev-frontend` / `test` |
| `LICENSE` | MIT 许可证（上游 LightRAG） |
| `.gitignore` | 忽略 `.env`、`rag_storage/`、`inputs/`、`__pycache__`、日志等 |
| `rag_storage/` | 本地存储数据目录（图 / 向量 / KV / 文档状态，gitignore） |
| `inputs/` | 上传的原始文档存放目录（gitignore） |
| `lightrag.log` | 运行日志（gitignore） |

---

## 4. `lightrag/` 核心

### 4.1 包入口与引擎

| 文件 | 作用 |
|---|---|
| `__init__.py` | 包入口，`__getattr__` 惰性导出 `LightRAG`、`QueryParam`、`__version__` |
| `_version.py` | 版本号（`1.4.14`）与 API 版本（`0285`） |
| `lightrag.py` | **核心引擎 `LightRAG`**：编排文档插入、抽取、图谱/向量存储、检索与查询（`insert` / `aquery` / `get_knowledge_graph` 等） |
| `operate.py` | **抽取流水线**：调用 LLM 抽取实体/关系（使用 `prompt.py` 的提示词），合并去重、写入图谱；含 `json_repair` 容错解析 |
| `base.py` | 基础抽象与数据类型：`BaseKVStorage` / `BaseGraphStorage` / `BaseVectorStorage` / `BaseTextStorage`、`StorageNameSpace`、`QueryParam`、`DeletionResult` 等 |

### 4.2 常量与数据类型

| 文件 | 作用 |
|---|---|
| `constants.py` | 集中式默认常量（`GRAPH_FIELD_SEP`、`DEFAULT_MAX_GRAPH_NODES` 等） |
| `types.py` | Pydantic 数据模型：`GPTKeywordExtractionFormat`、`KnowledgeGraphNode`、`KnowledgeGraphEdge` 等 |
| `namespace.py` | `NameSpace` 类：定义 KV 存储的命名空间（`full_docs`、`text_chunks`、`full_entities` 等） |
| `exceptions.py` | 异常定义：`APIStatusError`、`PipelineCancelledException` 等 |

### 4.3 工具与提示词

| 文件 | 作用 |
|---|---|
| `utils.py` | 通用工具：`logger`、tokenizer、`compute_mdhash_id`、环境变量读取、时间统计等 |
| `utils_graph.py` | 图谱操作工具：节点/边增删、关系向量 ID 生成、`DeletionResult` 等 |
| `prompt.py` | 提示词注册表 `PROMPTS`；其中**故障树抽取提示词从 `lightrag.fault_tree.prompts` 导入**，其余（摘要等）在此定义 |
| `rerank.py` | 重排序（Cohere / Jina 等，本项目默认关闭） |
| `test001.json` | ⚠️ 遗留测试产物，可删除 |

---

## 5. `lightrag/llm/` — LLM / 嵌入后端

> 只有 `openai.py` 被本项目使用（SiliconFlow 的 OpenAI 兼容接口承载 DeepSeek-V3.2 与 bge-m3）。其余为上游保留，未启用。

| 文件 | 对应提供商 |
|---|---|
| `openai.py` | ✅ **本项目使用**（OpenAI 兼容协议，同时承担 LLM 与 Embedding） |
| `anthropic.py` | Anthropic Claude |
| `azure_openai.py` | Azure OpenAI |
| `bedrock.py` | AWS Bedrock |
| `gemini.py` | Google Gemini |
| `hf.py` | Hugging Face |
| `jina.py` | Jina |
| `llama_index_impl.py` | LlamaIndex 封装 |
| `lmdeploy.py` | LMDeploy |
| `lollms.py` | LoLLMs |
| `nvidia_openai.py` | NVIDIA OpenAI 兼容 |
| `ollama.py` | Ollama 本地模型 |
| `zhipu.py` | 智谱 |
| `binding_options.py` | 各 provider 的选项 dataclass（如 `GeminiLLMOptions`、`OllamaEmbeddingOptions`） |
| `deprecated/siliconcloud.py` | ⚠️ 已废弃的 SiliconCloud 专用后端 |
| `__init__.py` | 空（占位） |

---

## 6. `lightrag/kg/` — 存储后端

> `kg/__init__.py` 通过 `STORAGE_IMPLEMENTATIONS` 注册表 + `importlib` **动态**导入实现类（按 env 配置选择），因此未使用的后端不会加载。本项目只用本地 4 个（✅）。

| 文件 | 存储类型 | 状态 |
|---|---|---|
| `networkx_impl.py` | 图存储 `NetworkXStorage` | ✅ 使用 |
| `json_kv_impl.py` | KV 存储 `JsonKVStorage` | ✅ 使用 |
| `json_doc_status_impl.py` | 文档状态 `JsonDocStatusStorage` | ✅ 使用 |
| `nano_vector_db_impl.py` | 向量存储 `NanoVectorDBStorage` | ✅ 使用 |
| `shared_storage.py` | 共享存储 / 键控锁基础设施（`get_storage_keyed_lock`、`initialize_share_data` 等） | 基础设施，始终加载 |
| `redis_impl.py` | Redis KV | 未使用 |
| `postgres_impl.py` | PostgreSQL（KV + 图） | 未使用 |
| `mongo_impl.py` | MongoDB（KV + 图 + 向量） | 未使用 |
| `neo4j_impl.py` | Neo4j 图 | 未使用 |
| `memgraph_impl.py` | Memgraph 图 | 未使用 |
| `milvus_impl.py` | Milvus 向量 | 未使用 |
| `qdrant_impl.py` | Qdrant 向量 | 未使用 |
| `opensearch_impl.py` | OpenSearch（KV + 向量） | 未使用 |
| `faiss_impl.py` | FAISS 向量 | 未使用 |
| `deprecated/chroma_impl.py` | ⚠️ 已废弃的 Chroma 向量 | 未使用 |
| `__init__.py` | 后端注册表 `STORAGE_IMPLEMENTATIONS` + 环境变量依赖声明 | — |

---

## 7. `lightrag/api/` — FastAPI 服务层

### 7.1 服务与配置

| 文件 | 作用 |
|---|---|
| `lightrag_server.py` | **服务主入口**：定义 `FastAPI` app 与 `main()`，创建 `LightRAG`，挂载所有路由与静态 WebUI，处理 CORS、健康检查 |
| `config.py` | API 配置解析：根据 `.env`/命令行构造 LLM、Embedding、各存储后端实例 |
| `utils_api.py` | API 通用工具：`get_combined_auth_dependency`（鉴权依赖）、`display_splash_screen`、`check_env_file`、workspace 解析等 |
| `auth.py` | JWT 鉴权（token 签发 / 校验，配合 `AUTH_ACCOUNTS`） |
| `passwords.py` | bcrypt 密码哈希 / 校验（`AUTH_ACCOUNTS` 用） |
| `runtime_validation.py` | 校验 `.env` 的启动期运行时预期（容器/本地差异） |
| `gunicorn_config.py` | gunicorn 多进程部署配置 |
| `run_with_gunicorn.py` | gunicorn 启动入口（`lightrag-gunicorn` 脚本） |
| `config.py.bak` | ⚠️ `config.py` 的旧备份，可删除 |

### 7.2 路由 `lightrag/api/routers/`

| 文件 | 作用 |
|---|---|
| `__init__.py` | 聚合导出 `document_router` / `query_router` / `graph_router` / `OllamaAPI` |
| `document_routes.py` | 文档上传、状态管理、解析（pdf/docx/xlsx/pptx 等） |
| `query_routes.py` | 查询接口：`/query`、`/query/stream`、`/query/data`、**`/query/fault-tree-json`**（故障树三元组 JSON）；`FaultTreeTriplesResponse` 等响应模型；故障树构建逻辑已抽到 `lightrag.fault_tree.builder` |
| `graph_routes.py` | 图谱接口：节点/边 CRUD、标签搜索、**`/graph/fault-tree/export`**（故障树导出）；导出摘要逻辑已抽到 `lightrag.fault_tree.builder` |
| `ollama_api.py` | Ollama 兼容 API（`/api/*`），供外部 Ollama 客户端调用 |

### 7.3 静态资源

| 路径 | 作用 |
|---|---|
| `static/swagger-ui/` | Swagger UI 前端资源（`/docs` 使用） |

---

## 8. `lightrag/fault_tree/` — 故障树模块（本项目核心）

> 从原 `query_routes.py` / `graph_routes.py` / `fault_tree_validation_routes.py` / `prompt.py` 中按功能抽出，独立成模块。

| 文件 | 作用 |
|---|---|
| `__init__.py` | 模块说明文档字符串 |
| `prompts.py` | 4 段**故障树抽取提示词**：`ENTITY_EXTRACTION_SYSTEM_PROMPT`、`ENTITY_EXTRACTION_USER_PROMPT`、`ENTITY_CONTINUE_EXTRACTION_USER_PROMPT`、`ENTITY_EXTRACTION_EXAMPLES`（教 LLM 区分 `BasicEvent`/`IntermediateEvent`/`TopEvent` 与 `resultsIn`/`jointly_resultsIn` 的 AND/OR 逻辑） |
| `schemas.py` | Pydantic 数据模型：`FaultTreeTriple`、`FaultTreeTriplesPayload`（查询三元组载荷）；`Triplet`、`TripletExtractionResult`（⚠️ 死代码，未使用，沿用上游 V1 `@validator`） |
| `builder.py` | **图谱 → 故障树** 核心：`FAULT_TREE_JSON_PROMPT`、`_extract_first_json_object`、`_normalize_fault_tree_type`、`_extract_fault_tree_relation`、`_resolve_fault_tree_top_event_label`、`_orient_fault_tree_edge`（按距离/类型确定因果方向）、`_build_fault_tree_payload_from_graph`（生成三元组 + 引用）、`_derive_fault_tree_export_summary`（导出摘要：事件 + 门） |
| `validation.py` | **故障树结构校验**：`create_fault_tree_validation_routes` → `POST /fault-tree/validate`，校验拓扑合法性（层级、环、门类型、与知识图谱一致性等） |

---

## 9. `lightrag/tools/` — CLI 工具

| 文件 | 作用 |
|---|---|
| `check_initialization.py` | 检查初始化状态 |
| `clean_llm_query_cache.py` | 清理 LLM 查询缓存（`lightrag-clean-llmqc`） |
| `download_cache.py` | 下载缓存（`lightrag-download-cache`） |
| `hash_password.py` | 生成 bcrypt 密码（`lightrag-hash-password`） |
| `migrate_llm_cache.py` | 迁移旧 LLM 缓存结构 |
| `prepare_qdrant_legacy_data.py` | 迁移 Qdrant 旧数据 |
| `lightrag_visualizer/` | 知识图谱可视化工具（含字体资源、README） |

---

## 10. `lightrag/evaluation/` — 评测

| 文件 | 作用 |
|---|---|
| `eval_rag_quality.py` | RAGAS 评测脚本 |
| `sample_dataset.json` / `sample_documents/` | 示例评测数据与文档 |
| `README_EVALUASTION_RAGAS.md` | 评测说明 |

---

## 11. `scripts/` — 故障树校验脚本

| 文件 | 作用 |
|---|---|
| `fault_tree_validation_business_cases.json` | 业务校验用例（fixture） |
| `run_fault_tree_validation_business_check.py` | 跑业务用例校验（打本地服务或离线） |
| `run_fault_tree_validation_regression.py` | 回归脚本（⚠️ 内部仍引用已改名的 `lightrag_webui`，见「待清理」） |

---

## 12. `tests/` — 测试

| 文件 | 作用 |
|---|---|
| `conftest.py` | pytest 配置 / fixtures / markers |
| `test_fault_tree_json_endpoint.py` | 测 `/query/fault-tree-json`（用 FakeRAG） |
| `test_fault_tree_validation_endpoint.py` | 测 `/fault-tree/validate`（用 FakeRAG） |
| `test_fault_tree_validation_regression_scripts.py` | 测 scripts/ 下的校验脚本 |
| `README_WORKSPACE_ISOLATION_TESTS.md` | workspace 隔离测试说明 |

---

## 13. 故障树生成完整链路

```
1. 上传工业文本          POST /documents/scan  → 存储到 inputs/ → 分块
2. 知识抽取              operate.py 调 LLM（fault_tree/prompts.py 提示词）
                         抽取实体（Top/Intermediate/BasicEvent）与关系（resultsIn / jointly_resultsIn）
3. 入图谱                kg/networkx_impl.py（NetworkXStorage）+ 向量 / KV
4. 用户给顶事件          POST /query/fault-tree-json（query_routes.py）
        ├─ 命中图谱：fault_tree/builder.py::_build_fault_tree_payload_from_graph
        │    解析顶事件 → BFS 取子图 → 判定边方向（距离/类型）→ 生成三元组 + 引用
        └─ 未命中：走 RAG 检索 + FAULT_TREE_JSON_PROMPT 让 LLM 现生成三元组 JSON
5. 结构校验              POST /fault-tree/validate（fault_tree/validation.py）
6. 导出                  GET /graph/fault-tree/export（fault_tree/builder.py::_derive_fault_tree_export_summary）
                         输出 events + gates（AND/OR 门），供前端 Vue 故障树编辑器渲染
```

---

## 14. 待清理 / 注意事项

以下为本次「按功能划分」重构过程中发现的遗留项，均**不影响功能**，建议后续单独处理：

1. **`lightrag/api/config.py.bak`** — `config.py` 的旧备份，与当前 `config.py` 等长（604 行），可删除。
2. **`lightrag/test001.json`** — 遗留测试产物，可删除。
3. **`lightrag_webui` 残留引用** — 前端目录已从 `lightrag_webui/` 改名为 `frontend/`，但仍有 3 处旧引用：
   - `lightrag/api/lightrag_server.py` 启动横幅文字 `cd lightrag_webui`（2 处）与 1 处注释。
   - `scripts/run_fault_tree_validation_regression.py` 的 `WEBUI_DIR = ROOT / "lightrag_webui"`（**功能性问题**，跑回归脚本会找不到目录）。
4. **`fault_tree/schemas.py` 的 `Triplet` / `TripletExtractionResult`** — 死代码（无任何引用），且沿用上游 Pydantic V1 的 `@validator`，导入时会产生弃用告警（无害）。可删除或迁移到 V2 `@field_validator`。
5. **`_extract_first_json_object` 重复** — `fault_tree/builder.py` 与 `fault_tree/validation.py` 各有一份实现，逻辑相同，可合并。
6. **未启用的 LLM / 存储后端**（`llm/` 13 个 provider、`kg/` 10+ 个后端）—— 保留自上游，如需精简可裁剪（即此前暂缓的「Phase 3」）。
