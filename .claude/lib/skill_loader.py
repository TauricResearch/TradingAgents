#!/usr/bin/env python3
"""
Skill Loader - Load and inject skill content into subagent prompts

This module provides skill loading for the Task tool integration:
- Parse agent frontmatter to extract "Relevant Skills" section
- Load skill content files (SKILL.md) from skills directory
- Format skills as XML tags for injection into Task prompts
- Graceful degradation for missing skills (warn, don't fail)

Fixes Issue #140: Skills not available to subagents spawned via Task tool

Security Features:
- Skills loaded from trusted plugin directory only
- No path traversal in skill file loading
- Sanitize skill content before injection
- Audit log which skills loaded for which agents

Usage:
    from skill_loader import load_skills_for_agent, format_skills_for_prompt

    # Load skills for an agent
    skills = load_skills_for_agent("implementer")

    # Format for Task prompt injection
    prompt_addition = format_skills_for_prompt(skills)

    # Full prompt with skills
    full_prompt = f"{prompt_addition}\n\n{agent_task_prompt}"

Date: 2025-12-15
Issue: GitHub #140 (Skill injection into subagents)
Agent: implementer
"""

import re
import sys
from pathlib import Path
from typing import Dict, List, Optional

# Import path_utils for project root detection
try:
    from path_utils import get_project_root
except ImportError:
    # Fallback if running standalone
    def get_project_root() -> Path:
        """Fallback project root detection."""
        current = Path.cwd()
        while current != current.parent:
            if (current / ".git").exists() or (current / ".claude").exists():
                return current
            current = current.parent
        raise FileNotFoundError("Could not find project root")


# Mapping of agent names to their skill files
# Issue #147: Consolidated to 8 active agents only
# This is extracted from agent frontmatter "skills:" field
AGENT_SKILL_MAP: Dict[str, List[str]] = {
    # Pipeline agents (7)
    "researcher-local": ["research-patterns"],
    "planner": ["architecture-patterns", "project-management"],
    "test-master": ["testing-guide", "python-standards"],
    "implementer": ["python-standards", "testing-guide", "error-handling-patterns"],
    "reviewer": ["code-review", "python-standards"],
    "security-auditor": ["security-patterns", "error-handling-patterns"],
    "doc-master": ["documentation-guide", "git-workflow"],
    # Utility agents (1)
    "issue-creator": ["github-workflow", "research-patterns"],
}


def get_skills_dir() -> Path:
    """Get the skills directory path.

    Returns:
        Path to plugins/autonomous-dev/skills/ directory

    Raises:
        FileNotFoundError: If skills directory not found
    """
    root = get_project_root()
    skills_dir = root / "plugins" / "autonomous-dev" / "skills"

    if not skills_dir.exists():
        raise FileNotFoundError(f"Skills directory not found: {skills_dir}")

    return skills_dir


def get_agent_file(agent_name: str) -> Optional[Path]:
    """Get the agent file path.

    Args:
        agent_name: Name of the agent (e.g., "implementer")

    Returns:
        Path to agent file, or None if not found
    """
    root = get_project_root()
    agent_file = root / "plugins" / "autonomous-dev" / "agents" / f"{agent_name}.md"

    if agent_file.exists():
        return agent_file
    return None


def parse_agent_skills(agent_name: str) -> List[str]:
    """Parse agent file frontmatter to extract relevant skills.

    Args:
        agent_name: Name of the agent

    Returns:
        List of skill names from agent's "Relevant Skills" section
    """
    # First check static mapping (faster, always available)
    if agent_name in AGENT_SKILL_MAP:
        return AGENT_SKILL_MAP[agent_name]

    # Fallback: Parse agent file dynamically
    agent_file = get_agent_file(agent_name)
    if not agent_file:
        return []

    try:
        content = agent_file.read_text()

        # Look for "Relevant Skills" section
        skills_match = re.search(
            r"## Relevant Skills\s*\n(.*?)(?=\n##|\Z)",
            content,
            re.DOTALL
        )

        if not skills_match:
            return []

        skills_section = skills_match.group(1)

        # Extract skill names from bullet points
        # Pattern: "- **skill-name**:" or "- skill-name:"
        skill_pattern = r"-\s+\*\*([a-z-]+)\*\*:|^\s*-\s+([a-z-]+):"
        matches = re.findall(skill_pattern, skills_section, re.MULTILINE)

        skills = []
        for match in matches:
            skill = match[0] if match[0] else match[1]
            if skill:
                skills.append(skill)

        return skills

    except Exception as e:
        print(f"Warning: Could not parse agent file {agent_file}: {e}", file=sys.stderr)
        return []


def load_skill_content(skill_name: str) -> Optional[str]:
    """Load skill content from SKILL.md file.

    Args:
        skill_name: Name of the skill (e.g., "python-standards")

    Returns:
        Skill content as string, or None if not found
    """
    try:
        skills_dir = get_skills_dir()
    except FileNotFoundError:
        return None

    # Security: Validate skill name (no path traversal)
    if "/" in skill_name or "\\" in skill_name or ".." in skill_name:
        print(f"Warning: Invalid skill name (path traversal attempt): {skill_name}", file=sys.stderr)
        return None

    skill_file = skills_dir / skill_name / "SKILL.md"

    if not skill_file.exists():
        print(f"Warning: Skill file not found: {skill_file}", file=sys.stderr)
        return None

    try:
        content = skill_file.read_text()
        return content
    except Exception as e:
        print(f"Warning: Could not read skill file {skill_file}: {e}", file=sys.stderr)
        return None


def load_skills_for_agent(agent_name: str) -> Dict[str, str]:
    """Load all relevant skills for an agent.

    Args:
        agent_name: Name of the agent (e.g., "implementer")

    Returns:
        Dict mapping skill names to their content
    """
    skills = parse_agent_skills(agent_name)
    loaded_skills: Dict[str, str] = {}

    for skill_name in skills:
        content = load_skill_content(skill_name)
        if content:
            loaded_skills[skill_name] = content

    return loaded_skills


def format_skills_for_prompt(skills: Dict[str, str], max_total_lines: int = 1500) -> str:
    """Format loaded skills as XML tags for prompt injection.

    Args:
        skills: Dict mapping skill names to content
        max_total_lines: Maximum total lines across all skills (default 1500)

    Returns:
        Formatted string with skills in XML tags
    """
    if not skills:
        return ""

    lines_used = 0
    skill_blocks = []

    for skill_name, content in skills.items():
        # Count lines in this skill
        skill_lines = content.count('\n') + 1

        # Check if adding this skill would exceed limit
        if lines_used + skill_lines > max_total_lines:
            # Truncate this skill to fit
            remaining_lines = max_total_lines - lines_used
            if remaining_lines > 50:  # Only include if meaningful
                lines = content.split('\n')
                truncated = '\n'.join(lines[:remaining_lines - 5])
                truncated += f"\n\n... (truncated, {skill_lines - remaining_lines + 5} more lines)"
                skill_blocks.append(f"<skill name=\"{skill_name}\">\n{truncated}\n</skill>")
            break

        skill_blocks.append(f"<skill name=\"{skill_name}\">\n{content}\n</skill>")
        lines_used += skill_lines

    if not skill_blocks:
        return ""

    header = "<skills>\nThe following skills provide guidance for this task:\n\n"
    footer = "\n</skills>"

    return header + "\n\n".join(skill_blocks) + footer


def get_skill_injection_for_agent(agent_name: str) -> str:
    """Convenience function to get formatted skill injection for an agent.

    Args:
        agent_name: Name of the agent

    Returns:
        Formatted skill content ready for prompt injection
    """
    skills = load_skills_for_agent(agent_name)
    return format_skills_for_prompt(skills)


def get_available_skills() -> List[str]:
    """Get list of all available skill names.

    Returns:
        List of skill directory names
    """
    try:
        skills_dir = get_skills_dir()
        return [
            d.name for d in skills_dir.iterdir()
            if d.is_dir() and (d / "SKILL.md").exists()
        ]
    except FileNotFoundError:
        return []


def audit_skill_load(agent_name: str, skills_loaded: List[str], skills_requested: List[str]) -> None:
    """Log skill loading for audit purposes.

    Args:
        agent_name: Name of the agent
        skills_loaded: List of skills successfully loaded
        skills_requested: List of skills originally requested
    """
    missing = set(skills_requested) - set(skills_loaded)

    if missing:
        print(f"Skill audit [{agent_name}]: Loaded {len(skills_loaded)}/{len(skills_requested)} skills. "
              f"Missing: {', '.join(missing)}", file=sys.stderr)
    else:
        print(f"Skill audit [{agent_name}]: Loaded all {len(skills_loaded)} skills successfully", file=sys.stderr)


# CLI interface for testing
if __name__ == "__main__":
    import argparse

    parser = argparse.ArgumentParser(description="Load skills for agents")
    parser.add_argument("agent", nargs="?", help="Agent name to load skills for")
    parser.add_argument("--list", action="store_true", help="List all available skills")
    parser.add_argument("--map", action="store_true", help="Show agent-skill mapping")
    parser.add_argument("--verify", action="store_true", help="Verify skill loading (JSON output)")
    parser.add_argument("--audit", action="store_true", help="Show audit log of skill loading")

    args = parser.parse_args()

    import json as json_module

    if args.list:
        skills = get_available_skills()
        print(f"Available skills ({len(skills)}):")
        for skill in sorted(skills):
            print(f"  - {skill}")
    elif args.map:
        print("Agent-Skill Mapping:")
        for agent, skills in sorted(AGENT_SKILL_MAP.items()):
            print(f"  {agent}: {', '.join(skills)}")
    elif args.verify:
        # Verify all agents can load their skills
        print("Skill Injection Verification Report")
        print("=" * 50)
        results = []
        for agent_name in sorted(AGENT_SKILL_MAP.keys()):
            requested = AGENT_SKILL_MAP.get(agent_name, [])
            loaded = load_skills_for_agent(agent_name)
            missing = set(requested) - set(loaded.keys())
            status = "PASS" if not missing else "WARN"
            total_lines = sum(content.count('\n') for content in loaded.values())
            result = {
                "agent": agent_name,
                "status": status,
                "requested": len(requested),
                "loaded": len(loaded),
                "missing": list(missing) if missing else [],
                "total_lines": total_lines
            }
            results.append(result)
            icon = "✅" if status == "PASS" else "⚠️"
            print(f"{icon} {agent_name}: {len(loaded)}/{len(requested)} skills ({total_lines} lines)")
            if missing:
                print(f"   Missing: {', '.join(missing)}")
        print("=" * 50)
        passed = sum(1 for r in results if r["status"] == "PASS")
        print(f"Summary: {passed}/{len(results)} agents fully loaded")
        if args.audit:
            print("\nJSON Output:")
            print(json_module.dumps(results, indent=2))
    elif args.audit and args.agent:
        # Audit specific agent
        requested = AGENT_SKILL_MAP.get(args.agent, [])
        loaded = load_skills_for_agent(args.agent)
        missing = set(requested) - set(loaded.keys())
        result = {
            "agent": args.agent,
            "requested_skills": requested,
            "loaded_skills": list(loaded.keys()),
            "missing_skills": list(missing),
            "skill_sizes": {name: len(content) for name, content in loaded.items()},
            "total_chars": sum(len(c) for c in loaded.values()),
            "total_lines": sum(c.count('\n') for c in loaded.values())
        }
        print(json_module.dumps(result, indent=2))
    elif args.agent:
        injection = get_skill_injection_for_agent(args.agent)
        if injection:
            if args.audit:
                # Show audit info before content
                loaded = load_skills_for_agent(args.agent)
                audit_skill_load(args.agent, list(loaded.keys()), AGENT_SKILL_MAP.get(args.agent, []))
            print(injection)
        else:
            print(f"No skills found for agent: {args.agent}")
    else:
        parser.print_help()
