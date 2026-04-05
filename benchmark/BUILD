load("@pip//:requirements.bzl", "requirement")

py_library(
    name = "registry",
    srcs = ["registry.py"],
    deps = [
        "//models/resnet50:resnet50",
        "//models/dinov2_b:dinov2_b",
        "//runtimes/pytorch:pytorch",
        "//runtimes/tensorrt:tensorrt",
        "//runtimes/torch_tensorrt:torch_tensorrt",
        "//runtimes/executorch:executorch",
        "//runtimes/aot_inductor:aot_inductor",
        "//inputs:imagenet",
        "//inputs:dinov2",
    ],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "run",
    srcs = ["runner.py"],
    main = "runner.py",
    deps = [
        "//benchmark:registry",
        "//hardware:thor",
        "//lib:log",
        "//runtimes/pytorch:pytorch",
        "//runtimes/tensorrt:tensorrt",
        "//runtimes/torch_tensorrt:torch_tensorrt",
        "//runtimes/executorch:executorch",
        "//runtimes/aot_inductor:aot_inductor",
        requirement("tomli-w"),
    ],
    visibility = ["//visibility:public"],
)
