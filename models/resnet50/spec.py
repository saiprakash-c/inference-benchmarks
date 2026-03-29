"""
models/resnet50/spec.py

ResNet50 model metadata: shape, weights identifier, benchmark protocol.
Input preprocessing lives in inputs/imagenet.py — not here.

Forward-only: this package does not import from inputs/, runtimes/,
benchmark/, results/, or site/.
"""

from pathlib import Path

NAME    = "resnet50"
TASK    = "image_classification"

# Standard ImageNet inference resolution: (batch, C, H, W)
INPUT_SHAPE = (1, 3, 224, 224)

ACTIVE_PRECISION = "fp32"

# torchvision weights identifier
TORCHVISION_WEIGHTS = "ResNet50_Weights.IMAGENET1K_V2"

# Benchmark protocol
WARMUP_ITERS  = 10
MEASURE_ITERS = 100


def sample_image_path() -> Path:
    """Canonical real input image for benchmark runs."""
    return Path(__file__).parent / "sample.jpg"
