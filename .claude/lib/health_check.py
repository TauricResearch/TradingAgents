"""
Health check system for autonomous-dev v2.0 agents

Monitors agent execution to detect:
- Agent started successfully
- Agent making progress (file updates, log activity)
- Agent hung/crashed (no activity for timeout period)
- Agent completed successfully (expected artifacts created)


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See api-integration-patterns skill for standardized design patterns.
"""

import json
import time
from datetime import datetime
from pathlib import Path
from typing import Dict, Any, List


class AgentHealthCheck:
    """Monitor agent health and execution progress"""

    def __init__(self, workflow_id: str, agent_name: str):
        self.workflow_id = workflow_id
        self.agent_name = agent_name
        self.artifacts_dir = Path(f".claude/artifacts/{workflow_id}")
        self.log_file = self.artifacts_dir / "logs" / f"{agent_name}.log"

    def check_started(self, timeout_seconds: int = 60) -> Dict[str, Any]:
        """
        Check if agent has started (log file exists with recent activity)

        Args:
            timeout_seconds: How long to wait for agent to start

        Returns:
            Dict with status and details
        """
        start_time = time.time()

        while time.time() - start_time < timeout_seconds:
            if self.log_file.exists():
                # Check if log has content
                if self.log_file.stat().st_size > 0:
                    mtime = datetime.fromtimestamp(self.log_file.stat().st_mtime)
                    age_seconds = (datetime.now() - mtime).total_seconds()

                    return {
                        'started': True,
                        'log_file': str(self.log_file),
                        'log_size': self.log_file.stat().st_size,
                        'last_modified': mtime.isoformat(),
                        'age_seconds': age_seconds
                    }

            time.sleep(1)

        return {
            'started': False,
            'error': f'Agent {self.agent_name} did not start within {timeout_seconds}s',
            'log_file': str(self.log_file),
            'log_exists': self.log_file.exists()
        }

    def check_progress(self, max_idle_seconds: int = 300) -> Dict[str, Any]:
        """
        Check if agent is making progress (recent log activity)

        Args:
            max_idle_seconds: Maximum seconds without log updates before considering hung

        Returns:
            Dict with progress status
        """
        if not self.log_file.exists():
            return {
                'active': False,
                'error': f'Log file does not exist: {self.log_file}'
            }

        mtime = datetime.fromtimestamp(self.log_file.stat().st_mtime)
        age_seconds = (datetime.now() - mtime).total_seconds()

        # Read last few log entries
        try:
            with open(self.log_file, 'r') as f:
                lines = f.readlines()
                last_entries = lines[-5:] if len(lines) >= 5 else lines

            last_events = []
            for line in last_entries:
                try:
                    entry = json.loads(line)
                    last_events.append({
                        'timestamp': entry.get('timestamp', 'unknown'),
                        'event': entry.get('event_type', 'unknown'),
                        'message': entry.get('message', '')
                    })
                except:
                    pass

        except Exception as e:
            last_events = []

        is_active = age_seconds < max_idle_seconds

        return {
            'active': is_active,
            'last_modified': mtime.isoformat(),
            'age_seconds': age_seconds,
            'max_idle_seconds': max_idle_seconds,
            'log_size': self.log_file.stat().st_size,
            'last_events': last_events,
            'status': 'active' if is_active else 'possibly_hung'
        }

    def check_completion(self, expected_artifacts: List[str]) -> Dict[str, Any]:
        """
        Check if agent completed successfully (expected artifacts exist)

        Args:
            expected_artifacts: List of artifact filenames that should exist

        Returns:
            Dict with completion status
        """
        missing_artifacts = []
        existing_artifacts = []

        for artifact in expected_artifacts:
            artifact_path = self.artifacts_dir / artifact

            if artifact_path.exists():
                existing_artifacts.append({
                    'name': artifact,
                    'path': str(artifact_path),
                    'size': artifact_path.stat().st_size,
                    'modified': datetime.fromtimestamp(
                        artifact_path.stat().st_mtime
                    ).isoformat()
                })
            else:
                missing_artifacts.append(artifact)

        completed = len(missing_artifacts) == 0

        return {
            'completed': completed,
            'existing_artifacts': existing_artifacts,
            'missing_artifacts': missing_artifacts,
            'total_expected': len(expected_artifacts),
            'total_found': len(existing_artifacts)
        }

    def full_health_check(
        self,
        expected_artifacts: List[str],
        start_timeout: int = 60,
        max_idle: int = 300
    ) -> Dict[str, Any]:
        """
        Comprehensive health check

        Args:
            expected_artifacts: Artifacts that should be created
            start_timeout: Seconds to wait for agent to start
            max_idle: Seconds without activity before considering hung

        Returns:
            Dict with complete health status
        """
        started = self.check_started(start_timeout)

        if not started['started']:
            return {
                'status': 'not_started',
                'details': started
            }

        progress = self.check_progress(max_idle)
        completion = self.check_completion(expected_artifacts)

        if completion['completed']:
            status = 'completed'
        elif progress['active']:
            status = 'running'
        else:
            status = 'hung'

        return {
            'status': status,
            'workflow_id': self.workflow_id,
            'agent': self.agent_name,
            'started': started,
            'progress': progress,
            'completion': completion,
            'timestamp': datetime.now().isoformat()
        }


def monitor_agent_execution(
    workflow_id: str,
    agent_name: str,
    expected_artifacts: List[str],
    poll_interval: int = 5,
    max_wait: int = 900
) -> Dict[str, Any]:
    """
    Monitor agent execution until completion or timeout

    Args:
        workflow_id: Workflow ID
        agent_name: Agent being monitored
        expected_artifacts: Artifacts that should be created
        poll_interval: Seconds between health checks
        max_wait: Maximum seconds to wait

    Returns:
        Final health check result
    """
    health = AgentHealthCheck(workflow_id, agent_name)
    start_time = time.time()

    print(f"Monitoring {agent_name} agent for workflow {workflow_id}...")
    print(f"Expected artifacts: {', '.join(expected_artifacts)}")
    print(f"Max wait time: {max_wait}s\n")

    while time.time() - start_time < max_wait:
        check = health.full_health_check(expected_artifacts)
        elapsed = int(time.time() - start_time)

        print(f"[{elapsed}s] Status: {check['status']}")

        if check['status'] == 'completed':
            print("✓ Agent completed successfully!")
            return check
        elif check['status'] == 'hung':
            print(f"✗ Agent appears to be hung (no activity for {check['progress']['age_seconds']}s)")
            return check
        elif check['status'] == 'not_started':
            print("⏳ Waiting for agent to start...")
        else:  # running
            print(f"⏺ Agent running (last activity {int(check['progress']['age_seconds'])}s ago)")
            if check['progress'].get('last_events'):
                last_event = check['progress']['last_events'][-1]
                print(f"   Latest: {last_event['event']} - {last_event['message'][:60]}")

        time.sleep(poll_interval)

    print(f"\n✗ Timeout after {max_wait}s")
    return health.full_health_check(expected_artifacts)


if __name__ == '__main__':
    import sys

    if len(sys.argv) < 3:
        print("Usage: python health_check.py <workflow_id> <agent_name> [artifact1 artifact2 ...]")
        sys.exit(1)

    workflow_id = sys.argv[1]
    agent_name = sys.argv[2]
    expected_artifacts = sys.argv[3:] if len(sys.argv) > 3 else []

    if expected_artifacts:
        result = monitor_agent_execution(workflow_id, agent_name, expected_artifacts)
    else:
        health = AgentHealthCheck(workflow_id, agent_name)
        result = health.full_health_check([])

    print("\n=== FINAL STATUS ===")
    print(json.dumps(result, indent=2))
