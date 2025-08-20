# TradingAgents SLURM Cluster Guide

This guide explains how to run the TradingAgents framework on a SLURM cluster environment.

## Overview

The TradingAgents framework has been configured to run efficiently on SLURM clusters with the following features:

-   **Multi-job support**: Single analysis, batch processing, and GPU-accelerated runs
-   **Resource management**: Optimized CPU, memory, and GPU allocation
-   **Environment isolation**: Python virtual environments and dependency management
-   **Result collection**: Structured output and error handling
-   **LLM flexibility**: Support for various LLM providers (OpenAI, Anthropic, Ollama, etc.)

## Files Created

| File                       | Purpose                                       |
| -------------------------- | --------------------------------------------- |
| `slurm_setup.sh`           | Environment setup and dependency installation |
| `slurm_single_analysis.sh` | Single stock analysis job                     |
| `slurm_batch_analysis.sh`  | Batch analysis for multiple stocks            |
| `slurm_gpu_analysis.sh`    | GPU-accelerated analysis with local models    |
| `slurm_manager.sh`         | Job management and utility script             |
| `.env.slurm.template`      | Environment configuration template            |

## Quick Start

### 1. Initial Setup

```bash
# Make the manager script executable
chmod +x slurm_manager.sh

# Setup environment and create directories
./slurm_manager.sh setup

# Submit setup job to install dependencies
./slurm_manager.sh submit-setup
```

### 2. Configure Environment

Edit the `.env` file (created from template) to configure your LLM provider:

```bash
# For Ollama (local models)
LLM_PROVIDER=ollama
LLM_BACKEND_URL=http://localhost:11434/v1
DEEP_THINK_LLM=llama3.2
QUICK_THINK_LLM=llama3.2

# For OpenAI
LLM_PROVIDER=openai
OPENAI_API_KEY=your_api_key_here
DEEP_THINK_LLM=gpt-4
QUICK_THINK_LLM=gpt-3.5-turbo

# For Anthropic
LLM_PROVIDER=anthropic
ANTHROPIC_API_KEY=your_api_key_here
DEEP_THINK_LLM=claude-3-sonnet-20240229
QUICK_THINK_LLM=claude-3-haiku-20240307
```

### 3. Submit Jobs

```bash
# Single stock analysis
./slurm_manager.sh submit-single AAPL

# Batch analysis (multiple stocks)
./slurm_manager.sh submit-batch

# GPU-accelerated analysis
./slurm_manager.sh submit-gpu TSLA
```

### 4. Monitor Jobs

```bash
# Check all recent jobs
./slurm_manager.sh status

# Check specific job
./slurm_manager.sh status 12345

# View job output
./slurm_manager.sh output 12345

# View job errors
./slurm_manager.sh output 12345 err
```

### 5. Collect Results

```bash
# View results for all symbols
./slurm_manager.sh results

# View results for specific symbol
./slurm_manager.sh results AAPL

# View results for specific date
./slurm_manager.sh results AAPL 2024-01-15
```

## Job Types

### 1. Single Analysis (`slurm_single_analysis.sh`)

-   **Purpose**: Analyze a single stock symbol
-   **Resources**: 8 CPUs, 16GB RAM, 4 hours
-   **Usage**: Best for focused analysis or testing

```bash
sbatch slurm_single_analysis.sh SYMBOL DATE
# or
./slurm_manager.sh submit-single SYMBOL DATE
```

### 2. Batch Analysis (`slurm_batch_analysis.sh`)

-   **Purpose**: Analyze multiple stocks in parallel
-   **Resources**: Array job with up to 5 concurrent tasks
-   **Default symbols**: SPY, QQQ, AAPL, MSFT, GOOGL, AMZN, TSLA, NVDA, META, NFLX
-   **Usage**: Efficient for portfolio-wide analysis

```bash
sbatch slurm_batch_analysis.sh
# or
./slurm_manager.sh submit-batch
```

### 3. GPU Analysis (`slurm_gpu_analysis.sh`)

-   **Purpose**: GPU-accelerated analysis with local models
-   **Resources**: 1 GPU, 8 CPUs, 32GB RAM, 8 hours
-   **Usage**: Best for Ollama or other local LLM providers

```bash
sbatch slurm_gpu_analysis.sh SYMBOL DATE
# or
./slurm_manager.sh submit-gpu SYMBOL DATE
```

## Resource Requirements

### Minimum Requirements

-   **CPU Jobs**: 4-8 cores, 8-16GB RAM
-   **GPU Jobs**: 1 GPU, 8 cores, 32GB RAM
-   **Storage**: ~1GB for dependencies, variable for results/cache

### Recommended Partitions

-   **CPU Partition**: For most analysis jobs
-   **GPU Partition**: For local LLM acceleration
-   **High-Memory Partition**: For large-scale batch processing

## LLM Provider Configuration

### Ollama (Recommended for Clusters)

-   Runs locally on compute nodes
-   No external API dependencies
-   GPU acceleration support
-   Models: llama3.2, mistral, etc.

### OpenAI/OpenRouter

-   Requires API key and internet access
-   Fast inference
-   Usage costs apply
-   Models: gpt-4, gpt-3.5-turbo, etc.

### Anthropic

-   Requires API key and internet access
-   High-quality reasoning
-   Usage costs apply
-   Models: claude-3-sonnet, claude-3-haiku

## File Structure

```
TradingAgents/
├── slurm_*.sh           # SLURM job scripts
├── slurm_manager.sh     # Job management utility
├── .env                 # Environment configuration
├── logs/                # Job output and error logs
├── results/             # Analysis results by symbol/date
├── venv/                # Python virtual environment
└── data_cache/          # Cached market data
```

## Error Handling and Exit Behavior

### **Automatic Script Exit**

✅ **Yes, scripts will exit automatically on failures** with the following behavior:

#### **1. Bash Script Level**

-   **`set -euo pipefail`**: Scripts exit immediately on any command failure
-   **`-e`**: Exit on any non-zero exit status
-   **`-u`**: Exit on undefined variables
-   **`-o pipefail`**: Exit if any command in a pipeline fails

#### **2. Python Script Level**

-   **Exception handling**: All Python errors are caught and logged
-   **Explicit exit**: `sys.exit(1)` on any analysis failure
-   **Error logging**: Failures are saved to JSON files for debugging

#### **3. SLURM Level**

-   **Job cancellation**: Failed jobs are marked as FAILED in SLURM
-   **Resource cleanup**: Allocated resources are automatically released
-   **Log preservation**: Output and error logs are saved for investigation

### **What Happens on Failure**

1. **Immediate termination** of the failing script
2. **Error information saved** to `results/[SYMBOL]/[DATE]/error_[JOB_ID].json`
3. **SLURM job status** set to FAILED
4. **Exit code 1** returned to SLURM scheduler
5. **Resources released** back to the cluster

## Troubleshooting

### Common Issues

1. **Job Fails to Start**

    - Check SLURM partition availability: `sinfo`
    - Verify resource requirements match cluster limits
    - Ensure environment setup job completed successfully

2. **Python Dependencies Missing**

    - Run setup job: `./slurm_manager.sh submit-setup`
    - Check setup job output: `./slurm_manager.sh output SETUP_JOB_ID`

3. **LLM Connection Issues**

    - Verify API keys in `.env` file
    - Check network connectivity for external providers
    - For Ollama, ensure GPU resources are available

4. **Out of Memory Errors**

    - Increase memory allocation in job scripts
    - Reduce `max_debate_rounds` in configuration
    - Use GPU partition for memory-intensive models

5. **Script Exit Issues**
    - Check exit codes: `sacct -j JOB_ID --format=JobID,State,ExitCode`
    - Review error logs: `./slurm_manager.sh output JOB_ID err`
    - Verify all prerequisites are met before job submission

### Debugging

```bash
# Check job status and exit codes
squeue -u $USER
sacct -j JOB_ID --format=JobID,State,ExitCode,Reason

# View detailed job information
scontrol show job JOB_ID

# Check node resources
sinfo -N -l

# View job output in real-time
tail -f logs/trading_JOB_ID.out

# Check for error files
find results -name "error_*.json" -exec echo "Found error in: {}" \; -exec cat {} \;
```

## Customization

### Modify Stock Lists

Edit the `SYMBOLS` array in `slurm_batch_analysis.sh`:

```bash
SYMBOLS=("AAPL" "MSFT" "GOOGL" "AMZN" "TSLA")
```

### Adjust Resources

Modify SLURM directives in job scripts:

```bash
#SBATCH --cpus-per-task=16    # More CPUs
#SBATCH --mem=64G             # More memory
#SBATCH --time=12:00:00       # Longer runtime
```

### Configure Analysis Parameters

Edit the config in Python scripts:

```python
config["max_debate_rounds"] = 3        # More thorough analysis
config["max_risk_discuss_rounds"] = 3  # More risk assessment
config["online_tools"] = True          # Enable web scraping
```

## Best Practices

1. **Start Small**: Test with single analysis before batch jobs
2. **Monitor Resources**: Check CPU/memory usage during jobs
3. **Batch Wisely**: Use array jobs for multiple symbols
4. **Cache Data**: Leverage data caching to reduce API calls
5. **Log Everything**: Review job logs for optimization opportunities
6. **Backup Results**: Copy important results to permanent storage

## Performance Tips

1. **Use Local Models**: Ollama reduces API latency and costs
2. **Parallel Processing**: Leverage array jobs for batch analysis
3. **Resource Matching**: Match job resources to actual needs
4. **Data Locality**: Store frequently accessed data on fast storage
5. **Network Optimization**: Use cluster-internal services when possible

## Security Considerations

1. **API Keys**: Store sensitive keys in `.env` file, not in scripts
2. **File Permissions**: Ensure job scripts and data have appropriate permissions
3. **Network Access**: Some clusters restrict external API access
4. **Data Privacy**: Be aware of data residency requirements for financial data

## Support

For issues specific to:

-   **SLURM**: Consult your cluster documentation or administrator
-   **TradingAgents**: Check the main repository issues and documentation
-   **LLM Providers**: Refer to respective provider documentation
