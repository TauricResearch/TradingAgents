# Flox Playbook

**Source:** [flox.dev/docs](https://flox.dev/docs) — official documentation for Flox CLI, manifest format, and concepts.

---

## Purpose

Flox is the **environment delivery mechanism** for the silo. It guarantees that every agent — Claude, GPT, Gemini, or human — gets the same toolchain regardless of host OS or architecture. The `flox.toml` at the silo root is the single source of truth for what tools are required, which are optional, and how to install things nixpkgs doesn't carry.

Without Flox, a silo's reproducibility depends on README instructions that drift. With Flox, the first command (`flox activate`) reproduces the environment.

---

## Prerequisites

- Flox installed: `apt`, `yum`, `brew`, or standalone installer — see [flox.dev/docs/install-flox/install](https://flox.dev/docs/install-flox/install/)
- A `flox.toml` at the silo root (see this project's `flox.toml` as the reference)
- For FloxHub sharing: authenticated with `flox auth login`

---

## Core Workflow

### Initialise a Silo

```bash
cd silo
flox init                     # Creates .flox/ directory
```

This generates `.flox/env/manifest.toml`, `.flox/env.lock`, and `.flox/env.json`. The manifest declares packages, environment variables, and activation scripts. The lock pins exact versions for reproducibility.

**A silo should commit its `.flox/` directory** — this is what enables `git clone && flox activate` zero-friction onboarding. See [flox.dev/docs/concepts/environments](https://flox.dev/docs/concepts/environments).

### Install Dependencies

Flox installs from the `flox.toml` manifest. Unlike `flox install` (which adds packages interactively), the silo declares everything upfront in `flox.toml` so the manifest is version-controlled:

```bash
flox install        # Installs all packages from manifest
```

### Activate the Environment

```bash
flox activate       # Enters a subshell with all tools on PATH
# Run just check    # Now all silo commands work
```

Activation layers the environment over your existing shell — your aliases, dotfiles, and IDE config remain. It does not use containers. See [flox.dev/docs/concepts/activation](https://flox.dev/docs/concepts/activation).

For one-shot commands without entering a subshell:

```bash
flox run -- just check
```

### Edit the Manifest

```bash
flox edit           # Opens $EDITOR, validates on save
```

For declarative changes to `flox.toml`, edit the manifest directly and run `flox install` to apply.

### Update Package Versions

```bash
flox update         # Refresh package resolutions in lockfile
```

Run this periodically to pick up patches. The lockfile ensures deterministic builds between updates.

---

## Key Patterns

### Pattern: Adding a New Tool

Decision flow for adding to `flox.toml`:

1. **Is it in nixpkgs?** Search with `flox search <tool>` or browse [floxhub.dev/packages](https://floxhub.dev/packages). If yes, add to `[install]` in `flox.toml`:
   ```toml
   [install]
   mytool.pkg-path = "mytool"
   ```
2. **Is it optional?** Mark as optional so activation doesn't fail on systems that can't build it:
   ```toml
   mytool.optional = true
   ```
3. **Not in nixpkgs?** Add to the "NOT in nixpkgs" section in `flox.toml` comments, with install instructions. These must be installed separately after `flox activate`. See this project's `flox.toml` for examples (bun, td, mmdc, biome).

### Pattern: Cross-Platform Manifests

The `[options]` section declares target systems:

```toml
[options]
systems = [
  "x86_64-linux",
  "aarch64-linux",
  "x86_64-darwin",
  "aarch64-darwin",
]
```

If a package is unavailable on a specific system, mark it optional — the environment will activate without it. Activation scripts should check `command -v` before using optional tools. See [flox.dev/docs/concepts/environments/#environment-uses](https://flox.dev/docs/concepts/environments/#environment-uses).

### Pattern: Activation Scripts

The `[profile]` section runs shell commands on activation:

```toml
[profile]
common = '''
  if [ -f "$BUN_INSTALL/bun" ]; then
    [ -d "$BUN_INSTALL/bin" ] && export PATH="$BUN_INSTALL/bin:$PATH"
  fi
'''
```

Use this for PATH adjustments, fzf setup, or any per-session configuration. Keep it minimal — complex logic belongs in `scripts/`.

### Pattern: Environment Variables

Set variables in `[vars]`:

```toml
[vars]
BUN_INSTALL = "$HOME/.bun"
```

These are exported on activation. Prefer this over `.env` files for tools that need to find their own installation paths.

### Pattern: CI/CD Integration

Flox can build in CI without activation overhead:

```bash
flox run -- just check
```

See [flox.dev/docs/tutorials/ci-cd](https://flox.dev/docs/tutorials/ci-cd) for GitHub Actions, CircleCI, and GitLab integrations.

### Pattern: Containerisation

For deployment, package the environment as an OCI image:

```bash
flox containerize
```

This produces a container with the exact pinned toolchain. See [flox.dev/docs/man/flox-containerize](https://flox.dev/docs/man/flox-containerize).

---

## `flox.toml` Reference

The `flox.toml` is version-controlled at the silo root. It differs from the generated `.flox/env/manifest.toml` — the `flox.toml` is the **source of truth** for initialising the `.flox/` directory, while the `.flox/` directory is the **build artefact** that Flox uses at activation.

| Section | Purpose |
|---------|---------|
| `[install]` | Package declarations (`pkg-path`, `optional`) |
| `[vars]` | Environment variables |
| `[profile]` | Shell scripts run on activation |
| `[options]` | Target platforms |

Notable: this project's `flox.toml` includes a full tool availability map (nixpkgs vs Arch vs Brew) in its comments — keep this updated when adding new tools.

---

## Common Issues

| Issue | Cause | Fix |
|-------|-------|-----|
| `flox init` creates `.flox/` that conflicts with existing manifest | Running `flox init` on an already-initialised silo | Check for `.flox/env/manifest.toml` first. Use `flox edit` instead |
| Package not found on target system | Package unavailable for that OS/arch | Mark `optional = true` in `flox.toml`, gate usage with `command -v` in scripts |
| Activation fails with build error | Nix derivation cache miss or broken upstream | Run `flox update` then `flox install` again. Check [flox status page](https://status.flox.dev) if persistent |
| `bun` not found after activation | Bun installed outside Flox, not on PATH | Ensure `BUN_INSTALL` is set in `[vars]` and PATH appended in `[profile]`. See the Bun pattern in this project's `flox.toml` |
| Package version different across machines | Lockfile out of date or not committed | Commit `.flox/env.lock` to version control. Run `flox update` periodically | 
| Very slow first activation | Nix downloading and building all packages | First activation downloads everything. Subsequent activations use cached derivations. Run `flox gc` periodically to clean unused store paths |

---

## Related

- Reference: `flox.toml` at silo root (the canonical manifest for this project)
- Playbook: `playbooks/just-playbook.md` — justfile facade relies on flox for tool availability
- Playbook: `playbooks/conventions-playbook.md` — environment conventions
- Brief: `briefs/2026-05-11-brief-code-registry.md` — mentions adding ast-grep to `flox.toml`
- External: [flox.dev/docs](https://flox.dev/docs) — official documentation
- External: [flox.dev/blog](https://flox.dev/blog) — tutorials and use cases (Node, Python, Go, Rust, CI/CD)
- External: [hub.flox.dev/packages](https://hub.flox.dev/packages) — package search
