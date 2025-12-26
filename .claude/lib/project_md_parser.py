"""
PROJECT.md parsing and validation.

Parses PROJECT.md to extract GOALS, SCOPE (included/excluded), and CONSTRAINTS.
Provides structured access to project governance information.
"""

import re
from pathlib import Path
from typing import Dict, Any, Optional, List


class ProjectMdParser:
    """Parse and validate PROJECT.md"""

    def __init__(self, project_md_path: Path):
        """
        Initialize parser

        Args:
            project_md_path: Path to PROJECT.md file
        """
        self.project_md_path = project_md_path

        if not project_md_path.exists():
            raise FileNotFoundError(f"PROJECT.md not found at: {project_md_path}")

        self.content = project_md_path.read_text()
        self.goals = self._parse_section("GOALS")

        # Parse SCOPE section by emoji
        self.scope_included = self._parse_section("SCOPE", emoji_filter='✅')
        self.scope_excluded = self._parse_section("SCOPE", emoji_filter='❌')

        self.constraints = self._parse_section("CONSTRAINTS")

    def _parse_section(
        self,
        section_name: str,
        subsection: Optional[str] = None,
        emoji_filter: Optional[str] = None
    ) -> List[str]:
        """
        Parse a section from PROJECT.md

        Args:
            section_name: Name of main section (GOALS, SCOPE, CONSTRAINTS)
            subsection: Optional subsection name (e.g., "In Scope")
            emoji_filter: Optional emoji to filter items (e.g., '✅' or '❌')

        Returns:
            List of items in the section
        """
        # Find section (allow any characters after section name, like emojis)
        section_pattern = rf"^##\s+{section_name}\b"
        section_match = re.search(section_pattern, self.content, re.MULTILINE)

        if not section_match:
            return []

        # Extract section content (until next ## heading)
        start = section_match.end()
        next_section = re.search(r"^##\s+", self.content[start:], re.MULTILINE)
        end = start + next_section.start() if next_section else len(self.content)

        section_content = self.content[start:end]

        # If subsection specified, extract that
        if subsection:
            # Try ### header first (h3)
            subsection_pattern = rf"^###\s+{subsection}\s*$"
            subsection_match = re.search(subsection_pattern, section_content, re.MULTILINE)

            # If not found, try **bold** header with flexible matching
            if not subsection_match:
                # Match "**What's IN Scope**" for subsection="In Scope"
                # Use case-insensitive and partial matching
                subsection_pattern = rf"\*\*.*?{re.escape(subsection)}.*?\*\*"
                subsection_match = re.search(subsection_pattern, section_content, re.IGNORECASE)

            if not subsection_match:
                return []

            subsection_start = subsection_match.end()

            # Find next subsection (either ### or **)
            next_subsection = re.search(r"(^###\s+|\*\*.*?\*\*)", section_content[subsection_start:], re.MULTILINE)
            subsection_end = subsection_start + next_subsection.start() if next_subsection else len(section_content)

            section_content = section_content[subsection_start:subsection_end]

        # Extract bullet points and numbered lists
        items = []
        for line in section_content.split('\n'):
            line = line.strip()

            # Skip section headers (lines with ** that end with : or **:)
            if line.startswith('**') and (':' in line or line.endswith('**')):
                continue

            # Skip horizontal rules (---, ***, etc.)
            if line.startswith('---') or line.startswith('***') or line == '--':
                continue

            # Apply emoji filter if specified
            if emoji_filter and emoji_filter not in line:
                continue

            # Match bullet points (-, *) or numbered lists (1., 2., etc.)
            if line.startswith('-') or line.startswith('*') or re.match(r'^\d+\.', line):
                # Remove leading marker and ❌/✅ symbols
                item = re.sub(r'^[-*]\s*[❌✅]?\s*', '', line).strip()
                item = re.sub(r'^\d+\.\s*[❌✅]?\s*', '', item).strip()

                # Remove **bold** markers
                item = re.sub(r'\*\*(.*?)\*\*', r'\1', item)

                # Extract main content before dash or hyphen (for items like "Goal - explanation")
                # This gets "Goal" from "Goal - explanation text"
                if ' - ' in item:
                    item = item.split(' - ')[0].strip()

                if item and not item.endswith(':'):  # Skip headers and empty items
                    items.append(item)

        return items

    def to_dict(self) -> Dict[str, Any]:
        """Convert parsed PROJECT.md to dictionary"""
        return {
            'goals': self.goals,
            'scope': {
                'included': self.scope_included,
                'excluded': self.scope_excluded
            },
            'constraints': self.constraints
        }
