# Database Migrations

This directory contains Alembic database migrations for TradingAgents.

## Quick Start

```bash
# Apply all migrations
alembic upgrade head

# Check current version
alembic current

# View migration history
alembic history
```

## Migration Commands

### Applying Migrations

```bash
# Apply all pending migrations
alembic upgrade head

# Apply to a specific revision
alembic upgrade 003

# Apply next migration only
alembic upgrade +1
```

### Rolling Back Migrations

```bash
# Roll back one migration
alembic downgrade -1

# Roll back to specific revision
alembic downgrade 002

# Roll back all migrations
alembic downgrade base
```

### Checking Status

```bash
# Show current revision
alembic current

# Show migration history
alembic history

# Show pending migrations
alembic heads
```

## Creating New Migrations

### Auto-generate from Model Changes

After modifying models in `tradingagents/api/models/`:

```bash
# Generate migration from model changes
alembic revision --autogenerate -m "Add new_feature table"
```

### Manual Migration

```bash
# Create empty migration
alembic revision -m "Manual migration description"
```

Then edit the generated file in `migrations/versions/`.

## Migration Files

| Revision | Description |
|----------|-------------|
| 001 | Initial migration - Users and Strategies tables |
| 002 | User profile fields - tax_jurisdiction, timezone, api_key_hash |
| 003 | Portfolio model - live, paper, backtest types |
| 004 | Settings model - risk profiles, alert preferences |
| 005 | Trade model - execution history with CGT tracking |

## SQLite Compatibility

This project uses SQLite by default. For operations that SQLite doesn't support
natively (like ALTER CONSTRAINT), use batch mode:

```python
with op.batch_alter_table('table_name') as batch_op:
    batch_op.add_column(sa.Column('new_col', sa.String(50)))
    batch_op.create_unique_constraint('uq_name', ['column'])
```

## Best Practices

1. **Always test migrations locally** before committing
2. **Include both upgrade() and downgrade()** functions
3. **Use meaningful revision messages**
4. **Add docstrings** explaining what the migration does
5. **Use batch mode** for SQLite compatibility when needed
6. **Create indexes** for foreign keys and frequently queried columns

## Troubleshooting

### "Target database is not up to date"

```bash
alembic stamp head  # Mark current DB as up-to-date
```

### "Can't locate revision"

Check that all migrations have correct `down_revision` values forming a chain.

### SQLite Constraint Error

Use `batch_alter_table` for constraint operations on SQLite.
