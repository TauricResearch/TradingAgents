---
name: scaffold
description: Create a new DDD domain with all required stubs under src/ and tests/
disable-model-invocation: true
argument-hint: <domain-name>
---

Scaffold a new domain named $ARGUMENTS following the DDD layout in `.claude/rules/rules.md`.

**Create these files:**

```
src/silvie_agent/domain/$ARGUMENTS/
  __init__.py
  models.py        # Entities and value objects (dataclass / pydantic)
  repository.py    # Abstract repository interface (ABC)
  services.py      # Pure domain logic

src/silvie_agent/application/$ARGUMENTS/
  __init__.py
  commands.py      # Dataclasses for write intents
  queries.py       # Dataclasses for read intents
  handlers.py      # Use case handlers (depend on domain abstractions only)

src/silvie_agent/infrastructure/$ARGUMENTS/
  __init__.py
  repository.py    # Concrete repository implementation
  adapters.py      # External service adapters

src/silvie_agent/interfaces/$ARGUMENTS/
  __init__.py
  routes.py        # Entry points (CLI, HTTP, events)

tests/$ARGUMENTS/
  __init__.py
  test_models.py
  test_services.py
  test_handlers.py
  test_repository.py
```

**Each stub must include:**
- Module docstring stating its DDD role.
- A `TODO` comment indicating what to implement.
- Correct imports relative to `src/silvie_agent/`.

After creation, confirm the files exist and remind the user to add the domain to the package `__init__.py` if needed.
