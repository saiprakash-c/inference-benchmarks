import sys
sys.path.insert(0, "/workspace")
from benchmark.runner import BenchmarkConfig, run
cfg = BenchmarkConfig(
    models=["resnet50", "dinov2_b"],
    runtimes=["pytorch", "tensorrt", "torch_tensorrt", "executorch", "aot_inductor"],
    hardware=["thor"],
)
sys.exit(run(cfg))
