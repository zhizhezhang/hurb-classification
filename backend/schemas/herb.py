"""Public herbal atlas response models."""

from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


class HerbReference(BaseModel):
    title: str
    location: str


class Herb(BaseModel):
    model_config = ConfigDict(frozen=True)

    id: str
    name: str
    pinyin: str
    image_url: str
    summary: str | None
    recognition_intro: str | None
    source: str | None
    medicinal_part: str | None
    appearance: str | None
    traditional_effects: str
    allusion: str
    traditional_uses: str | None
    references: list[HerbReference] = Field(default_factory=list)


class HerbListResponse(BaseModel):
    success: Literal[True] = True
    total: int
    data: list[Herb]


class HerbDetailResponse(BaseModel):
    success: Literal[True] = True
    data: Herb
