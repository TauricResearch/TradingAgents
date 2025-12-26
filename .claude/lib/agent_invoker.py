"""
Unified agent invocation factory pattern.

Eliminates 1,200+ lines of duplication across orchestrator.py by providing
a single factory for invoking all agents with consistent patterns.

See error-handling-patterns skill for exception hierarchy and error handling best practices.


Design Patterns:
    See library-design-patterns skill for standardized design patterns.
    See state-management-patterns skill for standardized design patterns.
"""

from typing import Dict, Any

# Use absolute imports for better test compatibility
# (relative imports fail when module is imported from test files)
try:
    from .artifacts import ArtifactManager
    from .logging_utils import WorkflowLogger, WorkflowProgressTracker
except ImportError:
    # Fallback to absolute imports (for tests)
    from artifacts import ArtifactManager
    from logging_utils import WorkflowLogger, WorkflowProgressTracker


class AgentInvoker:
    """Factory for invoking agents with consistent patterns."""

    # Agent configuration mapping
    AGENT_CONFIGS = {
        'alignment-validator': {
            'progress_pct': 5,
            'artifacts_required': [],  # No artifacts needed, just PROJECT.md
            'description_template': 'Validate PROJECT.md alignment for: {request}',
            'mission': 'Validate if request aligns with PROJECT.md GOALS, SCOPE, and CONSTRAINTS'
        },
        'researcher': {
            'progress_pct': 20,
            'artifacts_required': ['manifest'],
            'description_template': 'Research patterns and best practices for: {request}',
            'mission': 'Research the requested feature to inform implementation'
        },
        'planner': {
            'progress_pct': 35,
            'artifacts_required': ['manifest', 'research'],
            'description_template': 'Design architecture for: {request}',
            'mission': 'Design a comprehensive architecture plan'
        },
        'test-master': {
            'progress_pct': 50,
            'artifacts_required': ['manifest', 'architecture'],
            'description_template': 'Write TDD tests for: {request}',
            'mission': 'Write failing tests that define expected behavior (TDD red phase)'
        },
        'implementer': {
            'progress_pct': 70,
            'artifacts_required': ['manifest', 'architecture', 'tests'],
            'description_template': 'Implement: {request}',
            'mission': 'Write clean, tested implementation that makes all tests pass (TDD green phase)'
        },
        'reviewer': {
            'progress_pct': 80,
            'artifacts_required': ['manifest', 'architecture', 'tests', 'implementation'],
            'description_template': 'Review implementation for: {request}',
            'mission': 'Validate code quality and test coverage'
        },
        'security-auditor': {
            'progress_pct': 90,
            'artifacts_required': ['manifest', 'architecture', 'implementation'],
            'description_template': 'Security audit for: {request}',
            'mission': 'Perform comprehensive security audit'
        },
        'doc-master': {
            'progress_pct': 95,
            'artifacts_required': ['manifest', 'architecture', 'implementation'],
            'description_template': 'Document: {request}',
            'mission': 'Synchronize documentation with implementation'
        },
        'commit-message-generator': {
            'progress_pct': 90,
            'artifacts_required': ['manifest', 'architecture', 'implementation'],
            'description_template': 'Generate commit message for: {request}',
            'mission': 'Generate descriptive commit message following conventional commits format'
        },
        'pr-description-generator': {
            'progress_pct': 96,
            'artifacts_required': ['manifest', 'architecture', 'implementation', 'tests', 'security', 'review', 'documentation'],
            'description_template': 'Generate PR description for: {request}',
            'mission': 'Generate comprehensive pull request description from implementation artifacts'
        },
        'project-progress-tracker': {
            'progress_pct': 98,
            'artifacts_required': ['manifest', 'implementation'],
            'description_template': 'Track PROJECT.md progress for: {request}',
            'mission': 'Track and update PROJECT.md goal completion progress'
        }
    }

    def __init__(self, artifact_manager: ArtifactManager):
        """
        Initialize agent invoker.

        Args:
            artifact_manager: ArtifactManager instance for reading/writing artifacts
        """
        self.artifact_manager = artifact_manager

    def invoke(
        self,
        agent_name: str,
        workflow_id: str,
        **context
    ) -> Dict[str, Any]:
        """
        Generic agent invocation with consistent logging and progress tracking.

        Args:
            agent_name: Name of agent to invoke (e.g., 'researcher', 'planner')
            workflow_id: Unique workflow identifier
            **context: Additional context to pass to agent (e.g., request, user_prompt)

        Returns:
            Dict with subagent invocation details:
                - subagent_type: Agent name
                - description: Human-readable description
                - prompt: Formatted prompt for the agent

        Raises:
            ValueError: If agent_name is not recognized
        """
        if agent_name not in self.AGENT_CONFIGS:
            raise ValueError(
                f"Unknown agent: {agent_name}. "
                f"Valid agents: {list(self.AGENT_CONFIGS.keys())}"
            )

        config = self.AGENT_CONFIGS[agent_name]

        # Initialize logging
        logger = WorkflowLogger(workflow_id, 'orchestrator')
        logger.log_event(f'invoke_{agent_name}', f'Invoking {agent_name}')

        # Update progress
        progress_tracker = WorkflowProgressTracker(workflow_id)
        progress_tracker.update_progress(
            current_agent=agent_name,
            status='in_progress',
            progress_percentage=config['progress_pct'],
            message=f'{agent_name}: Starting...'
        )

        # Read required artifacts
        artifacts = {}
        for artifact_name in config['artifacts_required']:
            try:
                artifacts[artifact_name] = self.artifact_manager.read_artifact(
                    workflow_id,
                    artifact_type=artifact_name,
                    validate=True
                )
            except FileNotFoundError:
                # Some artifacts may not exist yet (acceptable for early agents)
                logger.log_event(
                    'artifact_missing',
                    f'Artifact {artifact_name} not found (may be expected)'
                )

        # Build invocation response
        return {
            'subagent_type': agent_name,
            'description': config['description_template'].format(**context),
            'prompt': self._build_prompt(agent_name, workflow_id, artifacts, context)
        }

    def _build_prompt(
        self,
        agent_name: str,
        workflow_id: str,
        artifacts: Dict[str, Any],
        context: Dict[str, Any]
    ) -> str:
        """
        Build agent prompt from artifacts and context.

        Trust the model - provide essential context, let agent figure out details.

        Args:
            agent_name: Name of agent
            workflow_id: Workflow identifier
            artifacts: Available artifacts
            context: Additional context

        Returns:
            Formatted prompt string
        """
        config = self.AGENT_CONFIGS[agent_name]

        # Extract request from manifest or context
        manifest = artifacts.get('manifest', {})
        request = manifest.get('request', context.get('request', 'No request specified'))

        # Build concise prompt
        prompt_parts = [
            f"You are the {agent_name} agent.",
            f"",
            f"Mission: {config['mission']}",
            f"",
            f"Request: {request}",
            f"",
            f"Workflow ID: {workflow_id}",
            f"",
            f"Available artifacts: {list(artifacts.keys())}",
            f"",
            f"See your agent definition ({agent_name}.md) for detailed responsibilities.",
            f"",
            f"Execute your mission effectively. Trust your training."
        ]

        return "\n".join(prompt_parts)

    def invoke_with_task_tool(
        self,
        agent_name: str,
        workflow_id: str,
        **context
    ) -> Dict[str, Any]:
        """
        Invoke agent with Task tool enabled for complex workflows.

        Same as invoke() but signals that agent should use Task tool
        for multi-step research/analysis.

        Args:
            agent_name: Name of agent to invoke
            workflow_id: Workflow identifier
            **context: Additional context

        Returns:
            Dict with subagent invocation details (includes task_tool_enabled flag)
        """
        result = self.invoke(agent_name, workflow_id, **context)
        result['task_tool_enabled'] = True
        result['prompt'] += "\n\nTask tool is enabled for complex multi-step work."
        return result
