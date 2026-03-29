py_test(
    name = "lint",
    srcs = ["lint.py"],
    main = "lint.py",
    deps = ["//lib:log"],
    data = [
        "//docs:all_docs",
        "//:versions.toml",
    ],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "doc_review",
    srcs = ["doc_review.py"],
    main = "doc_review.py",
    deps = ["//lib:log"],
    visibility = ["//visibility:public"],
)

py_binary(
    name = "doc_gardening",
    srcs = ["doc_gardening.py"],
    main = "doc_gardening.py",
    deps = ["//lib:log"],
    visibility = ["//visibility:public"],
)
