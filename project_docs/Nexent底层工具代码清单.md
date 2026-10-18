# Nexent 底层工具代码清单

> 盘点日期：2026-10-16
>
> 目标：把现有 LightRAG/FastAPI/故障树代码映射为 Nexent 可调用的底层工具。
>
> 本清单只做“边界抽取”和工具分级，不把现有领域代码改写成 Agent。当前仓库处于旧目录删除、新目录新增的迁移状态，因此先保留原实现，使用 API/MCP 适配层暴露能力；不要直接移动或删除核心函数。

## 1. 推荐的分层

```text
Nexent Agent / Skill
        |
        |  HTTP/OpenAPI 或 MCP
        v
工具适配层（建议后续新增 nexent_tools/）
        |
        v
现有 LightRAG + 故障树领域服务
        |
        +-- 文档/Chunk/向量检索
        +-- 实体与关系抽取
        +-- 知识图谱查询与编辑
        +-- 故障树投影与校验
```

工具适配层应处理：输入输出模型、鉴权、workspace、错误码、超时和审计。它不应把存储对象（`BaseGraphStorage`、VDB、KV）直接暴露给 Nexent。

## 2. 第一批必须工具化的能力

| 工具名 | 现有代码入口 | 类型 | 第一版结论 |
|---|---|---|---|
| `search_fault_context` | `LightRAG.aquery_data()`（`backend/lightrag/lightrag.py:2677`）；`POST /query/data`（`backend/lightrag/api/routers/query_routes.py:929`） | 只读检索 | 直接封装。返回实体、关系、Chunk、references 和检索元数据，不返回流式迭代器。 |
| `get_evidence` | `LightRAG.get_entity_info()`、`LightRAG.get_relation_info()`（`backend/lightrag/lightrag.py:4223`、`:4236`）；`GET /graph/...` 相关查询 | 只读证据 | 直接封装。必须返回 `document_id/file_path/chunk_id/page/quote` 能提供的全部来源信息。 |
| `extract_fault_knowledge` | `operate.extract_entities()`（`backend/lightrag/operate.py:2883`）；关系解析 `_handle_single_relationship_extraction()`（`:473`）；实体解析 `_handle_single_entity_extraction()`（`:386`） | 候选抽取 | 不直接把内部函数暴露出去；通过一个稳定的 JSON API/MCP 工具封装，统一输出 `events/relations/evidence`。 |
| `normalize_entities` | `utils_graph.aedit_entity()`、`amerge_entities()`（`backend/lightrag/utils_graph.py:524`、`:1557`）；`POST /graph/entities/merge`（`backend/lightrag/api/routers/graph_routes.py:712`） | 受控写入 | 做成“候选合并/人工确认”工具。默认不得由 Agent 自动调用正式合并。 |
| `query_subgraph` | `LightRAG.get_knowledge_graph()`（`backend/lightrag/lightrag.py:1150`）；`GET /graphs`（`backend/lightrag/api/routers/graph_routes.py:256`） | 只读图谱 | 直接封装。输入 `label/top_event/max_depth/max_nodes`，返回节点、边和 `is_truncated`。 |
| `validate_knowledge_graph` | `get_entity_info()`、`get_relation_info()`、`utils_graph` 查询函数，以及现有关系字段检查 | 只读校验 | 新增适配函数组合现有查询；检查实体类型、关系枚举、方向、证据、自环、重复和冲突。 |
| `project_fault_tree` | `_build_fault_tree_payload_from_graph()`（`backend/lightrag/fault_tree/builder.py:265`）；`_derive_fault_tree_export_summary()`（`:355`）；`GET /graph/fault-tree/export`（`backend/lightrag/api/routers/graph_routes.py:126`） | 确定性计算 | 必须做成工具，不能让 Agent 自由生成 AND/OR 树。输入明确 `top_event` 和结构化关系，输出 `FaultTreeDraft`。 |
| `validate_fault_tree` | `_validate_fault_tree()`（`backend/lightrag/fault_tree/validation.py:577`）；`POST /fault-tree/validate`（`:975`） | 确定性校验 | 直接封装现有规则校验器；默认先关闭 LLM 建议，Agent 需要解释时另行调用审核 Agent。 |

## 3. 第二批工具

| 工具名 | 现有代码入口 | 适用时机 | 风险/限制 |
|---|---|---|---|
| `ingest_document` | `LightRAG.ainsert()`（`backend/lightrag/lightrag.py:1237`）；`POST /documents/insert`（`backend/lightrag/api/routers/document_routes.py:2659`） | 文档入库稳定后 | 会触发异步处理和 LLM/向量写入，需返回 `track_id`，不能让 Agent 重复提交。 |
| `get_ingestion_status` | `LightRAG.get_processing_status()`（`backend/lightrag/lightrag.py:4202`）；`GET /documents/pipeline_status`（`document_routes.py:3028`） | 需要异步进度时 | 只读，适合编排 Agent 轮询。 |
| `get_document_status` | `GET /documents`、分页和状态路由（`document_routes.py:3135`、`:3522`、`:3703`） | 文档管理页面 | 只读工具；不要一开始把删除接口开放给 Agent。 |
| `create_candidate_entity` | `LightRAG.acreate_entity()`；`POST /graph/entity/create`（`graph_routes.py:548`） | 人工确认后补录 | 这是写入正式图谱的能力，应改名/加状态字段，优先写候选层。 |
| `create_candidate_relation` | `LightRAG.acreate_relation()`；`POST /graph/relation/create`（`graph_routes.py:622`） | 人工确认后补录 | 当前接口文档明确说明底层边是无向的；在因果方向修复前不能作为故障因果正式工具。 |
| `edit_entity` | `LightRAG.aedit_entity()`；`POST /graph/entity/edit`（`graph_routes.py:321`） | 图谱人工维护 | 受控写工具；Agent 不应直接修改名称或类型。 |
| `edit_relation` | `LightRAG.aedit_relation()`；`POST /graph/relation/edit`（`graph_routes.py:512`） | 图谱人工维护 | 受控写工具；需先解决有向因果关系的一等字段。 |
| `submit_review` | 当前没有独立后端实现 | 专家审核阶段 | 新增工具。保存接受/修改/拒绝、审核人、理由、证据和版本，不直接复用图谱 CRUD。 |
| `save_fault_tree_draft` / `get_fault_tree_draft` | 当前前端有草稿能力，但后端没有统一 draft 资源 | 端到端闭环阶段 | 新增工具和持久化模型，解决生成后下载/上传和后端丢结果问题。 |
| `run_extraction_eval` | `backend/lightrag/evaluation/eval_rag_quality.py`；项目成员自己的评测脚本 | 研究/回归阶段 | 只对开发者/评测 Agent 开放；不能放进普通用户工作流。 |

## 4. 现有代码与 Nexent 工具的准确边界

### 4.1 文档与检索

保留为内部服务，外面暴露工具：

- `LightRAG.ainsert()`：文档入库工具的内部实现。
- `LightRAG.aquery_data()`：检索工具的内部实现。
- `LightRAG.aquery_llm()`：普通问答工具可以使用，但不应作为故障树事实抽取的唯一来源。
- `operate.kg_query()`：检索编排内部函数，不直接作为 MCP 工具。
- `operate._get_node_data()`、`_get_edge_data()` 及相关 Chunk 关联函数：内部检索实现，不直接暴露。

原因：这些函数依赖多个存储对象和 `QueryParam`，直接暴露会把 LightRAG 内部实现泄漏给 Nexent，后续替换存储会破坏工具契约。

### 4.2 实体/关系抽取

可复用但应包在一个稳定工具后面：

- `operate.extract_entities()`：批量调用 LLM 并处理 Chunk，是抽取工具的核心内部实现。
- `_handle_single_entity_extraction()`：解析和清洗实体记录。
- `_handle_single_relationship_extraction()`：解析和清洗关系记录。
- `operate._process_extraction_result()`、`merge_nodes_and_edges()`：抽取结果合并和写图内部实现。

建议第一版对 Nexent 只暴露：

```text
extract_fault_knowledge(context, ontology, top_event)
```

返回候选事件、关系和证据；不要把 `chunks`、`global_config`、LLM cache 或存储句柄作为工具参数。

### 4.3 图谱查询、编辑与合并

只读能力可以优先开放：

- `LightRAG.get_graph_labels()`：标签/实体发现工具。
- `LightRAG.get_knowledge_graph()`：局部子图工具。
- `LightRAG.get_entity_info()`：实体详情/证据工具。
- `LightRAG.get_relation_info()`：关系详情/证据工具。

写入能力必须分级：

1. 候选层写入：Agent 可以调用，但要有 `review_status=pending`。
2. 正式层发布：只能由人工审核工具或管理员确认流程调用。
3. 删除、合并、改名：第一版不开放给总编排 Agent。

特别注意：`NetworkXStorage` 以及 `graph_routes.py` 的关系接口当前使用无向图语义；因此不能把现有 `create_relation` 直接宣传为“有向因果关系写入工具”。必须先增加结构化的 `source_event_id/target_event_id/relation_type/gate_type` 字段并验证持久化方向。

### 4.4 故障树

故障树模块已经是最清晰的领域服务边界：

- `fault_tree/schemas.py`：作为输入输出模型的起点，但应新增统一的 `FaultEvent/FaultRelation/FaultTreeDraft`，不要继续让三元组和编辑器节点各自定义一套模型。
- `fault_tree/builder.py`：投影和引用构建内部实现；对外包装 `project_fault_tree`。
- `fault_tree/validation.py`：规则校验内部实现；对外包装 `validate_fault_tree`。
- `fault_tree/prompts.py`：提示词和领域规范，适合沉淀到 Nexent Skill，不是工具。

当前 `builder.py` 的 `_orient_fault_tree_edge()` 仍有按距离/事件类型推断方向的逻辑。方向修复前，`project_fault_tree` 应返回 `direction_source` 和风险警告，不能静默把推断方向当成事实。

## 5. API/MCP 工具合同建议

### `search_fault_context`

```json
{
  "top_event": "液压泵压力不足",
  "query": "液压泵压力不足的原因",
  "max_chunks": 8,
  "include_graph": true
}
```

返回必须包含：`context_id`、`chunks[]`、`entities[]`、`relations[]`、`references[]`、`truncated`。

### `extract_fault_knowledge`

```json
{
  "context_id": "ctx_001",
  "top_event": "液压泵压力不足",
  "ontology_version": "industrial-fault-v1"
}
```

返回：`events[]`、`relations[]`、`evidence[]`、`review_status=pending`、`warnings[]`。

### `project_fault_tree`

```json
{
  "top_event": "液压泵压力不足",
  "events": [],
  "relations": [],
  "direction_policy": "explicit_only"
}
```

返回：`draft_id`、`nodes[]`、`gates[]`、`references[]`、`direction_source`、`warnings[]`。

### `validate_fault_tree`

输入可以继续兼容现有 `FaultTreeValidationRequest`，但输出统一增加：

```json
{
  "valid": false,
  "issues": [],
  "score": 0.0,
  "checks": {
    "structure": true,
    "hierarchy": false,
    "logic": true,
    "evidence": false
  }
}
```

## 6. 哪些代码暂时不要做成 Nexent 工具

- `lightrag/llm/*` 各家模型适配器：属于基础设施，不是业务工具。
- `lightrag/kg/*` 各种存储实现：属于存储驱动，不直接暴露给 Agent。
- `lightrag/api/auth.py`、`passwords.py`：鉴权基础设施，不交给 Agent。
- `lightrag/tools/clean_llm_query_cache.py`、迁移脚本、密码脚本：运维 CLI，不属于用户工作流。
- `document_routes.py` 中的清空、删除、取消任务接口：高风险写操作，第一版不开放。
- `frontend/` 和 `frontend-vue/`：是交互界面，不是 Nexent 底层工具；前端应调用工具 API。
- `fault_tree/prompts.py`：应转成 Skill/版本化提示词，而不是暴露为工具。

## 7. 推荐的提取顺序

1. 先把现有 `/query/data`、`/graphs`、`/graph/fault-tree/export`、`/fault-tree/validate` 作为只读/计算工具接入。
2. 将 `/query/fault-tree-json` 改造成明确的 `extract_fault_knowledge` 候选抽取工具，并返回 `source=graph|llm`、`top_event`、`warnings`。
3. 增加 `save_fault_tree_draft` 和 `submit_review`，打通生成—编辑—校验—审核。
4. 修复图谱边的方向和门类型结构化存储后，再开放实体/关系写入工具。
5. 最后再把文档上传、批量入库、评测和版本发布接入 Nexent 工作流。

## 8. 三位同学的代码边界

| 成员 | 负责的工具边界 |
|---|---|
| 数据/知识工程 | `ingest_document`、`get_ingestion_status`、`search_fault_context`、`get_evidence`、文档来源和 Chunk 证据 |
| 算法/评测 | `extract_fault_knowledge`、`normalize_entities`、`validate_knowledge_graph`、`run_extraction_eval`、本体和抽取 Skill |
| 平台/集成 | `query_subgraph`、`project_fault_tree`、`validate_fault_tree`、`save_fault_tree_draft`、`submit_review`、OpenAPI/MCP 适配和 Nexent 编排 |

## 9. 结论

现有代码已经具备工具化所需的核心能力，但不建议按“一个函数一个工具”机械拆分。推荐保留内部实现，新增稳定的工具适配层：

```text
LightRAG 检索       -> search_fault_context
实体/关系抽取       -> extract_fault_knowledge
图谱查询            -> query_subgraph / get_evidence
实体规范化          -> normalize_entities
图谱校验            -> validate_knowledge_graph
故障树投影          -> project_fault_tree
故障树校验          -> validate_fault_tree
草稿/审核/发布      -> save_fault_tree_draft / submit_review / publish_graph_version
```

第一阶段只开放只读检索和确定性计算工具；候选写入与正式发布分离；删除、清空、改名和 API Key 等高风险能力不开放给 Agent。
