# inference-benchmarks Docker image
#
# Execution environment for benchmark runs on Thor (Jetson AGX Orin).
# Versions here must match versions.toml [docker] section exactly.
# See docs/VERSIONING.md for rebuild trigger rules.
#
# Build:  bazel run //docker:build
# Push:   bazel run //docker:push
# After push: update [docker].digest in versions.toml with the new digest.

# hadolint ignore=DL3006
FROM nvcr.io/nvidia/l4t-tensorrt:r10.9.0-runtime

LABEL org.opencontainers.image.source="https://github.com/saiprakash-c/inference-benchmarks"
LABEL org.opencontainers.image.description="Inference benchmark environment: TensorRT + PyTorch + ExecuTorch on JetPack"

# ── System dependencies ──────────────────────────────────────────────────────
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    curl \
    git \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# ── Bazel ─────────────────────────────────────────────────────────────────────
ARG BAZEL_VERSION=7.4.1
RUN curl -fsSL \
    "https://github.com/bazelbuild/bazel/releases/download/${BAZEL_VERSION}/bazel-${BAZEL_VERSION}-linux-arm64" \
    -o /usr/local/bin/bazel \
    && chmod +x /usr/local/bin/bazel

# ── gh CLI ────────────────────────────────────────────────────────────────────
ARG GH_VERSION=2.67.0
RUN curl -fsSL \
    "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_arm64.tar.gz" \
    | tar -xz -C /usr/local --strip-components=1 gh_${GH_VERSION}_linux_arm64/bin/gh

# ── Python runtimes ───────────────────────────────────────────────────────────
# Versions must match versions.toml [runtimes].
# These are installed as wheels; they do NOT trigger an image rebuild when
# updated — only cuda/jetpack/cudnn changes require a rebuild.
# See docs/VERSIONING.md "Docker Image Rebuild Trigger".
ARG PYTORCH_VERSION=2.7.0
ARG EXECUTORCH_VERSION=0.5.1

# hadolint ignore=DL3013
RUN pip3 install --no-cache-dir \
    "torch==${PYTORCH_VERSION}" \
    "executorch==${EXECUTORCH_VERSION}"

# TensorRT Python bindings are provided by the base image (l4t-tensorrt).
# Verify the version is as expected at build time.
RUN python3 -c "import tensorrt; assert tensorrt.__version__.startswith('10.9'), \
    f'Unexpected TensorRT version: {tensorrt.__version__}'"

# ── Workspace ─────────────────────────────────────────────────────────────────
WORKDIR /workspace

# Default entrypoint: bazel run target specified at docker run time.
# Example: docker run --rm inference-benchmarks bazel run //benchmark:run
ENTRYPOINT ["bazel"]
CMD ["help"]
