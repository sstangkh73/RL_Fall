#!/usr/bin/env bash
# Create the project venv on Linux (WSL2 or an HPC login node) without sudo.
# Usage: scripts/setup_linux.sh [venv-path]
set -euo pipefail

VENV="${1:-$HOME/venvs/rl_fall}"
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
UV="${UV:-$(command -v uv || echo "$HOME/.local/bin/uv")}"

if [ ! -x "$UV" ]; then
    curl -LsSf https://astral.sh/uv/install.sh | env UV_NO_MODIFY_PATH=1 sh
    UV="$HOME/.local/bin/uv"
fi

"$UV" venv --python 3.12 "$VENV"
# The lock pins PyPI packages and a PyTorch-index torch build; both indexes are trusted.
"$UV" pip install --python "$VENV/bin/python" --index-strategy unsafe-best-match \
    -r "$ROOT/requirements-lock.txt"
"$VENV/bin/python" -c "import torch, mujoco; print('torch', torch.__version__, 'cuda', torch.cuda.is_available(), 'mujoco', mujoco.__version__)"
