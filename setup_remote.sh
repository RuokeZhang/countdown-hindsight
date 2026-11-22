#!/bin/bash
set -euo pipefail
cd /root/countdown_baseline
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH=/root/.local/bin:$PATH
uv venv --python 3.12 .venv
uv pip install --python .venv/bin/python vllm==0.32.0 datasets
echo SETUP_DONE
