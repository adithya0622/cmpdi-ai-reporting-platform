#!/usr/bin/env bash
# ==============================================================================
# CMPDI / CIL AI Platform - Local LoRA Fine-Tuning in WSL with NVIDIA GPU
# ==============================================================================
set -e

DIR="$( cd "$( dirname "${BASH_SOURCE[0]}" )/.." && pwd )"
DATA_PATH="$DIR/data/finetune/train.jsonl"
OUT_PATH="$DIR/data/finetune/adapter"
VENV_PATH="/tmp/cmpdi_train_venv"

echo "=========================================================="
echo " CMPDI / CIL Qwen 2.5 3B LoRA Fine-Tuning (WSL Ubuntu)"
echo "=========================================================="

if ! command -v nvidia-smi &> /dev/null; then
    echo "[!] Warning: nvidia-smi not found. Ensure NVIDIA WSL drivers are installed."
else
    echo "[+] GPU Detected:"
    nvidia-smi --query-gpu=name,memory.total,memory.free --format=csv,noheader
fi

if [ ! -f "$DATA_PATH" ]; then
    echo "[!] Error: Training data not found at $DATA_PATH"
    echo "    Run '.venv\\Scripts\\python scripts/finetune_lora.py --build-only' on Windows first."
    exit 1
fi

COUNT=$(wc -l < "$DATA_PATH")
echo "[+] Verified training dataset: $COUNT samples ($DATA_PATH)"

# Create Python environment if needed
if [ ! -d "$VENV_PATH" ]; then
    echo "[*] Setting up dedicated training virtualenv in $VENV_PATH..."
    python3 -m venv "$VENV_PATH"
    "$VENV_PATH/bin/pip" install --upgrade pip setuptools wheel
    echo "[*] Installing PyTorch with CUDA support..."
    "$VENV_PATH/bin/pip" install torch --index-url https://download.pytorch.org/whl/cu124
    echo "[*] Installing fine-tuning suite (transformers, peft, datasets, trl, accelerate)..."
    "$VENV_PATH/bin/pip" install transformers peft datasets trl accelerate bitsandbytes
fi

echo "[*] Launching fine-tuning workflow..."
"$VENV_PATH/bin/python" "$DIR/scripts/finetune_lora.py" \
    --data "$DATA_PATH" \
    --out "$OUT_PATH" \
    --epochs 3 \
    --batch-size 2 \
    --lr 0.0002

echo "=========================================================="
echo "[+] Fine-tuning complete! Adapter saved to: $OUT_PATH"
echo "    Load into llama-server: llama-server.exe --lora $OUT_PATH"
echo "=========================================================="
