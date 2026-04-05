"""
benchmark/registry.py

Central registries mapping string keys to model specs, runtime classes,
and input pipeline modules. Adding a new entry requires only registering
the new key here — the runner resolves everything via these dicts.
"""

import inputs.imagenet as imagenet
from models.resnet50 import spec as resnet50_spec
from runtimes.aot_inductor.runtime import AOTInductorRuntime
from runtimes.executorch.runtime import ExecuTorchRuntime
from runtimes.pytorch.runtime import PyTorchRuntime
from runtimes.tensorrt.runtime import TensorRTRuntime

MODEL_REGISTRY: dict = {
    "resnet50": resnet50_spec,
}

RUNTIME_REGISTRY: dict = {
    "pytorch":      PyTorchRuntime,
    "tensorrt":     TensorRTRuntime,
    "executorch":   ExecuTorchRuntime,
    "aot_inductor": AOTInductorRuntime,
}

INPUT_REGISTRY: dict = {
    "imagenet": imagenet,
}
