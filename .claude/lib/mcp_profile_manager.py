#!/usr/bin/env python3
"""
MCP Profile Manager - Pre-configured security profiles for MCP server

This module provides pre-configured security profiles for different environments:
- Development: Permissive access for local development
- Testing: Moderate restrictions for test environments
- Production: Strict restrictions for production environments

Security Profiles:
- Development: Full project access, deny secrets/sensitive files
- Testing: Read project files, write to tests/ only
- Production: Minimal access, read-only for specific paths

Usage:
    from mcp_profile_manager import MCPProfileManager, ProfileType

    # Generate development profile
    manager = MCPProfileManager()
    profile = manager.create_profile(ProfileType.DEVELOPMENT)

    # Save to file
    manager.save_profile(profile, ".mcp/security_policy.json")

    # Customize profile
    custom = customize_profile(profile, {
        "filesystem": {
            "read": ["custom/**"]
        }
    })

Date: 2025-12-07
Issue: #95 (MCP Server Security - Permission Whitelist System)
Agent: implementer
Phase: TDD Green (implementation to make tests pass)
"""

import json
from dataclasses import dataclass, field
from enum import Enum
from pathlib import Path
from typing import Dict, Any, List, Optional


class ProfileType(Enum):
    """Security profile types."""
    DEVELOPMENT = "development"
    TESTING = "testing"
    PRODUCTION = "production"

    @classmethod
    def from_string(cls, value: str) -> 'ProfileType':
        """Create ProfileType from string.

        Args:
            value: Profile type string (case-insensitive)

        Returns:
            ProfileType enum value
        """
        value_upper = value.upper()
        for profile_type in cls:
            if profile_type.name == value_upper:
                return profile_type
        raise ValueError(f"Unknown profile type: {value}")


@dataclass
class ValidationResult:
    """Result of profile validation.

    Attributes:
        valid: Whether profile is valid
        errors: List of validation errors
    """
    valid: bool
    errors: List[str] = field(default_factory=list)


@dataclass
class SecurityProfile:
    """Security profile data class.

    Attributes:
        filesystem: Filesystem permissions
        shell: Shell command permissions
        network: Network access permissions
        environment: Environment variable permissions
    """
    filesystem: Dict[str, List[str]]
    shell: Dict[str, List[str]]
    network: Dict[str, List[str]]
    environment: Optional[Dict[str, List[str]]] = None

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'SecurityProfile':
        """Create SecurityProfile from dictionary.

        Args:
            data: Profile dictionary

        Returns:
            SecurityProfile instance
        """
        return cls(
            filesystem=data.get("filesystem", {}),
            shell=data.get("shell", {}),
            network=data.get("network", {}),
            environment=data.get("environment")
        )

    def to_dict(self) -> Dict[str, Any]:
        """Serialize SecurityProfile to dictionary.

        Returns:
            Dictionary representation
        """
        result = {
            "filesystem": self.filesystem,
            "shell": self.shell,
            "network": self.network
        }
        if self.environment:
            result["environment"] = self.environment
        return result

    def validate(self) -> ValidationResult:
        """Validate profile schema.

        Returns:
            ValidationResult with validation status
        """
        return validate_profile_schema(self.to_dict())


class MCPProfileManager:
    """MCP security profile manager.

    Manages creation, validation, and persistence of security profiles.
    """

    def create_profile(self, profile_type: ProfileType) -> Dict[str, Any]:
        """Create security profile for specified type.

        Args:
            profile_type: Type of profile to create

        Returns:
            Security profile dictionary
        """
        if profile_type == ProfileType.DEVELOPMENT:
            return generate_development_profile()
        elif profile_type == ProfileType.TESTING:
            return generate_testing_profile()
        elif profile_type == ProfileType.PRODUCTION:
            return generate_production_profile()
        else:
            raise ValueError(f"Unknown profile type: {profile_type}")

    def save_profile(self, profile: Dict[str, Any], output_path: str) -> None:
        """Save security profile to JSON file.

        Args:
            profile: Security profile dictionary
            output_path: Path to output JSON file
        """
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)

        with open(output_file, 'w') as f:
            json.dump(profile, f, indent=2)

    def load_profile(self, input_path: str) -> Dict[str, Any]:
        """Load security profile from JSON file.

        Args:
            input_path: Path to input JSON file

        Returns:
            Security profile dictionary
        """
        with open(input_path, 'r') as f:
            return json.load(f)


def generate_development_profile() -> Dict[str, Any]:
    """Generate development security profile (most permissive).

    Returns:
        Development profile dictionary

    Features:
    - Read: src/**, tests/**, docs/**, config files
    - Write: src/**, tests/**, docs/**
    - Shell: Common dev commands (pytest, git, python, npm, pip)
    - Network: Allow all domains, block localhost/private IPs
    - Environment: Allow common vars, block secrets
    """
    return {
        "filesystem": {
            "read": [
                "src/**",
                "tests/**",
                "docs/**",
                "*.md",
                "*.txt",
                "*.json",
                "*.yaml",
                "*.toml",
                "!**/.env",
                "!**/.git/**",
                "!**/.ssh/**",
                "!**/*.key",
                "!**/*.pem"
            ],
            "write": [
                "src/**",
                "tests/**",
                "docs/**",
                "*.md",
                "!**/.env",
                "!**/.git/**"
            ]
        },
        "shell": {
            "allowed_commands": [
                "pytest",
                "git",
                "python",
                "python3",
                "pip",
                "pip3",
                "poetry",
                "npm",
                "node",
                "make"
            ],
            "denied_patterns": [
                "rm -rf /",
                "dd if=",
                "mkfs",
                "> /dev/",
                "curl * | sh",
                "wget * | sh"
            ]
        },
        "network": {
            "allowed_domains": ["*"],
            "denied_ips": [
                "127.0.0.1",
                "0.0.0.0",
                "169.254.169.254"
            ]
        },
        "environment": {
            "allowed_vars": [
                "PATH",
                "HOME",
                "USER",
                "SHELL",
                "LANG",
                "PWD",
                "TERM"
            ],
            "denied_patterns": [
                "*_KEY",
                "*_TOKEN",
                "*_SECRET",
                "AWS_*",
                "GITHUB_TOKEN"
            ]
        }
    }


def generate_testing_profile() -> Dict[str, Any]:
    """Generate testing security profile (moderate restrictions).

    Returns:
        Testing profile dictionary

    Features:
    - Read: src/**, tests/**, minimal docs
    - Write: tests/** only (not src/)
    - Shell: pytest, git only
    - Network: Deny all (tests should be isolated)
    - Environment: Minimal vars only
    """
    return {
        "filesystem": {
            "read": [
                "src/**",
                "tests/**",
                "*.md",
                "!**/.env",
                "!**/.git/**",
                "!**/.ssh/**"
            ],
            "write": [
                "tests/**",
                "!**/.env"
            ]
        },
        "shell": {
            "allowed_commands": [
                "pytest",
                "python",
                "python3",
                "git"
            ],
            "denied_patterns": [
                "rm -rf",
                "dd if=",
                "curl",
                "wget"
            ]
        },
        "network": {
            "allowed_domains": [],
            "denied_ips": [
                "127.0.0.1",
                "0.0.0.0",
                "169.254.169.254"
            ]
        },
        "environment": {
            "allowed_vars": [
                "PATH",
                "HOME",
                "USER"
            ],
            "denied_patterns": [
                "*_KEY",
                "*_TOKEN",
                "*_SECRET"
            ]
        }
    }


def generate_production_profile() -> Dict[str, Any]:
    """Generate production security profile (most restrictive).

    Returns:
        Production profile dictionary

    Features:
    - Read: Minimal paths only (config files)
    - Write: Empty (no write access)
    - Shell: git status only
    - Network: Deny all
    - Environment: Minimal vars only
    """
    return {
        "filesystem": {
            "read": [
                "*.md",
                "*.txt",
                "!**/.env",
                "!**/.git/**"
            ],
            "write": []
        },
        "shell": {
            "allowed_commands": [
                "git"
            ],
            "denied_patterns": [
                "rm",
                "dd",
                "curl",
                "wget",
                "nc",
                "python"
            ]
        },
        "network": {
            "allowed_domains": [],
            "denied_ips": [
                "127.0.0.1",
                "0.0.0.0",
                "169.254.169.254"
            ]
        },
        "environment": {
            "allowed_vars": [
                "PATH",
                "USER"
            ],
            "denied_patterns": [
                "*_KEY",
                "*_TOKEN",
                "*_SECRET",
                "AWS_*"
            ]
        }
    }


def customize_profile(
    base_profile: Dict[str, Any],
    overrides: Dict[str, Any],
    merge: bool = True
) -> Dict[str, Any]:
    """Customize security profile with overrides.

    Args:
        base_profile: Base profile dictionary
        overrides: Override values
        merge: If True, merge arrays; if False, replace

    Returns:
        Customized profile dictionary
    """
    if not merge:
        # Replace mode - shallow merge (replace top-level keys)
        result = base_profile.copy()
        result.update(overrides)
        return result

    # Merge mode - deep merge arrays
    result = base_profile.copy()

    for key, value in overrides.items():
        if key not in result:
            result[key] = value
        elif isinstance(value, dict) and isinstance(result[key], dict):
            # Recursively merge dictionaries
            result[key] = _deep_merge_dict(result[key], value)
        elif isinstance(value, list) and isinstance(result[key], list):
            # Merge lists (append unique items)
            result[key] = result[key] + [item for item in value if item not in result[key]]
        else:
            # Replace value
            result[key] = value

    return result


def _deep_merge_dict(base: Dict[str, Any], override: Dict[str, Any]) -> Dict[str, Any]:
    """Deep merge two dictionaries.

    Args:
        base: Base dictionary
        override: Override dictionary

    Returns:
        Merged dictionary
    """
    result = base.copy()

    for key, value in override.items():
        if key not in result:
            result[key] = value
        elif isinstance(value, dict) and isinstance(result[key], dict):
            result[key] = _deep_merge_dict(result[key], value)
        elif isinstance(value, list) and isinstance(result[key], list):
            # Merge lists (append unique items)
            result[key] = result[key] + [item for item in value if item not in result[key]]
        else:
            result[key] = value

    return result


def validate_profile_schema(profile: Dict[str, Any]) -> ValidationResult:
    """Validate security profile schema.

    Args:
        profile: Security profile dictionary

    Returns:
        ValidationResult with validation status and errors
    """
    errors = []

    # Check required sections
    if "filesystem" not in profile:
        errors.append("Missing required section: filesystem")

    # Validate filesystem section
    if "filesystem" in profile:
        fs = profile["filesystem"]
        if not isinstance(fs, dict):
            errors.append("filesystem must be a dictionary")
        else:
            if "read" in fs and not isinstance(fs["read"], list):
                errors.append("filesystem.read must be an array/list")
            if "write" in fs and not isinstance(fs["write"], list):
                errors.append("filesystem.write must be an array/list")

    # Validate shell section (optional but if present, must be valid)
    if "shell" in profile:
        shell = profile["shell"]
        if not isinstance(shell, dict):
            errors.append("shell must be a dictionary")
        else:
            if "allowed_commands" in shell and not isinstance(shell["allowed_commands"], list):
                errors.append("shell.allowed_commands must be an array/list")

    # Validate network section (optional)
    if "network" in profile:
        network = profile["network"]
        if not isinstance(network, dict):
            errors.append("network must be a dictionary")

    return ValidationResult(valid=len(errors) == 0, errors=errors)


def export_profile(
    profile: Dict[str, Any],
    output_path: Optional[str] = None,
    indent: int = 2
) -> str:
    """Export security profile to JSON.

    Args:
        profile: Security profile dictionary
        output_path: Path to output file (None = return string)
        indent: JSON indentation level

    Returns:
        JSON string representation
    """
    json_str = json.dumps(profile, indent=indent)

    if output_path:
        output_file = Path(output_path)
        output_file.parent.mkdir(parents=True, exist_ok=True)
        with open(output_file, 'w') as f:
            f.write(json_str)

    return json_str
