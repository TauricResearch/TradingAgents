"""
Test suite for documentation structure validation.

This module tests:
1. Documentation directory structure exists
2. Required documentation files are present
3. Documentation files have valid markdown structure
4. Internal links resolve correctly
5. No sensitive information (API keys, secrets) in docs
6. Documentation follows consistent formatting
7. Code examples in docs are valid

Tests are written TDD-style and will fail until documentation is created.
"""

import os
import re
from pathlib import Path
from typing import List, Set, Tuple
import pytest


# ============================================================================
# Fixtures and Constants
# ============================================================================

@pytest.fixture
def project_root() -> Path:
    """Get the project root directory."""
    # Navigate up from tests/ to project root
    return Path(__file__).parent.parent


@pytest.fixture
def docs_root(project_root: Path) -> Path:
    """Get the documentation root directory."""
    return project_root / "docs"


# Expected documentation structure
REQUIRED_DOCS_STRUCTURE = {
    # Root documentation files
    "docs/README.md": "Main documentation index",
    "docs/QUICKSTART.md": "Quick start guide",

    # Architecture documentation
    "docs/architecture/multi-agent-system.md": "Multi-agent system architecture",
    "docs/architecture/data-flow.md": "Data flow documentation",
    "docs/architecture/llm-integration.md": "LLM integration architecture",

    # API documentation
    "docs/api/trading-graph.md": "Trading graph API reference",
    "docs/api/agents.md": "Agents API reference",
    "docs/api/dataflows.md": "Data flows API reference",

    # User guides
    "docs/guides/adding-new-analyst.md": "Guide for adding new analyst agents",
    "docs/guides/adding-llm-provider.md": "Guide for adding new LLM providers",
    "docs/guides/configuration.md": "Configuration guide",

    # Testing documentation
    "docs/testing/README.md": "Testing documentation index",
    "docs/testing/running-tests.md": "Guide for running tests",
    "docs/testing/writing-tests.md": "Guide for writing tests",

    # Development documentation
    "docs/development/setup.md": "Development environment setup",
    "docs/development/contributing.md": "Contribution guidelines",
}

# Patterns for detecting sensitive information
SENSITIVE_PATTERNS = [
    (r"sk-[a-zA-Z0-9]{32,}", "OpenAI API key"),
    (r"sk-or-v1-[a-zA-Z0-9]{32,}", "OpenRouter API key"),
    (r"sk-ant-[a-zA-Z0-9]{32,}", "Anthropic API key"),
    (r"ghp_[a-zA-Z0-9]{36,}", "GitHub Personal Access Token"),
    (r"gho_[a-zA-Z0-9]{36,}", "GitHub OAuth Token"),
    (r"[a-zA-Z0-9]{40}", "Generic 40-char secret (potential GitHub token)"),
    (r"(?i)password\s*[=:]\s*['\"][^'\"]+['\"]", "Hardcoded password"),
    (r"(?i)secret\s*[=:]\s*['\"][^'\"]+['\"]", "Hardcoded secret"),
    (r"(?i)api[_-]?key\s*[=:]\s*['\"][^'\"]+['\"]", "Hardcoded API key"),
]

# Required markdown headers for each document type
REQUIRED_HEADERS = {
    "README.md": ["# ", "## "],  # Must have at least h1 and h2
    ".md": ["# "],  # All other markdown files must have at least h1
}


# ============================================================================
# Structure Tests
# ============================================================================

class TestDocumentationStructure:
    """Test that documentation directory structure exists and is complete."""

    def test_docs_root_exists(self, docs_root: Path):
        """Test that docs/ directory exists."""
        assert docs_root.exists(), (
            f"Documentation root directory not found at {docs_root}. "
            "Create docs/ directory to start."
        )
        assert docs_root.is_dir(), f"{docs_root} exists but is not a directory"

    def test_all_required_files_exist(self, docs_root: Path):
        """Test that all required documentation files exist."""
        missing_files = []

        for doc_path, description in REQUIRED_DOCS_STRUCTURE.items():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                missing_files.append(f"{doc_path} - {description}")

        assert not missing_files, (
            f"Missing {len(missing_files)} required documentation files:\n" +
            "\n".join(f"  - {f}" for f in missing_files)
        )

    def test_all_required_directories_exist(self, docs_root: Path):
        """Test that all required documentation subdirectories exist."""
        required_dirs = [
            "architecture",
            "api",
            "guides",
            "testing",
            "development",
        ]

        missing_dirs = []
        for dir_name in required_dirs:
            dir_path = docs_root / dir_name
            if not dir_path.exists():
                missing_dirs.append(dir_name)
            elif not dir_path.is_dir():
                missing_dirs.append(f"{dir_name} (exists but not a directory)")

        assert not missing_dirs, (
            f"Missing required documentation directories:\n" +
            "\n".join(f"  - docs/{d}" for d in missing_dirs)
        )

    def test_no_empty_files(self, docs_root: Path):
        """Test that no documentation files are empty."""
        empty_files = []

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if full_path.exists() and full_path.stat().st_size == 0:
                empty_files.append(doc_path)

        assert not empty_files, (
            f"Found {len(empty_files)} empty documentation files:\n" +
            "\n".join(f"  - {f}" for f in empty_files)
        )


# ============================================================================
# Content Validation Tests
# ============================================================================

class TestMarkdownStructure:
    """Test that documentation files have valid markdown structure."""

    def test_all_files_have_required_headers(self, docs_root: Path):
        """Test that all markdown files have required header levels."""
        files_missing_headers = []

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue  # Skip missing files (covered by structure tests)

            content = full_path.read_text(encoding="utf-8")

            # Determine required headers based on filename
            filename = full_path.name
            required = REQUIRED_HEADERS.get(filename, REQUIRED_HEADERS[".md"])

            missing_headers = []
            for header_prefix in required:
                if not any(line.startswith(header_prefix) for line in content.splitlines()):
                    missing_headers.append(header_prefix.strip())

            if missing_headers:
                files_missing_headers.append(
                    f"{doc_path}: missing {', '.join(missing_headers)}"
                )

        assert not files_missing_headers, (
            f"Files with missing required headers:\n" +
            "\n".join(f"  - {f}" for f in files_missing_headers)
        )

    def test_markdown_has_valid_code_blocks(self, docs_root: Path):
        """Test that markdown code blocks are properly closed."""
        files_with_unclosed_blocks = []

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            content = full_path.read_text(encoding="utf-8")

            # Count code block delimiters (```)
            code_block_count = content.count("```")

            # Code blocks must come in pairs
            if code_block_count % 2 != 0:
                files_with_unclosed_blocks.append(
                    f"{doc_path} (found {code_block_count} ``` markers)"
                )

        assert not files_with_unclosed_blocks, (
            f"Files with unclosed code blocks:\n" +
            "\n".join(f"  - {f}" for f in files_with_unclosed_blocks)
        )

    def test_readme_has_table_of_contents(self, docs_root: Path):
        """Test that main README has a table of contents."""
        readme_path = docs_root / "README.md"

        if not readme_path.exists():
            pytest.skip("README.md does not exist yet")

        content = readme_path.read_text(encoding="utf-8").lower()

        # Look for common TOC indicators
        has_toc = any(
            indicator in content
            for indicator in [
                "table of contents",
                "## contents",
                "## overview",
                "[architecture]",
                "[api reference]",
                "[guides]",
            ]
        )

        assert has_toc, (
            "docs/README.md should include a table of contents or overview section "
            "linking to major documentation sections"
        )

    def test_quickstart_has_installation_steps(self, docs_root: Path):
        """Test that QUICKSTART has installation/setup steps."""
        quickstart_path = docs_root / "QUICKSTART.md"

        if not quickstart_path.exists():
            pytest.skip("QUICKSTART.md does not exist yet")

        content = quickstart_path.read_text(encoding="utf-8").lower()

        # Look for installation-related content
        has_installation = any(
            keyword in content
            for keyword in [
                "install",
                "pip install",
                "setup",
                "requirements",
                "getting started",
            ]
        )

        assert has_installation, (
            "docs/QUICKSTART.md should include installation or setup instructions"
        )


# ============================================================================
# Cross-Reference Tests
# ============================================================================

class TestDocumentationLinks:
    """Test that internal documentation links are valid."""

    def _extract_markdown_links(self, content: str) -> List[Tuple[str, str]]:
        """Extract all markdown links from content.

        Returns:
            List of (link_text, link_url) tuples
        """
        # Match [text](url) pattern
        link_pattern = r'\[([^\]]+)\]\(([^)]+)\)'
        return re.findall(link_pattern, content)

    def _is_external_link(self, url: str) -> bool:
        """Check if a URL is external (http/https)."""
        return url.startswith(('http://', 'https://', 'mailto:'))

    def _resolve_relative_link(
        self, base_path: Path, link_url: str
    ) -> Path:
        """Resolve a relative link from a base document path.

        Args:
            base_path: Path to the document containing the link
            link_url: The relative URL from the link

        Returns:
            Resolved absolute path
        """
        # Remove anchor fragments
        link_url = link_url.split('#')[0]

        if not link_url:  # Just an anchor link
            return base_path

        # Resolve relative to the directory containing the base file
        base_dir = base_path.parent
        return (base_dir / link_url).resolve()

    def test_internal_links_resolve(self, docs_root: Path):
        """Test that all internal documentation links resolve to existing files."""
        broken_links = []

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            content = full_path.read_text(encoding="utf-8")
            links = self._extract_markdown_links(content)

            for link_text, link_url in links:
                # Skip external links
                if self._is_external_link(link_url):
                    continue

                # Resolve relative link
                target_path = self._resolve_relative_link(full_path, link_url)

                # Check if target exists
                if not target_path.exists():
                    broken_links.append(
                        f"{doc_path}: [{link_text}]({link_url}) -> {target_path}"
                    )

        assert not broken_links, (
            f"Found {len(broken_links)} broken internal links:\n" +
            "\n".join(f"  - {link}" for link in broken_links)
        )

    def test_readme_links_to_main_sections(self, docs_root: Path):
        """Test that main README links to all major documentation sections."""
        readme_path = docs_root / "README.md"

        if not readme_path.exists():
            pytest.skip("README.md does not exist yet")

        content = readme_path.read_text(encoding="utf-8")
        links = self._extract_markdown_links(content)
        link_urls = [url for _, url in links]

        # Required sections that should be linked
        required_links = [
            ("architecture", "Architecture documentation"),
            ("api", "API documentation"),
            ("guides", "User guides"),
            ("testing", "Testing documentation"),
        ]

        missing_links = []
        for section, description in required_links:
            # Check if any link points to this section
            has_link = any(section in url.lower() for url in link_urls)
            if not has_link:
                missing_links.append(f"{section}/ - {description}")

        assert not missing_links, (
            f"README.md missing links to major sections:\n" +
            "\n".join(f"  - {link}" for link in missing_links)
        )


# ============================================================================
# Security Tests
# ============================================================================

class TestDocumentationSecurity:
    """Test that documentation contains no sensitive information."""

    def test_no_api_keys_in_docs(self, docs_root: Path):
        """Test that documentation files contain no API keys or secrets."""
        files_with_secrets = []

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            content = full_path.read_text(encoding="utf-8")

            # Check against all sensitive patterns
            for pattern, secret_type in SENSITIVE_PATTERNS:
                matches = re.finditer(pattern, content)
                for match in matches:
                    # Skip if it's clearly an example/placeholder
                    matched_text = match.group(0)
                    if self._is_placeholder(matched_text):
                        continue

                    files_with_secrets.append(
                        f"{doc_path}: Found {secret_type}: {matched_text[:20]}..."
                    )

        assert not files_with_secrets, (
            f"Found potential secrets in documentation:\n" +
            "\n".join(f"  - {s}" for s in files_with_secrets) +
            "\n\nUse placeholders like 'your-api-key-here' or 'sk-xxx' instead."
        )

    def _is_placeholder(self, text: str) -> bool:
        """Check if text is likely a placeholder rather than real secret.

        Args:
            text: The potentially sensitive text

        Returns:
            True if text appears to be a placeholder
        """
        placeholder_indicators = [
            "xxx",
            "your-",
            "example",
            "placeholder",
            "replace",
            "insert",
            "paste",
            "...",
        ]

        text_lower = text.lower()
        return any(indicator in text_lower for indicator in placeholder_indicators)

    def test_env_examples_use_placeholders(self, docs_root: Path):
        """Test that .env examples in docs use placeholders, not real values."""
        files_with_real_values = []

        # Pattern to match environment variable assignments
        env_var_pattern = r'^([A-Z_]+)=(.+)$'

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            content = full_path.read_text(encoding="utf-8")

            # Find code blocks that might contain .env examples
            code_blocks = re.findall(r'```(?:bash|shell|env)?\n(.*?)```', content, re.DOTALL)

            for block in code_blocks:
                for line in block.splitlines():
                    match = re.match(env_var_pattern, line.strip())
                    if match:
                        var_name, var_value = match.groups()

                        # Check if value looks like a real key
                        if (
                            var_name.endswith(('_KEY', '_TOKEN', '_SECRET'))
                            and not self._is_placeholder(var_value)
                            and len(var_value) > 20  # Real keys are typically longer
                        ):
                            files_with_real_values.append(
                                f"{doc_path}: {var_name}={var_value[:20]}..."
                            )

        assert not files_with_real_values, (
            f"Found environment variables with potentially real values:\n" +
            "\n".join(f"  - {v}" for v in files_with_real_values) +
            "\n\nUse placeholders in documentation."
        )


# ============================================================================
# Code Example Tests
# ============================================================================

class TestCodeExamples:
    """Test that code examples in documentation are valid."""

    def _extract_code_blocks(self, content: str, language: str = None) -> List[str]:
        """Extract code blocks from markdown content.

        Args:
            content: Markdown content
            language: Optional language filter (e.g., 'python')

        Returns:
            List of code block contents
        """
        if language:
            pattern = rf'```{language}\n(.*?)```'
        else:
            pattern = r'```(?:\w+)?\n(.*?)```'

        return re.findall(pattern, content, re.DOTALL)

    def test_python_code_examples_have_valid_syntax(self, docs_root: Path):
        """Test that Python code examples have valid syntax."""
        files_with_syntax_errors = []

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            content = full_path.read_text(encoding="utf-8")
            python_blocks = self._extract_code_blocks(content, "python")

            for i, code_block in enumerate(python_blocks):
                try:
                    # Try to compile the code (doesn't execute it)
                    compile(code_block, f"{doc_path}:block{i}", "exec")
                except SyntaxError as e:
                    files_with_syntax_errors.append(
                        f"{doc_path} (block {i}): {e.msg} at line {e.lineno}"
                    )

        assert not files_with_syntax_errors, (
            f"Found Python code blocks with syntax errors:\n" +
            "\n".join(f"  - {err}" for err in files_with_syntax_errors)
        )

    def test_code_examples_use_project_imports(self, docs_root: Path):
        """Test that code examples use correct import paths."""
        files_with_wrong_imports = []

        # Expected import prefix for this project
        expected_prefix = "tradingagents"

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            content = full_path.read_text(encoding="utf-8")
            python_blocks = self._extract_code_blocks(content, "python")

            for i, code_block in enumerate(python_blocks):
                # Look for import statements
                import_lines = [
                    line for line in code_block.splitlines()
                    if line.strip().startswith(('import ', 'from '))
                ]

                for line in import_lines:
                    # Check if it's importing from this project
                    if 'tradingagents' in line.lower() and expected_prefix not in line:
                        files_with_wrong_imports.append(
                            f"{doc_path} (block {i}): {line.strip()}"
                        )

        assert not files_with_wrong_imports, (
            f"Found code examples with incorrect import paths:\n" +
            "\n".join(f"  - {imp}" for imp in files_with_wrong_imports) +
            f"\n\nAll imports should use '{expected_prefix}' prefix."
        )


# ============================================================================
# Content Quality Tests
# ============================================================================

class TestDocumentationQuality:
    """Test documentation quality and completeness."""

    def test_architecture_docs_describe_key_components(self, docs_root: Path):
        """Test that architecture docs describe key system components."""
        arch_path = docs_root / "architecture" / "multi-agent-system.md"

        if not arch_path.exists():
            pytest.skip("Architecture documentation does not exist yet")

        content = arch_path.read_text(encoding="utf-8").lower()

        # Key components that should be documented
        required_components = [
            "agent",
            "graph",
            "state",
            "workflow",
        ]

        missing_components = []
        for component in required_components:
            if component not in content:
                missing_components.append(component)

        assert not missing_components, (
            f"Architecture documentation missing key components:\n" +
            "\n".join(f"  - {c}" for c in missing_components)
        )

    def test_api_docs_include_code_examples(self, docs_root: Path):
        """Test that API documentation includes code examples."""
        api_files = [
            "docs/api/trading-graph.md",
            "docs/api/agents.md",
            "docs/api/dataflows.md",
        ]

        files_without_examples = []

        for doc_path in api_files:
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            content = full_path.read_text(encoding="utf-8")

            # Check for code blocks
            has_code = "```" in content

            if not has_code:
                files_without_examples.append(doc_path)

        assert not files_without_examples, (
            f"API documentation files missing code examples:\n" +
            "\n".join(f"  - {f}" for f in files_without_examples)
        )

    def test_guides_have_step_by_step_instructions(self, docs_root: Path):
        """Test that guides include step-by-step instructions."""
        guide_files = [
            "docs/guides/adding-new-analyst.md",
            "docs/guides/adding-llm-provider.md",
            "docs/guides/configuration.md",
        ]

        files_without_steps = []

        for doc_path in guide_files:
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            content = full_path.read_text(encoding="utf-8").lower()

            # Look for step indicators
            has_steps = any(
                indicator in content
                for indicator in [
                    "step 1",
                    "1.",
                    "first,",
                    "## setup",
                    "## installation",
                ]
            )

            if not has_steps:
                files_without_steps.append(doc_path)

        assert not files_without_steps, (
            f"Guide files missing step-by-step instructions:\n" +
            "\n".join(f"  - {f}" for f in files_without_steps)
        )

    def test_contributing_guide_exists_and_complete(self, docs_root: Path):
        """Test that contributing guide exists and covers key topics."""
        contrib_path = docs_root / "development" / "contributing.md"

        if not contrib_path.exists():
            pytest.skip("Contributing guide does not exist yet")

        content = contrib_path.read_text(encoding="utf-8").lower()

        # Key topics for contributing guide
        required_topics = [
            ("pull request", "Pull request guidelines"),
            ("test", "Testing requirements"),
            ("code", "Code standards"),
        ]

        missing_topics = []
        for keyword, topic in required_topics:
            if keyword not in content:
                missing_topics.append(topic)

        assert not missing_topics, (
            f"Contributing guide missing key topics:\n" +
            "\n".join(f"  - {t}" for t in missing_topics)
        )


# ============================================================================
# Integration Tests
# ============================================================================

class TestDocumentationIntegration:
    """Test documentation integrates properly with project."""

    def test_docs_referenced_in_main_readme(self, project_root: Path):
        """Test that main project README references the documentation."""
        main_readme = project_root / "README.md"

        if not main_readme.exists():
            pytest.skip("Main README.md does not exist")

        content = main_readme.read_text(encoding="utf-8").lower()

        # Should reference docs directory
        has_docs_reference = any(
            ref in content
            for ref in [
                "docs/",
                "documentation",
                "[docs]",
                "see docs",
            ]
        )

        assert has_docs_reference, (
            "Main README.md should reference the docs/ directory or documentation"
        )

    def test_all_public_apis_documented(self, project_root: Path, docs_root: Path):
        """Test that all public APIs have corresponding documentation."""
        # This is a basic check - could be enhanced with AST parsing
        api_doc_path = docs_root / "api"

        if not api_doc_path.exists():
            pytest.skip("API documentation directory does not exist yet")

        # Check that major modules have API docs
        major_modules = [
            ("graph/trading_graph.py", "trading-graph.md"),
            ("agents/", "agents.md"),
            ("dataflows/", "dataflows.md"),
        ]

        missing_docs = []
        for module_path, expected_doc in major_modules:
            module_full_path = project_root / "tradingagents" / module_path
            doc_full_path = api_doc_path / expected_doc

            if module_full_path.exists() and not doc_full_path.exists():
                missing_docs.append(f"{expected_doc} for {module_path}")

        assert not missing_docs, (
            f"Missing API documentation for modules:\n" +
            "\n".join(f"  - {d}" for d in missing_docs)
        )


# ============================================================================
# Performance Tests
# ============================================================================

class TestDocumentationSize:
    """Test that documentation files are reasonable in size."""

    def test_no_excessively_large_files(self, docs_root: Path):
        """Test that no documentation files are excessively large."""
        max_size_kb = 500  # 500 KB max per file
        large_files = []

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            size_kb = full_path.stat().st_size / 1024
            if size_kb > max_size_kb:
                large_files.append(f"{doc_path}: {size_kb:.1f} KB")

        assert not large_files, (
            f"Found excessively large documentation files (>{max_size_kb} KB):\n" +
            "\n".join(f"  - {f}" for f in large_files) +
            f"\n\nConsider splitting large files into smaller documents."
        )

    def test_reasonable_line_length(self, docs_root: Path):
        """Test that documentation lines are reasonable length."""
        max_line_length = 120
        files_with_long_lines = []

        for doc_path in REQUIRED_DOCS_STRUCTURE.keys():
            full_path = docs_root.parent / doc_path
            if not full_path.exists():
                continue

            content = full_path.read_text(encoding="utf-8")
            long_lines = []

            for i, line in enumerate(content.splitlines(), 1):
                # Skip code blocks and URLs
                if line.strip().startswith(('```', 'http://', 'https://')):
                    continue

                if len(line) > max_line_length:
                    long_lines.append(i)

            if long_lines:
                files_with_long_lines.append(
                    f"{doc_path}: lines {long_lines[:3]}{'...' if len(long_lines) > 3 else ''}"
                )

        assert not files_with_long_lines, (
            f"Found files with lines exceeding {max_line_length} characters:\n" +
            "\n".join(f"  - {f}" for f in files_with_long_lines) +
            f"\n\nConsider breaking long lines for better readability."
        )
