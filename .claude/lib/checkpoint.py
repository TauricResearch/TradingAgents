"""
Checkpoint/Resume System for autonomous-dev v2.0
Allows workflows to be saved and resumed after interruptions or failures.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See state-management-patterns skill for standardized design patterns.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, List


class CheckpointManager:
    """
    Manages workflow checkpoints for resume capability

    Checkpoints allow workflows to be interrupted and resumed later without
    starting over from the beginning.
    """

    def __init__(self, artifacts_dir: Optional[Path] = None):
        """
        Initialize checkpoint manager

        Args:
            artifacts_dir: Base directory for artifacts (default: .claude/artifacts)
        """
        if artifacts_dir is None:
            artifacts_dir = Path(".claude/artifacts")

        self.artifacts_dir = artifacts_dir

    def create_checkpoint(
        self,
        workflow_id: str,
        completed_agents: List[str],
        current_agent: str,
        artifacts_created: List[str],
        metadata: Optional[Dict[str, Any]] = None
    ) -> Path:
        """
        Create a checkpoint after an agent completes

        Args:
            workflow_id: Workflow identifier
            completed_agents: List of agents that have completed
            current_agent: Agent that just completed (or next to run)
            artifacts_created: List of artifact files created so far
            metadata: Additional checkpoint metadata

        Returns:
            Path to checkpoint file
        """
        checkpoint = {
            'version': '2.0',
            'workflow_id': workflow_id,
            'created_at': datetime.utcnow().isoformat(),
            'checkpoint_type': 'agent_completion',
            'completed_agents': completed_agents,
            'current_agent': current_agent,
            'artifacts_created': artifacts_created,
            'metadata': metadata or {}
        }

        checkpoint_path = self._get_checkpoint_path(workflow_id)
        checkpoint_path.parent.mkdir(parents=True, exist_ok=True)
        checkpoint_path.write_text(json.dumps(checkpoint, indent=2))

        return checkpoint_path

    def load_checkpoint(self, workflow_id: str) -> Optional[Dict[str, Any]]:
        """
        Load checkpoint for a workflow

        Args:
            workflow_id: Workflow identifier

        Returns:
            Checkpoint data or None if not found
        """
        checkpoint_path = self._get_checkpoint_path(workflow_id)

        if not checkpoint_path.exists():
            return None

        return json.loads(checkpoint_path.read_text())

    def checkpoint_exists(self, workflow_id: str) -> bool:
        """Check if checkpoint exists for workflow"""
        return self._get_checkpoint_path(workflow_id).exists()

    def delete_checkpoint(self, workflow_id: str):
        """Delete checkpoint (after workflow completes)"""
        checkpoint_path = self._get_checkpoint_path(workflow_id)
        if checkpoint_path.exists():
            checkpoint_path.unlink()

    def list_resumable_workflows(self) -> List[Dict[str, Any]]:
        """
        List all workflows that can be resumed

        Returns:
            List of workflow summaries with checkpoint info
        """
        resumable = []

        if not self.artifacts_dir.exists():
            return resumable

        for workflow_dir in self.artifacts_dir.iterdir():
            if not workflow_dir.is_dir():
                continue

            checkpoint_path = workflow_dir / "checkpoint.json"
            if not checkpoint_path.exists():
                continue

            try:
                checkpoint = json.loads(checkpoint_path.read_text())
                resumable.append({
                    'workflow_id': checkpoint['workflow_id'],
                    'created_at': checkpoint['created_at'],
                    'current_agent': checkpoint['current_agent'],
                    'completed_agents': checkpoint['completed_agents'],
                    'progress': f"{len(checkpoint['completed_agents'])}/8 agents"
                })
            except Exception:
                continue

        return sorted(resumable, key=lambda x: x['created_at'], reverse=True)

    def validate_checkpoint(self, workflow_id: str) -> tuple[bool, Optional[str]]:
        """
        Validate checkpoint integrity

        Args:
            workflow_id: Workflow identifier

        Returns:
            (is_valid, error_message)
        """
        checkpoint = self.load_checkpoint(workflow_id)

        if checkpoint is None:
            return False, "Checkpoint not found"

        # Check required fields
        required_fields = ['version', 'workflow_id', 'completed_agents', 'current_agent']
        for field in required_fields:
            if field not in checkpoint:
                return False, f"Missing required field: {field}"

        # Check artifacts exist
        artifacts_created = checkpoint.get('artifacts_created', [])
        workflow_dir = self.artifacts_dir / workflow_id

        for artifact in artifacts_created:
            artifact_path = workflow_dir / artifact
            if not artifact_path.exists():
                return False, f"Artifact missing: {artifact}"

        return True, None

    def get_resume_plan(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get plan for resuming workflow

        Args:
            workflow_id: Workflow identifier

        Returns:
            Resume plan with next steps
        """
        checkpoint = self.load_checkpoint(workflow_id)

        if checkpoint is None:
            return {'error': 'Checkpoint not found'}

        # Agent pipeline
        all_agents = [
            'orchestrator',
            'researcher',
            'planner',
            'test-master',
            'implementer',
            'reviewer',
            'security-auditor',
            'doc-master'
        ]

        completed = checkpoint.get('completed_agents', [])
        remaining = [agent for agent in all_agents if agent not in completed]

        return {
            'workflow_id': workflow_id,
            'checkpoint_valid': True,
            'completed_agents': completed,
            'remaining_agents': remaining,
            'next_agent': remaining[0] if remaining else None,
            'progress_percentage': int((len(completed) / len(all_agents)) * 100),
            'can_resume': len(remaining) > 0
        }

    def _get_checkpoint_path(self, workflow_id: str) -> Path:
        """Get path to checkpoint file"""
        return self.artifacts_dir / workflow_id / "checkpoint.json"


class CheckpointError(Exception):
    """Raised when checkpoint operations fail"""
    pass


class WorkflowResumer:
    """
    Resume interrupted workflows

    Handles the logic of loading checkpoints and continuing from where
    the workflow was interrupted.
    """

    def __init__(
        self,
        checkpoint_manager: CheckpointManager,
        artifact_manager: Any  # Avoid circular import
    ):
        """
        Initialize workflow resumer

        Args:
            checkpoint_manager: CheckpointManager instance
            artifact_manager: ArtifactManager instance
        """
        self.checkpoint_manager = checkpoint_manager
        self.artifact_manager = artifact_manager

    def can_resume(self, workflow_id: str) -> bool:
        """Check if workflow can be resumed"""
        if not self.checkpoint_manager.checkpoint_exists(workflow_id):
            return False

        is_valid, _ = self.checkpoint_manager.validate_checkpoint(workflow_id)
        return is_valid

    def resume_workflow(self, workflow_id: str) -> tuple[bool, str, Dict[str, Any]]:
        """
        Resume a workflow from checkpoint

        Args:
            workflow_id: Workflow identifier

        Returns:
            (success, message, resume_context)
        """
        # Validate checkpoint
        is_valid, error = self.checkpoint_manager.validate_checkpoint(workflow_id)

        if not is_valid:
            return False, f"Cannot resume: {error}", {}

        # Load checkpoint
        checkpoint = self.checkpoint_manager.load_checkpoint(workflow_id)

        # Get resume plan
        resume_plan = self.checkpoint_manager.get_resume_plan(workflow_id)

        if not resume_plan.get('can_resume'):
            return False, "Workflow already completed", {}

        # Load workflow manifest
        try:
            manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        except Exception as e:
            return False, f"Cannot load manifest: {e}", {}

        # Prepare resume context
        resume_context = {
            'workflow_id': workflow_id,
            'original_request': manifest.get('request'),
            'completed_agents': checkpoint['completed_agents'],
            'next_agent': resume_plan['next_agent'],
            'remaining_agents': resume_plan['remaining_agents'],
            'progress': resume_plan['progress_percentage'],
            'artifacts_available': checkpoint.get('artifacts_created', []),
            'checkpoint_timestamp': checkpoint['created_at']
        }

        success_msg = f"""
✅ **Workflow Resumed**

Workflow ID: {workflow_id}
Original Request: {resume_context['original_request']}

Progress: {resume_context['progress']}% complete
Completed: {', '.join(resume_context['completed_agents'])}
Next: {resume_context['next_agent']}

Checkpoint from: {resume_context['checkpoint_timestamp']}

Continuing workflow...
"""

        return True, success_msg, resume_context


if __name__ == '__main__':
    # Example usage
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        tmppath = Path(tmpdir)
        artifacts_dir = tmppath / ".claude" / "artifacts"

        # Create checkpoint manager
        manager = CheckpointManager(artifacts_dir)

        # Create a checkpoint
        workflow_id = "20251023_093456"
        checkpoint_path = manager.create_checkpoint(
            workflow_id=workflow_id,
            completed_agents=['orchestrator', 'researcher', 'planner'],
            current_agent='test-master',
            artifacts_created=['manifest.json', 'research.json', 'architecture.json'],
            metadata={'error': None, 'retry_count': 0}
        )

        print(f"Created checkpoint: {checkpoint_path}")
        print()

        # Load checkpoint
        checkpoint = manager.load_checkpoint(workflow_id)
        print("Loaded checkpoint:")
        print(json.dumps(checkpoint, indent=2))
        print()

        # Validate checkpoint
        is_valid, error = manager.validate_checkpoint(workflow_id)
        print(f"Checkpoint valid: {is_valid}")
        if error:
            print(f"Error: {error}")
        print()

        # Get resume plan
        resume_plan = manager.get_resume_plan(workflow_id)
        print("Resume plan:")
        print(json.dumps(resume_plan, indent=2))
        print()

        # List resumable workflows
        resumable = manager.list_resumable_workflows()
        print(f"Resumable workflows: {len(resumable)}")
        for workflow in resumable:
            print(f"  - {workflow['workflow_id']}: {workflow['progress']}, next: {workflow['current_agent']}")
