load("@pip//:requirements.bzl", "requirement")

py_binary(
    name = "build",
    srcs = ["build.py"],
    main = "build.py",
    data = glob(["templates/**"]),
    deps = [
        "//lib:log",
        requirement("jinja2"),
    ],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "deploy",
    srcs = ["deploy.py"],
    main = "deploy.py",
    deps = ["//lib:log"],
    visibility = ["//visibility:public"],
)
