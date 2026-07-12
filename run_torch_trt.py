import sys
sys.path.insert(0, "/workspace")
from benchmark.runner import BenchmarkConfig, run
cfg = BenchmarkConfig(models=["resnet50", "dinov2_b"], runtimes=["torch_tensorrt"], hardware=["thor"])
sys.exit(run(cfg))
