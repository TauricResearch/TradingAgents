## Summary

Rename the project from "TradingAgents" to "Spektiv" including package directory, all imports, configuration files, documentation, database file, and CLI entry point. This is a complete rebrand before wider release.

## What Does NOT Work

**Failed Approaches to Avoid:**

- **Partial rename leaving mixed references**: Creates confusion and import errors. All references must be updated atomically.
- **Find-replace without import verification**: Breaks code when string matches occur in comments/strings that shouldn't be changed.
- **Renaming without database migration strategy**: Users with existing tradingagents.db files will have broken database paths.
- **Not bumping version to 0.2.0**: Rebrand is a significant milestone that warrants version bump.
- **Gradual deprecation with backwards compatibility**: Unnecessary complexity for pre-release project.

## Scenarios

### Fresh Install (No Existing Data)
**What happens**: User clones repo after rename, runs pip install -e .
- Package installs as spektiv
- CLI command spektiv is available
- All imports resolve: from spektiv.models import User
- Database created as spektiv.db
- No prompts or configuration needed

### Update/Upgrade (Existing Development Setup)
**What happens**: Developer has existing clone with tradingagents/ directory and tradingagents.db

**With valid existing data**:
- Database file tradingagents.db preserved and renamed to spektiv.db
- alembic.ini updated to point to spektiv.db
- Existing migrations remain compatible (no schema changes)
- User runs git pull, reinstalls package, continues work

**With invalid/broken data**:
- Same as above, but user may need to delete corrupted tradingagents.db
- Fresh spektiv.db created on next run

**With user customizations**:
- Never overwrite user's database file without explicit migration
- Provide clear migration instructions in PR description

## Implementation Approach

**Phased Implementation** (execute in order):

### Phase 1: Package Directory Rename
- git mv tradingagents spektiv
- Verify: Directory structure intact, no files lost

### Phase 2: Update All Python Imports
- Target: All .py files in project root, spektiv/, tests/, scripts/, examples/
- Pattern: from tradingagents -> from spektiv
- Pattern: import tradingagents -> import spektiv
- Files affected: ~120+ Python files

### Phase 3: Update Configuration Files
**setup.py**:
- Change name="tradingagents" to name="spektiv"
- Update entry_points to spektiv=cli.main:app
- Update description and author fields

**pyproject.toml**:
- Change name = "tradingagents" to name = "spektiv"

**alembic.ini**:
- Line 61: sqlalchemy.url = sqlite:///spektiv.db

**migrations/env.py**:
- Update imports: from spektiv.api.models import Base

### Phase 4: Update Documentation
- README.md - project name, CLI examples, import examples
- PROJECT.md - project name and branding
- docs/**/*.md - all code examples and references
- Replace "TradingAgents" with "Spektiv" throughout

### Phase 5: Database Migration
For existing users after git pull:
- mv tradingagents.db spektiv.db
- pip install -e .

### Phase 6: Verification and Testing
- pytest tests/ - All tests should pass
- spektiv --help - CLI works
- python -c "from spektiv.api.models import User" - Imports work
- alembic current - Database connects

## Test Scenarios

### 1. Fresh Install (No Existing Data)
- git clone, pip install -e ., spektiv --help
- Expected: All commands succeed, spektiv.db created

### 2. Update with Valid Existing Data
- git pull, mv tradingagents.db spektiv.db, pip install -e ., pytest
- Expected: Database preserved, all tests pass

### 3. Import Resolution Verification
- grep -r "from tradingagents" --include="*.py" . | grep -v venv
- Expected: No matches found

### 4. Rollback After Failure
- git reset --hard HEAD~1, pip install -e ., mv spektiv.db tradingagents.db
- Expected: Project restored to pre-rename state

## Acceptance Criteria

### Fresh Install
- [ ] Package installs with name spektiv
- [ ] CLI command spektiv is available
- [ ] All imports resolve: from spektiv.* works
- [ ] Database created as spektiv.db
- [ ] All tests pass with fresh install

### Updates
- [ ] Existing tradingagents.db can be renamed to spektiv.db
- [ ] Migration instructions clear in PR description
- [ ] Updated code works with renamed database

### Package Structure
- [ ] Directory renamed: tradingagents/ to spektiv/
- [ ] All Python imports updated (~120+ files)
- [ ] No broken import statements

### Configuration
- [ ] setup.py updated with new package name and entry point
- [ ] pyproject.toml updated with new package name
- [ ] alembic.ini points to spektiv.db
- [ ] Version bumped to 0.2.0

### Documentation
- [ ] README.md updated with new project name
- [ ] PROJECT.md updated with new project name
- [ ] All docs/**/*.md files updated
- [ ] CLI examples show spektiv command

### Database
- [ ] Database file reference updated to spektiv.db
- [ ] Migrations run successfully
- [ ] No schema changes required

### Testing
- [ ] All existing tests pass after rename
- [ ] No test failures due to import errors
- [ ] CLI entry point spektiv works

### Validation
- [ ] grep -r "tradingagents" returns no code results (except comments/docs history)
- [ ] pip show spektiv displays package info
