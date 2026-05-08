---
id: PB-006
title: "CLI Design Playbook"
role: "Build"
infrastructure: [bun]
last_updated: "2026-03-21"
tags: [playbook]
---

# CLI Design Playbook

## Purpose
This playbook defines the design patterns and standards for building CLI tools in the Mastra-Hono project, ensuring consistency, type safety, and maintainability. It provides guidelines for using the citty framework and ensures that all CLI tools follow a consistent structure and user experience.

**Core Philosophy:** Use declarative command structures with citty for complex CLIs, and native `util.parseArgs` for simple tools. Prioritize type safety, clear help text, and consistent error handling.


## Technology Stack

- **Runtime**: Bun (v1.3+)
- **CLI Framework**: [citty](https://github.com/unjs/citty) by UnJS
- **Parsing**: Native `util.parseArgs` for basic cases, citty for complex CLIs
- **Language**: TypeScript (strict mode)

## When to Use citty vs Native `util.parseArgs`

| Scenario | Recommended | Reason |
|----------|-------------|--------|
| Single-command tool | `util.parseArgs` | Minimal overhead, built-in |
| Multiple subcommands | **citty** | Declarative structure, auto-help |
| Type-safe args | **citty** | Inferred types from definition |
| POSIX-compliant | **citty** | Built-in validations |
| Auto-generated help | **citty** | Zero-effort documentation |

## Mandatory Directives

### Command Structure

Define a clear hierarchy using nested `defineCommand` calls:

```typescript
// src/cli/index.ts
import { defineCommand, runMain } from 'citty';

const main = defineCommand({
  meta: {
    name: 'mastra-cli',
    version: '0.1.0',
    description: 'Mastra Agent CLI - Interact with your AI agents',
  },
  subCommands: {
    agent: agentCommand,  // Subcommand definitions
  },
});

runMain(main);
```

**Why this matters:**
- Clear command hierarchy
- Auto-generated help for all commands
- Type-safe argument handling
- Consistent structure across all CLI tools

### Arg Definition Pattern

Always use descriptive arg definitions with types and aliases:

```typescript
const myCommand = defineCommand({
  meta: {
    name: 'run',
    description: 'Execute a single prompt and exit',
  },
  args: {
    agent: {
      type: 'positional',
      required: true,
      description: 'The agent ID to use',
    },
    prompt: {
      type: 'string',
      description: 'The prompt to send to the agent',
      alias: 'p',
      required: true,
    },
    model: {
      type: 'string',
      description: 'Override the default model',
      alias: 'm',
    },
  },
  async run({ args }) {
    // Args are fully typed here
    const { agent, prompt, model } = args;
    // ...
  },
});
```

**Best practices:**
- Use descriptive names for arguments
- Provide clear descriptions
- Use aliases for common flags
- Mark required arguments explicitly
- Use appropriate types (positional, string, boolean)

### Handler Structure

Keep handlers clean and focused:

```typescript
async run({ args }) {
  // 1. Extract and validate args
  const agentId = args.agent as AgentId;
  
  // 2. Validate business logic
  if (!isValidAgent(agentId)) {
    console.error(`❌ Error: Unknown agent ID "${agentId}"`);
    process.exit(1);
  }
  
  // 3. Execute
  await executeCommand(agentId, args);
}
```

**Why this structure:**
- Clear separation of concerns
- Early validation prevents wasted work
- Error handling is explicit
- Easy to test and maintain

### Error Handling

Use exit codes consistently:

| Exit Code | Meaning |
|-----------|---------|
| `0` | Success |
| `1` | General error / validation failure |
| `2` | Missing required argument |
| `127` | Command not found |

**Implementation:**
```typescript
if (!isValidAgent(agentId)) {
  console.error(`❌ Error: Unknown agent ID "${agentId}"`);
  process.exit(1);
}
```

### Output Formatting

Use emoji prefixes for consistent UX:

```typescript
console.log(`✅ Success: ${message}`);
console.error(`❌ Error: ${message}`);
console.warn(`⚠️ Warning: ${message}`);
console.info(`ℹ️ Info: ${message}`);
```

**Why emoji prefixes:**
- Visual distinction at a glance
- Consistent user experience
- Easy to scan output
- Industry-standard convention

### Help Text Quality

Ensure every command has:

```typescript
meta: {
  name: 'command-name',
  description: 'Clear, one-sentence description',
}
args: {
  myArg: {
    type: 'string',
    description: 'What this arg does and what values are accepted',
  },
}
```

**Guidelines:**
- Keep descriptions concise (one sentence)
- Explain what the argument does
- Mention valid values if applicable
- Use active voice

## Integration Patterns

### Pattern 1: Subcommand Delegation

Delegate to subcommand modules for maintainability:

```typescript
// src/cli/commands/agent.ts
import { runCommand } from './run';
import { chatCommand } from './chat';

export const agentCommand = defineCommand({
  meta: { name: 'agent', description: 'Agent commands' },
  subCommands: {
    run: runCommand,
    chat: chatCommand,
  },
});
```

**Benefits:**
- Modular command structure
- Easy to add new subcommands
- Clear separation of concerns
- Better code organization

### Pattern 2: Shared Arguments

Export reusable arg definitions:

```typescript
// src/cli/commands/agent.ts
export const modelArg = {
  type: 'string' as const,
  description: 'Override the default model',
  alias: 'm',
};

// In consumer:
args: {
  model: modelArg,
}
```

**Benefits:**
- Consistent argument definitions
- Single source of truth
- Easy to update across commands
- Type-safe reuse

### Pattern 3: External Tool Integration

When spawning external tools (like `gum`):

```typescript
const spinner = spawn(
  'gum',
  ['spin', '--spinner', 'dot', '--title', 'Thinking...', '--', 'sleep', '10000'],
  { stdio: 'inherit' }
);

// Always clean up on error
try {
  result = await agent.generate(prompt);
} finally {
  spinner.kill();
  process.stdout.write('\r\x1b[K'); // Clear spinner line
}
```

**Best practices:**
- Always clean up external processes
- Use try/finally for cleanup
- Handle process termination gracefully
- Clear spinner output on completion

## Testing CLI Commands

Test commands in isolation:

```bash
# Test help generation
bun run cli --help

# Test subcommand help
bun run cli agent --help
bun run cli agent run --help

# Test validation
bun run cli agent run  # Should error: missing agent ID
```

**What to test:**
- Help text generation
- Argument validation
- Error handling
- Subcommand routing
- Exit codes

## Type Safety Requirements

1. All args must be typed (citty handles this automatically)
2. Validate positional args with type guards:
   ```typescript
   const agentId = args.agent as AgentId;
   if (!agentIds.includes(agentId)) { /* ... */ }
   ```
3. Use `const` assertions for shared arg definitions

**Why type safety matters:**
- Catches errors at compile time
- Improves IDE autocomplete
- Reduces runtime errors
- Makes code more maintainable

## Performance Considerations

- citty is ~5KB - minimal bundle impact
- Lazy loading: subcommands only load their imports
- Bun's fast startup keeps CLI snappy

**Optimization tips:**
- Use lazy imports for subcommands
- Avoid heavy initialization in command definitions
- Keep handlers lightweight
- Use async operations for long-running tasks

## Migration from `util.parseArgs`

1. Identify subcommand boundaries
2. Create `src/cli/commands/<name>.ts` for each subcommand
3. Move arg definitions to `args` property
4. Convert validation logic to the `run` function
5. Wire up in parent via `subCommands`
6. Remove manual `parseArgs` calls and routing

**Example migration:**

**Before (util.parseArgs):**
```typescript
const args = parseArgs({
  args: process.argv.slice(2),
  options: {
    agent: { type: 'string' },
    prompt: { type: 'string' },
  },
});

if (args.agent === 'run') {
  // Handle run command
}
```

**After (citty):**
```typescript
const runCommand = defineCommand({
  meta: { name: 'run', description: 'Execute a prompt' },
  args: {
    agent: { type: 'positional', required: true },
    prompt: { type: 'string', required: true },
  },
  async run({ args }) {
    // Handle run command
  },
});
```

## Dependencies

```json
{
  "dependencies": {
    "citty": "^0.2.0"
  }
}
```

## Compliance Checklist

- [ ] Uses `defineCommand` for all commands
- [ ] Has descriptive `meta.name` and `meta.description`
- [ ] All args have `description`
- [ ] Positional args use `type: 'positional'`
- [ ] Optional string args use `type: 'string'`
- [ ] Boolean flags use `type: 'boolean'`
- [ ] Aliases defined with `alias` property
- [ ] Required args marked with `required: true`
- [ ] Business validation in `run` function
- [ ] Proper exit codes used
- [ ] Error messages use emoji prefixes

## Best Practices

### 1. Keep Commands Focused

Each command should do one thing well. If a command becomes too complex, consider splitting it into subcommands.

**Good:**
```typescript
const runCommand = defineCommand({
  meta: { name: 'run', description: 'Execute a single prompt' },
  // ... focused implementation
});
```

**Bad:**
```typescript
const agentCommand = defineCommand({
  meta: { name: 'agent', description: 'Do everything' },
  // ... complex implementation with multiple modes
});
```

### 2. Use Descriptive Names

Use clear, descriptive names for commands and arguments.

**Good:**
```typescript
args: {
  'model': { type: 'string', description: 'Override the default model' },
}
```

**Bad:**
```typescript
args: {
  'm': { type: 'string', description: 'Model' },
}
```

### 3. Provide Clear Error Messages

Error messages should be actionable and helpful.

**Good:**
```typescript
console.error(`❌ Error: Unknown agent ID "${agentId}". Available agents: ${agentIds.join(', ')}`);
```

**Bad:**
```typescript
console.error('Error');
```

### 4. Test Help Text

Always test the generated help text to ensure it's clear and helpful.

```bash
bun run cli --help
bun run cli agent --help
bun run cli agent run --help
```

### 5. Use Exit Codes Consistently

Follow the exit code conventions to ensure proper integration with other tools.

```typescript
process.exit(0);  // Success
process.exit(1);  // Error
process.exit(2);  // Missing argument
```

## Common Pitfalls

### Pitfall 1: Not Using `required: true`

**Problem:** Optional arguments that should be required.

**Solution:** Mark required arguments explicitly.

```typescript
// Bad
args: {
  agent: { type: 'positional' },
}

// Good
args: {
  agent: { type: 'positional', required: true },
}
```

### Pitfall 2: Missing Descriptions

**Problem:** Arguments without descriptions make help text unclear.

**Solution:** Always provide descriptions.

```typescript
// Bad
args: {
  model: { type: 'string' },
}

// Good
args: {
  model: { type: 'string', description: 'Override the default model' },
}
```

### Pitfall 3: Inconsistent Exit Codes

**Problem:** Using random exit codes.

**Solution:** Follow the standard exit code conventions.

```typescript
// Bad
process.exit(42);

// Good
process.exit(1);  // General error
```

### Pitfall 4: Not Cleaning Up External Processes

**Problem:** External processes left running after command completion.

**Solution:** Always clean up in finally blocks.

```typescript
// Bad
const spinner = spawn('gum', ['spin']);
await doWork();
spinner.kill();

// Good
const spinner = spawn('gum', ['spin']);
try {
  await doWork();
} finally {
  spinner.kill();
}
```

## References

- [citty Documentation](https://github.com/unjs/citty) – CLI framework by UnJS
- [Node.js util.parseArgs](https://nodejs.org/api/util.html#utilparseargsconfig) – Native argument parsing
- [Bun Documentation](https://bun.sh/docs) – Bun runtime documentation
- [Loading Process Playbook](./loading-process-playbook.md) – Two-step loading process pattern
- [Mastra Agent Playbook](./mastra-agent-playbook.md) – Mastra-specific patterns
- [Agentic SDLC Playbook](./agentic-sdlc.md) – Agent-assisted development practices

---

**Version:** 1.0  
**Last Updated:** 2026-03-21  
**Maintained by:** PolyVis Development Team
