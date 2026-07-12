"""
models/cosmos_reason2b/spec.py

Model spec for Cosmos-Reason2-2B (Qwen3-VL backbone).
Task: video_qa — evaluated on LingoQA with Lingo-Judge.

Forward-only: this package does not import from inputs/, runtimes/,
benchmark/, results/, or site/.
"""

from pathlib import Path

NAME = "cosmos_reason2b"
TASK = "video_qa"
INPUT_KEY = "lingoqa"
ACTIVE_PRECISION = "bf16"
SUPPORTED_PRECISIONS = ["bf16"]
EXCLUDED_RUNTIMES: frozenset[str] = frozenset({
    "pytorch",        # no VLM generate() path
    "tensorrt",       # no TRT engine for cosmos_reason2b
    "torch_tensorrt", # no TRT engine for cosmos_reason2b
    "executorch",     # no VLM support
    "aot_inductor",   # no VLM support
})

WARMUP_ITERS = 5        # 5 samples; VLM init is expensive
MEASURE_ITERS = 500     # full LingoQA eval set

# Model identifiers
HF_MODEL_ID = "nvidia/Cosmos-Reason2-2B"
TRT_LLM_ENGINE_DIR    = "/workspace/models/cosmos-reason2-2b-engine/llm"
TRT_VISUAL_ENGINE_DIR = "/workspace/models/cosmos-reason2-2b-engine/visual"

# Generation config — same as derisk eval
MAX_NEW_TOKENS = 64
MIN_PIXELS     = 163_840
MAX_PIXELS     = 196_608

# Lingo-Judge config
LINGO_JUDGE_MODEL      = "wayveai/Lingo-Judge"
LINGO_JUDGE_BATCH_SIZE = 64


def sample_image_path() -> Path:
    # Unused for VLMs — lingoqa.load() ignores this arg.
    # Required by runner interface.
    return Path(__file__).parent / "sample_frame.jpg"
