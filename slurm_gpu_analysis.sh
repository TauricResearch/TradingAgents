#!/bin/bash
#SBATCH --job-name=trading-agents-gpu
#SBATCH --output=logs/gpu_trading_%j.out
#SBATCH --error=logs/gpu_trading_%j.err
#SBATCH --time=08:00:00
#SBATCH --gpus=1
#SBATCH --cpus-per-task=8
#SBATCH --mem=32G
#SBATCH --partition=gpu

# Exit on any error, undefined variable, or pipe failure
set -euo pipefail

# GPU-accelerated analysis using local LLM models
# This script is useful when running with Ollama or other local models that can benefit from GPU acceleration

echo "Starting TradingAgents GPU analysis..."
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURM_NODELIST"
echo "GPU: $CUDA_VISIBLE_DEVICES"
echo "Started at: $(date)"

# Parse command line arguments
SYMBOL=${1:-"SPY"}
DATE=${2:-$(date +%Y-%m-%d)}

echo "Analyzing symbol: $SYMBOL for date: $DATE"

# Load necessary modules
module load python/3.10
module load cuda/11.8

# Set up environment
WORK_DIR=${SLURM_SUBMIT_DIR}
cd $WORK_DIR

# Activate virtual environment
source venv/bin/activate

# Set environment variables
export PYTHONPATH="${WORK_DIR}:${PYTHONPATH}"
export TRADINGAGENTS_RESULTS_DIR="${WORK_DIR}/results"
export CUDA_VISIBLE_DEVICES=$CUDA_VISIBLE_DEVICES

# Set up Ollama if using local models
if [ "$LLM_PROVIDER" == "ollama" ]; then
    # Start Ollama server on this node
    export OLLAMA_HOST=0.0.0.0:11434
    export OLLAMA_GPU_LAYERS=999  # Use all GPU layers
    
    # Start Ollama in background
    ollama serve &
    OLLAMA_PID=$!
    
    # Wait for Ollama to start
    sleep 10
    
    # Pull required models if they don't exist
    ollama pull llama3.2 || echo "Model llama3.2 already exists or failed to pull"
fi

# Create results directory for this job
RESULTS_DIR="${WORK_DIR}/results/${SYMBOL}/${DATE}"
mkdir -p "$RESULTS_DIR"

# Create a custom Python script for GPU analysis
cat > "gpu_analysis_${SLURM_JOB_ID}.py" << EOF
import os
import sys
import json
import torch
from datetime import datetime
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    symbol = "$SYMBOL"
    date = "$DATE"
    
    print(f"Starting GPU-accelerated analysis for {symbol} on {date}")
    print(f"CUDA available: {torch.cuda.is_available()}")
    if torch.cuda.is_available():
        print(f"GPU device: {torch.cuda.get_device_name()}")
        print(f"GPU memory: {torch.cuda.get_device_properties(0).total_memory / 1e9:.2f} GB")
    
    # Create a custom config for GPU SLURM environment
    config = DEFAULT_CONFIG.copy()
    
    # Adjust for GPU cluster environment
    config["results_dir"] = os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")
    config["max_debate_rounds"] = 3  # More rounds for thorough analysis
    config["max_risk_discuss_rounds"] = 3
    config["online_tools"] = True
    
    # Configure for GPU-accelerated LLM
    config["llm_provider"] = os.getenv("LLM_PROVIDER", "ollama")
    config["backend_url"] = os.getenv("LLM_BACKEND_URL", "http://localhost:11434/v1")
    config["deep_think_llm"] = os.getenv("DEEP_THINK_LLM", "llama3.2")
    config["quick_think_llm"] = os.getenv("QUICK_THINK_LLM", "llama3.2")
    
    try:
        # Initialize trading agents
        ta = TradingAgentsGraph(debug=True, config=config)
        
        # Run analysis
        print("Running GPU-accelerated trading analysis...")
        state, decision = ta.propagate(symbol, date)
        
        # Save results
        results = {
            "symbol": symbol,
            "date": date,
            "decision": decision,
            "job_id": os.getenv("SLURM_JOB_ID"),
            "node": os.getenv("SLURM_NODELIST"),
            "gpu_used": torch.cuda.is_available(),
            "completed_at": datetime.now().isoformat()
        }
        
        output_file = f"$RESULTS_DIR/gpu_analysis_results_{os.getenv('SLURM_JOB_ID')}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"GPU analysis completed. Results saved to: {output_file}")
        print(f"Decision: {decision}")
        
    except Exception as e:
        print(f"Error during GPU analysis: {str(e)}")
        # Save error information
        error_info = {
            "symbol": symbol,
            "date": date,
            "error": str(e),
            "job_id": os.getenv("SLURM_JOB_ID"),
            "gpu_available": torch.cuda.is_available(),
            "failed_at": datetime.now().isoformat()
        }
        
        error_file = f"$RESULTS_DIR/gpu_error_{os.getenv('SLURM_JOB_ID')}.json"
        with open(error_file, 'w') as f:
            json.dump(error_info, f, indent=2)
        
        sys.exit(1)

if __name__ == "__main__":
    main()
EOF

# Run the analysis
echo "Running GPU Python analysis script..."
python "gpu_analysis_${SLURM_JOB_ID}.py"

# Clean up
rm "gpu_analysis_${SLURM_JOB_ID}.py"

# Stop Ollama if we started it
if [ ! -z "$OLLAMA_PID" ]; then
    kill $OLLAMA_PID
fi

echo "GPU job completed at: $(date)"
