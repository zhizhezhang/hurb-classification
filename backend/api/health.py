"""Report the model state held by the running application."""

from fastapi import APIRouter, HTTPException, Request
from pydantic import BaseModel

from backend.services.model_loader import LoadedModel


router = APIRouter(prefix="/api", tags=["health"])


class HealthResponse(BaseModel):
    status: str
    model_loaded: bool
    model_name: str
    num_classes: int
    device: str


@router.get("/health", response_model=HealthResponse)
def health(request: Request) -> HealthResponse:
    loaded: LoadedModel | None = getattr(request.app.state, "model", None)
    if loaded is None:
        raise HTTPException(status_code=503, detail="Model is not loaded")
    return HealthResponse(
        status="ok",
        model_loaded=True,
        model_name=loaded.model_name,
        num_classes=loaded.num_classes,
        device=loaded.device,
    )
