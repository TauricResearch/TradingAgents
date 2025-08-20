#!/bin/bash
#SBATCH --job-name=trading-agents-batch
#SBATCH --output=logs/batch_%A_%a.out
#SBATCH --error=logs/batch_%A_%a.err
#SBATCH --time=06:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --partition=cpu
#SBATCH --array=1-10%5

# Exit on any error, undefined variable, or pipe failure
set -euo pipefail

# Batch analysis for multiple stocks
# This script runs trading analysis for multiple symbols in parallel
# The %5 limits to 5 concurrent jobs

echo "Starting TradingAgents batch analysis..."
echo "Job ID: ${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}"
echo "Node: $SLURM_NODELIST"
echo "Started at: $(date)"

# Load necessary modules
module load python/3.10

# Set up environment
WORK_DIR=${SLURM_SUBMIT_DIR}
cd $WORK_DIR

# Activate virtual environment
source venv/bin/activate

# Set environment variables
export PYTHONPATH="${WORK_DIR}:${PYTHONPATH}"
export TRADINGAGENTS_RESULTS_DIR="${WORK_DIR}/results"

# Define array of stocks to analyze
SYMBOLS=("SPY" "QQQ" "AAPL" "MSFT" "GOOGL" "AMZN" "TSLA" "NVDA" "META" "NFLX")

# Get the symbol for this array task
SYMBOL=${SYMBOLS[$((SLURM_ARRAY_TASK_ID-1))]}
DATE=$(date +%Y-%m-%d)

echo "Processing symbol: $SYMBOL (Task ${SLURM_ARRAY_TASK_ID})"

# Create results directory for this symbol
RESULTS_DIR="${WORK_DIR}/results/${SYMBOL}/${DATE}"
mkdir -p "$RESULTS_DIR"

# Create a custom Python script for this analysis
cat > "batch_analysis_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.py" << EOF
import os
import sys
import json
from datetime import datetime
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.default_config import DEFAULT_CONFIG
from dotenv import load_dotenv

# Load environment variables
load_dotenv()

def main():
    symbol = "$SYMBOL"
    date = "$DATE"
    task_id = "$SLURM_ARRAY_TASK_ID"
    
    print(f"Batch analysis - Task {task_id}: {symbol} on {date}")
    
    # Create a custom config for SLURM environment
    config = DEFAULT_CONFIG.copy()
    
    # Adjust for cluster environment
    config["results_dir"] = os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")
    config["max_debate_rounds"] = 2
    config["max_risk_discuss_rounds"] = 2
    config["online_tools"] = True
    
    # Use environment variables for LLM configuration
    config["llm_provider"] = os.getenv("LLM_PROVIDER", "ollama")
    config["backend_url"] = os.getenv("LLM_BACKEND_URL", "http://localhost:11434/v1")
    config["deep_think_llm"] = os.getenv("DEEP_THINK_LLM", "llama3.2")
    config["quick_think_llm"] = os.getenv("QUICK_THINK_LLM", "llama3.2")
    
    try:
        # Initialize trading agents
        ta = TradingAgentsGraph(debug=True, config=config)
        
        # Run analysis
        print(f"Running trading analysis for {symbol}...")
        state, decision = ta.propagate(symbol, date)
        
        # Save results
        results = {
            "symbol": symbol,
            "date": date,
            "decision": decision,
            "array_job_id": os.getenv("SLURM_ARRAY_JOB_ID"),
            "task_id": task_id,
            "node": os.getenv("SLURM_NODELIST"),
            "completed_at": datetime.now().isoformat()
        }
        
        output_file = f"$RESULTS_DIR/batch_results_task_{task_id}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"Analysis completed for {symbol}. Results saved to: {output_file}")
        print(f"Decision: {decision}")
        
    except Exception as e:
        print(f"Error during analysis of {symbol}: {str(e)}")
        # Save error information
        error_info = {
            "symbol": symbol,
            "date": date,
            "error": str(e),
            "array_job_id": os.getenv("SLURM_ARRAY_JOB_ID"),
            "task_id": task_id,
            "failed_at": datetime.now().isoformat()
        }
        
        error_file = f"$RESULTS_DIR/error_task_{task_id}.json"
        with open(error_file, 'w') as f:
            json.dump(error_info, f, indent=2)
        
        sys.exit(1)

if __name__ == "__main__":
    main()
EOF

# Run the analysis
echo "Running Python analysis script for $SYMBOL..."
python "batch_analysis_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.py"

# Clean up temporary script
rm "batch_analysis_${SLURM_ARRAY_JOB_ID}_${SLURM_ARRAY_TASK_ID}.py"

echo "Task ${SLURM_ARRAY_TASK_ID} for $SYMBOL completed at: $(date)"
