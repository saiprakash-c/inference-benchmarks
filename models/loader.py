"""
models/loader.py

Central model loader used by runtimes. Maps model names to nn.Module instances,
input shapes, and output shapes. Runtimes must use this instead of hardcoding
model-specific loading logic.

Forward-only: imports only torch and torchvision/hub. Does not import from
benchmark/, inputs/, runtimes/, results/, or site/.
"""

from typing import Any

import torch  # type: ignore[import]


# ── Shape registry ────────────────────────────────────────────────────────────

_INPUT_SHAPES: dict[str, tuple] = {
    "resnet50":  (1, 3, 224, 224),
    "dinov2_b":  (1, 3, 518, 518),
}

_OUTPUT_SHAPES: dict[str, tuple] = {
    "resnet50":  (1, 1000),
    "dinov2_b":  (1, 768),
}


def input_shape(model_name: str) -> tuple:
    """Return (B, C, H, W) input shape for model_name."""
    if model_name not in _INPUT_SHAPES:
        raise ValueError(f"Unknown model: {model_name!r}. Known: {list(_INPUT_SHAPES)}")
    return _INPUT_SHAPES[model_name]


def output_shape(model_name: str) -> tuple:
    """Return output shape for model_name."""
    if model_name not in _OUTPUT_SHAPES:
        raise ValueError(f"Unknown model: {model_name!r}. Known: {list(_OUTPUT_SHAPES)}")
    return _OUTPUT_SHAPES[model_name]


# ── Model loaders ─────────────────────────────────────────────────────────────

def load(model_name: str, device: str) -> Any:
    """Load model_name in eval mode on device and return the nn.Module."""
    if model_name == "resnet50":
        return _load_resnet50(device)
    if model_name == "dinov2_b":
        return _load_dinov2_b(device)
    raise ValueError(f"Unknown model: {model_name!r}. Known: {list(_INPUT_SHAPES)}")


def _load_resnet50(device: str) -> Any:
    import torchvision.models as tv_models  # type: ignore[import]
    weights = tv_models.ResNet50_Weights.IMAGENET1K_V2
    return tv_models.resnet50(weights=weights).eval().to(device)


def _load_dinov2_b(device: str) -> Any:
    model = torch.hub.load("facebookresearch/dinov2", "dinov2_vitb14", pretrained=True)
    return model.eval().to(device)
