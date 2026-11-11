"""Response models for saved recognition results."""

from typing import Literal

from pydantic import BaseModel, Field

from backend.api.predict import RankedPrediction


class HistoryRecord(BaseModel):
    id: int
    created_at: str
    image_url: str
    predicted_class: str
    confidence: float = Field(ge=0, le=1)
    top3: list[RankedPrediction] = Field(min_length=3, max_length=3)
    inference_time_ms: float = Field(ge=0)
    model_version: str


class HistoryPage(BaseModel):
    total: int
    page: int
    page_size: int
    items: list[HistoryRecord]


class HistoryListResponse(BaseModel):
    success: Literal[True] = True
    data: HistoryPage


class HistoryDetailResponse(BaseModel):
    success: Literal[True] = True
    data: HistoryRecord


class HistoryDeleteResult(BaseModel):
    id: int
    deleted: Literal[True] = True


class HistoryDeleteResponse(BaseModel):
    success: Literal[True] = True
    data: HistoryDeleteResult
