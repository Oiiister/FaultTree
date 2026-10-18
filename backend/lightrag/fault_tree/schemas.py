"""故障树数据模型：抽取三元组与查询三元组载荷。"""

from typing import List

from pydantic import BaseModel, Field, field_validator, validator


class Triplet(BaseModel):
    subject_name: str = Field(..., description="故障节点的具体名称，如 '气路压力不足'") # [cite: 4]
    subject_type: str = Field(..., description="故障节点的分类标签，如 'BasicEvent'") # [cite: 5]
    relation: str = Field(..., description="头实体与尾实体之间的关联关系，如 'resultsIn'") # [cite: 6]
    object_name: str = Field(..., description="故障节点的具体名称，如 '回收故障'") # [cite: 7]
    object_type: str = Field(..., description="故障节点的分类标签，如 'IntermediateEvent'") # [cite: 8]
    confidence: float = Field(..., description="该三元组的可信程度，取值范围 0~1") # [cite: 9]
    source: str = Field(..., description="该三元组的来源依据") # [cite: 10]

    @validator('subject_type', 'object_type')
    def check_entity_type(cls, v):
        allowed = {"BasicEvent", "IntermediateEvent", "TopEvent"} # [cite: 28]
        if v not in allowed:
            raise ValueError(f"实体类型必须是 {allowed} 之一")
        return v

    @validator('relation')
    def check_relation(cls, v):
        allowed = {"resultsIn",  "jointly_resultsIn"} # [cite: 30]
        if v not in allowed:
            raise ValueError(f"关系类型必须是 {allowed} 之一")
        return v

class TripletExtractionResult(BaseModel):
    triplets: List[Triplet]


class FaultTreeTriple(BaseModel):
    subject_name: str = Field(
        min_length=1,
        description="Specific name of the subject fault node",
    )
    subject_type: str = Field(
        min_length=1,
        description="Subject fault node type",
    )
    relation: str = Field(
        min_length=1,
        description="Relation between subject and object",
    )
    object_name: str = Field(
        min_length=1,
        description="Specific name of the object fault node",
    )
    object_type: str = Field(
        min_length=1,
        description="Object fault node type",
    )
    confidence: float = Field(
        ge=0,
        le=1,
        description="Confidence score in range 0 to 1",
    )
    source: str = Field(
        min_length=1,
        description="Supporting evidence for the triplet",
    )

    @field_validator("subject_type", "object_type")
    @classmethod
    def validate_entity_type(cls, value: str) -> str:
        allowed = {"BasicEvent", "IntermediateEvent", "TopEvent"}
        if value not in allowed:
            raise ValueError(f"Entity type must be one of {sorted(allowed)}")
        return value

    @field_validator("relation")
    @classmethod
    def validate_relation(cls, value: str) -> str:
        allowed = {"resultsIn", "jointly_resultsIn"}
        if value not in allowed:
            raise ValueError(f"Relation must be one of {sorted(allowed)}")
        return value


class FaultTreeTriplesPayload(BaseModel):
    triplets: List[FaultTreeTriple] = Field(
        default_factory=list,
        description="Fault-tree triplets generated from retrieved context",
    )
