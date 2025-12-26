"""
Logging Infrastructure for autonomous-dev v2.0
Provides multi-level logging, structured logging, and workflow tracking.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
"""

import json
import logging
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Literal
from enum import Enum


class LogLevel(str, Enum):
    """Log levels for autonomous-dev"""
    DEBUG = "DEBUG"
    INFO = "INFO"
    WARNING = "WARNING"
    ERROR = "ERROR"
    CRITICAL = "CRITICAL"


class WorkflowLogger:
    """
    Structured logger for agent workflows
    Logs to both files and stdout with proper formatting
    """

    def __init__(self, workflow_id: str, agent_name: str, log_dir: Optional[Path] = None):
        """
        Initialize workflow logger

        Args:
            workflow_id: Unique workflow identifier
            agent_name: Name of the agent (orchestrator, researcher, planner, etc.)
            log_dir: Base directory for logs (default: .claude/logs/workflows)
        """
        self.workflow_id = workflow_id
        self.agent_name = agent_name

        # Set up log directory
        if log_dir is None:
            log_dir = Path(".claude/logs/workflows")
        self.log_dir = log_dir / workflow_id
        self.log_dir.mkdir(parents=True, exist_ok=True)

        # Create log file for this agent
        self.log_file = self.log_dir / f"{agent_name}.log"

        # Set up Python logger
        self.logger = logging.getLogger(f"autonomous-dev.{workflow_id}.{agent_name}")
        self.logger.setLevel(logging.DEBUG)

        # File handler (detailed logs)
        file_handler = logging.FileHandler(self.log_file)
        file_handler.setLevel(logging.DEBUG)
        file_format = logging.Formatter(
            '%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
        file_handler.setFormatter(file_format)
        self.logger.addHandler(file_handler)

        # Console handler (important logs only)
        console_handler = logging.StreamHandler()
        console_handler.setLevel(logging.INFO)
        console_format = logging.Formatter('%(levelname)s: %(message)s')
        console_handler.setFormatter(console_format)
        self.logger.addHandler(console_handler)

    def log_event(
        self,
        event_type: str,
        message: str,
        level: LogLevel = LogLevel.INFO,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log a structured event

        Args:
            event_type: Type of event (e.g., 'agent_start', 'decision', 'artifact_created')
            message: Human-readable message
            level: Log level
            metadata: Additional structured data
        """
        event = {
            'timestamp': datetime.utcnow().isoformat(),
            'workflow_id': self.workflow_id,
            'agent': self.agent_name,
            'event_type': event_type,
            'message': message,
            'metadata': metadata or {}
        }

        # Log as JSON for structured parsing
        event_json = json.dumps(event)

        # Log at appropriate level
        if level == LogLevel.DEBUG:
            self.logger.debug(f"EVENT: {event_json}")
        elif level == LogLevel.INFO:
            self.logger.info(f"EVENT: {event_json}")
        elif level == LogLevel.WARNING:
            self.logger.warning(f"EVENT: {event_json}")
        elif level == LogLevel.ERROR:
            self.logger.error(f"EVENT: {event_json}")
        elif level == LogLevel.CRITICAL:
            self.logger.critical(f"EVENT: {event_json}")

    def log_decision(
        self,
        decision: str,
        rationale: str,
        alternatives_considered: Optional[list] = None,
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log a decision made by the agent with rationale

        Args:
            decision: The decision made
            rationale: Why this decision was made
            alternatives_considered: Other options that were considered
            metadata: Additional context
        """
        decision_metadata = {
            'decision': decision,
            'rationale': rationale,
            'alternatives_considered': alternatives_considered or [],
            **(metadata or {})
        }

        self.log_event(
            'decision',
            f"Decision: {decision}",
            level=LogLevel.INFO,
            metadata=decision_metadata
        )

    def log_artifact_created(
        self,
        artifact_path: Path,
        artifact_type: str,
        summary: Optional[str] = None
    ):
        """
        Log artifact creation

        Args:
            artifact_path: Path to created artifact
            artifact_type: Type of artifact (manifest, research, architecture, etc.)
            summary: Brief summary of artifact contents
        """
        self.log_event(
            'artifact_created',
            f"Created {artifact_type} artifact",
            level=LogLevel.INFO,
            metadata={
                'artifact_path': str(artifact_path),
                'artifact_type': artifact_type,
                'summary': summary,
                'size_bytes': artifact_path.stat().st_size if artifact_path.exists() else 0
            }
        )

    def log_alignment_check(
        self,
        is_aligned: bool,
        reason: str,
        project_md_sections: Optional[Dict[str, Any]] = None
    ):
        """
        Log PROJECT.md alignment validation

        Args:
            is_aligned: Whether request aligns with PROJECT.md
            reason: Explanation of alignment decision
            project_md_sections: Relevant sections from PROJECT.md
        """
        self.log_event(
            'alignment_check',
            f"Alignment: {'✓ ALIGNED' if is_aligned else '✗ NOT ALIGNED'}",
            level=LogLevel.INFO if is_aligned else LogLevel.WARNING,
            metadata={
                'is_aligned': is_aligned,
                'reason': reason,
                'project_md_sections': project_md_sections or {}
            }
        )

    def log_performance_metric(
        self,
        metric_name: str,
        value: float,
        unit: str = "",
        metadata: Optional[Dict[str, Any]] = None
    ):
        """
        Log performance metrics (duration, token usage, cost, etc.)

        Args:
            metric_name: Name of metric (e.g., 'duration', 'tokens_used', 'cost')
            value: Numeric value
            unit: Unit of measurement (e.g., 'seconds', 'tokens', 'USD')
            metadata: Additional context
        """
        self.log_event(
            'performance_metric',
            f"{metric_name}: {value} {unit}",
            level=LogLevel.DEBUG,
            metadata={
                'metric_name': metric_name,
                'value': value,
                'unit': unit,
                **(metadata or {})
            }
        )

    def log_error(
        self,
        error_message: str,
        exception: Optional[Exception] = None,
        context: Optional[Dict[str, Any]] = None
    ):
        """
        Log an error with context

        Args:
            error_message: Description of the error
            exception: Python exception object (if available)
            context: Additional context about what was happening
        """
        error_metadata = {
            'error_message': error_message,
            'exception_type': type(exception).__name__ if exception else None,
            'exception_details': str(exception) if exception else None,
            'context': context or {}
        }

        self.log_event(
            'error',
            error_message,
            level=LogLevel.ERROR,
            metadata=error_metadata
        )

    def get_log_summary(self) -> Dict[str, Any]:
        """
        Get summary of logs for this agent

        Returns:
            Dictionary with log statistics and key events
        """
        if not self.log_file.exists():
            return {'error': 'Log file does not exist'}

        log_lines = self.log_file.read_text().splitlines()

        # Count events by type
        event_counts = {}
        errors = []
        decisions = []

        for line in log_lines:
            if 'EVENT:' in line:
                try:
                    event_start = line.index('EVENT:') + 7
                    event_json = line[event_start:]
                    event = json.loads(event_json)

                    event_type = event.get('event_type', 'unknown')
                    event_counts[event_type] = event_counts.get(event_type, 0) + 1

                    if event_type == 'error':
                        errors.append(event)
                    elif event_type == 'decision':
                        decisions.append(event)
                except (json.JSONDecodeError, ValueError):
                    continue

        return {
            'workflow_id': self.workflow_id,
            'agent': self.agent_name,
            'total_events': len(log_lines),
            'event_counts': event_counts,
            'errors': errors,
            'decisions': decisions,
            'log_file': str(self.log_file)
        }


class WorkflowProgressTracker:
    """Track overall workflow progress across all agents"""

    def __init__(self, workflow_id: str, log_dir: Optional[Path] = None):
        """
        Initialize progress tracker

        Args:
            workflow_id: Unique workflow identifier
            log_dir: Base directory for logs
        """
        self.workflow_id = workflow_id

        if log_dir is None:
            log_dir = Path(".claude/logs/workflows")

        self.progress_file = log_dir / workflow_id / "progress.json"
        self.progress_file.parent.mkdir(parents=True, exist_ok=True)

        # Initialize progress
        if not self.progress_file.exists():
            self.update_progress(
                current_agent="orchestrator",
                status="started",
                progress_percentage=0
            )

    def update_progress(
        self,
        current_agent: str,
        status: Literal["started", "in_progress", "completed", "failed"],
        progress_percentage: int,
        message: Optional[str] = None
    ):
        """
        Update workflow progress

        Args:
            current_agent: Name of current agent
            status: Current status
            progress_percentage: Overall progress (0-100)
            message: Optional status message
        """
        progress = {
            'workflow_id': self.workflow_id,
            'current_agent': current_agent,
            'status': status,
            'progress_percentage': progress_percentage,
            'message': message,
            'updated_at': datetime.utcnow().isoformat()
        }

        self.progress_file.write_text(json.dumps(progress, indent=2))

        # Also log to stdout for CLI visibility
        print(f"PROGRESS: {json.dumps(progress)}")

    def get_progress(self) -> Dict[str, Any]:
        """Get current progress"""
        if not self.progress_file.exists():
            return {'error': 'Progress file does not exist'}

        return json.loads(self.progress_file.read_text())


if __name__ == '__main__':
    # Example usage
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create logger
        logger = WorkflowLogger(
            workflow_id="test_20251023_123456",
            agent_name="orchestrator",
            log_dir=Path(tmpdir)
        )

        # Log various events
        logger.log_event('agent_start', 'Orchestrator started')
        logger.log_decision(
            'Use researcher for web search',
            'Request requires external research',
            alternatives_considered=['Skip research', 'Use cached data']
        )
        logger.log_alignment_check(True, 'Request aligns with PROJECT.md goals')
        logger.log_performance_metric('duration', 5.2, 'seconds')

        # Get summary
        summary = logger.get_log_summary()
        print(json.dumps(summary, indent=2))
