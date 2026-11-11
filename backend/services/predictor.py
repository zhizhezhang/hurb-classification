"""Run the accepted final-evaluation transform and model inference."""

from __future__ import annotations

import time

import torch
from PIL import Image
from herb_classifier.data import get_eval_transform

from backend.services.model_loader import LoadedModel


def infer_image(loaded: LoadedModel, image: Image.Image) -> dict:
    batch = get_eval_transform()(image).unsqueeze(0)
    device = torch.device(loaded.device)
    loaded.model.eval()
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    started = time.perf_counter()
    with torch.inference_mode():
        with torch.autocast("cuda", enabled=device.type == "cuda" and loaded.amp_enabled):
            logits = loaded.model(batch.to(device))
        if logits.shape != (1, loaded.num_classes) or not torch.isfinite(logits).all():
            raise RuntimeError("Invalid model output")
        probabilities = logits.float().softmax(dim=1)[0]
        values, indices = probabilities.topk(3)
    if device.type == "cuda":
        torch.cuda.synchronize(device)
    elapsed_ms = (time.perf_counter() - started) * 1000

    names = [name for name, _ in sorted(loaded.class_to_idx.items(), key=lambda item: item[1])]
    top3 = [
        {"class_name": names[index], "probability": float(value)}
        for value, index in zip(values.cpu().tolist(), indices.cpu().tolist())
    ]
    return {
        "record_id": None,
        "predicted_class": top3[0]["class_name"],
        "confidence": top3[0]["probability"],
        "top3": top3,
        "inference_time_ms": elapsed_ms,
        "model_version": loaded.model_version,
    }
