"""
inputs/dinov2.py

Preprocessing pipeline for DINOv2 models.
Loads images at 518×518 using standard ImageNet normalisation.
DINOv2 requires input resolution to be a multiple of its patch size (14),
and 518 = 37 × 14 is the canonical resolution from the paper.

Forward-only: this package imports only from lib/. It does not import
from runtimes/, benchmark/, results/, or site/.
"""

from pathlib import Path
from typing import Any

from inputs.imagenet import NORMALIZE_MEAN, NORMALIZE_STD


def load(image_path: Path) -> Any:
    """
    Load image from disk and return a batched float32 tensor shaped
    (1, 3, 518, 518), normalised with ImageNet mean/std.
    """
    from PIL import Image  # type: ignore[import]
    from torchvision import transforms  # type: ignore[import]

    pipeline = transforms.Compose([
        transforms.Resize(518),
        transforms.CenterCrop(518),
        transforms.ToTensor(),
        transforms.Normalize(mean=NORMALIZE_MEAN, std=NORMALIZE_STD),
    ])
    img = Image.open(image_path).convert("RGB")
    return pipeline(img).unsqueeze(0)
