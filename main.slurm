#!/bin/bash
#SBATCH --job-name=tradingAgents
#SBATCH --output=runs/%j/run_%j.out
#SBATCH --error=runs/%j/run_%j.err
#SBATCH --time=02:00:00
#SBATCH --partition=gpu
#SBATCH --ntasks=1
#SBATCH --cpus-per-task=4
#SBATCH --gpus=h100-96:1
#SBATCH --mem=700G

# Run the script
uv sync
uv run main.py
