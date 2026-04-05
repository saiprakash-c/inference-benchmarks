py_library(
    name = "registry",
    srcs = ["registry.py"],
    deps = [
        "//models/resnet50:resnet50",
        "//runtimes/pytorch:pytorch",
        "//runtimes/tensorrt:tensorrt",
        "//runtimes/executorch:executorch",
        "//runtimes/aot_inductor:aot_inductor",
        "//inputs:imagenet",
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
        "//runtimes/executorch:executorch",
        "//runtimes/aot_inductor:aot_inductor",
    ],
    visibility = ["//visibility:public"],
)
