"""
Artifact Management for autonomous-dev v2.0
Handles creation, validation, and reading of workflow artifacts.

See error-handling-patterns skill for exception hierarchy and error handling best practices.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See state-management-patterns skill for standardized design patterns.
"""

import json
from pathlib import Path
from datetime import datetime
from typing import Dict, Any, Optional, Literal
from dataclasses import dataclass


@dataclass
class ArtifactMetadata:
    """Metadata for all artifacts"""
    version: str = "2.0"
    workflow_id: str = ""
    agent: str = ""
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    created_at: Optional[str] = None
    updated_at: Optional[str] = None

    def __post_init__(self):
        if self.created_at is None:
            self.created_at = datetime.utcnow().isoformat()
        if self.updated_at is None:
            self.updated_at = self.created_at


class ArtifactManager:
    """
    Manages workflow artifacts with validation and schema enforcement
    """

    # Required fields for all artifacts
    REQUIRED_FIELDS = ['version', 'agent', 'workflow_id', 'status']

    # Valid artifact types
    ARTIFACT_TYPES = [
        'manifest',
        'research',
        'architecture',
        'test-plan',
        'implementation',
        'review',
        'security',
        'docs',
        'final-report'
    ]

    def __init__(self, artifacts_dir: Optional[Path] = None):
        """
        Initialize artifact manager

        Args:
            artifacts_dir: Base directory for artifacts (default: .claude/artifacts)
        """
        if artifacts_dir is None:
            artifacts_dir = Path(".claude/artifacts")

        self.artifacts_dir = artifacts_dir
        self.artifacts_dir.mkdir(parents=True, exist_ok=True)

    def create_workflow_directory(self, workflow_id: str) -> Path:
        """
        Create directory for a new workflow

        Args:
            workflow_id: Unique workflow identifier

        Returns:
            Path to workflow directory
        """
        workflow_dir = self.artifacts_dir / workflow_id
        workflow_dir.mkdir(parents=True, exist_ok=True)
        return workflow_dir

    def get_workflow_directory(self, workflow_id: str) -> Path:
        """Get path to workflow directory"""
        return self.artifacts_dir / workflow_id

    def write_artifact(
        self,
        workflow_id: str,
        artifact_type: str,
        data: Dict[str, Any],
        validate: bool = True
    ) -> Path:
        """
        Write artifact to file

        Args:
            workflow_id: Workflow identifier
            artifact_type: Type of artifact (manifest, research, etc.)
            data: Artifact data (must include metadata fields)
            validate: Whether to validate artifact before writing

        Returns:
            Path to written artifact file

        Raises:
            ValueError: If artifact is invalid
        """
        # Validate artifact type
        if artifact_type not in self.ARTIFACT_TYPES:
            raise ValueError(
                f"Invalid artifact type: {artifact_type}. "
                f"Valid types: {self.ARTIFACT_TYPES}"
            )

        # Validate artifact data
        if validate:
            is_valid, error = self.validate_artifact(data)
            if not is_valid:
                raise ValueError(f"Invalid artifact: {error}")

        # Ensure workflow directory exists
        workflow_dir = self.create_workflow_directory(workflow_id)

        # Write artifact
        artifact_path = workflow_dir / f"{artifact_type}.json"
        artifact_path.write_text(json.dumps(data, indent=2))

        return artifact_path

    def read_artifact(
        self,
        workflow_id: str,
        artifact_type: str,
        validate: bool = True
    ) -> Dict[str, Any]:
        """
        Read artifact from file

        Args:
            workflow_id: Workflow identifier
            artifact_type: Type of artifact
            validate: Whether to validate artifact after reading

        Returns:
            Artifact data

        Raises:
            FileNotFoundError: If artifact doesn't exist
            ValueError: If artifact is invalid
        """
        artifact_path = self.get_workflow_directory(workflow_id) / f"{artifact_type}.json"

        if not artifact_path.exists():
            raise FileNotFoundError(f"Artifact not found: {artifact_path}")

        data = json.loads(artifact_path.read_text())

        if validate:
            is_valid, error = self.validate_artifact(data)
            if not is_valid:
                raise ValueError(f"Invalid artifact: {error}")

        return data

    def artifact_exists(self, workflow_id: str, artifact_type: str) -> bool:
        """Check if artifact exists"""
        artifact_path = self.get_workflow_directory(workflow_id) / f"{artifact_type}.json"
        return artifact_path.exists()

    def list_artifacts(self, workflow_id: str) -> list[str]:
        """
        List all artifacts for a workflow

        Args:
            workflow_id: Workflow identifier

        Returns:
            List of artifact types (without .json extension)
        """
        workflow_dir = self.get_workflow_directory(workflow_id)

        if not workflow_dir.exists():
            return []

        artifacts = []
        for artifact_path in workflow_dir.glob("*.json"):
            artifact_type = artifact_path.stem  # Remove .json extension
            if artifact_type in self.ARTIFACT_TYPES:
                artifacts.append(artifact_type)

        return sorted(artifacts)

    @classmethod
    def validate_artifact(cls, data: Dict[str, Any]) -> tuple[bool, Optional[str]]:
        """
        Validate artifact has required fields and correct format

        Args:
            data: Artifact data to validate

        Returns:
            (is_valid, error_message)
        """
        # Check required fields
        for field in cls.REQUIRED_FIELDS:
            if field not in data:
                return False, f"Missing required field: {field}"

        # Validate version format
        if not data['version'].startswith('2.'):
            return False, f"Invalid version: {data['version']} (expected 2.x)"

        # Validate status values
        valid_statuses = ['pending', 'in_progress', 'completed', 'failed']
        if data['status'] not in valid_statuses:
            return False, f"Invalid status: {data['status']} (expected: {valid_statuses})"

        return True, None

    def create_manifest_artifact(
        self,
        workflow_id: str,
        request: str,
        alignment_data: Dict[str, Any],
        workflow_plan: Dict[str, Any]
    ) -> Path:
        """
        Create workflow manifest artifact (created by orchestrator)

        Args:
            workflow_id: Workflow identifier
            request: User's original request
            alignment_data: PROJECT.md alignment validation results
            workflow_plan: Plan for which agents to run and in what order

        Returns:
            Path to created manifest
        """
        manifest = {
            'version': '2.0',
            'agent': 'orchestrator',
            'workflow_id': workflow_id,
            'status': 'in_progress',
            'created_at': datetime.utcnow().isoformat(),
            'request': request,
            'alignment': alignment_data,
            'workflow_plan': workflow_plan
        }

        return self.write_artifact(workflow_id, 'manifest', manifest)

    def get_workflow_summary(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get summary of workflow progress

        Args:
            workflow_id: Workflow identifier

        Returns:
            Summary with artifact statuses, progress, etc.
        """
        workflow_dir = self.get_workflow_directory(workflow_id)

        if not workflow_dir.exists():
            return {'error': f'Workflow not found: {workflow_id}'}

        # List all artifacts
        artifacts = self.list_artifacts(workflow_id)

        # Get status of each artifact
        artifact_statuses = {}
        for artifact_type in artifacts:
            try:
                artifact_data = self.read_artifact(workflow_id, artifact_type, validate=False)
                artifact_statuses[artifact_type] = {
                    'status': artifact_data.get('status', 'unknown'),
                    'agent': artifact_data.get('agent', 'unknown'),
                    'created_at': artifact_data.get('created_at', 'unknown')
                }
            except Exception as e:
                artifact_statuses[artifact_type] = {'error': str(e)}

        # Calculate overall progress
        total_expected = len(self.ARTIFACT_TYPES)
        completed = sum(1 for s in artifact_statuses.values() if s.get('status') == 'completed')
        progress_percentage = int((completed / total_expected) * 100)

        return {
            'workflow_id': workflow_id,
            'artifacts': artifact_statuses,
            'total_artifacts': len(artifacts),
            'completed': completed,
            'progress_percentage': progress_percentage,
            'workflow_dir': str(workflow_dir)
        }

    def cleanup_old_workflows(self, keep_recent: int = 10):
        """
        Clean up old workflow directories

        Args:
            keep_recent: Number of recent workflows to keep
        """
        workflows = sorted(
            [d for d in self.artifacts_dir.iterdir() if d.is_dir()],
            key=lambda d: d.stat().st_mtime,
            reverse=True
        )

        # Delete old workflows
        for workflow_dir in workflows[keep_recent:]:
            try:
                import shutil
                shutil.rmtree(workflow_dir)
            except Exception as e:
                print(f"Warning: Could not delete {workflow_dir}: {e}")


def generate_workflow_id() -> str:
    """
    Generate unique workflow identifier

    Returns:
        Workflow ID in format: YYYYMMDD_HHMMSS
    """
    return datetime.utcnow().strftime("%Y%m%d_%H%M%S")


if __name__ == '__main__':
    # Example usage
    import tempfile

    with tempfile.TemporaryDirectory() as tmpdir:
        # Create artifact manager
        manager = ArtifactManager(artifacts_dir=Path(tmpdir))

        # Create workflow
        workflow_id = generate_workflow_id()
        print(f"Created workflow: {workflow_id}")

        # Write manifest
        manifest_path = manager.create_manifest_artifact(
            workflow_id=workflow_id,
            request="Implement user authentication",
            alignment_data={
                'validated': True,
                'matches_goals': ['Improve security'],
                'within_scope': True
            },
            workflow_plan={
                'agents': ['researcher', 'planner', 'test-master', 'implementer'],
                'parallel_validators': ['reviewer', 'security-auditor', 'doc-master']
            }
        )
        print(f"Created manifest: {manifest_path}")

        # Read manifest
        manifest = manager.read_artifact(workflow_id, 'manifest')
        print(f"Read manifest: {manifest['request']}")

        # Get summary
        summary = manager.get_workflow_summary(workflow_id)
        print(f"Workflow summary: {json.dumps(summary, indent=2)}")
