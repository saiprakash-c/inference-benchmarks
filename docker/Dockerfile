# inference-benchmarks runtime image
#
# Execution environment for benchmark runs on Thor (Jetson AGX Thor).
# Base: nvcr.io/nvidia/cuda:13.0.2-runtime-ubuntu24.04 (arm64).
# TensorRT 10.16.0 installed via NVIDIA Jetson apt repo (r38.4).
# Python deps installed from pyproject.toml [project.optional-dependencies.gpu].
#
# Versions here must match versions.toml [docker] section exactly.
# See docs/VERSIONING.md for rebuild trigger rules.
#
# Build:  bazel run //docker:build
# Push:   bazel run //docker:push
# After push: update [docker].digest in versions.toml with the new digest.

FROM nvcr.io/nvidia/cuda:13.0.2-devel-ubuntu24.04

SHELL ["/bin/bash", "-o", "pipefail", "-c"]

LABEL org.opencontainers.image.source="https://github.com/saiprakash-c/inference-benchmarks"
LABEL org.opencontainers.image.description="Inference benchmark environment: TensorRT + PyTorch + ExecuTorch on Jetson AGX Thor"

# ── System dependencies ────────────────────────────────────────────────────────
# hadolint ignore=DL3008
RUN apt-get update && apt-get install -y --no-install-recommends \
    python3-pip \
    python3-dev \
    gcc \
    g++ \
    curl \
    git \
    ca-certificates \
    gnupg \
    vim \
    zsh \
    && rm -rf /var/lib/apt/lists/*

# ── TensorRT via NVIDIA Jetson apt repo ───────────────────────────────────────
# Adds the Jetson r38.4 package repo and installs TensorRT 10.16.0 (CUDA 13.0).
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

# ── Triton ptxas fix for Jetson AGX Thor (sm_110a) ────────────────────────────
# Triton 3.6 bundles ptxas-blackwell built against CUDA 12.8, which does not
# recognise sm_110a (Blackwell variant on Thor). Replace it with the CUDA 13.0
# ptxas bundled with PyTorch, which supports sm_110a.
# hadolint ignore=SC2046
RUN torch_ptxas=$(find /usr/local/lib/python3* -name ptxas -path "*/torch/bin/*" 2>/dev/null | head -1) && \
    triton_blackwell=$(find /usr/local/lib/python3* -name ptxas-blackwell -path "*/triton/*" 2>/dev/null | head -1) && \
    cp "$torch_ptxas" "$triton_blackwell"

# ── Node.js 18 LTS + Claude Code ──────────────────────────────────────────────
ARG NODE_VERSION=18.20.8
ARG CLAUDE_CODE_VERSION=2.1.92
RUN curl -fsSL "https://nodejs.org/dist/v${NODE_VERSION}/node-v${NODE_VERSION}-linux-arm64.tar.gz" \
    | tar -xz -C /usr/local --strip-components=1
RUN npm install -g @anthropic-ai/claude-code@${CLAUDE_CODE_VERSION}

# ── User ──────────────────────────────────────────────────────────────────────
ARG UID=1000
ARG USERNAME=saip
COPY docker/saip.zshrc /tmp/saip.zshrc
RUN userdel -r ubuntu 2>/dev/null || true && \
    useradd -m -l -u ${UID} -s /bin/zsh ${USERNAME} && \
    cat /tmp/saip.zshrc >> /home/${USERNAME}/.zshrc

USER ${USERNAME}

# ── Workspace ─────────────────────────────────────────────────────────────────
WORKDIR /workspace

ENTRYPOINT ["bazel"]
CMD ["help"]
