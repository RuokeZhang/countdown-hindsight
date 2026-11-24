#!/bin/bash
# Same environment as on the L40S: verl-agent 20bd331 + our patch, vllm 0.11.0, flash-attn 2.8.3 (torch 2.8 wheel), transformers 4.57.3.
set -euxo pipefail
curl -LsSf https://astral.sh/uv/install.sh | sh
export PATH=/root/.local/bin:$PATH
mkdir -p /root/alf && cd /root/alf
git clone -q https://github.com/langfengQ/verl-agent.git && cd verl-agent && git checkout -q 20bd331bdbc9026a5668e11362178e10ab7400c8
git apply /root/alf/hs/verl_agent_changes.patch
cd /root/alf
uv venv --python 3.12 venv
source venv/bin/activate
uv pip install vllm==0.11.0
uv pip install "https://github.com/Dao-AILab/flash-attention/releases/download/v2.8.3/flash_attn-2.8.3+cu12torch2.8cxx11abiTRUE-cp312-cp312-linux_x86_64.whl"
cd verl-agent && uv pip install -e . "transformers==4.57.3" && cd ..
uv pip install gymnasium==0.29.1 stable-baselines3==2.6.0 alfworld
python -c "import torch, vllm, transformers, flash_attn; print(torch.__version__, vllm.__version__, transformers.__version__, flash_attn.__version__)"
export ALFWORLD_DATA=/root/alf/alfworld_data
alfworld-download -f
cd /root/alf/hs && python make_train_subset.py --out_list train_subset_240.regenerated.txt --out_dir /root/alf/alfworld_data/train_subset_240
cmp train_subset_240.txt train_subset_240.regenerated.txt && echo SUBSET_IDENTICAL
python -c "from huggingface_hub import snapshot_download; snapshot_download('Qwen/Qwen2.5-1.5B-Instruct')"
uv pip freeze > /root/alf/pip_freeze.txt
echo SETUP_DONE
