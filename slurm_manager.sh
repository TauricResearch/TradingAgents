#!/bin/bash

# TradingAgents SLURM Job Management Script
# This script provides convenience functions for managing TradingAgents jobs on SLURM

# Colors for output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# Print colored output
print_status() {
    echo -e "${GREEN}[INFO]${NC} $1"
}

print_warning() {
    echo -e "${YELLOW}[WARNING]${NC} $1"
}

print_error() {
    echo -e "${RED}[ERROR]${NC} $1"
}

print_header() {
    echo -e "${BLUE}=== $1 ===${NC}"
}

# Check if required files exist
check_prerequisites() {
    print_header "Checking Prerequisites"
    
    local missing_files=()
    
    if [ ! -f "requirements.txt" ]; then
        missing_files+=("requirements.txt")
    fi
    
    if [ ! -f "slurm_setup.sh" ]; then
        missing_files+=("slurm_setup.sh")
    fi
    
    if [ ! -f ".env.slurm.template" ]; then
        missing_files+=(".env.slurm.template")
    fi
    
    if [ ${#missing_files[@]} -ne 0 ]; then
        print_error "Missing required files: ${missing_files[*]}"
        return 1
    fi
    
    print_status "All required files found"
    return 0
}

# Setup environment
setup_environment() {
    print_header "Setting Up Environment"
    
    # Create necessary directories
    mkdir -p logs results data_cache
    
    # Copy environment template if .env doesn't exist
    if [ ! -f ".env" ]; then
        cp .env.slurm.template .env
        print_status "Created .env file from template. Please customize it for your environment."
    fi
    
    # Make scripts executable
    chmod +x slurm_*.sh
    
    print_status "Environment setup completed"
}

# Submit setup job
submit_setup() {
    print_header "Submitting Setup Job"
    
    if [ ! -f "slurm_setup.sh" ]; then
        print_error "slurm_setup.sh not found"
        return 1
    fi
    
    local job_id=$(sbatch slurm_setup.sh | grep -o '[0-9]*')
    print_status "Setup job submitted with ID: $job_id"
    echo "$job_id"
}

# Submit single analysis job
submit_single_analysis() {
    local symbol=${1:-"SPY"}
    local date=${2:-$(date +%Y-%m-%d)}
    
    print_header "Submitting Single Analysis Job"
    print_status "Symbol: $symbol, Date: $date"
    
    if [ ! -f "slurm_single_analysis.sh" ]; then
        print_error "slurm_single_analysis.sh not found"
        return 1
    fi
    
    local job_id=$(sbatch slurm_single_analysis.sh "$symbol" "$date" | grep -o '[0-9]*')
    print_status "Single analysis job submitted with ID: $job_id"
    echo "$job_id"
}

# Submit batch analysis job
submit_batch_analysis() {
    print_header "Submitting Batch Analysis Job"
    
    if [ ! -f "slurm_batch_analysis.sh" ]; then
        print_error "slurm_batch_analysis.sh not found"
        return 1
    fi
    
    local job_id=$(sbatch slurm_batch_analysis.sh | grep -o '[0-9]*')
    print_status "Batch analysis job submitted with ID: $job_id"
    echo "$job_id"
}

# Submit GPU analysis job
submit_gpu_analysis() {
    local symbol=${1:-"SPY"}
    local date=${2:-$(date +%Y-%m-%d)}
    
    print_header "Submitting GPU Analysis Job"
    print_status "Symbol: $symbol, Date: $date"
    
    if [ ! -f "slurm_gpu_analysis.sh" ]; then
        print_error "slurm_gpu_analysis.sh not found"
        return 1
    fi
    
    local job_id=$(sbatch slurm_gpu_analysis.sh "$symbol" "$date" | grep -o '[0-9]*')
    print_status "GPU analysis job submitted with ID: $job_id"
    echo "$job_id"
}

# Check job status
check_job_status() {
    local job_id=$1
    
    if [ -z "$job_id" ]; then
        print_error "Job ID required"
        return 1
    fi
    
    print_header "Job Status for ID: $job_id"
    squeue -j "$job_id" --format="%.18i %.9P %.20j %.8u %.8T %.10M %.6D %R"
}

# Show recent jobs
show_recent_jobs() {
    print_header "Recent TradingAgents Jobs"
    squeue -u $USER --name=trading-agents* --format="%.18i %.9P %.20j %.8u %.8T %.10M %.6D %R"
}

# Cancel job
cancel_job() {
    local job_id=$1
    
    if [ -z "$job_id" ]; then
        print_error "Job ID required"
        return 1
    fi
    
    print_header "Cancelling Job: $job_id"
    scancel "$job_id"
    print_status "Job $job_id cancelled"
}

# View job output
view_job_output() {
    local job_id=$1
    local output_type=${2:-"out"}  # "out" or "err"
    
    if [ -z "$job_id" ]; then
        print_error "Job ID required"
        return 1
    fi
    
    local output_file
    if [ "$output_type" == "err" ]; then
        output_file="logs/trading_${job_id}.err"
    else
        output_file="logs/trading_${job_id}.out"
    fi
    
    if [ -f "$output_file" ]; then
        print_header "Job $job_id Output ($output_type)"
        tail -f "$output_file"
    else
        print_error "Output file not found: $output_file"
    fi
}

# Check for failed jobs and show errors
check_failed_jobs() {
    print_header "Checking for Failed Jobs"
    
    # Get failed jobs from sacct
    local failed_jobs=$(sacct -u $USER --name=trading-agents* --state=FAILED --format=JobID,State,ExitCode --noheader --parsable2 | cut -d'|' -f1)
    
    if [ -z "$failed_jobs" ]; then
        print_status "No failed jobs found"
        return 0
    fi
    
    echo "$failed_jobs" | while read -r job_id; do
        if [ -n "$job_id" ]; then
            print_warning "Failed job: $job_id"
            
            # Look for error files
            local error_files=$(find results -name "error_${job_id}.json" 2>/dev/null)
            if [ -n "$error_files" ]; then
                echo "$error_files" | while read -r error_file; do
                    echo "Error details from: $error_file"
                    if command -v jq >/dev/null 2>&1; then
                        jq '.' "$error_file" 2>/dev/null || cat "$error_file"
                    else
                        cat "$error_file"
                    fi
                done
            else
                echo "No error details found for job $job_id"
            fi
            echo ""
        fi
    done
}

# Collect results
collect_results() {
    local symbol=${1:-"*"}
    local date=${2:-$(date +%Y-%m-%d)}
    
    print_header "Collecting Results"
    print_status "Symbol: $symbol, Date: $date"
    
    find results -name "*.json" -path "*/$symbol/$date/*" | while read -r file; do
        echo "Found result: $file"
        if command -v jq >/dev/null 2>&1; then
            jq '.decision' "$file" 2>/dev/null || echo "  (Could not parse decision)"
        fi
    done
}

# Main function
main() {
    case "$1" in
        "setup")
            check_prerequisites && setup_environment
            ;;
        "submit-setup")
            submit_setup
            ;;
        "submit-single")
            submit_single_analysis "$2" "$3"
            ;;
        "submit-batch")
            submit_batch_analysis
            ;;
        "submit-gpu")
            submit_gpu_analysis "$2" "$3"
            ;;
        "status")
            if [ -n "$2" ]; then
                check_job_status "$2"
            else
                show_recent_jobs
            fi
            ;;
        "cancel")
            cancel_job "$2"
            ;;
        "output")
            view_job_output "$2" "$3"
            ;;
        "results")
            collect_results "$2" "$3"
            ;;
        "check-failed")
            check_failed_jobs
            ;;
        "help"|"--help"|"-h"|"")
            cat << EOF
TradingAgents SLURM Job Manager

Usage: $0 <command> [arguments]

Commands:
  setup                     - Setup environment and create necessary directories
  submit-setup             - Submit environment setup job
  submit-single [SYM] [DATE] - Submit single analysis job (default: SPY, today)
  submit-batch             - Submit batch analysis job for multiple symbols
  submit-gpu [SYM] [DATE]  - Submit GPU-accelerated analysis job
  status [JOB_ID]          - Show job status (specific job or all recent jobs)
  cancel <JOB_ID>          - Cancel a specific job
  output <JOB_ID> [err]    - View job output (stdout or stderr)
  results [SYM] [DATE]     - Collect and display results
  check-failed             - Check for failed jobs and show error details
  help                     - Show this help message

Examples:
  $0 setup                 # Initial setup
  $0 submit-single AAPL    # Analyze AAPL for today
  $0 submit-batch          # Analyze multiple stocks
  $0 status 12345          # Check status of job 12345
  $0 output 12345          # View output of job 12345
  $0 results AAPL          # Show results for AAPL

EOF
            ;;
        *)
            print_error "Unknown command: $1"
            print_status "Use '$0 help' for usage information"
            exit 1
            ;;
    esac
}

# Run main function with all arguments
main "$@"
