"""
models/dinov2_b/spec.py

DINOv2 ViT-B/14 model metadata: shape, benchmark protocol.
Input preprocessing lives in inputs/dinov2.py — not here.

DINOv2 is a self-supervised vision encoder from Meta. The ViT-B/14 variant
outputs a 768-dimensional CLS token embedding. Patch size is 14 so input
resolution must be a multiple of 14; the canonical resolution is 518×518.

Forward-only: this package does not import from inputs/, runtimes/,
benchmark/, results/, or site/.
"""

from pathlib import Path

NAME    = "dinov2_b"
TASK    = "vision_encoder"

# Input resolution: must be divisible by patch size 14; 518 = 37 × 14.
INPUT_SHAPE = (1, 3, 518, 518)

ACTIVE_PRECISION = "fp32"
SUPPORTED_PRECISIONS = ["fp32", "fp16"]
INPUT_KEY = "dinov2"
EXCLUDED_RUNTIMES: frozenset[str] = frozenset({"executorch"})

# Benchmark protocol
WARMUP_ITERS  = 10
MEASURE_ITERS = 100


def sample_image_path() -> Path:
    """Canonical real input image for benchmark runs."""
    return Path(__file__).parent / "sample.jpg"
