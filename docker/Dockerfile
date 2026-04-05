# inference-benchmarks runtime image
#
# Execution environment for benchmark runs on Thor (Jetson AGX Thor).
# Base: nvcr.io/nvidia/cuda:13.0.2-runtime-ubuntu24.04 (arm64).
# TensorRT 10.x installed via NVIDIA Jetson apt repo (r38.4).
# Python deps installed from pyproject.toml [project.optional-dependencies.gpu].
#
# Versions here must match versions.toml [docker] section exactly.
# See docs/VERSIONING.md for rebuild trigger rules.
#
# Build:  bazel run //docker:build
# Push:   bazel run //docker:push
# After push: update [docker].digest in versions.toml with the new digest.

FROM nvcr.io/nvidia/cuda:13.0.2-runtime-ubuntu24.04

LABEL org.opencontainers.image.source="https://github.com/saiprakash-c/inference-benchmarks"
LABEL org.opencontainers.image.description="Inference benchmark environment: TensorRT + PyTorch + ExecuTorch on Jetson AGX Thor"

# ── System dependencies ────────────────────────────────────────────────────────
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    curl \
    git \
    ca-certificates \
    gnupg \
    zsh \
    && rm -rf /var/lib/apt/lists/*

# ── TensorRT via NVIDIA Jetson apt repo ───────────────────────────────────────
# Adds the Jetson r38.4 package repo and installs TensorRT 10.x (CUDA 13.0).
# hadolint ignore=DL3008
RUN curl -fsSL https://repo.download.nvidia.com/jetson/jetson-ota-public.asc \
    | gpg --dearmor -o /usr/share/keyrings/nvidia-jetson.gpg && \
    echo "deb [signed-by=/usr/share/keyrings/nvidia-jetson.gpg] \
https://repo.download.nvidia.com/jetson/common r38.4 main" \
    > /etc/apt/sources.list.d/nvidia-jetson.list && \
    apt-get update && apt-get install -y --no-install-recommends \
    tensorrt \
    && rm -rf /var/lib/apt/lists/*

# ── Bazel ─────────────────────────────────────────────────────────────────────
ARG BAZEL_VERSION=7.4.1
RUN curl -fsSL \
    "https://github.com/bazelbuild/bazel/releases/download/${BAZEL_VERSION}/bazel-${BAZEL_VERSION}-linux-arm64" \
    -o /usr/local/bin/bazel \
    && chmod +x /usr/local/bin/bazel

# ── gh CLI ────────────────────────────────────────────────────────────────────
ARG GH_VERSION=2.67.0
# hadolint ignore=DL4006
RUN curl -fsSL \
    "https://github.com/cli/cli/releases/download/v${GH_VERSION}/gh_${GH_VERSION}_linux_arm64.tar.gz" \
    | tar -xz -C /usr/local --strip-components=1 gh_${GH_VERSION}_linux_arm64/bin/gh

# ── Python deps from pyproject.toml ───────────────────────────────────────────
# Jetson wheels come from pypi.jetson-ai-lab.io; PyPI is the fallback.
COPY pyproject.toml /workspace/pyproject.toml
# hadolint ignore=DL3013
RUN pip3 install --no-cache-dir --break-system-packages \
    --extra-index-url https://pypi.jetson-ai-lab.io/jp7/cu130 \
    "/workspace[gpu]"

# ── Node.js 18 LTS + Claude Code ──────────────────────────────────────────────
ARG NODE_VERSION=18.20.8
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.gz" \
    | tar -xz -C /usr/local --strip-components=1
RUN npm install -g @anthropic-ai/claude-code

# ── User ──────────────────────────────────────────────────────────────────────
ARG UID=1000
COPY docker/saip.zshrc /tmp/saip.zshrc
RUN useradd -m -u ${UID} -s /bin/zsh saip && \
    cat /tmp/saip.zshrc >> /home/saip/.zshrc

USER saip

# ── Workspace ─────────────────────────────────────────────────────────────────
WORKDIR /workspace

ENTRYPOINT ["bazel"]
CMD ["help"]
