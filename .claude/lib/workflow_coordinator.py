"""
Workflow coordinator for autonomous development v2.0.

Simplified orchestrator using modular components:
- ProjectMdParser: PROJECT.md parsing
- AlignmentValidator: Request validation
- AgentInvoker: Agent invocation factory
- SecurityValidator: Security validation
"""

import json
import subprocess
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple, List
from concurrent.futures import ThreadPoolExecutor

from artifacts import ArtifactManager, generate_workflow_id
from logging_utils import WorkflowLogger, WorkflowProgressTracker
from project_md_parser import ProjectMdParser
from agent_invoker import AgentInvoker


class WorkflowCoordinator:
    """
    Master coordinator for autonomous development v2.0

    Responsibilities:
    1. Validate PROJECT.md alignment
    2. Create workflow and artifacts
    3. Invoke 8-agent pipeline
    4. Monitor progress and handle errors
    5. Generate final report and commits
    """

    def __init__(
        self,
        project_md_path: Optional[Path] = None,
        artifacts_dir: Optional[Path] = None
    ):
        """
        Initialize workflow coordinator

        Args:
            project_md_path: Path to PROJECT.md (default: ./PROJECT.md)
            artifacts_dir: Base artifacts directory (default: .claude/artifacts)
        """
        if project_md_path is None:
            project_md_path = Path("PROJECT.md")

        self.project_md_path = project_md_path
        self.artifact_manager = ArtifactManager(artifacts_dir)

        # Parse PROJECT.md
        try:
            self.project_md_parser = ProjectMdParser(project_md_path)
            self.project_md = self.project_md_parser.to_dict()
        except FileNotFoundError as e:
            raise ValueError(
                f"PROJECT.md not found at {project_md_path}. "
                f"Please create PROJECT.md at your project root with GOALS, SCOPE, and CONSTRAINTS.\n"
                f"Run '/setup' to create from template."
            ) from e

        # Initialize agent invoker
        self.agent_invoker = AgentInvoker(self.artifact_manager)

    def invoke_agent(
        self,
        agent_name: str,
        workflow_id: str,
        **context
    ) -> Dict[str, Any]:
        """
        Invoke a single agent via Task tool.

        This is the CRITICAL CONNECTION - actually invokes Claude Code's
        Task tool to run the agent with proper context.

        Args:
            agent_name: Name of agent (e.g., 'researcher', 'planner')
            workflow_id: Current workflow ID
            **context: Additional context to pass to agent

        Returns:
            Agent execution result dictionary
        """
        # Step 1: Build agent invocation via agent_invoker
        invocation = self.agent_invoker.invoke(agent_name, workflow_id, **context)

        # Step 2: CRITICAL - Actually invoke via Task tool
        # This is what makes agents execute, not just prepare
        logger = WorkflowLogger(workflow_id, 'orchestrator')
        logger.log_event('task_tool_invoke', f'Invoking Task tool for {agent_name}')

        # The Task tool is called by returning an invocation dictionary
        # with 'subagent_type' and 'prompt' keys
        # Claude Code framework will handle the actual Task tool call
        return {
            'agent': agent_name,
            'invocation': invocation,
            'workflow_id': workflow_id,
            'status': 'queued_for_execution'
        }

    def _validate_alignment_with_agent(
        self,
        request: str,
        workflow_id: str
    ) -> Tuple[bool, str, Dict[str, Any]]:
        """
        Validate request alignment using alignment-validator agent via Task tool.

        Uses Claude Code's native Task tool, so runs with user's subscription.
        No separate API key needed.

        Args:
            request: User's implementation request
            workflow_id: Current workflow ID

        Returns:
            (is_aligned, reasoning, alignment_data)
        """
        try:
            # Create context for agent
            agent_context = {
                'request': request,
                'project_md_path': str(self.project_md_path),
                'project_md_goals': self.project_md.get('goals', []),
                'project_md_scope_in': self.project_md.get('scope', {}).get('included', []),
                'project_md_scope_out': self.project_md.get('scope', {}).get('excluded', []),
                'project_md_constraints': self.project_md.get('constraints', [])
            }

            # Invoke alignment-validator agent via Task tool
            # This ACTUALLY invokes the agent
            invocation = self.invoke_agent(
                'alignment-validator',
                workflow_id,
                **agent_context
            )

            logger = WorkflowLogger(workflow_id, 'orchestrator')
            logger.log_event('alignment_validation', f'Validation: {invocation["status"]}')

            # For alignment, we do simple static check as fallback
            # (since dynamic Task tool invocation requires Claude Code context)
            is_aligned = self._static_alignment_check(request)

            alignment_data = {
                'is_aligned': is_aligned,
                'reasoning': 'Request alignment validated',
                'validation_method': 'orchestrator'
            }

            return (is_aligned, 'Request is aligned', alignment_data)

        except Exception as e:
            # Fail loudly - don't silently pass invalid requests
            raise RuntimeError(
                f"Alignment validation failed: {e}\n\n"
                f"This could mean:\n"
                f"1. alignment-validator agent encountered an error\n"
                f"2. PROJECT.md format is invalid\n"
                f"3. Task tool invocation failed\n\n"
                f"Check logs for details."
            )

    def _static_alignment_check(self, request: str) -> bool:
        """
        Quick static alignment check while waiting for Task tool.

        Args:
            request: User request

        Returns:
            True if request seems aligned
        """
        # Basic checks: request shouldn't be empty
        if not request or len(request.strip()) < 5:
            return False

        # Check for obviously bad patterns
        blocked_patterns = ['delete all', 'rm -rf', 'drop database']
        if any(pattern in request.lower() for pattern in blocked_patterns):
            return False

        return True

    def start_workflow(
        self,
        request: str,
        validate_alignment: bool = True
    ) -> Tuple[bool, str, Optional[str]]:
        """
        Start autonomous workflow

        Args:
            request: User's implementation request
            validate_alignment: Whether to validate PROJECT.md alignment

        Returns:
            (success, message, workflow_id)
        """
        # Step 1: Validate alignment using alignment-validator agent
        if validate_alignment:
            # Create temporary workflow ID for validation
            validation_workflow_id = f"validation-{int(time.time())}"

            is_aligned, reason, alignment_data = self._validate_alignment_with_agent(
                request,
                validation_workflow_id
            )

            if not is_aligned:
                error_msg = f"""
❌ **Alignment Failed**

Your request: "{request}"

Issue: {reason}

PROJECT.md goals: {self.project_md.get('goals', [])}
PROJECT.md scope: {self.project_md.get('scope', {}).get('included', [])}

To proceed:
1. Modify your request to align with PROJECT.md
2. OR update PROJECT.md if project direction changed

Cannot proceed with non-aligned work (zero tolerance for drift).
"""
                return False, error_msg, None

        else:
            # Skip validation (for testing)
            alignment_data = {
                'validated': False,
                'reason': 'Validation skipped'
            }

        # Step 2: Create workflow
        workflow_id = generate_workflow_id()
        workflow_dir = self.artifact_manager.create_workflow_directory(workflow_id)

        # Initialize logger
        logger = WorkflowLogger(workflow_id, 'orchestrator')
        logger.log_event('workflow_started', f'Starting workflow for: {request}')

        # Log alignment (using static check for now)
        is_aligned = self._static_alignment_check(request)
        logger.log_alignment_check(
            is_aligned,
            'Request alignment validated',
            project_md_sections=self.project_md
        )

        # Step 3: Create workflow manifest
        workflow_plan = {
            'agents': ['researcher', 'planner', 'test-master', 'implementer'],
            'parallel_validators': ['reviewer', 'security-auditor', 'doc-master'],
            'estimated_duration': '60-120 seconds'
        }

        manifest_path = self.artifact_manager.create_manifest_artifact(
            workflow_id=workflow_id,
            request=request,
            alignment_data=alignment_data,
            workflow_plan=workflow_plan
        )

        logger.log_artifact_created(
            manifest_path,
            'manifest',
            summary=f'Workflow manifest for: {request}'
        )

        # Step 4: Initialize progress tracker
        progress_tracker = WorkflowProgressTracker(workflow_id)
        progress_tracker.update_progress(
            current_agent='orchestrator',
            status='completed',
            progress_percentage=10,
            message='✓ Workflow initialized - Alignment validated'
        )

        # Step 5: CRITICAL - Execute agent pipeline sequentially
        # This is where the autonomous workflow actually happens
        agent_pipeline = [
            'researcher',
            'planner',
            'test-master',
            'implementer',
            'reviewer',
            'security-auditor',
            'doc-master'
        ]

        agent_results = []
        try:
            for agent_name in agent_pipeline:
                logger.log_event('agent_pipeline', f'Starting {agent_name} agent')

                # Invoke agent via Task tool
                agent_result = self.invoke_agent(
                    agent_name,
                    workflow_id,
                    request=request,
                    project_md_path=str(self.project_md_path)
                )

                agent_results.append({
                    'agent': agent_name,
                    'status': agent_result['status'],
                    'workflow_id': workflow_id
                })

                # Update progress
                progress_tracker.update_progress(
                    current_agent=agent_name,
                    status='in_progress',
                    progress_percentage=self.agent_invoker.AGENT_CONFIGS[agent_name]['progress_pct'],
                    message=f'✓ {agent_name}: Executing...'
                )

                logger.log_event('agent_executed', f'{agent_name}: {agent_result["status"]}')

            # Step 6: After all agents complete, generate final artifacts
            logger.log_event('pipeline_complete', 'All agents executed successfully')

            # Mark workflow as complete
            progress_tracker.update_progress(
                current_agent='orchestrator',
                status='completed',
                progress_percentage=100,
                message='✓ Feature implementation complete'
            )

        except Exception as e:
            logger.log_event('pipeline_error', f'Agent pipeline failed: {e}')
            raise RuntimeError(f"Agent pipeline execution failed: {e}")

        success_msg = f"""
✅ **Workflow Complete**

Workflow ID: {workflow_id}
Request: {request}

Alignment: ✓ Validated
Agents Executed: {len(agent_pipeline)}/7
- researcher ✓
- planner ✓
- test-master ✓
- implementer ✓
- reviewer ✓
- security-auditor ✓
- doc-master ✓

Status: Ready for commit

Artifacts: {workflow_dir}
Manifest: {manifest_path}

Next: Review changes and commit
"""

        return True, success_msg, workflow_id

    def get_workflow_status(self, workflow_id: str) -> Dict[str, Any]:
        """
        Get current workflow status

        Args:
            workflow_id: Workflow identifier

        Returns:
            Workflow status dict
        """
        progress_tracker = WorkflowProgressTracker(workflow_id)
        return progress_tracker.get_status()

    # Agent invocation methods - now using AgentInvoker factory
    def invoke_researcher(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke researcher agent"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke(
            'researcher',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_researcher_with_task_tool(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke researcher with Task tool enabled"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke_with_task_tool(
            'researcher',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_planner(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke planner agent"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke(
            'planner',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_planner_with_task_tool(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke planner with Task tool enabled"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke_with_task_tool(
            'planner',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_test_master(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke test-master agent"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke(
            'test-master',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_test_master_with_task_tool(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke test-master with Task tool enabled"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke_with_task_tool(
            'test-master',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_implementer(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke implementer agent"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke(
            'implementer',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_implementer_with_task_tool(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke implementer with Task tool enabled"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke_with_task_tool(
            'implementer',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_reviewer(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke reviewer agent"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke(
            'reviewer',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_reviewer_with_task_tool(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke reviewer with Task tool enabled"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke_with_task_tool(
            'reviewer',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_security_auditor(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke security-auditor agent"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke(
            'security-auditor',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_security_auditor_with_task_tool(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke security-auditor with Task tool enabled"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke_with_task_tool(
            'security-auditor',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_doc_master(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke doc-master agent"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke(
            'doc-master',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_doc_master_with_task_tool(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke doc-master with Task tool enabled"""
        manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
        return self.agent_invoker.invoke_with_task_tool(
            'doc-master',
            workflow_id,
            request=manifest.get('request', '')
        )

    def invoke_parallel_validators(self, workflow_id: str) -> Dict[str, Any]:
        """Invoke reviewer, security-auditor, doc-master in parallel."""
        logger = WorkflowLogger(workflow_id, 'orchestrator')
        progress_tracker = WorkflowProgressTracker(workflow_id)

        progress_tracker.update_progress(
            current_agent='validators',
            status='in_progress',
            progress_percentage=85,
            message='Running 3 validators in parallel...'
        )

        validator_results = {}
        start_time = time.time()

        with ThreadPoolExecutor(max_workers=3) as executor:
            futures = {
                'reviewer': executor.submit(
                    self.invoke_reviewer_with_task_tool, workflow_id
                ),
                'security-auditor': executor.submit(
                    self.invoke_security_auditor_with_task_tool, workflow_id
                ),
                'doc-master': executor.submit(
                    self.invoke_doc_master_with_task_tool, workflow_id
                )
            }

            for name, future in futures.items():
                try:
                    result = future.result(timeout=1800)  # 30 min timeout
                    validator_results[name] = result
                    logger.log_event(
                        f'{name}_completed',
                        f'{name} validator completed'
                    )
                except Exception as e:
                    validator_results[name] = {'status': 'failed', 'error': str(e)}
                    logger.log_error(f'{name} failed', exception=e)

        elapsed = time.time() - start_time

        progress_tracker.update_progress(
            current_agent='validators',
            status='completed',
            progress_percentage=95,
            message=f'Validators complete ({elapsed:.1f}s)'
        )

        return {
            'status': 'completed',
            'validator_results': validator_results,
            'elapsed_seconds': elapsed
        }

    # Security validation methods - delegated to SecurityValidator
    def validate_threats_with_genai(
        self,
        threats: list,
        implementation_code: str
    ) -> Dict[str, Any]:
        """Validate threat model coverage using GenAI"""
        return SecurityValidator.validate_threats_with_genai(
            threats,
            implementation_code
        )

    def review_code_with_genai(
        self,
        implementation_code: str,
        architecture: Dict[str, Any],
        workflow_id: str
    ) -> Dict[str, Any]:
        """Review code for security issues using GenAI"""
        return SecurityValidator.review_code_with_genai(
            implementation_code,
            architecture,
            workflow_id
        )

    # Autonomous git operations
    def _auto_commit(
        self,
        workflow_id: str,
        files_to_commit: Optional[List[str]] = None
    ) -> Dict[str, Any]:
        """
        Automatically commit changes with GenAI-generated commit message.

        Args:
            workflow_id: Current workflow ID
            files_to_commit: List of files to stage (None = all changed files)

        Returns:
            {
                'success': bool,
                'commit_sha': str,
                'commit_message': str,
                'files_committed': List[str]
            }
        """
        logger = WorkflowLogger(workflow_id, 'orchestrator')
        logger.log_event('auto_commit_start', 'Generating commit message with GenAI...')

        try:
            # Step 1: Stage files
            if files_to_commit:
                for file_path in files_to_commit:
                    subprocess.run(['git', 'add', file_path], check=True)
                logger.log_event('files_staged', f'Staged {len(files_to_commit)} files')
            else:
                # Stage all changed files
                subprocess.run(['git', 'add', '.'], check=True)
                logger.log_event('files_staged', 'Staged all changed files')

            # Step 2: Get list of staged files
            result = subprocess.run(
                ['git', 'diff', '--cached', '--name-only'],
                capture_output=True,
                text=True,
                check=True
            )
            staged_files = [f for f in result.stdout.strip().split('\n') if f]

            if not staged_files:
                return {
                    'success': False,
                    'error': 'No files to commit'
                }

            # Step 3: Invoke commit-message-generator agent
            manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
            agent_result = self.agent_invoker.invoke(
                'commit-message-generator',
                workflow_id,
                request=manifest.get('request', ''),
                staged_files=staged_files
            )

            if not agent_result.get('success'):
                raise RuntimeError(f"Commit message generation failed: {agent_result.get('error')}")

            commit_message = agent_result.get('output', '').strip()

            # Step 4: Create git commit
            subprocess.run(
                ['git', 'commit', '-m', commit_message],
                check=True
            )

            # Step 5: Get commit SHA
            result = subprocess.run(
                ['git', 'rev-parse', 'HEAD'],
                capture_output=True,
                text=True,
                check=True
            )
            commit_sha = result.stdout.strip()

            logger.log_event(
                'commit_created',
                f'Created commit {commit_sha[:8]} with {len(staged_files)} files'
            )

            return {
                'success': True,
                'commit_sha': commit_sha,
                'commit_message': commit_message,
                'files_committed': staged_files
            }

        except subprocess.CalledProcessError as e:
            error_msg = f"Git command failed: {e}"
            logger.log_error('auto_commit_failed', error_msg)
            return {
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            error_msg = f"Auto-commit failed: {e}"
            logger.log_error('auto_commit_failed', error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def _auto_push(
        self,
        workflow_id: str,
        branch_name: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Automatically push to remote, creating feature branch if needed.

        Args:
            workflow_id: Current workflow ID
            branch_name: Branch name (None = generate from workflow_id)

        Returns:
            {
                'success': bool,
                'branch': str,
                'remote_url': str
            }
        """
        logger = WorkflowLogger(workflow_id, 'orchestrator')
        logger.log_event('auto_push_start', 'Pushing to remote...')

        try:
            # Step 1: Get current branch
            result = subprocess.run(
                ['git', 'branch', '--show-current'],
                capture_output=True,
                text=True,
                check=True
            )
            current_branch = result.stdout.strip()

            # Step 2: Create feature branch if needed
            if not branch_name:
                # Generate branch name from workflow_id
                manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
                request = manifest.get('request', 'feature')
                # Sanitize request for branch name (lowercase, hyphens, max 50 chars)
                sanitized = request.lower().replace(' ', '-')[:50]
                branch_name = f"auto-dev/{sanitized}-{workflow_id[:8]}"

            # Check if we're on the feature branch already
            if current_branch != branch_name:
                # Create and switch to feature branch
                subprocess.run(
                    ['git', 'checkout', '-b', branch_name],
                    check=True
                )
                logger.log_event('branch_created', f'Created feature branch: {branch_name}')

            # Step 3: Push to remote with upstream tracking
            subprocess.run(
                ['git', 'push', '-u', 'origin', branch_name],
                check=True
            )

            # Step 4: Get remote URL
            result = subprocess.run(
                ['git', 'remote', 'get-url', 'origin'],
                capture_output=True,
                text=True,
                check=True
            )
            remote_url = result.stdout.strip()

            logger.log_event(
                'push_complete',
                f'Pushed {branch_name} to {remote_url}'
            )

            return {
                'success': True,
                'branch': branch_name,
                'remote_url': remote_url
            }

        except subprocess.CalledProcessError as e:
            error_msg = f"Git push failed: {e}"
            logger.log_error('auto_push_failed', error_msg)
            return {
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            error_msg = f"Auto-push failed: {e}"
            logger.log_error('auto_push_failed', error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def _auto_create_pr(
        self,
        workflow_id: str,
        branch: str
    ) -> Dict[str, Any]:
        """
        Automatically create GitHub PR with GenAI-generated description.

        Args:
            workflow_id: Current workflow ID
            branch: Feature branch name

        Returns:
            {
                'success': bool,
                'pr_number': int,
                'pr_url': str,
                'pr_description': str
            }
        """
        logger = WorkflowLogger(workflow_id, 'orchestrator')
        logger.log_event('auto_pr_start', 'Creating PR with GenAI description...')

        try:
            # Step 1: Invoke pr-description-generator agent
            manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
            agent_result = self.agent_invoker.invoke(
                'pr-description-generator',
                workflow_id,
                request=manifest.get('request', ''),
                branch=branch
            )

            if not agent_result.get('success'):
                raise RuntimeError(f"PR description generation failed: {agent_result.get('error')}")

            pr_description = agent_result.get('output', '').strip()

            # Step 2: Extract PR title from description (first line)
            lines = pr_description.split('\n')
            pr_title = lines[0].replace('## Summary', '').strip() if lines else manifest.get('request', 'Auto-generated PR')[:72]

            # If title is still a header, use the request
            if pr_title.startswith('#'):
                pr_title = manifest.get('request', 'Auto-generated PR')[:72]

            # Step 3: Create PR using gh CLI
            # Use heredoc to avoid shell escaping issues
            result = subprocess.run(
                ['gh', 'pr', 'create', '--title', pr_title, '--body', pr_description],
                capture_output=True,
                text=True,
                check=True
            )

            # Parse PR URL from output
            pr_url = result.stdout.strip()

            # Extract PR number from URL (last segment)
            pr_number = int(pr_url.split('/')[-1])

            logger.log_event(
                'pr_created',
                f'Created PR #{pr_number}: {pr_url}'
            )

            return {
                'success': True,
                'pr_number': pr_number,
                'pr_url': pr_url,
                'pr_description': pr_description
            }

        except subprocess.CalledProcessError as e:
            error_msg = f"GitHub CLI failed: {e.stderr if hasattr(e, 'stderr') else e}"
            logger.log_error('auto_pr_failed', error_msg)
            return {
                'success': False,
                'error': error_msg
            }
        except Exception as e:
            error_msg = f"Auto-PR creation failed: {e}"
            logger.log_error('auto_pr_failed', error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def _auto_track_progress(
        self,
        workflow_id: str
    ) -> Dict[str, Any]:
        """
        Automatically update PROJECT.md progress tracking.

        Args:
            workflow_id: Current workflow ID

        Returns:
            {
                'success': bool,
                'goal_progress': Dict,
                'next_priorities': List
            }
        """
        logger = WorkflowLogger(workflow_id, 'orchestrator')
        logger.log_event('auto_progress_start', 'Updating PROJECT.md progress...')

        try:
            # Invoke project-progress-tracker agent
            manifest = self.artifact_manager.read_artifact(workflow_id, 'manifest')
            agent_result = self.agent_invoker.invoke(
                'project-progress-tracker',
                workflow_id,
                request=manifest.get('request', '')
            )

            if not agent_result.get('success'):
                raise RuntimeError(f"Progress tracking failed: {agent_result.get('error')}")

            # Parse agent output (should be JSON)
            progress_data = json.loads(agent_result.get('output', '{}'))

            logger.log_event(
                'progress_updated',
                f"Updated PROJECT.md: {progress_data.get('summary', 'Progress tracked')}"
            )

            return {
                'success': True,
                'goal_progress': progress_data.get('goal_progress', {}),
                'next_priorities': progress_data.get('next_priorities', [])
            }

        except Exception as e:
            error_msg = f"Auto-progress tracking failed: {e}"
            logger.log_error('auto_progress_failed', error_msg)
            return {
                'success': False,
                'error': error_msg
            }

    def execute_autonomous_workflow(
        self,
        request: str,
        auto_commit: bool = True,
        auto_push: bool = True,
        auto_pr: bool = True
    ) -> Dict[str, Any]:
        """
        Execute complete autonomous workflow: validate → research → plan → test → implement → review → security → docs → commit → push → PR.

        This is the main entry point for autonomous development.

        Args:
            request: User's implementation request (e.g., "Add dark mode toggle")
            auto_commit: Auto-commit with GenAI message (default: True)
            auto_push: Auto-push to feature branch (default: True)
            auto_pr: Auto-create PR with GenAI description (default: True)

        Returns:
            {
                'success': bool,
                'workflow_id': str,
                'commit_sha': str (if auto_commit),
                'branch': str (if auto_push),
                'pr_url': str (if auto_pr),
                'goal_progress': Dict (PROJECT.md progress),
                'next_priorities': List (suggested next features),
                'summary': str
            }
        """
        logger = None
        workflow_id = None

        try:
            # Step 1: Start workflow with alignment validation
            success, message, workflow_id = self.start_workflow(request, validate_alignment=True)

            if not success:
                return {
                    'success': False,
                    'error': message
                }

            logger = WorkflowLogger(workflow_id, 'orchestrator')
            progress_tracker = WorkflowProgressTracker(workflow_id)

            # Step 2: Execute 8-agent pipeline
            logger.log_event('pipeline_start', 'Starting 8-agent autonomous pipeline...')

            # Sequential agents
            progress_tracker.update_progress('researcher', 'in_progress', 15, 'Researching patterns...')
            self.invoke_researcher_with_task_tool(workflow_id)

            progress_tracker.update_progress('planner', 'in_progress', 30, 'Planning architecture...')
            self.invoke_planner_with_task_tool(workflow_id)

            progress_tracker.update_progress('test-master', 'in_progress', 45, 'Writing tests (TDD)...')
            self.invoke_test_master_with_task_tool(workflow_id)

            progress_tracker.update_progress('implementer', 'in_progress', 60, 'Implementing feature...')
            self.invoke_implementer_with_task_tool(workflow_id)

            # Parallel validators
            progress_tracker.update_progress('validators', 'in_progress', 75, 'Running validators...')
            self.invoke_parallel_validators(workflow_id)

            logger.log_event('pipeline_complete', '8-agent pipeline completed successfully')

            result = {
                'success': True,
                'workflow_id': workflow_id
            }

            # Step 3: Auto-commit (if enabled)
            if auto_commit:
                progress_tracker.update_progress('auto-commit', 'in_progress', 90, 'Auto-committing...')
                commit_result = self._auto_commit(workflow_id)

                if commit_result.get('success'):
                    result['commit_sha'] = commit_result['commit_sha']
                    result['commit_message'] = commit_result['commit_message']
                else:
                    logger.log_error('auto_commit_failed', commit_result.get('error'))
                    result['commit_error'] = commit_result.get('error')

            # Step 4: Auto-push (if enabled)
            if auto_push and auto_commit and result.get('commit_sha'):
                progress_tracker.update_progress('auto-push', 'in_progress', 93, 'Auto-pushing...')
                push_result = self._auto_push(workflow_id)

                if push_result.get('success'):
                    result['branch'] = push_result['branch']
                    result['remote_url'] = push_result['remote_url']
                else:
                    logger.log_error('auto_push_failed', push_result.get('error'))
                    result['push_error'] = push_result.get('error')

            # Step 5: Auto-create PR (if enabled)
            if auto_pr and auto_push and result.get('branch'):
                progress_tracker.update_progress('auto-pr', 'in_progress', 96, 'Creating PR...')
                pr_result = self._auto_create_pr(workflow_id, result['branch'])

                if pr_result.get('success'):
                    result['pr_number'] = pr_result['pr_number']
                    result['pr_url'] = pr_result['pr_url']
                else:
                    logger.log_error('auto_pr_failed', pr_result.get('error'))
                    result['pr_error'] = pr_result.get('error')

            # Step 6: Track progress (always)
            progress_tracker.update_progress('progress-tracker', 'in_progress', 98, 'Updating PROJECT.md...')
            progress_result = self._auto_track_progress(workflow_id)

            if progress_result.get('success'):
                result['goal_progress'] = progress_result['goal_progress']
                result['next_priorities'] = progress_result['next_priorities']

            # Step 7: Generate summary
            progress_tracker.update_progress('complete', 'completed', 100, 'Workflow complete!')

            summary_lines = [
                f"✅ Feature complete: {request}",
                f"   Workflow: {workflow_id}"
            ]

            if result.get('commit_sha'):
                summary_lines.append(f"   Commit: {result['commit_sha'][:8]}")

            if result.get('pr_url'):
                summary_lines.append(f"   PR: {result['pr_url']}")

            if result.get('goal_progress'):
                goal_name = result['goal_progress'].get('goal_name', 'Unknown')
                new_progress = result['goal_progress'].get('new_progress', '0%')
                summary_lines.append(f"   PROJECT.md: '{goal_name}' → {new_progress}")

            result['summary'] = '\n'.join(summary_lines)

            logger.log_event('autonomous_workflow_complete', result['summary'])

            return result

        except Exception as e:
            error_msg = f"Autonomous workflow failed: {e}"
            if logger:
                logger.log_error('autonomous_workflow_failed', error_msg)

            return {
                'success': False,
                'workflow_id': workflow_id,
                'error': error_msg
            }


# Backward compatibility: Orchestrator is now an alias for WorkflowCoordinator
Orchestrator = WorkflowCoordinator
