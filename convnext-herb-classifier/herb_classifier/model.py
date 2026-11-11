"""ConvNeXt-Tiny transfer-learning model and portable checkpoint loading."""

from __future__ import annotations

from pathlib import Path

import torch
from torchvision.models import ConvNeXt_Tiny_Weights, convnext_tiny

MODEL_NAME = "convnext_tiny"
WEIGHTS_NAME = "ConvNeXt_Tiny_Weights.IMAGENET1K_V1"
WEIGHTS_CACHE = Path(__file__).resolve().parents[1] / ".cache" / "torch" / "hub"


def build_model(num_classes: int, pretrained: bool = True) -> torch.nn.Module:
    if num_classes < 1:
        raise ValueError("num_classes must be positive")
    try:
        if pretrained:
            WEIGHTS_CACHE.mkdir(parents=True, exist_ok=True)
            torch.hub.set_dir(str(WEIGHTS_CACHE))
        model = convnext_tiny(weights=ConvNeXt_Tiny_Weights.IMAGENET1K_V1 if pretrained else None)
    except Exception as exc:
        raise RuntimeError("Failed to load official ConvNeXt-Tiny ImageNet-1K V1 weights; check network/cache") from exc
    in_features = model.classifier[2].in_features
    model.classifier[2] = torch.nn.Linear(in_features, num_classes)
    return model


def parameter_counts(model: torch.nn.Module) -> dict[str, int]:
    return {"total": sum(p.numel() for p in model.parameters()),
            "trainable": sum(p.numel() for p in model.parameters() if p.requires_grad)}


def load_checkpoint(path: str | Path, device: str | torch.device = "cpu"):
    """Construct from saved weights without downloading ImageNet weights again."""
    try:
        checkpoint = torch.load(path, map_location=device, weights_only=False)
        if checkpoint["model_name"] != MODEL_NAME:
            raise ValueError(f"Unsupported model: {checkpoint['model_name']}")
        mapping = checkpoint["class_to_idx"]
        if sorted(mapping.values()) != list(range(checkpoint["num_classes"])):
            raise ValueError("Invalid checkpoint class mapping")
        model = build_model(checkpoint["num_classes"], pretrained=False)
        model.load_state_dict(checkpoint["model_state_dict"], strict=True)
        return model.to(device).eval(), checkpoint
    except Exception as exc:
        raise RuntimeError(f"Could not load checkpoint {path}: {exc}") from exc
