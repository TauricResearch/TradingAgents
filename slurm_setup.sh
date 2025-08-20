#!/bin/bash
#SBATCH --job-name=trading-agents-setup
#SBATCH --output=setup_%j.out
#SBATCH --error=setup_%j.err
#SBATCH --time=02:00:00
#SBATCH --cpus-per-task=4
#SBATCH --mem=8G
#SBATCH --partition=cpu

# Exit on any error, undefined variable, or pipe failure
set -euo pipefail

# TradingAgents SLURM Setup Script
# This script sets up the environment for running TradingAgents on a SLURM cluster

echo "Setting up TradingAgents environment on SLURM cluster..."
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURM_NODELIST"
echo "Started at: $(date)"

# Load necessary modules (adjust based on your cluster's available modules)
module load python/3.10
module load git

# Set up working directory
WORK_DIR=${SLURM_SUBMIT_DIR}
cd $WORK_DIR

# Create Python virtual environment if it doesn't exist
if [ ! -d "venv" ]; then
    echo "Creating Python virtual environment..."
    python -m venv venv
fi

# Activate virtual environment
source venv/bin/activate

# Upgrade pip
pip install --upgrade pip

# Install dependencies
echo "Installing Python dependencies..."
pip install -r requirements.txt

# Create necessary directories
mkdir -p results
mkdir -p logs
mkdir -p data_cache

# Set environment variables
export PYTHONPATH="${WORK_DIR}:${PYTHONPATH}"

echo "Environment setup completed at: $(date)"
