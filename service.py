from tradingagents.external.redis.repo import redis_queue, redis_repo
from tradingagents.domain.model import AnalysisMeta,  AnalysisStatus
from tradingagents.domain.response import EnqueueAnalysisResponse
from rq import get_current_job
from tradingagents.graph.trading_graph import TradingAgentsGraph
from tradingagents.dataflows.config import get_config

DEFAULT_USER = "global_user"

trading_agent = None

def get_trading_agent():
    global trading_agent
    if trading_agent is None:
        print("INFO: Initializing TradingAgent (once per worker)")
        trading_agent = TradingAgentsGraph(
            debug=False,
            config=get_config()
        )
    return trading_agent

def process_job(user_id: str, symbol: str, date: str):
    print(f"INFO: Starting job for symbol {symbol} and date {date} by user {user_id}")
    try:
        job = get_current_job()
        attempt = job.meta.get("attempt", 1)
        job.meta["attempt"] = attempt
        job.save_meta()

        print(f"INFO: Processing job-id {job.id} for symbol {symbol} and date {date} by user {user_id}")

        # Update status to RUNNING
        redis_repo.update_status_analysis_meta(job_id=job.id, status=AnalysisStatus.RUNNING)

        final_state, decision = get_trading_agent().propagate(ticker=symbol, trade_date=date)

        print(f"INFO: Decision for job-id {job.id}: {decision}")

        # Save the final result
        redis_repo.save_result(job_id=job.id, final_trade=final_state["final_trade_decision"])
        # Update status to DONE
        redis_repo.update_status_analysis_meta(job_id=job.id, status=AnalysisStatus.DONE)
        
        print(f"INFO: Completed job-id {job.id} for symbol {symbol}")
    except Exception as e:
        job.meta["attempt"] = attempt + 1
        job.save_meta()
        print(f"ERROR: Failed to process job-id {job.id}: {e} (Attempt {attempt})")
        # Update status to FAILED
        redis_repo.update_status_analysis_meta(job_id=job.id, status=AnalysisStatus.FAILED)
        raise e


def enqueue_analysis(symbol: str, date: str) -> EnqueueAnalysisResponse:
    """
    Enqueue a background task to analyze trading data for a given symbol and date.

    Args:
        symbol (str): The trading symbol to analyze (e.g., "BTC/USDT").
        date (str): The date for which to perform the analysis in YYYY-MM-DD format.
    Returns:
        EnqueueAnalysisResponse: The response containing job_id, status, and message.
    """
    try:
        # Check if the analysis is on cooldown, if cooldown return the job-id
        job_id, ttl = redis_repo.get_cooldown(DEFAULT_USER, symbol) 
        if job_id:
            return EnqueueAnalysisResponse(
                job_id=job_id,
                status="on_cooldown",
                message=f"Analysis for {symbol} is on cooldown. Please try again later. TTL: {ttl} seconds remaining.",
            )
        
        # If not on cooldown, enqueue the task, insert cooldown key with TTL 6 hours, insert with status pending redis key for analysis analysis:job:{job_id}
        task = redis_queue.enqueue(process_job, DEFAULT_USER, symbol, date, job_timeout=7200)

        redis_repo.save_cooldown(DEFAULT_USER, symbol, task.id)
        redis_repo.create_analysis_meta(AnalysisMeta.new(job_id=task.id, user_id=DEFAULT_USER, symbol=symbol, trade_date=date))

        return EnqueueAnalysisResponse(
            job_id=task.id,
            status="enqueued",
            message=f"Analysis for {symbol} has been enqueued successfully."
        )
    except Exception as e:
        print(f"ERROR: Failed to enqueue analysis task: {e}")
        return EnqueueAnalysisResponse(
            job_id=None,
            status="error",
            message=f"Failed to enqueue analysis task: {str(e)}"
        )
