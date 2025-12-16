"""
Hybrid Task Manager - Redis + In-Memory

Uses Redis when available (production on Railway),
falls back to in-memory storage (local development).
"""
import uuid
import json
import threading
import logging
from typing import Dict, Any, Optional
from datetime import datetime, timedelta

from backend.app.services.redis_client import (
    save_task_to_redis,
    get_task_from_redis,
    delete_task_from_redis,
    is_redis_available,
)

logger = logging.getLogger(__name__)


class HybridTaskManager:
    """
    Manages async tasks using Redis when available,
    with in-memory fallback for local development.
    
    Features:
    - Thread-safe in-memory storage
    - Redis persistence when REDIS_URL is configured
    - Automatic cleanup of expired tasks
    - Seamless fallback between storage backends
    """
    
    def __init__(self):
        """Initialize hybrid task storage"""
        # In-memory storage (always available as fallback)
        self._tasks: Dict[str, Dict[str, Any]] = {}
        self._lock = threading.RLock()
        self._cleanup_interval = 3600  # 1 hour
        self._task_expiry = 86400  # 24 hours
        
        # Check Redis availability on startup
        if is_redis_available():
            logger.info("📦 Task Manager: Using Redis for task storage")
        else:
            logger.info("📦 Task Manager: Using in-memory storage (Redis not available)")
        
        # Start background cleanup thread
        self._start_cleanup_thread()
    
    def _start_cleanup_thread(self):
        """Start a background thread to clean up expired tasks"""
        def cleanup_worker():
            while True:
                threading.Event().wait(self._cleanup_interval)
                self._cleanup_expired_tasks()
        
        cleanup_thread = threading.Thread(target=cleanup_worker, daemon=True)
        cleanup_thread.start()
    
    def _cleanup_expired_tasks(self):
        """Remove tasks older than expiry time (in-memory only, Redis has TTL)"""
        with self._lock:
            current_time = datetime.now()
            expired_keys = []
            
            for task_id, task_data in self._tasks.items():
                created_at_str = task_data.get("created_at", "")
                if created_at_str:
                    try:
                        created_at = datetime.fromisoformat(created_at_str)
                        if current_time - created_at > timedelta(seconds=self._task_expiry):
                            expired_keys.append(task_id)
                    except:
                        pass
            
            for key in expired_keys:
                del self._tasks[key]
    
    def _save_to_storage(self, task_id: str, task_data: dict):
        """Save task to both Redis (if available) and in-memory"""
        # Always save to in-memory (fast access)
        with self._lock:
            self._tasks[task_id] = task_data
        
        # Also save to Redis if available (persistence)
        if is_redis_available():
            save_task_to_redis(task_id, task_data, self._task_expiry)
    
    def _get_from_storage(self, task_id: str) -> Optional[dict]:
        """Get task from in-memory first, then Redis"""
        # Check in-memory first (fastest)
        with self._lock:
            if task_id in self._tasks:
                return self._tasks[task_id]
        
        # Try Redis if not in memory (e.g., after server restart)
        if is_redis_available():
            redis_data = get_task_from_redis(task_id)
            if redis_data:
                # Cache in memory for future access
                with self._lock:
                    self._tasks[task_id] = redis_data
                return redis_data
        
        return None
    
    def create_task(self, initial_data: Dict[str, Any]) -> str:
        """
        Create a new task with initial data
        
        Args:
            initial_data: Initial task data
            
        Returns:
            Task ID
        """
        task_id = str(uuid.uuid4())
        
        task_data = {
            "task_id": task_id,
            "status": "pending",
            "progress": "Task created",
            "result": None,
            "error": None,
            "created_at": datetime.now().isoformat(),
            **initial_data
        }
        
        self._save_to_storage(task_id, task_data)
        return task_id
    
    def update_task_status(self, task_id: str, status: str, progress: Optional[str] = None):
        """
        Update task status and optional progress message
        
        Args:
            task_id: Task ID
            status: New status (pending, running, completed, failed)
            progress: Optional progress message
        """
        task_data = self._get_from_storage(task_id)
        if task_data:
            task_data["status"] = status
            if progress:
                task_data["progress"] = progress
            task_data["updated_at"] = datetime.now().isoformat()
            self._save_to_storage(task_id, task_data)
    
    def update_task_progress(self, task_id: str, progress: str):
        """
        Update task progress message
        
        Args:
            task_id: Task ID
            progress: Progress message
        """
        task_data = self._get_from_storage(task_id)
        if task_data:
            task_data["progress"] = progress
            task_data["updated_at"] = datetime.now().isoformat()
            self._save_to_storage(task_id, task_data)
    
    def set_task_result(self, task_id: str, result: Any):
        """
        Set task result and mark as completed
        
        Args:
            task_id: Task ID
            result: Task result
        """
        task_data = self._get_from_storage(task_id)
        if task_data:
            task_data["status"] = "completed"
            task_data["result"] = result
            task_data["progress"] = "Analysis completed"
            task_data["completed_at"] = datetime.now().isoformat()
            self._save_to_storage(task_id, task_data)
    
    def set_task_error(self, task_id: str, error: str):
        """
        Set task error and mark as failed
        
        Args:
            task_id: Task ID
            error: Error message
        """
        task_data = self._get_from_storage(task_id)
        if task_data:
            task_data["status"] = "failed"
            task_data["error"] = error
            task_data["progress"] = "Analysis failed"
            task_data["failed_at"] = datetime.now().isoformat()
            self._save_to_storage(task_id, task_data)
    
    def get_task(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task data by ID
        
        Args:
            task_id: Task ID
            
        Returns:
            Task data or None if not found
        """
        return self._get_from_storage(task_id)
    
    def get_task_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        Get task status information
        
        Args:
            task_id: Task ID
            
        Returns:
            Dictionary with task status information
        """
        task = self.get_task(task_id)
        if not task:
            return None
        
        return {
            "task_id": task["task_id"],
            "status": task["status"],
            "created_at": task.get("created_at"),
            "updated_at": task.get("updated_at", task.get("created_at")),
            "progress": task.get("progress"),
            "result": task.get("result"),
            "error": task.get("error"),
            "completed_at": task.get("completed_at"),
        }
    
    def delete_task(self, task_id: str):
        """
        Delete a task
        
        Args:
            task_id: Task ID
        """
        with self._lock:
            if task_id in self._tasks:
                del self._tasks[task_id]
        
        if is_redis_available():
            delete_task_from_redis(task_id)
    
    def get_all_tasks(self) -> Dict[str, Dict[str, Any]]:
        """
        Get all tasks (for debugging)
        
        Returns:
            Dictionary of all tasks (in-memory only)
        """
        with self._lock:
            return self._tasks.copy()


# Global task manager instance
task_manager = HybridTaskManager()
