---
name: code-reviewer
description: Comprehensive code review toolkit for evaluating quality across multiple
  languages. Use for PR analysis, quality checking, and generating review reports.
  Based on alirezarezvani/claude-skills.
type: reference
version: 1.0.0
category: development
last_updated: 2026-01-19
source: https://github.com/alirezarezvani/claude-skills
related_skills:
- tdd-obra
- systematic-debugging
- subagent-driven
capabilities: []
requires: []
tags:
- code-review
- security
- performance
- quality
- pull-request
- multi-language
freedom: high
---

# Code Reviewer

## Overview

This skill provides comprehensive code review capabilities across multiple programming languages including TypeScript, JavaScript, Python, Swift, and Kotlin. Focus areas: code quality, security, performance, and maintainability.

## Quick Start

1. **Identify scope** - Files or PR to review
2. **Run analysis** - Check code quality, security, performance
3. **Document findings** - Categorize by severity
4. **Provide recommendations** - Actionable improvements
5. **Generate report** - Structured review output

## When to Use

- Pull request reviews
- Pre-merge quality gates
- Code audit requirements
- Security assessments
- Performance optimization reviews
- Onboarding code familiarization

## Related Skills

- [tdd-obra](../tdd-obra/SKILL.md) - Test-first development
- [systematic-debugging](../systematic-debugging/SKILL.md) - Debugging methodology
- [subagent-driven](../subagent-driven/SKILL.md) - Development with reviews

---

## Version History

- **1.0.0** (2026-01-19): Initial release adapted from alirezarezvani/claude-skills

## Sub-Skills

- [Best Practices](best-practices/SKILL.md)
- [Error Handling](error-handling/SKILL.md)
- [Metrics](metrics/SKILL.md)

## Sub-Skills

- [1. Code Quality (+3)](1-code-quality/SKILL.md)
- [Step 1: Context Gathering](step-1-context-gathering/SKILL.md)
- [Step 2: High-Level Analysis (+4)](step-2-high-level-analysis/SKILL.md)
- [Severity Levels](severity-levels/SKILL.md)
- [General (+5)](general/SKILL.md)
- [Code Smells (+1)](code-smells/SKILL.md)
- [Review Report Template](review-report-template/SKILL.md)
- [Summary](summary/SKILL.md)
- [Statistics](statistics/SKILL.md)
- [[Finding Title]](finding-title/SKILL.md)
- [Medium/Low Findings](mediumlow-findings/SKILL.md)
- [Positive Observations](positive-observations/SKILL.md)
- [Recommendations](recommendations/SKILL.md)
- [Test Coverage](test-coverage/SKILL.md)
- [TypeScript/JavaScript (+2)](typescriptjavascript/SKILL.md)
