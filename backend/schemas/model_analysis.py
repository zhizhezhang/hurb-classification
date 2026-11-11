"""Public data contracts for the selected Run02 model only."""

from typing import Literal

from pydantic import BaseModel, Field


class ChartLink(BaseModel):
    name: str
    url: str


class ModelInfo(BaseModel):
    model_name: str
    model_version: str
    num_classes: int
    parameter_count: int
    trainable_parameter_count: int
    input_size: int
    pretrained: str
    best_epoch: int
    charts: list[ChartLink]


class ModelInfoResponse(BaseModel):
    success: Literal[True] = True
    data: ModelInfo


class BestValidation(BaseModel):
    best_epoch: int
    accuracy: float = Field(ge=0, le=1)
    macro_f1: float = Field(ge=0, le=1)


class FinalTest(BaseModel):
    total_samples: int = Field(ge=0)
    correct_predictions: int = Field(ge=0)
    accuracy: float = Field(ge=0, le=1)
    macro_precision: float = Field(ge=0, le=1)
    macro_recall: float = Field(ge=0, le=1)
    macro_f1: float = Field(ge=0, le=1)
    weighted_f1: float = Field(ge=0, le=1)


class PerClass(BaseModel):
    class_name: str
    precision: float = Field(ge=0, le=1)
    recall: float = Field(ge=0, le=1)
    f1_score: float = Field(ge=0, le=1)
    support: int = Field(ge=0)


class ModelMetrics(BaseModel):
    best_validation: BestValidation
    final_test: FinalTest
    per_class: list[PerClass]
    charts: list[ChartLink]


class ModelMetricsResponse(BaseModel):
    success: Literal[True] = True
    data: ModelMetrics
