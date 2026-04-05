# Thor Setup

Runbook for provisioning a Jetson AGX Thor from factory state to benchmark-ready.
Current Thor: `100.117.216.89` (Tailscale), hostname `thor`, user `saip`.

---

## Hardware

| Item | Value |
|---|---|
| Device | NVIDIA Jetson AGX Thor |
| JetPack | 7.1 (L4T R38.4.0) |
| CUDA | 13.0 |
| Driver | 580.00 |
| Disk | 937 GB NVMe |

---

## Stage 1 — Initial boot and OS setup (manual, one-time)

This stage requires a monitor + keyboard connected to Thor.

Reference: https://youtu.be/FVPE5zCte_E?t=420

1. Power on Thor. It boots into a Ubuntu 24.04 setup wizard.
2. Follow the wizard: set language, timezone, username (`saip`), password.
3. Complete setup and log into the desktop.

---

## Stage 2 — Tailscale (manual, one-time)

Done from the Thor desktop (browser + terminal).

1. Open Firefox (pre-installed). Go to https://tailscale.com/download/linux and follow install steps:
   ```bash
   curl -fsSL https://tailscale.com/install.sh | sh
   sudo tailscale up
   ```
2. A browser tab opens — log in with your Tailscale account to authenticate.
3. Verify Thor appears in your tailnet:
   ```bash
   tailscale ip   # should show 100.x.x.x
   ```

---

## Stage 3 — SSH key auth (manual, one-time)

Done from Thor (paste your Mac's public key).

```bash
mkdir -p ~/.ssh && chmod 700 ~/.ssh
# Paste your Mac public key (cat ~/.ssh/id_ed25519.pub on Mac)
echo "YOUR_PUBLIC_KEY" >> ~/.ssh/authorized_keys
chmod 600 ~/.ssh/authorized_keys
```

On Mac, add Thor to `~/.ssh/config`:
```
Host thor
  HostName 100.117.216.89
  User saip
```

Test: `ssh saip@thor "echo ok"`

---

## Stage 4 — Automated post-flash setup (run once on Thor)

SSH into Thor and run:

```bash
# Passwordless sudo (required for CI/agent automation)
echo 'saip ALL=(ALL) NOPASSWD: ALL' | sudo tee /etc/sudoers.d/saip-nopasswd

# Add saip to docker group
sudo usermod -aG docker saip

# Set nvidia as default Docker runtime
sudo python3 -c "
import json
json.dump({
    'default-runtime': 'nvidia',
    'runtimes': {'nvidia': {'args': [], 'path': 'nvidia-container-runtime'}}
}, open('/etc/docker/daemon.json', 'w'), indent=2)
"
sudo systemctl restart docker

# Install Docker Compose v2 plugin (not included in Ubuntu 24.04 apt)
DOCKER_CONFIG=${DOCKER_CONFIG:-$HOME/.docker}
mkdir -p $DOCKER_CONFIG/cli-plugins
curl -SL https://github.com/docker/compose/releases/download/v2.35.0/docker-compose-linux-aarch64 \
    -o $DOCKER_CONFIG/cli-plugins/docker-compose
chmod +x $DOCKER_CONFIG/cli-plugins/docker-compose

# Set JETPACK_VERSION env var (used by //versions:check)
echo 'JETPACK_VERSION=38.4.0' | sudo tee -a /etc/environment
```

Log out and back in (or `newgrp docker`) for group change to take effect.

Verify GPU works in Docker:
```bash
docker run --rm --runtime nvidia ubuntu:22.04 nvidia-smi
```

---

## Stage 5 — Clone repo and build containers

```bash
# Clone the repo
git clone https://github.com/saiprakash-c/inference-benchmarks.git ~/inference-benchmarks

# Pre-create files that docker-compose bind-mounts (Docker creates a dir if missing)
touch ~/.zsh_history ~/.claude.json
mkdir -p ~/.claude ~/.config/gh

# Build the runtime image (~5 min first time)
docker build \
    --build-arg USERNAME=$(whoami) \
    --build-arg UID=$(id -u) \
    -f ~/inference-benchmarks/docker/Dockerfile \
    -t ghcr.io/saiprakash-c/inference-benchmarks:latest \
    ~/inference-benchmarks

# Launch the runtime container
~/inference-benchmarks/bin/docker_rt
```

---

## Stage 6 — Verify

Run the verification script from your Mac:

```bash
bazel run //tools:verify_thor
```

All checks must pass before running benchmarks.

---

## Re-provisioning a new Thor

Repeat Stages 1–6 in order. Stage 3 onwards can be done entirely over SSH
once Tailscale is up. The only stage requiring physical access is Stage 1–2
(initial boot + Tailscale auth in browser).
