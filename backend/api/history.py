"""Read and delete saved recognition records."""

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import FileResponse

from backend.schemas.history import (
    HistoryDeleteResponse,
    HistoryDeleteResult,
    HistoryDetailResponse,
    HistoryListResponse,
)
from backend.services.history_service import HistoryStore, ImageMissing, UnsafeImagePath


router = APIRouter(prefix="/api/history", tags=["history"])


def store_from(request: Request) -> HistoryStore:
    store: HistoryStore | None = getattr(request.app.state, "history_store", None)
    if store is None:
        raise HTTPException(status_code=503, detail="History store is not available")
    return store


@router.get("", response_model=HistoryListResponse)
def list_history(request: Request, page: int = Query(1, ge=1),
                 page_size: int = Query(10, ge=1, le=50)) -> HistoryListResponse:
    return HistoryListResponse(data=store_from(request).list_page(page, page_size))


@router.get("/{record_id}", response_model=HistoryDetailResponse)
def get_history(record_id: int, request: Request) -> HistoryDetailResponse:
    record = store_from(request).get(record_id)
    if record is None:
        raise HTTPException(status_code=404, detail="History record not found")
    return HistoryDetailResponse(data=record)


@router.get("/{record_id}/image", response_class=FileResponse)
def get_history_image(record_id: int, request: Request) -> FileResponse:
    try:
        result = store_from(request).image(record_id)
    except ImageMissing:
        raise HTTPException(status_code=404, detail="Stored image is missing") from None
    except UnsafeImagePath:
        raise HTTPException(status_code=500, detail="Stored image path is invalid") from None
    if result is None:
        raise HTTPException(status_code=404, detail="History record not found")
    path, media_type = result
    return FileResponse(path, media_type=media_type)


@router.delete("/{record_id}", response_model=HistoryDeleteResponse)
def delete_history(record_id: int, request: Request) -> HistoryDeleteResponse:
    try:
        deleted = store_from(request).delete(record_id)
    except UnsafeImagePath:
        raise HTTPException(status_code=500, detail="Stored image path is invalid") from None
    except OSError:
        raise HTTPException(status_code=500, detail="Could not delete history image") from None
    if not deleted:
        raise HTTPException(status_code=404, detail="History record not found")
    return HistoryDeleteResponse(data=HistoryDeleteResult(id=record_id))
