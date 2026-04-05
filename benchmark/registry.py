"""
benchmark/registry.py

Central registries mapping string keys to model specs, runtime classes,
and input pipeline modules. Adding a new entry requires only registering
the new key here — the runner resolves everything via these dicts.
"""

import inputs.dinov2 as dinov2_input
import inputs.imagenet as imagenet
from models.dinov2_b import spec as dinov2_b_spec
from models.resnet50 import spec as resnet50_spec
from runtimes.aot_inductor.runtime import AOTInductorRuntime
from runtimes.executorch.runtime import ExecuTorchRuntime
from runtimes.pytorch.runtime import PyTorchRuntime
from runtimes.tensorrt.runtime import TensorRTRuntime
from runtimes.torch_tensorrt.runtime import TorchTensorRTRuntime

MODEL_REGISTRY: dict = {
    "resnet50":  resnet50_spec,
    "dinov2_b":  dinov2_b_spec,
}

RUNTIME_REGISTRY: dict = {
    "pytorch":         PyTorchRuntime,
    "tensorrt":        TensorRTRuntime,
    "torch_tensorrt":  TorchTensorRTRuntime,
    "executorch":      ExecuTorchRuntime,
    "aot_inductor":    AOTInductorRuntime,
}

INPUT_REGISTRY: dict = {
    "imagenet": imagenet,
    "dinov2":   dinov2_input,
}
