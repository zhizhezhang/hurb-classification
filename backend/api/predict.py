"""Validate an uploaded image and return real ConvNeXt probabilities."""

from __future__ import annotations

import warnings
from io import BytesIO
from typing import Annotated, Literal

from fastapi import APIRouter, File, HTTPException, Request, UploadFile
from PIL import Image, ImageOps
from pydantic import BaseModel, Field

from backend.services.model_loader import LoadedModel
from backend.services.predictor import infer_image


MAX_UPLOAD_BYTES = 10 * 1024 * 1024
MAX_IMAGE_PIXELS = 20_000_000
PNG_SIGNATURE = b"\x89PNG\r\n\x1a\n"

router = APIRouter(prefix="/api", tags=["prediction"])


class RankedPrediction(BaseModel):
    class_name: str
    probability: float = Field(ge=0, le=1)


class PredictionData(BaseModel):
    record_id: int | None = Field(default=None, gt=0)
    predicted_class: str
    confidence: float = Field(ge=0, le=1)
    top3: list[RankedPrediction] = Field(min_length=3, max_length=3)
    inference_time_ms: float = Field(ge=0)
    model_version: str


class SavedPredictionData(PredictionData):
    record_id: int = Field(gt=0)


class PredictionResponse(BaseModel):
    success: Literal[True] = True
    data: SavedPredictionData


def decode_image(contents: bytes) -> Image.Image:
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty")
    if len(contents) > MAX_UPLOAD_BYTES:
        raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit")

    if contents.startswith(PNG_SIGNATURE):
        expected_format = "PNG"
    elif contents.startswith(b"\xff\xd8\xff"):
        expected_format = "JPEG"
    else:
        raise HTTPException(status_code=415, detail="Only JPEG and PNG images are supported")

    try:
        with warnings.catch_warnings():
            warnings.simplefilter("error", Image.DecompressionBombWarning)
            with Image.open(BytesIO(contents), formats=("JPEG", "PNG")) as image:
                if image.format != expected_format:
                    raise HTTPException(status_code=415, detail="Image format does not match its content")
                if image.width * image.height > MAX_IMAGE_PIXELS:
                    raise HTTPException(status_code=413, detail="Image exceeds the 20 million pixel limit")
                image.verify()
            with Image.open(BytesIO(contents), formats=("JPEG", "PNG")) as image:
                image.load()
                return ImageOps.exif_transpose(image).convert("RGB")
    except HTTPException:
        raise
    except (Image.DecompressionBombError, Image.DecompressionBombWarning) as exc:
        raise HTTPException(status_code=413, detail="Image exceeds the pixel safety limit") from exc
    except Exception as exc:
        raise HTTPException(status_code=422, detail="Image data is damaged or cannot be decoded") from exc


@router.post("/predict", response_model=PredictionResponse)
def predict(request: Request, file: Annotated[UploadFile, File(description="JPEG or PNG image")]) -> PredictionResponse:
    try:
        if file.size is not None and file.size > MAX_UPLOAD_BYTES:
            raise HTTPException(status_code=413, detail="Image exceeds the 10 MB limit")
        contents = file.file.read(MAX_UPLOAD_BYTES + 1)
    except HTTPException:
        raise
    except Exception:
        raise HTTPException(status_code=422, detail="Uploaded file could not be read") from None
    finally:
        file.file.close()
    image = decode_image(contents)
    loaded: LoadedModel | None = getattr(request.app.state, "model", None)
    if loaded is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")
    try:
        prediction = PredictionData(**infer_image(loaded, image))
    except Exception:
        raise HTTPException(status_code=500, detail="Model inference failed") from None
    store = getattr(request.app.state, "history_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="History store is not available")
    try:
        record = store.create(contents, prediction)
        return PredictionResponse(data=SavedPredictionData(**{
            **prediction.model_dump(), "record_id": record.id,
        }))
    except Exception:
        raise HTTPException(status_code=500, detail="Could not save recognition history") from None
