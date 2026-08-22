from fastapi import FastAPI
from fastapi.testclient import TestClient

from lightrag.api.routers.query_routes import create_query_routes


class FakeRAG:
    def __init__(self):
        self.last_query = None
        self.last_param = None
        self.next_content = (
            '{"triplets":[{"subject_name":"电源故障","subject_type":"BasicEvent",'
            '"relation":"resultsIn","object_name":"主泵失效",'
            '"object_type":"TopEvent","confidence":0.98,'
            '"source":"电源故障会导致主泵失效"}]}'
        )

    async def aquery_llm(self, query, param=None, system_prompt=None):
        self.last_query = query
        self.last_param = param
        return {
            "llm_response": {"content": self.next_content},
            "data": {
                "references": [
                    {
                        "reference_id": "1",
                        "file_path": "/documents/fault_tree_spec.pdf",
                    }
                ]
            },
        }


fake_rag = FakeRAG()
app = FastAPI()
app.include_router(create_query_routes(fake_rag, api_key=None))
client = TestClient(app)


def test_fault_tree_json_endpoint_injects_prompt_and_returns_validated_json():
    fake_rag.next_content = (
        '{"triplets":[{"subject_name":"电源故障","subject_type":"BasicEvent",'
        '"relation":"resultsIn","object_name":"主泵失效",'
        '"object_type":"TopEvent","confidence":0.98,'
        '"source":"电源故障会导致主泵失效"}]}'
    )

    response = client.post(
        "/query/fault-tree-json",
        json={
            "query": "生成以主泵失效为顶事件的json三元组",
            "mode": "mix",
            "user_prompt": "谓词统一使用'导致'",
        },
    )

    assert response.status_code == 200
    payload = response.json()

    assert payload["triplets"] == [
        {
            "subject_name": "电源故障",
            "subject_type": "BasicEvent",
            "relation": "resultsIn",
            "object_name": "主泵失效",
            "object_type": "TopEvent",
            "confidence": 0.98,
            "source": "电源故障会导致主泵失效",
        }
    ]
    assert payload["references"] == [
        {"reference_id": "1", "file_path": "/documents/fault_tree_spec.pdf", "content": None}
    ]

    assert fake_rag.last_query == "生成以主泵失效为顶事件的json三元组"
    assert fake_rag.last_param is not None
    assert fake_rag.last_param.response_type == "JSON object"
    assert "Return exactly one valid JSON object" in fake_rag.last_param.user_prompt
    assert "subject_name" in fake_rag.last_param.user_prompt
    assert "confidence must be a number between 0 and 1" in fake_rag.last_param.user_prompt
    assert "谓词统一使用'导致'" in fake_rag.last_param.user_prompt


def test_fault_tree_json_endpoint_rejects_invalid_schema():
    fake_rag.next_content = '{"triplets":[{"subject_name":"缺少字段"}]}'

    response = client.post(
        "/query/fault-tree-json",
        json={"query": "生成以主泵失效为顶事件的json三元组", "mode": "mix"},
    )

    assert response.status_code == 502
    assert "subject_type" in response.json()["detail"]