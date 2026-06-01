"""Asynchronous AI analysis execution for trading decisions."""

import logging
from datetime import datetime
from typing import Dict, Optional, Callable
from threading import Thread
import queue
from enum import Enum

logger = logging.getLogger(__name__)


class AnalysisStatus(Enum):
    """Status of analysis execution."""
    QUEUED = "QUEUED"
    RUNNING = "RUNNING"
    COMPLETED = "COMPLETED"
    FAILED = "FAILED"
    TIMEOUT = "TIMEOUT"


class AnalysisTask:
    """Represents an asynchronous analysis task."""
    
    def __init__(self, task_id: str, ticker: str, analysis_date: str,
                 analysis_func: Callable):
        """Initialize analysis task.
        
        Args:
            task_id: Unique task identifier
            ticker: Stock ticker to analyze
            analysis_date: Date to analyze (YYYY-MM-DD)
            analysis_func: Callable that performs the analysis
        """
        self.task_id = task_id
        self.ticker = ticker
        self.analysis_date = analysis_date
        self.analysis_func = analysis_func
        
        self.status = AnalysisStatus.QUEUED
        self.queued_at = datetime.now()
        self.started_at = None
        self.completed_at = None
        self.result = None
        self.error = None
    
    def execute(self):
        """Execute the analysis task."""
        try:
            self.status = AnalysisStatus.RUNNING
            self.started_at = datetime.now()
            
            logger.info(f"Starting analysis {self.task_id} for {self.ticker} on {self.analysis_date}")
            
            # Call analysis function (e.g., TradingAgentsGraph.propagate)
            self.result = self.analysis_func(self.ticker, self.analysis_date)
            
            self.status = AnalysisStatus.COMPLETED
            self.completed_at = datetime.now()
            
            elapsed = (self.completed_at - self.started_at).total_seconds()
            logger.info(f"Analysis {self.task_id} completed in {elapsed:.1f}s")
            
        except Exception as e:
            self.status = AnalysisStatus.FAILED
            self.error = str(e)
            self.completed_at = datetime.now()
            logger.error(f"Analysis {self.task_id} failed: {e}")
    
    def get_analysis_time(self) -> Optional[float]:
        """Get analysis execution time in seconds.
        
        Returns:
            Time in seconds or None if not completed
        """
        if self.started_at and self.completed_at:
            return (self.completed_at - self.started_at).total_seconds()
        return None
    
    def to_dict(self) -> Dict:
        """Convert to dictionary."""
        return {
            "task_id": self.task_id,
            "ticker": self.ticker,
            "analysis_date": self.analysis_date,
            "status": self.status.value,
            "queued_at": self.queued_at.isoformat(),
            "started_at": self.started_at.isoformat() if self.started_at else None,
            "completed_at": self.completed_at.isoformat() if self.completed_at else None,
            "analysis_time_sec": self.get_analysis_time(),
            "error": self.error,
        }


class AsyncAnalyzer:
    """Manage asynchronous AI analysis execution."""
    
    def __init__(self, max_workers: int = 3):
        """Initialize async analyzer.
        
        Args:
            max_workers: Maximum parallel analysis threads
        """
        self.max_workers = max_workers
        self.tasks = {}  # task_id -> AnalysisTask
        self.task_counter = 0
        self.result_queue = queue.Queue()
        self.worker_threads = []
    
    def queue_analysis(self, ticker: str, analysis_date: str,
                      analysis_func: Callable) -> str:
        """Queue an analysis task.
        
        Args:
            ticker: Stock ticker
            analysis_date: Date to analyze (YYYY-MM-DD)
            analysis_func: Function that performs analysis (e.g., TradingAgentsGraph.propagate)
            
        Returns:
            Task ID
        """
        self.task_counter += 1
        task_id = f"ANALYSIS_{self.task_counter:06d}"
        
        task = AnalysisTask(task_id, ticker, analysis_date, analysis_func)
        self.tasks[task_id] = task
        
        # Execute in background thread
        thread = Thread(target=self._run_task, args=(task_id,), daemon=False)
        thread.start()
        self.worker_threads.append(thread)
        
        logger.info(f"Queued analysis {task_id} for {ticker} on {analysis_date}")
        return task_id
    
    def _run_task(self, task_id: str):
        """Execute task in background thread.
        
        Args:
            task_id: Task ID to execute
        """
        if task_id in self.tasks:
            task = self.tasks[task_id]
            task.execute()
            self.result_queue.put(task_id)
    
    def get_task_status(self, task_id: str) -> Optional[str]:
        """Get task status.
        
        Args:
            task_id: Task ID
            
        Returns:
            Status string or None
        """
        task = self.tasks.get(task_id)
        return task.status.value if task else None
    
    def is_completed(self, task_id: str) -> bool:
        """Check if task is completed.
        
        Args:
            task_id: Task ID
            
        Returns:
            True if completed or failed
        """
        task = self.tasks.get(task_id)
        if not task:
            return False
        return task.status in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED)
    
    def wait_for_result(self, task_id: str, timeout_sec: float = 600.0) -> Optional[Dict]:
        """Wait for analysis to complete.
        
        Args:
            task_id: Task ID
            timeout_sec: Maximum wait time in seconds (default 10 minutes)
            
        Returns:
            Analysis result or None if timeout/failed
        """
        task = self.tasks.get(task_id)
        if not task:
            logger.error(f"Task {task_id} not found")
            return None
        
        try:
            # Wait for task to complete (via queue)
            completed_id = self.result_queue.get(timeout=timeout_sec)
            if completed_id == task_id:
                if task.status == AnalysisStatus.COMPLETED:
                    return task.result
                else:
                    logger.error(f"Task {task_id} failed: {task.error}")
                    return None
        except queue.Empty:
            task.status = AnalysisStatus.TIMEOUT
            logger.error(f"Task {task_id} timed out after {timeout_sec}s")
            return None
        
        return None
    
    def get_cached_decision(self, task_id: str) -> Optional[Dict]:
        """Get cached decision from completed task.
        
        Args:
            task_id: Task ID
            
        Returns:
            Decision result or None
        """
        task = self.tasks.get(task_id)
        if task and task.status == AnalysisStatus.COMPLETED:
            return task.result
        return None
    
    def get_pending_tasks(self) -> list:
        """Get all pending/running tasks.
        
        Returns:
            List of tasks not yet completed
        """
        return [task for task in self.tasks.values() 
                if task.status not in (AnalysisStatus.COMPLETED, AnalysisStatus.FAILED)]
    
    def get_completed_tasks(self) -> list:
        """Get all completed tasks.
        
        Returns:
            List of completed tasks
        """
        return [task for task in self.tasks.values() 
                if task.status == AnalysisStatus.COMPLETED]
    
    def get_analysis_latency_stats(self) -> Dict:
        """Get statistics on analysis latencies.
        
        Returns:
            Dictionary of latency stats
        """
        completed = self.get_completed_tasks()
        if not completed:
            return {"count": 0, "avg_sec": 0, "min_sec": 0, "max_sec": 0}
        
        times = [task.get_analysis_time() for task in completed if task.get_analysis_time()]
        
        if not times:
            return {"count": 0, "avg_sec": 0, "min_sec": 0, "max_sec": 0}
        
        return {
            "count": len(times),
            "avg_sec": sum(times) / len(times),
            "min_sec": min(times),
            "max_sec": max(times),
        }
    
    def get_summary(self) -> Dict:
        """Get summary of all tasks.
        
        Returns:
            Summary dictionary
        """
        completed = sum(1 for t in self.tasks.values() if t.status == AnalysisStatus.COMPLETED)
        failed = sum(1 for t in self.tasks.values() if t.status == AnalysisStatus.FAILED)
        pending = sum(1 for t in self.tasks.values() if t.status in (AnalysisStatus.QUEUED, AnalysisStatus.RUNNING))
        
        return {
            "total_tasks": len(self.tasks),
            "completed": completed,
            "failed": failed,
            "pending": pending,
            "latency_stats": self.get_analysis_latency_stats(),
        }
    
    def wait_all(self, timeout_sec: float = 600.0) -> bool:
        """Wait for all pending tasks to complete.
        
        Args:
            timeout_sec: Maximum wait time
            
        Returns:
            True if all completed, False if timeout
        """
        import time
        start = time.time()
        
        while time.time() - start < timeout_sec:
            pending = self.get_pending_tasks()
            if not pending:
                return True
            time.sleep(1)
        
        return False
    
    def cleanup(self):
        """Clean up threads."""
        for thread in self.worker_threads:
            if thread.is_alive():
                thread.join(timeout=1)
        logger.info("Async analyzer cleanup completed")
