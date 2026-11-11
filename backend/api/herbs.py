"""Read-only herbal atlas endpoints."""

from fastapi import APIRouter, HTTPException, Request

from backend.schemas.herb import HerbDetailResponse, HerbListResponse
from backend.services.herb_service import HerbCatalog


router = APIRouter(prefix="/api/herbs", tags=["herbal atlas"])


def catalog_from(request: Request) -> HerbCatalog:
    catalog: HerbCatalog | None = getattr(request.app.state, "herb_catalog", None)
    if catalog is None:
        raise HTTPException(status_code=503, detail="Herbal atlas is not loaded")
    return catalog


@router.get("", response_model=HerbListResponse)
def list_herbs(request: Request, q: str | None = None) -> HerbListResponse:
    matches = catalog_from(request).search(q)
    return HerbListResponse(total=len(matches), data=matches)


@router.get("/{herb_id}", response_model=HerbDetailResponse)
def get_herb(herb_id: str, request: Request) -> HerbDetailResponse:
    herb = catalog_from(request).by_id.get(herb_id)
    if herb is None:
        raise HTTPException(status_code=404, detail="Herb not found")
    return HerbDetailResponse(data=herb)
