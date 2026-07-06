"""
//benchmark:run_resnet50

Runs benchmarks for resnet50 only (all runtimes, both precisions).
Used to derisk new features before running the full suite.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from benchmark.runner import BenchmarkConfig, run  # noqa: E402

cfg = BenchmarkConfig(
    models=["resnet50"],
    runtimes=["pytorch", "tensorrt", "torch_tensorrt", "executorch", "aot_inductor"],
    hardware=["thor"],
)
sys.exit(run(cfg))
