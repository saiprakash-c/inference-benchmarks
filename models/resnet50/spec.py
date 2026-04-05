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
SUPPORTED_PRECISIONS = ["fp32", "fp16"]
INPUT_KEY = "imagenet"
AOT_COMPILE_OPTIONS: dict = {
    "freezing":                  True,   # fold BN into preceding Conv weights
    "layout_optimization":       True,   # keep tensors in NHWC, eliminates layout copies
    "coordinate_descent_tuning": True,   # lightweight Triton tile search
}
EXCLUDED_RUNTIMES: frozenset[str] = frozenset()

# torchvision weights identifier
TORCHVISION_WEIGHTS = "ResNet50_Weights.IMAGENET1K_V2"

# Benchmark protocol
WARMUP_ITERS  = 10
MEASURE_ITERS = 100


def sample_image_path() -> Path:
    """Canonical real input image for benchmark runs."""
    return Path(__file__).parent / "sample.jpg"
