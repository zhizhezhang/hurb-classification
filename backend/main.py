"""FastAPI entry point with a single model per application lifespan."""

from contextlib import asynccontextmanager

import torch
from fastapi import FastAPI

from backend.api.ai import router as ai_router
from backend.api.health import router as health_router
from backend.api.herbs import router as herbs_router
from backend.api.history import router as history_router
from backend.api.model_analysis import router as model_analysis_router
from backend.api.predict import router as predict_router
from backend.core.config import Settings
from backend.services.ai_service import load_skill
from backend.services.herb_service import load_herbs
from backend.services.history_service import HistoryStore
from backend.services.model_loader import load_model
from backend.services.model_analysis_service import load_model_analysis


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = Settings.from_env()
    loaded = load_model(settings)
    app.state.model = loaded
    try:
        app.state.herbal_skill = load_skill()
        app.state.herb_catalog = load_herbs(loaded.class_to_idx)
        app.state.model_analysis = load_model_analysis(loaded, settings.model_path)
        history_store = HistoryStore(settings.history_db_path, settings.uploads_dir, loaded.class_to_idx)
        history_store.initialize()
        app.state.history_store = history_store
        yield
    finally:
        app.state.model_analysis = None
        app.state.herbal_skill = None
        app.state.history_store = None
        app.state.herb_catalog = None
        app.state.model = None
        del loaded
        if torch.cuda.is_available():
            torch.cuda.empty_cache()


app = FastAPI(title="中药材图像分类服务", lifespan=lifespan)
app.include_router(health_router)
app.include_router(predict_router)
app.include_router(herbs_router)
app.include_router(history_router)
app.include_router(ai_router)
app.include_router(model_analysis_router)
