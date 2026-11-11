"""Request and response contracts for the one-turn herbal advisor."""

from typing import Literal

from pydantic import BaseModel, Field, field_validator


class ChatRequest(BaseModel):
    message: str = Field(min_length=1, max_length=2000)
    herb_id: str | None = None
    mode: Literal["knowledge", "deepseek"] | None = None

    @field_validator("message")
    @classmethod
    def nonblank_message(cls, value: str) -> str:
        value = value.strip()
        if not value:
            raise ValueError("message must not be blank")
        return value


class ChatSource(BaseModel):
    key: str
    source_type: Literal["built_in"] = "built_in"
    title: Literal["灵枝本草内置药材资料"] = "灵枝本草内置药材资料"
    herb_id: str
    herb_name: str
    field: str


class ChatData(BaseModel):
    answer: str
    herb_id: str | None
    model: str
    grounding_status: Literal["grounded", "insufficient", "ungrounded_legacy"] | None = None
    answer_origin: Literal["model_with_retrieved_context", "local_guardrail", "local_knowledge", "model_general"] | None = None
    sources: list[ChatSource] = Field(default_factory=list)
    switch_recommended: bool = False


class ChatResponse(BaseModel):
    success: Literal[True] = True
    data: ChatData
