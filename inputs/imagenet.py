"""
inputs/imagenet.py

ImageNet preprocessing pipeline and image loading.
Used by any model that expects standard ImageNet-normalised input.

Forward-only: this package imports only from lib/. It does not import
from runtimes/, benchmark/, results/, or site/.
"""

from pathlib import Path
from typing import Any

# Standard ImageNet per-channel normalisation
NORMALIZE_MEAN = (0.485, 0.456, 0.406)
NORMALIZE_STD  = (0.229, 0.224, 0.225)


def pipeline(resize: int = 256, crop: int = 224) -> Any:
    """
    Return a torchvision transform that converts a PIL Image to a
    normalised float32 tensor ready for ImageNet-trained models.

    Usage:
        transform = pipeline()
        tensor = transform(pil_image).unsqueeze(0)  # → (1, 3, 224, 224)
    """
    from torchvision import transforms  # type: ignore[import]

    return transforms.Compose([
        transforms.Resize(resize),
        transforms.CenterCrop(crop),
        transforms.ToTensor(),
        transforms.Normalize(mean=NORMALIZE_MEAN, std=NORMALIZE_STD),
    ])


def load(image_path: Path, resize: int = 256, crop: int = 224) -> Any:
    """
    Load a JPEG/PNG from disk and return a batched float32 tensor
    shaped (1, 3, crop, crop), ready for inference.
    """
    from PIL import Image  # type: ignore[import]

    img = Image.open(image_path).convert("RGB")
    return pipeline(resize, crop)(img).unsqueeze(0)
