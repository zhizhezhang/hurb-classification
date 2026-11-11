"""Read-only endpoints for the deployed Run02 ConvNeXt model."""

from fastapi import APIRouter, HTTPException, Request
from fastapi.responses import FileResponse

from backend.schemas.model_analysis import ModelInfoResponse, ModelMetricsResponse
from backend.services.model_analysis_service import ModelAnalysis


router = APIRouter(prefix="/api/model", tags=["model analysis"])


def analysis_from(request: Request) -> ModelAnalysis:
    analysis: ModelAnalysis | None = getattr(request.app.state, "model_analysis", None)
    if analysis is None:
        raise HTTPException(status_code=503, detail="Model analysis is not loaded")
    return analysis


@router.get("/info", response_model=ModelInfoResponse)
def model_info(request: Request) -> ModelInfoResponse:
    return ModelInfoResponse(data=analysis_from(request).info)


@router.get("/metrics", response_model=ModelMetricsResponse)
def model_metrics(request: Request) -> ModelMetricsResponse:
    return ModelMetricsResponse(data=analysis_from(request).metrics)


@router.get("/charts/{name}", response_class=FileResponse)
def model_chart(name: str, request: Request) -> FileResponse:
    path = analysis_from(request).chart_paths.get(name)
    if path is None or not path.is_file():
        raise HTTPException(status_code=404, detail="Model chart not found")
    return FileResponse(path, media_type="image/png")
