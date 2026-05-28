"""Scheduler for daily trading execution."""

import logging
from typing import Dict, Optional, List, Callable
from datetime import datetime, time

logger = logging.getLogger(__name__)

try:
    from apscheduler.schedulers.background import BackgroundScheduler
    from apscheduler.triggers.cron import CronTrigger
    import pytz
    HAS_APSCHEDULER = True
except ImportError:
    HAS_APSCHEDULER = False
    logger.warning("APScheduler not installed. Install with: pip install apscheduler")


class TradingScheduler:
    """Schedule and manage daily trading sessions."""
    
    def __init__(self, timezone: str = "America/New_York"):
        """Initialize trading scheduler.
        
        Args:
            timezone: Timezone for scheduling (default: US Eastern)
        """
        if not HAS_APSCHEDULER:
            raise ImportError("APScheduler not installed. Install with: pip install apscheduler")
        
        self.scheduler = BackgroundScheduler(timezone=timezone)
        self.timezone = pytz.timezone(timezone)
        self.trading_sessions = {}  # job_id -> session info
        self.is_running = False
    
    def start(self):
        """Start the scheduler."""
        if not self.scheduler.running:
            self.scheduler.start()
            self.is_running = True
            logger.info("Trading scheduler started")
    
    def stop(self):
        """Stop the scheduler."""
        if self.scheduler.running:
            self.scheduler.shutdown()
            self.is_running = False
            logger.info("Trading scheduler stopped")
    
    def schedule_daily_execution(self, hour: int, minute: int, 
                                trading_func: Callable, job_id: str = None,
                                args: tuple = None, kwargs: dict = None) -> str:
        """Schedule a trading function to run daily at specific time.
        
        Args:
            hour: Hour (0-23)
            minute: Minute (0-59)
            trading_func: Function to execute
            job_id: Unique job identifier (auto-generated if None)
            args: Positional arguments for trading_func
            kwargs: Keyword arguments for trading_func
            
        Returns:
            Job ID
        """
        if job_id is None:
            job_id = f"trading_job_{len(self.trading_sessions)}"
        
        if args is None:
            args = ()
        if kwargs is None:
            kwargs = {}
        
        trigger = CronTrigger(hour=hour, minute=minute, timezone=self.timezone)
        
        job = self.scheduler.add_job(
            trading_func, trigger, id=job_id, args=args, kwargs=kwargs,
            replace_existing=True, misfire_grace_time=60
        )
        
        next_run = getattr(job, "next_run_time", None)
        if next_run is None:
            try:
                if hasattr(job, 'trigger') and hasattr(job.trigger, 'get_next_fire_time'):
                    next_run = job.trigger.get_next_fire_time(None, datetime.now(self.timezone))
            except Exception:
                pass

        self.trading_sessions[job_id] = {
            "function": trading_func.__name__,
            "schedule": f"{hour:02d}:{minute:02d}",
            "next_run": next_run,
            "job": job,
        }
        
        logger.info(f"Scheduled job {job_id}: {trading_func.__name__} at {hour:02d}:{minute:02d}")
        return job_id
    
    def schedule_analysis_execution(self, hour: int, minute: int,
                                   analysis_func: Callable, job_id: str = None) -> str:
        """Schedule AI analysis to run daily.
        
        Args:
            hour: Hour to run analysis
            minute: Minute to run analysis
            analysis_func: Analysis function (e.g., queue_all_analyses)
            job_id: Unique job identifier
            
        Returns:
            Job ID
        """
        return self.schedule_daily_execution(hour, minute, analysis_func, job_id)
    
    def schedule_execution_phase(self, hour: int, minute: int,
                                execute_func: Callable, job_id: str = None) -> str:
        """Schedule execution phase to run daily.
        
        Args:
            hour: Hour to execute trades
            minute: Minute to execute trades
            execute_func: Execution function
            job_id: Unique job identifier
            
        Returns:
            Job ID
        """
        return self.schedule_daily_execution(hour, minute, execute_func, job_id)
    
    def get_job(self, job_id: str) -> Optional[Dict]:
        """Get job information.
        
        Args:
            job_id: Job ID
            
        Returns:
            Job information dictionary or None
        """
        return self.trading_sessions.get(job_id)
    
    def get_next_run(self, job_id: str) -> Optional[datetime]:
        """Get next run time for a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            Next run time or None
        """
        session = self.trading_sessions.get(job_id)
        if session and session["job"]:
            job = session["job"]
            next_run = getattr(job, "next_run_time", None)
            if next_run is None:
                try:
                    if hasattr(job, 'trigger') and hasattr(job.trigger, 'get_next_fire_time'):
                        next_run = job.trigger.get_next_fire_time(None, datetime.now(self.timezone))
                except Exception:
                    pass
            return next_run
        return None
    
    def get_all_jobs(self) -> List[Dict]:
        """Get all scheduled jobs.
        
        Returns:
            List of job information dictionaries
        """
        return list(self.trading_sessions.values())
    
    def remove_job(self, job_id: str) -> bool:
        """Remove a scheduled job.
        
        Args:
            job_id: Job ID
            
        Returns:
            True if removed, False if not found
        """
        if job_id not in self.trading_sessions:
            return False
        
        job = self.trading_sessions[job_id]["job"]
        self.scheduler.remove_job(job.id)
        del self.trading_sessions[job_id]
        logger.info(f"Removed job {job_id}")
        return True
    
    def pause_job(self, job_id: str) -> bool:
        """Pause a job.
        
        Args:
            job_id: Job ID
            
        Returns:
            True if paused, False if not found
        """
        if job_id not in self.trading_sessions:
            return False
        
        job = self.trading_sessions[job_id]["job"]
        job.pause()
        logger.info(f"Paused job {job_id}")
        return True
    
    def resume_job(self, job_id: str) -> bool:
        """Resume a paused job.
        
        Args:
            job_id: Job ID
            
        Returns:
            True if resumed, False if not found
        """
        if job_id not in self.trading_sessions:
            return False
        
        job = self.trading_sessions[job_id]["job"]
        job.resume()
        logger.info(f"Resumed job {job_id}")
        return True
    
    def get_scheduler_status(self) -> Dict:
        """Get scheduler status.
        
        Returns:
            Scheduler status dictionary
        """
        jobs_info = []
        for job_id, info in self.trading_sessions.items():
            next_run = None
            try:
                job = info.get("job")
                next_run_val = None
                if job:
                    next_run_val = getattr(job, 'next_run_time', None)
                    if next_run_val is None:
                        if hasattr(job, 'trigger') and hasattr(job.trigger, 'get_next_fire_time'):
                            next_run_val = job.trigger.get_next_fire_time(None, datetime.now(self.timezone))
                
                if next_run_val:
                    next_run = next_run_val.isoformat()
                elif info.get("next_run"):
                    next_run = info["next_run"].isoformat()
            except Exception:
                pass
            
            jobs_info.append({
                "job_id": job_id,
                "function": info.get("function"),
                "schedule": info.get("schedule"),
                "next_run": next_run,
            })
        
        return {
            "running": self.is_running,
            "timezone": self.timezone.zone,
            "num_jobs": len(self.trading_sessions),
            "jobs": jobs_info
        }
    
    def __enter__(self):
        """Context manager entry."""
        self.start()
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        """Context manager exit."""
        self.stop()


class TradingSession:
    """Represents a single trading session (analysis + execution)."""
    
    def __init__(self, session_id: str, date: str):
        """Initialize trading session.
        
        Args:
            session_id: Unique session identifier
            date: Session date (YYYY-MM-DD)
        """
        self.session_id = session_id
        self.date = date
        self.started_at = None
        self.completed_at = None
        self.status = "PENDING"  # PENDING, ANALYSIS, EXECUTING, COMPLETED, FAILED
        
        self.analysis_tasks = {}  # ticker -> task_id
        self.trade_executions = {}  # ticker -> execution result
        self.errors = []
    
    def start_analysis_phase(self):
        """Mark analysis phase as started."""
        self.started_at = datetime.now()
        self.status = "ANALYSIS"
        logger.info(f"Session {self.session_id}: Analysis phase started")
    
    def mark_analysis_complete(self):
        """Mark analysis phase as complete."""
        self.status = "EXECUTING"
        logger.info(f"Session {self.session_id}: Analysis complete, starting execution")
    
    def complete_session(self):
        """Mark session as complete."""
        self.completed_at = datetime.now()
        self.status = "COMPLETED"
        duration = (self.completed_at - self.started_at).total_seconds()
        logger.info(f"Session {self.session_id}: Completed in {duration:.1f}s")
    
    def mark_failed(self, error: str):
        """Mark session as failed.
        
        Args:
            error: Error message
        """
        self.status = "FAILED"
        self.errors.append(error)
        logger.error(f"Session {self.session_id}: Failed - {error}")
    
    def add_analysis_task(self, ticker: str, task_id: str):
        """Record analysis task for ticker.
        
        Args:
            ticker: Stock ticker
            task_id: Analysis task ID
        """
        self.analysis_tasks[ticker] = task_id
    
    def add_trade_execution(self, ticker: str, execution_result: Dict):
        """Record trade execution.
        
        Args:
            ticker: Stock ticker
            execution_result: Execution result dictionary
        """
        self.trade_executions[ticker] = execution_result
    
    def get_summary(self) -> Dict:
        """Get session summary.
        
        Returns:
            Summary dictionary
        """
        return {
            "session_id": self.session_id,
            "date": self.date,
            "status": self.status,
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "duration_sec": (self.completed_at - self.started_at).total_seconds() 
                           if self.started_at and self.completed_at else None,
            "analysis_tasks": len(self.analysis_tasks),
            "trade_executions": len(self.trade_executions),
            "errors": self.errors,
        }
