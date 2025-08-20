#!/bin/bash
#SBATCH --job-name=trading-agents-single
#SBATCH --output=logs/trading_%j.out
#SBATCH --error=logs/trading_%j.err
#SBATCH --time=04:00:00
#SBATCH --cpus-per-task=8
#SBATCH --mem=16G
#SBATCH --partition=cpu

# Exit on any error, undefined variable, or pipe failure
set -euo pipefail

# Single stock analysis job
# Usage: sbatch slurm_single_analysis.sh SYMBOL DATE

echo "Starting TradingAgents single analysis..."
echo "Job ID: $SLURM_JOB_ID"
echo "Node: $SLURM_NODELIST"
echo "Started at: $(date)"

# Parse command line arguments
SYMBOL=${1:-"SPY"}
DATE=${2:-$(date +%Y-%m-%d)}

echo "Analyzing symbol: $SYMBOL for date: $DATE"

# Load necessary modules
if ! module load python/3.10; then
    echo "ERROR: Failed to load Python module"
    exit 1
fi

# Set up environment
WORK_DIR=${SLURM_SUBMIT_DIR}
cd "$WORK_DIR" || { echo "ERROR: Cannot access work directory $WORK_DIR"; exit 1; }

# Activate virtual environment
if [ ! -f "venv/bin/activate" ]; then
    echo "ERROR: Virtual environment not found. Run setup first."
    exit 1
fi

if ! source venv/bin/activate; then
    echo "ERROR: Failed to activate virtual environment"
    exit 1
fi

# Set environment variables
export PYTHONPATH="${WORK_DIR}:${PYTHONPATH}"
export TRADINGAGENTS_RESULTS_DIR="${WORK_DIR}/results"

# Set SLURM-specific configurations
export SLURM_JOB_MODE=true
export SLURM_CPUS_AVAILABLE=$SLURM_CPUS_PER_TASK

# Create results directory for this job
RESULTS_DIR="${WORK_DIR}/results/${SYMBOL}/${DATE}"
if ! mkdir -p "$RESULTS_DIR"; then
    echo "ERROR: Failed to create results directory: $RESULTS_DIR"
    exit 1
fi

# Create a custom Python script for this analysis
cat > "slurm_analysis_${SLURM_JOB_ID}.py" << EOF
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
    
    print(f"Starting analysis for {symbol} on {date}")
    
    # Create a custom config for SLURM environment
    config = DEFAULT_CONFIG.copy()
    
    # Adjust for cluster environment
    config["results_dir"] = os.getenv("TRADINGAGENTS_RESULTS_DIR", "./results")
    config["max_debate_rounds"] = 2  # Increase for more thorough analysis
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
        print("Running trading analysis...")
        state, decision = ta.propagate(symbol, date)
        
        # Save results
        results = {
            "symbol": symbol,
            "date": date,
            "decision": decision,
            "job_id": os.getenv("SLURM_JOB_ID"),
            "node": os.getenv("SLURM_NODELIST"),
            "completed_at": datetime.now().isoformat()
        }
        
        output_file = f"$RESULTS_DIR/analysis_results_{os.getenv('SLURM_JOB_ID')}.json"
        with open(output_file, 'w') as f:
            json.dump(results, f, indent=2)
        
        print(f"Analysis completed. Results saved to: {output_file}")
        print(f"Decision: {decision}")
        
    except Exception as e:
        print(f"Error during analysis: {str(e)}")
        # Save error information
        error_info = {
            "symbol": symbol,
            "date": date,
            "error": str(e),
            "job_id": os.getenv("SLURM_JOB_ID"),
            "failed_at": datetime.now().isoformat()
        }
        
        error_file = f"$RESULTS_DIR/error_{os.getenv('SLURM_JOB_ID')}.json"
        with open(error_file, 'w') as f:
            json.dump(error_info, f, indent=2)
        
        sys.exit(1)

if __name__ == "__main__":
    main()
EOF

# Run the analysis
echo "Running Python analysis script..."
if ! python "slurm_analysis_${SLURM_JOB_ID}.py"; then
    echo "ERROR: Python analysis script failed"
    rm -f "slurm_analysis_${SLURM_JOB_ID}.py"
    exit 1
fi

# Clean up temporary script
rm "slurm_analysis_${SLURM_JOB_ID}.py"

echo "Job completed successfully at: $(date)"
